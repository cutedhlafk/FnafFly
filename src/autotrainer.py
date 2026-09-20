"""Autonomous UCN training, bounded to the exact game process, with LAN viewer."""
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import argparse
import io
import json
import logging
import secrets
import socket
import threading
import time
import webbrowser
import numpy as np
from connectome import Brain, ROOT
from autopolicy import Learner
from screen_reader import ScreenReader, Observation

class ExclusiveHTTPServer(ThreadingHTTPServer):
    allow_reuse_address=False
    def server_bind(self):
        # Windows SO_REUSEADDR allows two independent servers on the same port.
        if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        super().server_bind()


class EpisodeLoop:
    """State machine separate from capture/HTTP so transitions can be tested."""
    def __init__(self, game, learner, brain, log):
        self.game,self.learner,self.brain,self.log=game,learner,brain,log
        self.phase='menu';self.active=False;self.verified=False
        self.elapsed=0.;self.started=0.;self.last_progress=0.
        self.deadline=0.;self.last_scene='';self.stable=0
        self.last_known=time.monotonic();self.last_recovery=0.
        self.results=deque(maxlen=80)
        self.action='WAIT';self.note='Oczekiwanie na menu UCN'

    def abort(self, reason):
        if self.active:
            self.learner.finish('abort',self.elapsed)
            self.log('abort',reason=reason,seconds=self.elapsed)
        self.active=False;self.verified=False;self.phase='menu'
        self.note=reason;self.game.release()

    def observe(self, obs, now):
        self.stable=self.stable+1 if obs.scene==self.last_scene else 1
        self.last_scene=obs.scene
        if obs.scene!='unknown':self.last_known=now
        if now<self.deadline:return
        if obs.scene=='menu':
            if self.active:
                self.abort('Powrót do menu bez rozpoznanego wyniku; próba pominięta')
            if self.phase=='verify' and obs.verified50:
                self.verified=True
                if 'go' in obs.buttons and self.game.click_normalized(*obs.buttons['go']):
                    self.phase='starting';self.deadline=now+1.5
                    self.note='Potwierdzone 50/20. Uruchamiam noc.'
                    self.log('configured',difficulty='50/20',evidence=obs.texts)
            elif self.phase!='verify' or now-self.last_recovery>5:
                if 'twenty' in obs.buttons and self.game.click_normalized(*obs.buttons['twenty']):
                    self.phase='verify';self.last_recovery=now;self.deadline=now+.5
                    self.note='Ustawiam wszystkie postacie na 20 i sprawdzam punktację.'
            else:
                self.note='Sprawdzam 50/20. Brak potwierdzenia 10 000 punktów — nie uruchamiam innej trudności.'
        elif obs.scene=='instructions' and self.verified:
            if 'go' in obs.buttons and self.game.click_normalized(*obs.buttons['go']):
                self.phase='starting';self.deadline=now+1.
        elif obs.scene=='playing':
            if not self.active:
                if not self.verified:
                    self.note='Zastana noc bez potwierdzonego 50/20. Wracam do menu.'
                    self.game.perform('ESC');self.deadline=now+2;return
                self.active=True;self.phase='playing';self.elapsed=0.
                self.started=now;self.last_progress=now;self.brain.reset()
                self.log('start',difficulty='50/20',episode=self.learner.episodes+1)
            if obs.seconds is not None:
                delta=obs.seconds-self.elapsed
                # Reject OCR jumps; neither a frozen clock nor real-world waiting earns rewards.
                if 0<=delta<=max(5.,(now-self.last_progress)*1.5+2) and obs.seconds<=400:
                    self.learner.progress(delta);self.elapsed=obs.seconds
                    if delta>0:self.last_progress=now
            self.note=f'Trening 50/20 · noc {self.learner.episodes+1} · {self.elapsed:.1f} s'
        elif obs.scene in ('loss','win') and self.stable>=2:
            if self.active:
                result=dict(episode=self.learner.episodes+1,result=obs.scene,seconds=round(self.elapsed,1))
                self.learner.finish(obs.scene,self.elapsed)
                self.results.append(result);self.log('result',**result,updates=self.learner.updates)
                self.active=False;self.verified=False;self.phase='result'
                self.note='Wynik zapisany. Model zaktualizowany. Uruchamiam następną próbę.'
                self.deadline=now+2
                return
            # UCN result screens dismiss on a click; no gameplay action is learned here.
            self.game.click_normalized(*obs.buttons.get('continue',(.5,.8)))
            self.phase='menu';self.deadline=now+2
        elif obs.scene=='bonus' and self.stable>=2:
            if self.active:self.abort('Ekran przedmiotu bez pewnego wyniku — próba pominięta')
            self.game.click_normalized(.5,.5);self.deadline=now+2
        elif obs.scene=='unknown':
            self.note='Przejście / nierozpoznany ekran — sprawdzam wynik.'
            if now-self.last_known>20 and now-self.last_recovery>20:
                self.abort('Przekroczony czas rozpoznawania; automatyczny powrót do menu')
                self.game.perform('ESC');self.last_recovery=now;self.deadline=now+2
        if self.active and now-self.started>420:
            self.abort('Limit długości nocy; wynik niepotwierdzony')
            self.game.perform('ESC');self.deadline=now+2

    def act(self, features, now):
        # A short grace period covers HUD occlusion, but never terminal/menu observations.
        if not self.active or now<self.deadline or self.last_scene in ('menu','instructions','win','loss','bonus'):
            return
        if now-self.last_known>3:return
        action,mouse,transition=self.learner.act(features)
        if self.game.perform(action,mouse):
            self.action=action;self.learner.record(transition)


class Trainer:
    def __init__(self):
        from windows_game import Game
        self.lock=threading.RLock();self.closed=threading.Event();self.paused=False
        self.commands=deque();self.events=deque(maxlen=30)
        self.brain=Brain()
        self.learner=Learner(self.brain.meta['feature_count'],self.brain.meta['signature'],ROOT/'models/auto50_policy.npz')
        self.game=Game(self.command)
        self.loop=EpisodeLoop(self.game,self.learner,self.brain,self.log)
        journal=ROOT/'logs/auto50.jsonl'
        if journal.exists():
            with journal.open(encoding='utf-8') as f:
                for line in deque(f,maxlen=500):
                    try:
                        item=json.loads(line)
                        if item.get('event')=='result':self.loop.results.append(item)
                    except ValueError:continue
        self.reader=None;self.latest=None;self.observed=None;self.ocr_id=0;self.used_id=0
        self.jpeg=b'';self.frame_time=0.;self.ticks=0;self.fps=0.
        self.focused=False;self.error='';self.ocr_text=[]
        self.anatomy=self.brain.anatomy();self.view_activity=[]
        self.worker=threading.Thread(target=self.run,daemon=True,name='autotrainer')
        self.ocr_worker=threading.Thread(target=self.read_loop,daemon=True,name='screen-reader')

    def log(self, kind, **data):
        item=dict(time=time.strftime('%H:%M:%S'),event=kind,**data)
        self.events.appendleft(item)
        with (ROOT/'logs/auto50.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(item,ensure_ascii=False)+'\n')
        logging.info('%s',item)

    def command(self, name):
        if name in ('stop','pause','shutdown'):
            self.game.emergency.set();self.game.release()
        if name=='shutdown':self.closed.set()
        if name in ('stop','pause','start','save','shutdown'):
            with self.lock:self.commands.append(name)

    def read_loop(self):
        try:
            self.reader=ScreenReader()
            while not self.closed.is_set():
                with self.lock:current=self.latest
                if current is None or self.paused:
                    self.closed.wait(.2);continue
                frame,stamp=current
                obs=self.reader.read(frame)
                with self.lock:
                    self.observed=(obs,stamp);self.ocr_id+=1
                self.closed.wait(.12)
        except Exception as exc:
            logging.exception('OCR failed')
            self.error='OCR: '+str(exc);self.command('stop')

    def run(self):
        try:
            self.game.launch()
            if not self.game.wait_for_window(60):raise RuntimeError('Nie znaleziono okna UCN')
            self.game.activate(10)
            self.ocr_worker.start()
            last_save=time.monotonic();last_action=0.;lost_at=None;last_launch=last_save
            while not self.closed.is_set():
                begin=time.monotonic()
                with self.lock:
                    while self.commands:
                        cmd=self.commands.popleft()
                        if cmd in ('pause','stop','shutdown'):
                            self.paused=True;self.loop.abort('Zatrzymano. F7 w grze wznawia trening.')
                            self.learner.save()
                            if cmd=='shutdown':self.closed.set()
                        elif cmd=='start':
                            self.paused=False;self.error='';self.game.emergency.clear()
                            self.loop.last_known=begin;self.loop.deadline=begin+.3
                            self.game.activate(5)
                        elif cmd=='save':self.learner.save()
                # F7 resumes. Other legacy hotkeys do not mark artificial results.
                self.focused=self.game.focused()
                if self.game.emergency.is_set():self.paused=True
                if self.paused or not self.focused:
                    if lost_at is None:lost_at=begin
                    if self.loop.active and begin-lost_at>1:
                        self.loop.abort('Utrata aktywnego okna; próba pominięta')
                    with self.lock:self.latest=None;self.observed=None;self.used_id=self.ocr_id
                    if not self.paused and not self.game.find() and begin-last_launch>30:
                        self.game.launch();last_launch=begin
                        if self.game.wait_for_window(20):self.game.activate(5)
                    self.closed.wait(.1);continue
                lost_at=None
                frame=self.game.capture()
                if frame is None:continue
                with self.lock:self.latest=(frame,begin)
                x=self.brain.step(frame)
                with self.lock:
                    observed=self.observed;oid=self.ocr_id
                if observed and oid!=self.used_id and begin-observed[1]<4:
                    obs,stamp=observed
                    self.ocr_text=obs.texts;self.loop.observe(obs,begin);self.used_id=oid
                # Do not let a stale gameplay OCR result dismiss a fresh death screen.
                # Black transitions are not rewards or inferred deaths: wait for OCR.
                brightness=np.asarray(frame.convert('L').resize((96,54)))
                near_black=float(np.mean(brightness>28))<.10
                if begin-last_action>=.22 and not near_black:
                    self.loop.act(x,begin);last_action=begin
                small=frame.copy();small.thumbnail((960,540));buf=io.BytesIO();small.save(buf,'JPEG',quality=72)
                with self.lock:
                    self.jpeg=buf.getvalue();self.frame_time=time.time();self.ticks+=1
                    self.view_activity=self.brain.activity()
                    self.fps=1/max(.001,time.monotonic()-begin)
                if begin-last_save>30:self.learner.save();last_save=begin
                self.closed.wait(max(0,.16-(time.monotonic()-begin)))
        except Exception as exc:
            logging.exception('Training failed');self.error=str(exc);self.paused=True
        finally:
            self.game.release();self.learner.save()

    def state(self):
        with self.lock:
            return dict(application='fly-ucn-autotrainer',paused=self.paused,focused=self.focused,
                phase=self.loop.phase,note=self.error or self.loop.note,action=self.loop.action,
                seconds=self.loop.elapsed,episodes=self.learner.episodes,wins=self.learner.wins,
                best=self.learner.best,updates=self.learner.updates,steps=self.learner.steps,
                loss=self.learner.loss,entropy=self.learner.entropy,fps=round(min(self.fps,6.25),1),
                activity=self.view_activity,ticks=self.ticks,frame_time=self.frame_time,
                history=list(self.events),results=list(self.loop.results),ocr=self.ocr_text,
                verified50=self.loop.verified,ocr_ready=self.reader is not None)

    def close(self):
        self.closed.set();self.game.close()
        self.worker.join(timeout=10)
        if not self.worker.is_alive():self.learner.save()


def local_addresses():
    ips={'127.0.0.1','localhost'}
    for info in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
        ip=info[4][0]
        if not ip.startswith(('169.254.','127.')):ips.add(ip)
    return ips

def make_handler(trainer, token, viewer, addresses, port):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup();self.connection.settimeout(5)
        def log_message(self,*args):pass
        def send(self,body,kind='application/json',status=200,headers=None):
            self.send_response(status);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            for k,v in (headers or {}).items():self.send_header(k,v)
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def local(self):return self.client_address[0]=='127.0.0.1'
        def valid_host(self):
            return self.headers.get('Host','') in {f'{a}:{port}' for a in addresses}
        def authorized(self):
            if not self.valid_host():return False
            if self.local():return True
            cookie=SimpleCookie()
            try:cookie.load(self.headers.get('Cookie',''))
            except Exception:return False
            return 'fly_view' in cookie and secrets.compare_digest(cookie['fly_view'].value,viewer)
        def do_GET(self):
            parsed=urlsplit(self.path)
            supplied=parse_qs(parsed.query).get('view',[''])[0]
            if self.valid_host() and supplied and secrets.compare_digest(supplied,viewer):
                self.send(b'',status=303,headers={'Location':'/','Set-Cookie':f'fly_view={viewer}; HttpOnly; SameSite=Strict; Path=/'})
                return
            if not self.authorized():self.send(b'Use the phone link from the PC dashboard.',status=403);return
            path=parsed.path
            if path=='/api/state':
                data=trainer.state()
                if self.local():data['phone_urls']=[f'http://{a}:{port}/?view={viewer}' for a in sorted(addresses) if a not in ('127.0.0.1','localhost')]
                self.send(json.dumps(data,ensure_ascii=False).encode());return
            if path=='/api/anatomy':self.send(json.dumps(trainer.anatomy).encode());return
            if path=='/api/frame':self.send(trainer.jpeg,'image/jpeg');return
            files={'/':'auto.html','/auto.js':'auto.js','/auto.css':'auto.css'}
            if path not in files:self.send(b'Not found',status=404);return
            file=ROOT/'ui'/files[path]
            content=file.read_text(encoding='utf-8').replace('__TOKEN__',token if self.local() else '').replace('__CONTROL__','true' if self.local() else 'false')
            kind='text/html; charset=utf-8' if path=='/' else 'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8'
            self.send(content.encode(),kind)
        def do_POST(self):
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<1024:raise ValueError()
                body=self.rfile.read(length)
            except (ValueError,TimeoutError,OSError):
                self.send(b'Invalid request',status=400);return
            origin=self.headers.get('Origin')
            if (not self.local() or not self.valid_host() or self.path!='/api/command'
                or not secrets.compare_digest(self.headers.get('X-Fly-Token',''),token)
                or (origin and origin!=f'http://{self.headers.get("Host")}')):
                self.send(b'Forbidden',status=403);return
            try:
                cmd=json.loads(body).get('command')
                if cmd not in ('start','stop','pause','save','shutdown'):raise ValueError()
                trainer.command(cmd);self.send(b'{"ok":true}')
            except (ValueError,TypeError,AttributeError):self.send(b'Invalid command',status=400)
    return Handler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    (ROOT/'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT/'logs/autotrainer.log',level=logging.INFO,format='%(asctime)s %(message)s')
    # Acquire the port before allocating a second brain or controlling the game.
    try:server=ExclusiveHTTPServer(('0.0.0.0',args.port),BaseHTTPRequestHandler)
    except OSError:
        print(f'Port {args.port} jest zajęty. Panel: http://127.0.0.1:{args.port}',flush=True)
        return
    trainer=Trainer()
    # Map existing F7 handler to resume without affecting manual mode.
    original=trainer.game.command
    trainer.game.command=lambda c:original('start' if c=='play' else c)
    viewer_path=ROOT/'data/cache/phone_token.txt'
    viewer=viewer_path.read_text().strip() if viewer_path.exists() else secrets.token_urlsafe(24)
    viewer_path.write_text(viewer)
    addresses=local_addresses();token=secrets.token_urlsafe(32)
    server.RequestHandlerClass=make_handler(trainer,token,viewer,addresses,args.port)
    info=dict(local=f'http://127.0.0.1:{args.port}',phone=[f'http://{a}:{args.port}/?view={viewer}' for a in sorted(addresses) if a not in ('127.0.0.1','localhost')])
    (ROOT/'PHONE_LINK.txt').write_text('\n'.join(info['phone']),encoding='utf-8')
    print(json.dumps(info),flush=True)
    if not args.no_browser:webbrowser.open(info['local'])
    trainer.worker.start()
    server.timeout=.5
    try:
        while not trainer.closed.is_set():server.handle_request()
    except KeyboardInterrupt:pass
    finally:trainer.close();server.server_close()

if __name__=='__main__':main()
