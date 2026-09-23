import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT)]
from autopolicy import Learner, ACTIONS, LEGACY_ACTIONS
from mouse_controls import MouseControls
from autotrainer import EpisodeLoop
from auto50 import Auto50Bootstrap, CONFIG_VERSION
from screen_reader import Observation, point_value_10000
from windows_game import Game
from game_state import GameStateDetector


class RevisionTests(unittest.TestCase):
    def test_migration_keeps_existing_weights_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model.npz'
            original=Learner(8,'test',path);original.steps=100;original.save()
            with np.load(path) as f:data={k:f[k].copy() for k in f.files}
            data['actions']=np.array(LEGACY_ACTIONS);data['h0']=data['h0'][:20];data['version']=3
            np.savez_compressed(path,**data)
            migrated=Learner(8,'test',path)
            np.testing.assert_array_equal(migrated.heads[0][:20],data['h0'])
            np.testing.assert_array_equal(migrated.heads[1],data['h1'])
            self.assertEqual(migrated.steps,100)
            migrated.save()
            self.assertTrue(path.with_suffix('.pre-mouse-backup.npz').exists())

    def test_masked_training_does_not_change_unavailable_actions_or_mouse(self):
        with tempfile.TemporaryDirectory() as folder:
            learner=Learner(8,'test',Path(folder)/'model.npz')
            allowed=[a in ('WAIT','MASK_ON') for a in ACTIONS]
            before=[h.copy() for h in learner.heads]
            for _ in range(20):
                action,_,transition=learner.act(np.ones(8),allowed)
                self.assertIn(action,('WAIT','MASK_ON'))
                learner.record(transition,1)
            learner._learn(learner.pending)
            np.testing.assert_array_equal(before[0][~np.array(allowed)],learner.heads[0][~np.array(allowed)])
            np.testing.assert_array_equal(before[1],learner.heads[1])
            self.assertTrue(np.isfinite(learner.heads[0]).all())

    def test_single_allowed_action_is_numerically_stable(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Learner(8,'x',Path(folder)/'m.npz')
            a,_,t=p.act(np.ones(8),[a=='MASK_OFF' for a in ACTIONS])
            self.assertEqual(a,'MASK_OFF');p.record(t,1);p._learn(p.pending)
            self.assertTrue(np.isfinite(p.heads[0]).all())
            with self.assertRaises(ValueError):p.act(np.ones(8),[False]*len(ACTIONS))

    def test_mouse_mode_needs_two_frames_and_expires(self):
        a=np.zeros((540,960,3),np.uint8)
        a[498:518,222:460]=(100,50,50)
        a[498:518,522:760]=(100,100,100)
        frame=Image.fromarray(a);c=MouseControls()
        c.observe(frame,10);self.assertEqual(c.mode,'unknown')
        c.observe(frame,10.2);self.assertEqual(c.mode,'office')
        self.assertTrue(c.allowed(ACTIONS,10.3)[ACTIONS.index('MASK_ON')])
        self.assertFalse(c.allowed(ACTIONS,12)[ACTIONS.index('MASK_ON')])
        c.performed('MASK_ON',10.3)
        self.assertEqual(sum(c.allowed(ACTIONS,10.4)),1)
        a[498:518,522:760]=0
        c.observe(Image.fromarray(a),11);c.observe(Image.fromarray(a),11.2)
        self.assertEqual(c.mode,'mask')
        self.assertEqual([a for a,v in zip(ACTIONS,c.allowed(ACTIONS,11.2)) if v],['WAIT','MASK_OFF'])

    def test_old_camera_ocr_cannot_survive_monitor_transition(self):
        c=MouseControls();obs=Observation(texts=['CAM SYSTEM','CAM 01','CAM 02','CAM 03'])
        c.read(obs,10);c.performed('MONITOR_CLOSE',11);c.read(obs,10)
        self.assertLess(c.camera_map_at,0)

    def test_hover_reenters_arrow_and_stops_after_emergency(self):
        game=Game.__new__(Game);game.emergency=threading.Event()
        calls=[]
        with patch.object(game,'focused',return_value=True):
            original=game._perform
            def perform(action,mouse):
                if action=='MOVE':calls.append(mouse);return True
                return original(action,mouse)
            with patch.object(game,'_perform',side_effect=perform):
                self.assertTrue(game.perform('HOVER_ARROW',(.355,.941)))
        self.assertEqual(calls,[(.355,.88),(.355,.941),(.355,.88)])
        game.emergency.set()
        with patch.object(game,'focused',return_value=True):
            self.assertFalse(game.perform('HOVER_ARROW',(.355,.941)))

    def test_trusted_start_cannot_bypass_fresh_observation(self):
        loop=EpisodeLoop(Mock(),Mock(),Mock(),Mock())
        loop.active=True;loop.trusted_auto50_start=True;loop.last_scene='playing';loop.last_known=10
        loop.act(np.ones(8),15)
        loop.game.perform.assert_not_called()
        loop.active=False;loop.verified=True;loop.last_scene='instructions'
        self.assertFalse(loop.start_auto50_episode(15))

    def test_auto50_rejects_invalid_timing_config(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'config.json'
            data=dict(config_version=CONFIG_VERSION,calibrated=True,set_all_0=[.9,.1],set_all_20=[.9,.3],go=[.9,.9])
            for invalid in (float('nan'),float('inf'),-2,'bad',999999):
                path.write_text(json.dumps({**data,'after_click_seconds':invalid}))
                with patch('auto50.CONFIG_PATH',path):self.assertIsNone(Auto50Bootstrap(Mock()).config)

    def test_missing_or_resized_frame_is_not_transition_evidence(self):
        self.assertEqual(Auto50Bootstrap._difference(None,Image.new('RGB',(10,10))),0)
        self.assertEqual(Auto50Bootstrap._difference(Image.new('RGB',(10,10)),Image.new('RGB',(20,20))),0)

    def test_auto50_never_clicks_on_nonmenu_screen(self):
        g=Mock();g.emergency.is_set.return_value=False;g.launch.return_value=False
        g.capture.return_value=Image.new('RGB',(32,18))
        reader=Mock();reader.read.return_value=Observation('playing')
        b=Auto50Bootstrap(g,reader);b.config={ 'after_focus_seconds':.1 }
        with patch.object(b,'_wait',return_value=True):result=b.run()
        self.assertFalse(result.ok);g.click_normalized.assert_not_called()

    def test_auto50_requires_ocr_50_20_even_if_images_change(self):
        g=Mock();g.emergency.is_set.return_value=False;g.launch.return_value=False
        g.capture.side_effect=[Image.new('RGB',(32,18)),Image.new('RGB',(32,18)),Image.new('RGB',(32,18),'white')]
        reader=Mock();reader.read.side_effect=[Observation('menu'),Observation('menu',verified50=False)]
        b=Auto50Bootstrap(g,reader);b.config=dict(after_focus_seconds=.1,after_click_seconds=.1,
            set_all_0=[.9,.1],set_all_20=[.9,.3],minimum_setup_difference=.001)
        with patch.object(b,'_wait',return_value=True):result=b.run()
        self.assertFalse(result.ok);self.assertEqual(g.click_normalized.call_count,2)

    def test_score_must_be_exact(self):
        self.assertFalse(point_value_10000([('POINTVALUE100000',.9,.6,.99)]))

    def test_invalid_templates_do_not_enter_detector(self):
        with self.assertRaises(ValueError):GameStateDetector(threshold=float('nan'))
        d=GameStateDetector(size=(2,2))
        for value in (float('nan'),float('inf'),-1,2):
            with self.assertRaises(ValueError):d.set_template('win',np.full((2,2),value))

    def test_freshness_uses_capture_time_not_ocr_completion(self):
        loop=EpisodeLoop(Mock(),Mock(),Mock(),Mock())
        loop.learner.episodes=0
        loop.verified=True;loop.active=True
        loop.observe(Observation('playing'),20,captured_at=16.5)
        self.assertEqual(loop.last_known,16.5)
        loop.act(np.ones(8),20)
        loop.game.perform.assert_not_called()

    def test_green_patch_without_text_is_not_instructions(self):
        from screen_reader import ScreenReader
        reader=ScreenReader.__new__(ScreenReader);reader.last_scene='unknown';reader.frame_index=0
        frame=Image.new('RGB',(640,360),'green')
        with patch.object(reader,'_menu',return_value=None), patch.object(reader,'_gameplay',return_value=None), \
             patch.object(reader,'_dark_terminal',return_value=None),patch.object(reader,'_words',return_value=[]):
            self.assertEqual(reader.read(frame).scene,'unknown')

    def test_instruction_fast_path_skips_keyboard_and_dark_terminal_ocr(self):
        from screen_reader import ScreenReader
        reader=ScreenReader.__new__(ScreenReader);reader.last_scene='menu';reader.frame_index=0
        words=[(s,.5,.1,.99) for s in ('Power Generator','Close Forward Vent','Close Left Door')]
        with patch.object(reader,'_menu',return_value=None),patch.object(reader,'_gameplay',return_value=None), \
             patch.object(reader,'_green_go',return_value=(.9,.9)),patch.object(reader,'_words',return_value=words), \
             patch.object(reader,'_dark_terminal') as terminal:
            result=reader.read(Image.new('RGB',(1280,720)))
        self.assertEqual(result.scene,'instructions');self.assertIn('go',result.buttons)
        terminal.assert_not_called()

    def test_ocr_does_not_upscale_short_hud_side_to_736(self):
        from screen_reader import ScreenReader
        with patch('rapidocr.RapidOCR') as factory:ScreenReader()
        params=factory.call_args.kwargs['params']
        self.assertEqual(params['Det.limit_type'],'max')
        self.assertLessEqual(params['Det.limit_side_len'],640)


if __name__=='__main__':unittest.main()
