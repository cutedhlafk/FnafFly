import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autopolicy import Learner, ROLLOUT
from screen_reader import classify, Observation
from defense_knowledge import catalog, DefenseAdvisor

class ContinualTests(unittest.TestCase):
    def test_update_reports_real_weight_change_and_restores_it(self):
        self.p.record(self.p.act(self.x)[2],reward=1,at=1)
        self.p._learn(self.p.pending)
        self.assertGreater(self.p.last_update_delta,0)
        self.assertGreater(self.p.last_weight_change,0)
        self.p.save()
        restored=Learner(8,'test',self.path)
        self.assertEqual(restored.last_update_delta,self.p.last_update_delta)

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'policy.npz'
        self.p=Learner(8,'test',self.path)
        self.x=np.ones(8)
    def tearDown(self):self.folder.cleanup()
    def add(self,t):self.p.record(self.p.act(self.x)[2],at=t)
    def test_reward_credit_respects_capture_time_and_is_shared(self):
        for t in (1,2,3,4):self.add(t)
        self.p.progress(2,through=3)
        self.assertEqual([round(e[1],3) for e in self.p.pending],[.08,.08,0,0])
        self.p.progress(0,through=5)
        self.assertEqual(self.p.credited,2)
        self.p.progress(1,through=4)
        self.assertAlmostEqual(self.p.pending[2][1],.08)
        self.assertEqual(self.p.pending[3][1],0)
    def test_updates_during_night_without_invented_terminal(self):
        before=self.p.heads[0].copy()
        for t in range(ROLLOUT+2):self.add(t)
        self.p.progress(8,through=ROLLOUT,next_features=self.x)
        self.assertEqual(self.p.continuous_updates,1)
        self.assertEqual(self.p.episodes,0)
        self.assertEqual(len(self.p.pending),2)
        self.assertGreater(np.linalg.norm(before-self.p.heads[0]),0)
        self.p.finish('abort',0)
        self.assertEqual(self.p.updates,1)
        self.assertEqual(len(self.p.pending),0)
    def test_no_learning_from_unconfirmed_wait_or_nan(self):
        for i in range(ROLLOUT):self.add(i)
        self.p.progress(0,next_features=self.x)
        self.assertEqual(self.p.updates,0)
        with self.assertRaises(ValueError):self.p.act(np.full(8,np.nan))
        np.testing.assert_array_equal(self.p.value,np.zeros(8))
    def test_legacy_checkpoint_migrates_without_reset_and_keeps_backup(self):
        self.p.finish('loss',5)
        with np.load(self.path) as f:old={k:f[k].copy() for k in f.files}
        old['version']=np.array(1)
        with self.path.open('wb') as f:np.savez_compressed(f,**old)
        migrated=Learner(8,'test',self.path)
        np.testing.assert_array_equal(migrated.heads[0],self.p.heads[0])
        self.assertEqual(migrated.episodes,1)
        migrated.save()
        self.assertTrue(self.path.with_suffix('.v1-backup.npz').exists())
        self.assertTrue(self.path.with_suffix('.previous.npz').exists())
        with np.load(self.path) as f:self.assertEqual(int(f['version']),2)
    def test_guided_actions_are_marked_and_teach_separately(self):
        initial=self.p.heads[0].copy()
        action,mouse,t=self.p.guided(self.x,'CLICK',(.33,.61))
        self.assertEqual(mouse,(.33,.61));self.assertFalse(t[4])
        self.p.record(t)
        self.assertEqual(self.p.guided_steps,1)
        self.assertGreater(np.linalg.norm(initial-self.p.heads[0]),0)
        after=self.p.heads[0].copy()
        self.p.finish('loss',1)
        np.testing.assert_array_equal(after,self.p.heads[0])

class DefenseTests(unittest.TestCase):
    def test_complete_unique_roster_and_sources(self):
        rows=catalog();self.assertEqual(len(rows),50)
        self.assertEqual(len({r['name'] for r in rows}),50)
        for r in rows:self.assertTrue(r['source'].startswith('https://'));self.assertTrue(r['plan'])
    def test_fresh_grounded_mute_and_cooldown(self):
        a=DefenseAdvisor();o=classify([('MUTE CALL',.4,.3,.99)])
        a.observe(o,10);advice=a.suggest(10.1)
        self.assertEqual(advice.action,'CLICK');self.assertEqual(advice.mouse,(.4,.3))
        a.performed('CLICK',10.1,advice)
        self.assertIsNone(a.suggest(10.2));self.assertIsNone(a.suggest(12))
    def test_low_confidence_tooltips_and_names_do_not_trigger(self):
        a=DefenseAdvisor()
        for words in [[('MUTE CALL',.5,.5,.6)], [('Phone Guy',.5,.5,1.)],
                      [('SET ALL 0',.9,.1,1.),('SET ALL 20',.9,.3,1.),('SKIP',.9,.8,1.)]]:
            a.observe(classify(words),10);self.assertIsNone(a.suggest(10.1))
    def test_toy_freddy_game_over_is_not_our_death(self):
        o=classify([('12 AM',.95,.05,.99),('0:12.3',.95,.1,.99),('GAME OVER',.5,.5,.99)])
        self.assertEqual(o.scene,'playing')
    def test_heat_and_music_do_not_guess_sides_or_enemy_presence(self):
        a=DefenseAdvisor();o=classify([('12 AM',.95,.05,.99),('90°',.95,.9,.99)])
        a.observe(o,10);advice=a.suggest(10.1);self.assertEqual(advice.action,'4')
        a.performed('4',10.1,advice);self.assertIsNone(a.suggest(10.2))
        a.reset();a.observe(Observation('playing',seconds=13),20)
        self.assertEqual(a.suggest(20.1).action,'5')

if __name__=='__main__':unittest.main()
