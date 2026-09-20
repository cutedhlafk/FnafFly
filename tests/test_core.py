import sys
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connectome import Brain
from policy import Policy,ACTIONS

class TestBrain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.brain=Brain()

    def test_full_graph_is_real_signed_and_bounded(self):
        b=self.brain
        self.assertEqual(b.w.shape,(138639,138639))
        self.assertEqual(b.w.nnz,15091983)
        self.assertTrue((b.w.data<0).any())
        self.assertTrue((b.w.data>0).any())
        sums=np.asarray(abs(b.w).sum(axis=1)).ravel()
        self.assertLessEqual(float(sums.max()),.921)

    def test_visual_input_propagates_beyond_input_neurons(self):
        b=self.brain;b.reset()
        frame=Image.fromarray(np.tile(np.arange(256,dtype=np.uint8),(144,1)))
        for _ in range(5):features=b.step(frame)
        indirect=np.ones(len(b.ids),bool);indirect[b.sensors]=False
        self.assertGreater(np.count_nonzero(abs(b.state[indirect])>1e-6),1000)
        self.assertTrue(np.isfinite(features).all())
        self.assertEqual(len(features),b.meta['feature_count'])
        first=b.state.copy();b.reset()
        for _ in range(5):b.step(frame)
        np.testing.assert_array_equal(first,b.state)
        for _ in range(5):b.step(Image.new('RGB',(256,144),'white'))
        self.assertGreater(float(np.linalg.norm(first-b.state)),1)

class TestPolicy(unittest.TestCase):
    def fresh(self):
        # Construct without reading any real training checkpoint.
        original=Policy.load
        try:
            Policy.load=lambda self:None
            return Policy(12,'unit-test-fixture')
        finally:Policy.load=original

    def test_learning_generalizes_and_round_trips(self):
        p=self.fresh();rng=np.random.default_rng(3)
        for label in [0,1,2]:
            for _ in range(80):
                x=rng.normal(0,.08,12).astype(np.float32);x[label]=2;x[-1]=1
                p.remember(x,label,[.25,.75])
        for _ in range(200):p.train_batch()
        correct=0
        for label in [0,1,2]:
            for _ in range(30):
                x=rng.normal(0,.08,12).astype(np.float32);x[label]=2;x[-1]=1
                correct+=p.predict(x)[0]==label
        self.assertGreater(correct,85)
        with tempfile.TemporaryDirectory() as folder:
            p.path=Path(folder)/'test.npz';p.save()
            other=self.fresh();other.path=p.path;other.load()
            np.testing.assert_array_equal(p.w,other.w)
            self.assertEqual(other.total_samples,240)
            self.assertTrue(other.ready)
            other.signature='wrong-connectome'
            with self.assertRaises(ValueError):other.load()

    def test_reward_changes_probability_only_with_actions(self):
        p=self.fresh();x=np.zeros(12,np.float32);x[-1]=1
        self.assertEqual(p.reward(1),0)
        _,before,_=p.predict(x)
        p.record_action(x,1,before);self.assertEqual(p.reward(5),1)
        _,after,_=p.predict(x)
        self.assertGreater(after[1],before[1])
        self.assertFalse(p.ready)

if __name__=='__main__':unittest.main()
