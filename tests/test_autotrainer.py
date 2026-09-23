import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autopolicy import Learner
from screen_reader import classify, Observation
from autotrainer import EpisodeLoop, Trainer
from collections import deque
import threading

class AutoTests(unittest.TestCase):
    def test_old_menu_frame_cannot_click_after_transition_deadline(self):
        game=Mock();loop=EpisodeLoop(game,Mock(),Mock(),Mock());loop.deadline=105
        loop.observe(Observation('menu',verified50=True,buttons={'go':(.9,.9)}),106,captured_at=103)
        game.click_normalized.assert_not_called()

    def test_resume_on_instructions_without_verification_recovers(self):
        game=Mock();loop=EpisodeLoop(game,Mock(),Mock(),Mock())
        loop.verified=True
        loop.abort('pause')
        loop.observe(Observation('instructions',buttons={'go':(.9,.9)}),100)
        game.perform.assert_called_once_with('ESC')
        self.assertEqual(loop.phase,'menu')
        game.click_normalized.assert_not_called()
        loop.observe(Observation('menu',verified50=True,buttons={'go':(.9,.9)}),103)
        self.assertTrue(loop.verified)
        loop.observe(Observation('instructions',buttons={'go':(.9,.9)}),105)
        self.assertEqual(game.click_normalized.call_count,2)

    def test_instructions_detected_when_go_ocr_missing(self):
        obs=classify([(t,.3,.3+i*.08,.99) for i,t in enumerate(['1 - Power Generator','Z - Flashlight','A - Close Left Door'])])
        self.assertEqual(obs.scene,'instructions')
        self.assertNotIn('go',obs.buttons)

    def test_missing_go_in_instructions_has_timeout(self):
        game=Mock();loop=EpisodeLoop(game,Mock(),Mock(),Mock());loop.verified=True
        loop.observe(Observation('instructions'),100)
        game.perform.assert_called_once_with('ESC')

    def test_f7_restarts_dead_worker(self):
        from unittest.mock import patch
        trainer=Trainer.__new__(Trainer);trainer.lock=threading.RLock();trainer.commands=deque()
        trainer.closed=threading.Event();trainer.worker=Mock(ident=123)
        trainer.worker.is_alive.return_value=False
        with patch('autotrainer.threading.Thread') as factory:
            trainer.command('play');factory.return_value.start.assert_called_once()
            self.assertEqual(list(trainer.commands),['start'])

    def test_f7_maps_to_start_without_main_wrapper(self):
        trainer=Trainer.__new__(Trainer)
        trainer.lock=threading.RLock();trainer.commands=deque()
        trainer.command('play')
        self.assertEqual(list(trainer.commands),['start'])

    def test_menu_requires_configured_score_not_highscore(self):
        words=[('SET ALL 0',.9,.1,.99),('SET ALL 20',.9,.3,.99),('GO',.9,.9,.99),('HIGH SCORE 10000',.5,.95,.99)]
        self.assertFalse(classify(words).verified50)
        obs=classify(words+[('POINT VALUE: 10000',.6,.9,.99)])
        self.assertTrue(obs.verified50)
        self.assertEqual(obs.buttons['twenty'],(.9,.3))

    def test_clock_and_unknown(self):
        obs=classify([('12 AM',.95,.03,.99),('0:09.5',.95,.09,.99)])
        self.assertEqual((obs.scene,obs.seconds),('playing',9.5))
        self.assertEqual(classify([('6 AM',.1,.9,.99)]).scene,'unknown')
        self.assertEqual(classify([('GAME OVER',.5,.4,.99)]).scene,'loss')

    def test_multiline_menu(self):
        obs=classify([('SET ALL',.92,.04,.99),('0',.92,.07,.99),('SET ALL',.92,.32,.99),
            ('20',.92,.35,.99),('Point Value:',.94,.54,.99),('10000',.94,.59,.99),
            ('High Score:',.94,.63,.99),('2000',.94,.67,.99)])
        self.assertEqual(obs.scene,'menu');self.assertTrue(obs.verified50)
        self.assertIn('twenty',obs.buttons)

    def test_learning_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'model.npz';a=Learner(8,'test',p)
            before=a.heads[0].copy()
            for _ in range(50):
                _,_,t=a.act(np.ones(8));a.record(t);a.progress(.2)
            a.finish('loss',10)
            self.assertGreater(np.max(np.abs(before-a.heads[0])),0)
            b=Learner(8,'test',p)
            self.assertEqual(b.episodes,1);self.assertEqual(b.updates,1)
            np.testing.assert_array_equal(a.heads[0],b.heads[0])
            self.assertEqual(a.act(np.ones(8))[:2],b.act(np.ones(8))[:2])
            with self.assertRaises(ValueError):Learner(8,'wrong',p)

    def test_automatic_two_episodes_and_abort(self):
        game=Mock();game.click_normalized.return_value=True;game.perform.return_value=True
        with tempfile.TemporaryDirectory() as d:
            learner=Learner(8,'test',Path(d)/'a.npz')
            loop=EpisodeLoop(game,learner,Mock(),Mock())
            for base in (100.,200.):
                menu=Observation('menu',buttons={'twenty':(.9,.3),'go':(.9,.9)})
                loop.observe(menu,base)
                self.assertFalse(loop.active)
                menu.verified50=True;loop.observe(menu,base+1)
                loop.observe(Observation('playing',seconds=0),base+3)
                # The initial defense sequence requires a fresh office frame.
                loop.mouse_controls.mode='office'
                loop.mouse_controls.observed_at=base+3
                with patch('autotrainer.time.monotonic',return_value=base+3.1):
                    loop.act(np.ones(8),base+3.1)
                loop.observe(Observation('playing',seconds=2),base+5)
                loop.observe(Observation('loss'),base+6)
                loop.observe(Observation('loss'),base+7)
                self.assertFalse(loop.active)
                loop.observe(Observation('loss'),base+10)
            self.assertEqual(learner.episodes,2);self.assertEqual(learner.updates,2)
            self.assertEqual(len(loop.results),2)
            learner.record(learner.act(np.ones(8))[2]);loop.active=True;loop.abort('focus lost')
            self.assertFalse(learner.pending);self.assertEqual(learner.episodes,2)

    def test_no_learning_or_actions_on_unknown_or_terminal(self):
        learner=Mock();game=Mock();loop=EpisodeLoop(game,learner,Mock(),Mock())
        loop.active=True;loop.started=100.;loop.last_known=100.
        loop.observe(Observation('unknown'),104.)
        loop.act(np.ones(8),104.)
        learner.act.assert_not_called();learner.progress.assert_not_called()
        loop.observe(Observation('loss'),105.)
        loop.act(np.ones(8),105.)
        learner.act.assert_not_called()

if __name__=='__main__':unittest.main()
