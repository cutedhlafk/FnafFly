import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from mouse_controls import MouseControls, SYSTEM_POINTS, VENT_POINTS, DUCT_POINTS, monitor_system, BASE_MOUSE_ACTIONS
from autopolicy import Learner, ACTIONS, LEGACY_ACTIONS


def panel(system):
    pixels=np.zeros((540,960,3),np.uint8)
    pixels[498:518,522:760]=(100,100,100)
    _,y=SYSTEM_POINTS[system]
    pixels[int((y-.023)*540):int((y+.023)*540),680:780]=(32,140,110)
    return Image.fromarray(pixels)


class VentDuctTests(unittest.TestCase):
    def observe(self,c,system,t):
        for offset in (0,.05,.1):c.observe(panel(system),t+offset)

    def test_tab_color_not_presence_of_all_three_labels(self):
        for name in SYSTEM_POINTS:
            self.assertEqual(monitor_system(panel(name)),name)
        self.assertEqual(monitor_system(Image.new('RGB',(960,540),'green')),'unknown')

    def test_wrong_panel_and_old_camera_map_are_blocked(self):
        c=MouseControls();self.observe(c,'VENT_SYSTEM',10);c.camera_map_at=10
        allowed=dict(zip(ACTIONS,c.allowed(ACTIONS,10.2)))
        self.assertTrue(allowed['VENT_SNARE_LEFT'])
        self.assertFalse(allowed['DUCT_SEAL_LEFT']);self.assertFalse(allowed['CAM_01'])
        self.observe(c,'DUCT_SYSTEM',11)
        allowed=dict(zip(ACTIONS,c.allowed(ACTIONS,11.2)))
        self.assertTrue(allowed['DUCT_LURE_LEFT']);self.assertFalse(allowed['VENT_SNARE_LEFT'])
        self.assertFalse(dict(zip(ACTIONS,c.allowed(ACTIONS,14)))['DUCT_SEAL_RIGHT'])

    def test_switch_invalidates_targets_until_new_frames(self):
        c=MouseControls();self.observe(c,'VENT_SYSTEM',10)
        c.performed('DUCT_SYSTEM',10.2)
        self.assertEqual(c.system,'unknown')
        self.assertEqual(sum(c.allowed(ACTIONS,10.3)),1)
        self.observe(c,'DUCT_SYSTEM',11)
        self.assertTrue(dict(zip(ACTIONS,c.allowed(ACTIONS,11.2)))['DUCT_SEAL_RIGHT'])

    def test_seal_clicks_opposite_open_button(self):
        c=MouseControls()
        self.assertGreater(c.physical('DUCT_SEAL_LEFT',(.5,.5))[1][0],.4)
        self.assertLess(c.physical('DUCT_SEAL_RIGHT',(.5,.5))[1][0],.3)
        for a in (*VENT_POINTS,*DUCT_POINTS,*SYSTEM_POINTS):
            kind,point=c.physical(a,(.5,.5))
            self.assertEqual(kind,'CLICK')
            self.assertTrue(all(0<=v<=1 for v in point))

    def test_initial_defense_sequence_and_timeout(self):
        c=MouseControls();c.begin_night(10)
        for i,wanted in enumerate(c.SETUP):
            t=10+i
            c.ready_at=0;c.observed_at=t
            c.mode='office' if wanted in ('W','MONITOR_OPEN') else 'monitor'
            c.system='VENT_SYSTEM' if wanted in VENT_POINTS else 'DUCT_SYSTEM' if wanted in DUCT_POINTS else 'unknown'
            self.assertEqual(c.setup_action(ACTIONS,t),wanted)
            c.performed(wanted,t)
        self.assertIsNone(c.setup_index)
        c.begin_night(50);self.assertIsNone(c.setup_action(ACTIONS,66))
        c.reset();self.assertIsNone(c.setup_index)

    def test_migration_of_33_actions_preserves_all_old_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'model.npz';p=Learner(8,'x',path);p.steps=42;p.save()
            with np.load(path) as f:data={k:f[k].copy() for k in f.files}
            old_actions=LEGACY_ACTIONS+BASE_MOUSE_ACTIONS
            data['h0']=data['h0'][:len(old_actions)];data['actions']=np.array(old_actions);data['version']=4
            np.savez_compressed(path,**data)
            q=Learner(8,'x',path)
            np.testing.assert_array_equal(q.heads[0][:len(old_actions)],data['h0'])
            self.assertEqual(q.steps,42);q.save()
            self.assertTrue(path.with_suffix('.pre-vent-duct-backup.npz').exists())

    def test_semantic_defense_does_not_train_mouse_coordinate_heads(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Learner(8,'x',Path(folder)/'model.npz');before=p.heads[1].copy()
            _,_,transition=p.guided(np.ones(8),'VENT_SNARE_LEFT')
            p.record(transition,1);p._learn(p.pending)
            np.testing.assert_array_equal(p.heads[1],before)
            self.assertEqual(p.guided_steps,1)


if __name__=='__main__':unittest.main()
