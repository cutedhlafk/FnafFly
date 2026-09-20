import http.client
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from autotrainer import make_handler, ExclusiveHTTPServer

class ViewerTests(unittest.TestCase):
    def test_only_one_training_server_can_bind(self):
        first=ExclusiveHTTPServer(('127.0.0.1',0),http.server.BaseHTTPRequestHandler)
        try:
            with self.assertRaises(OSError):
                duplicate=ExclusiveHTTPServer(first.server_address,http.server.BaseHTTPRequestHandler)
                duplicate.server_close()
        finally:first.server_close()
    def setUp(self):
        self.trainer=Mock();self.trainer.state.return_value={'application':'test'}
        self.server=ThreadingHTTPServer(('127.0.0.1',0),http.server.BaseHTTPRequestHandler)
        self.port=self.server.server_address[1]
        self.handler=make_handler(self.trainer,'control-secret','viewer-secret',{'127.0.0.1'},self.port)
        self.server.RequestHandlerClass=self.handler
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,method='GET',headers=None,body=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
        c.request(method,path,body,headers or {});r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
    def test_remote_requires_viewer_cookie_and_cannot_control(self):
        self.handler.local=lambda self:False
        self.assertEqual(self.request('/api/state')[0],403)
        r=self.request('/?view=viewer-secret')
        self.assertEqual(r[0],303);self.assertIn('HttpOnly',r[1]['Set-Cookie'])
        headers={'Cookie':'fly_view=viewer-secret'}
        self.assertEqual(self.request('/api/state',headers=headers)[0],200)
        body=self.request('/',headers=headers)[2].decode()
        self.assertNotIn('control-secret',body)
        headers['X-Fly-Token']='control-secret'
        self.assertEqual(self.request('/api/command','POST',headers,'{"command":"start"}')[0],403)
        self.trainer.command.assert_not_called()
    def test_local_requires_token_host_and_origin(self):
        self.assertEqual(self.request('/api/command','POST',{},'{"command":"stop"}')[0],403)
        h={'X-Fly-Token':'control-secret'}
        self.assertEqual(self.request('/api/command','POST',h,'{"command":"stop"}')[0],200)
        self.trainer.command.assert_called_once_with('stop')
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        h['Origin']='http://evil.example'
        self.assertEqual(self.request('/api/command','POST',h,'{"command":"start"}')[0],403)
