import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from game_audio import extract, combine, GameAudio, FEATURE_COUNT
from autopolicy import Learner

class AudioTests(unittest.TestCase):
    def test_silence_is_valid_but_has_no_direction(self):
        x,level=extract(np.zeros((4800,2)))
        self.assertEqual(level,0)
        np.testing.assert_array_equal(x[:-1],0)
        self.assertEqual(x[-1],1)
    def test_stereo_direction_and_spectrum(self):
        tone=.1*np.sin(2*np.pi*1500*np.arange(4800)/48000)
        right=np.column_stack([tone*.1,tone]);x,_=extract(right)
        self.assertGreater(x[4],.8)
        self.assertEqual(np.argmax(x[6:14]),4)
        left,_=extract(right[:,::-1]);self.assertLess(left[4],-.8)
    def test_stale_audio_is_zero_and_not_replayed(self):
        audio=GameAudio('unused');audio.features[:]=1;audio.stamp=0
        x,s=audio.sample();self.assertFalse(s['active']);self.assertFalse(x.any())
    def test_nonfinite_samples_do_not_poison_policy(self):
        x,_=extract(np.full((30,2),np.nan));self.assertFalse(x.any())
    def test_checkpoint_migration_preserves_visual_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model.npz';old=Learner(8,'graph',path)
            old.steps=45;old.save();vision=np.arange(8,dtype=np.float32);vision[-1]=1
            new=Learner(8+FEATURE_COUNT,'graph',path,extra_features=FEATURE_COUNT)
            for a,b in zip(old.heads,new.heads):
                np.testing.assert_allclose(a@old.features(vision),b@new.features(combine(vision,np.ones(FEATURE_COUNT))),atol=1e-6)
            self.assertEqual(new.steps,45);new.save()
            self.assertTrue(path.with_suffix('.pre-audio-backup.npz').exists())
            again=Learner(24,'graph',path,extra_features=16)
            np.testing.assert_array_equal(again.heads[0],new.heads[0])

if __name__=='__main__':unittest.main()
