import importlib.util
import random
import unittest
from chinesepoker.ai.training_games import KuhnState


@unittest.skipUnless(importlib.util.find_spec('numpy'),'Install training requirements')
class DeepCFRTests(unittest.TestCase):
    def test_encoder_does_not_read_hidden_card(self):
        from tools.deep_cfr_kuhn import encode_key
        a=KuhnState((0,1)); b=KuhnState((0,2))
        self.assertEqual(encode_key(a.key()),encode_key(b.key()))
        self.assertNotEqual(encode_key(a.key()),encode_key(a.child('p').key()))

    def test_external_sampling_advantages_and_average_records(self):
        from tools.deep_cfr_kuhn import DeepCFRKuhn
        solver=DeepCFRKuhn(seed=3)
        solver.iterations=1
        solver.traverse(KuhnState((0,1)),0)
        self.assertTrue(solver.regrets[0].data)
        self.assertFalse(solver.regrets[1].data)
        for _,regrets,weight in solver.regrets[0].data:
            self.assertAlmostEqual(sum(regrets),0)  # Uniform initial strategy.
            self.assertEqual(weight,1)
        for _,strategy,_ in solver.average.data:
            self.assertEqual(strategy,(.5,.5))

    def test_reservoir_is_bounded_and_tracks_stream_count(self):
        from tools.deep_cfr_kuhn import Reservoir, KEYS
        memory=Reservoir(10,random.Random(0))
        for i in range(1000):
            memory.add(KEYS[i%12],[1,-1],i+1)
        self.assertEqual(len(memory.data),10)
        self.assertEqual(memory.seen,1000)
        self.assertTrue(any(row[2]>10 for row in memory.data))


if __name__=='__main__':
    unittest.main()
