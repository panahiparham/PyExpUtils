from PyExpUtils.results.results import Result, getBest, splitOverParameter
from PyExpUtils.results.indices import listIndices
from PyExpUtils.models.ExperimentDescription import ExperimentDescription
import unittest
import numpy as np

exp = ExperimentDescription({
    'metaParameters': {
        'alpha': [1.0, 0.5, 0.25],
        'ratio': [1.0, 2.0, 4.0, 8.0],
    },
})

class TestResults(unittest.TestCase):
    def test_Results(self):
        results = [Result('fake/path', exp, i) for i in listIndices(exp)]

        r = results[0]
        self.assertDictEqual(r.params, { 'alpha': 1.0, 'ratio': 1.0 })
        r = results[1]
        self.assertDictEqual(r.params, { 'alpha': 0.5, 'ratio': 1.0 })
        self.assertEqual(r.idx, 1)

        # can overload load function
        class TestResult(Result):
            def _load(self):
                # (mean, std, runs)
                return (1, 2, 3)

        results = [TestResult('fake/path', exp, i) for i in listIndices(exp)]

        r = results[0]
        self.assertEqual(r.mean(), 1)


    def test_splitOverParameter(self):
        results = (Result('fake/path', exp, i) for i in listIndices(exp))

        split_results = splitOverParameter(results, 'alpha')
        self.assertEqual(list(split_results), [1.0, 0.5, 0.25]) # check keys
        self.assertEqual(len(split_results[1.0]), 4)

        for key in split_results:
            sub_results = split_results[key]
            for res in sub_results:
                self.assertEqual(res.params['alpha'], key)

    def test_getBest(self):
        # lowest
        load_counter = 0
        class TestResult(Result):
            def _load(self):
                nonlocal load_counter
                load_counter += 1
                return (np.ones(100) * load_counter, np.ones(100), 3)

        results = (TestResult('fake/path', exp, i) for i in listIndices(exp))

        best = getBest(results)
        self.assertEqual(best.mean()[0], 1)

        # highest
        results = (TestResult('fake/path', exp, i) for i in listIndices(exp))

        best = getBest(results, comparator=lambda a, b: a > b)
        self.assertEqual(best.mean()[0], load_counter)
