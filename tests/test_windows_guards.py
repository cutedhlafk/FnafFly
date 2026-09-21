import ctypes
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from windows_game import Game, INPUT

class TestInputGuard(unittest.TestCase):
    def stub(self):
        g=Game.__new__(Game)
        g.emergency=threading.Event()
        g.input_lock=threading.Lock()
        g.injected=set()
        return g

    def test_sendinput_abi(self):
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

    def test_f7_resumes_outside_game_once_per_press(self):
        for enabled in (True,False):
            g=self.stub();g.global_resume=enabled;g.observe_inputs=False;g.command=Mock()
            g.closed=Mock();g.closed.wait.side_effect=[False,False,True]
            with patch.object(g,'find'),patch.object(g,'focused',return_value=False),patch('windows_game.u.GetAsyncKeyState',side_effect=lambda vk:0x8000 if vk==0x76 else 0):
                g._sample()
            if enabled:g.command.assert_called_once_with('play')
            else:g.command.assert_not_called()

    def test_no_injection_outside_game_or_after_emergency(self):
        g=self.stub()
        with patch.object(g,'focused',return_value=False),patch.object(g,'_key') as key:
            self.assertFalse(g.perform('A'))
            key.assert_not_called()
        g.emergency.set()
        with patch.object(g,'focused',return_value=True),patch.object(g,'_key') as key:
            self.assertFalse(g.perform('A'))
            key.assert_not_called()

    def test_key_is_released_after_interrupt(self):
        g=self.stub();calls=[]
        def key(vk,up=False):
            calls.append((vk,up))
            if not up:g.emergency.set()
        with patch.object(g,'focused',return_value=True),patch.object(g,'_key',side_effect=key):
            self.assertTrue(g.perform('A'))
        self.assertEqual(calls,[(65,False),(65,True)])
        self.assertFalse(g.injected)

    def test_secure_desktop_input_failure_pauses_without_killing_worker(self):
        g=self.stub();g.command=Mock()
        with patch.object(g,'focused',return_value=True),patch.object(g,'_key',side_effect=OSError(5,'blocked')):
            self.assertFalse(g.perform('A'))
        self.assertTrue(g.emergency.is_set());g.command.assert_called_once_with('pause')

if __name__=='__main__':unittest.main()
