import os
import glob
import pandas as pd
from filelock import FileLock
from typing import Any, Optional
from PyExpUtils.models.ExperimentDescription import ExperimentDescription
from PyExpUtils.results.indices import listIndices
from PyExpUtils.utils.dict import flatKeys, get
from PyExpUtils.utils.types import NpList
from PyExpUtils.utils.asyncio import threadMap

def saveResults(exp: ExperimentDescription, idx: int, filename: str, data: NpList, base: str = './', batch_size: Optional[int] = 20000):
    context = exp.buildSaveContext(idx, base=base)
    context.ensureExists()

    params = exp.getPermutation(idx)['metaParameters']
    keys = flatKeys(params)
    header = sorted(keys)
    pvalues = [get(params, k) for k in header]

    run = exp.getRun(idx)

    df = pd.DataFrame([pvalues + [run] + list(data)])

    # --------------
    # -- batching --
    # --------------
    if batch_size is None:
        data_file = context.resolve(f'{filename}.csv')
    else:
        batch_idx = int(idx // batch_size)
        data_file = context.resolve(f'{filename}.{batch_idx}.csv')

    with FileLock(data_file + '.lock'):
        df.to_csv(data_file, mode='a+', header=False, index=False)

    return data_file

def saveSequentialRuns(exp: ExperimentDescription, idx: int, filename: str, data: Any, base: str = './', batch_size: Optional[int] = 20000):
    context = exp.buildSaveContext(idx, base=base)
    context.ensureExists()

    params = exp.getPermutation(idx)['metaParameters']
    keys = flatKeys(params)
    header = sorted(keys)
    pvalues = [get(params, k) for k in header]

    run = exp.getRun(idx)
    rows = []
    for i in range(len(data)):
        if data[i] is None:
            continue

        rows.append(pvalues + [run + i] + list(data[i]))

    df = pd.DataFrame(rows)

    # --------------
    # -- batching --
    # --------------
    if batch_size is None:
        data_file = context.resolve(f'{filename}.csv')
    else:
        batch_idx = int(idx // batch_size)
        data_file = context.resolve(f'{filename}.{batch_idx}.csv')

    with FileLock(data_file + '.lock'):
        df.to_csv(data_file, mode='a+', header=False, index=False)

    return data_file

def loadResults(exp: ExperimentDescription, filename: str, base: str = './', use_cache: bool = True) -> pd.DataFrame:
    context = exp.buildSaveContext(0, base=base)

    files = glob.glob(context.resolve(f'{filename}.*.csv'))

    # this could be because we did not use batching
    # try again without batching
    if len(files) == 0:
        files = glob.glob(context.resolve(f'{filename}.csv'))

    # get latest modification time
    times = (os.path.getmtime(f) for f in files)
    latest = max(*times, 0, 0)

    cache_file = context.resolve(filename + '.pkl')
    if use_cache and os.path.exists(cache_file) and os.path.getmtime(cache_file) > latest:
        return pd.read_pickle(cache_file)

    params = exp.getPermutation(0)['metaParameters']
    keys = flatKeys(params)
    header = sorted(keys)

    if len(files) == 0:
        raise Exception('No result files found')

    partials = threadMap(_readUnevenCsv, files)
    df = pd.concat(partials, ignore_index=True)

    nparams = len(header) + 1
    new_df = df.iloc[:, :nparams]
    new_df.columns = header + ['run']
    new_df['data'] = df.iloc[:, nparams:].values.tolist()

    if use_cache:
        new_df.to_pickle(cache_file)

    return new_df

def _readUnevenCsv(f: str):
    with open(f, 'r') as temp_f:
        col_count = ( len(l.split(",")) for l in temp_f.readlines() )

    return pd.read_csv(f, header=None, names=range(0, max(col_count)))

def detectMissingIndices(exp: ExperimentDescription, runs: int, filename: str, base: str = './'): # noqa: C901
    indices = listIndices(exp)
    nperms = exp.numPermutations()

    params = exp.getPermutation(0)['metaParameters']
    keys = flatKeys(params)
    header = sorted(keys)

    df = loadResults(exp, filename, base=base)
    grouped = df.groupby(header)

    # ----------------------------------
    # -- first case: no existing data --
    # ----------------------------------
    if len(df) == 0:
        for idx in indices:
            for run in range(runs):
                yield idx + run * nperms

        return

    for idx in indices:
        params = exp.getPermutation(idx)['metaParameters']
        pvals = tuple(get(params, k) for k in header)

        # get_group cannot handle singular tuples
        if len(pvals) == 1:
            pvals = pvals[0]

        # ------------------------------------
        # -- second case: no existing group --
        # ------------------------------------
        try:
            group = grouped.get_group(pvals)
        except KeyError:
            for run in range(runs):
                yield idx + run * nperms

            continue

        # -------------------------------------------------
        # -- final case: have data and group. check runs --
        # -------------------------------------------------
        for run in range(runs):
            if not (group['run'] == run).any():
                yield idx + run * nperms