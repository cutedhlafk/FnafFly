"""Process-only PCM capture and bounded stereo/spectral features; never records files."""
from pathlib import Path
import json
import struct
import subprocess
import threading
import time
import numpy as np

FEATURE_COUNT=16
ROOT=Path(__file__).resolve().parents[1]

def extract(pcm, previous_rms=0.):
    samples=np.asarray(pcm,np.float32).reshape(-1,2)
    if not len(samples) or not np.isfinite(samples).all():
        return np.zeros(FEATURE_COUNT,np.float32),0.
    samples=np.clip(samples,-1,1)
    rms=np.sqrt(np.mean(samples*samples,axis=0)); peak=np.max(abs(samples),axis=0)
    level=float(rms.mean()); balance=float((rms[1]-rms[0])/(rms.sum()+1e-6))
    mono=samples.mean(axis=1)
    spectrum=abs(np.fft.rfft(mono*np.hanning(len(mono))))**2
    freqs=np.fft.rfftfreq(len(mono),1/48000)
    edges=[0,125,250,500,1000,2000,4000,8000,24001]
    total=float(spectrum.sum())+1e-12
    bands=[float(spectrum[(freqs>=lo)&(freqs<hi)].sum()/total) for lo,hi in zip(edges,edges[1:])]
    zcr=float(np.mean(np.diff(np.signbit(mono)))) if len(mono)>1 else 0.
    features=np.array([*np.clip(rms*8,0,1),*peak,balance,
                       np.clip((level-previous_rms)*12,-1,1),*bands,zcr,1],np.float32)
    return features,level

def combine(vision,audio):
    # Preserve the final bias and every learned visual column during migration.
    return np.concatenate([vision[:-1],audio,vision[-1:]]).astype(np.float32)

class GameAudio:
    def __init__(self, executable):
        self.executable=str(executable)
        self.lock=threading.Lock();self.process=None;self.pid=None;self.thread=None
        self.features=np.zeros(FEATURE_COUNT,np.float32);self.stamp=0.;self.retry=0.
        self.status='Oczekiwanie na grę';self.packets=0;self.error=''

    def update(self,pid):
        now=time.monotonic()
        if pid==self.pid and self.process and self.process.poll() is None:return
        if now<self.retry:return
        self.close();self.pid=pid;self.retry=now+10
        if not pid:return
        helper=ROOT/'audio_capture/bin/publish/AudioCapture.exe'
        if not helper.exists():
            self.status='Brak pomocnika audio — uruchom build_audio.ps1';return
        try:
            process=subprocess.Popen([str(helper),str(pid),self.executable],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
            self.process=process;self.status='Łączenie z dźwiękiem UCN'
            self.thread=threading.Thread(target=self._read,args=(process,),daemon=True);self.thread.start()
        except OSError as e:self.status='Audio niedostępne';self.error=str(e)

    def _read(self,process):
        previous=0.;parts=[];frames=0
        try:
            while True:
                header=process.stdout.read(4)
                if len(header)!=4:break
                size=struct.unpack('<I',header)[0]
                if size<=0 or size>192000 or size%4:raise ValueError('Niepoprawny pakiet PCM')
                raw=process.stdout.read(size)
                if len(raw)!=size:break
                pcm=np.frombuffer(raw,dtype='<i2').astype(np.float32).reshape(-1,2)/32768
                parts.append(pcm);frames+=len(pcm)
                if frames<4800:continue
                features,previous=extract(np.concatenate(parts));parts=[];frames=0
                with self.lock:
                    self.features=features;self.stamp=time.monotonic();self.packets+=1
                    self.status='Dźwięk UCN: aktywny';self.error=''
            process.wait(timeout=2)
            if process.poll() is not None:
                self.error=process.stderr.read(4096).decode('utf-8',errors='replace')
                self.status='Audio zatrzymane; ponowna próba za 10 s'
        except (OSError,ValueError,subprocess.TimeoutExpired) as e:
            self.error=str(e);self.status='Błąd audio'
            if process.poll() is None:process.terminate()

    def sample(self):
        with self.lock:
            fresh=time.monotonic()-self.stamp<.75
            features=self.features.copy() if fresh else np.zeros(FEATURE_COUNT,np.float32)
            status=dict(status=self.status if fresh else 'Brak świeżych próbek UCN',
                active=fresh,pid=self.pid,packets=self.packets,error=self.error,
                left=float(features[0]),right=float(features[1]),balance=float(features[4]),
                bands=features[6:14].tolist(),scope='UCN process tree only; no microphone')
        return features,status

    def close(self):
        p=self.process
        if p:
            try:
                p.stdin.close();p.wait(timeout=2)
            except (OSError,subprocess.TimeoutExpired):
                if p.poll() is None:p.kill();p.wait(timeout=2)
            if self.thread:self.thread.join(timeout=1)
            for stream in (p.stdout,p.stderr):stream.close()
        self.process=None
        with self.lock:self.stamp=0.;self.features.fill(0)
