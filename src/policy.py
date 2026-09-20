"""Imitation learning and explicitly rewarded policy-gradient updates of the readout."""
from collections import deque
from pathlib import Path
import json
import os
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
# Verified against the in-game instruction screen. Mouse movement has a separate head.
ACTIONS = ['WAIT','A','D','W','F','S','SPACE','Z','X','C','1','2','3','4','5','6','ENTER','CLICK','MOVE']
POLICY_VERSION = 1

def softmax(logits):
    e = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)

class Policy:
    def __init__(self, nfeatures, signature):
        self.signature = signature
        self.rng = np.random.default_rng(42)
        self.w = np.zeros((len(ACTIONS), nfeatures), np.float32)
        self.w[0, -1] = 1.5
        self.mouse_w = np.zeros((2, nfeatures), np.float32)
        self.samples = [deque(maxlen=1500) for _ in ACTIONS]
        self.total_samples = 0
        self.updates = 0
        self.loss = 0.
        self.reward_total = 0.
        self.trajectory = deque(maxlen=400)
        self.path = ROOT / 'models' / 'fly_policy.npz'
        self.load()

    def predict(self, x, explore=False):
        p = softmax(self.w @ x)
        action = int(self.rng.choice(len(p), p=p)) if explore else int(np.argmax(p))
        mouse = 1 / (1 + np.exp(-np.clip(self.mouse_w @ x, -12, 12)))
        return action, p, mouse

    def remember(self, x, action, mouse):
        self.samples[action].append((x.copy(), np.asarray(mouse, np.float32).copy()))
        self.total_samples += 1

    def train_batch(self, batch=32):
        available = [i for i,q in enumerate(self.samples) if q]
        if not available:
            return
        # Preserve a useful WAIT prior while avoiding the common all-WAIT collapse.
        classes = self.rng.choice(available, batch)
        pairs = [self.samples[c][int(self.rng.integers(len(self.samples[c])))] for c in classes]
        x = np.array([p[0] for p in pairs]); mouse = np.array([p[1] for p in pairs])
        p = softmax(x @ self.w.T)
        self.loss = float(-np.log(np.maximum(p[np.arange(batch), classes], 1e-8)).mean())
        p[np.arange(batch), classes] -= 1
        grad = p.T @ x / batch + self.w * .0001
        self.w -= .035 * np.clip(grad, -1, 1)
        predicted = 1/(1+np.exp(-np.clip(x @ self.mouse_w.T, -12, 12)))
        self.mouse_w -= .025 * np.clip(((predicted-mouse)*predicted*(1-predicted)).T @ x / batch, -1, 1)
        self.updates += 1

    def record_action(self, x, action, p):
        self.trajectory.append((x.copy(), action, p.copy()))

    def reward(self, value):
        if not self.trajectory:
            return 0
        n = len(self.trajectory)
        for lag, (x, action, p) in enumerate(reversed(self.trajectory)):
            score = -p.copy(); score[action] += 1
            self.w += .003 * value * (.985**lag) * np.outer(score, x) / max(1, n**.5)
        self.reward_total += value
        self.trajectory.clear()
        return n

    @property
    def ready(self):
        # Counting retained non-WAIT examples avoids misleading lifetime counters.
        return sum(map(len, self.samples)) >= 200 and sum(len(q) for q in self.samples[1:]) >= 30 and self.updates >= 50

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        xs, ys, ms = [], [], []
        for label, queue in enumerate(self.samples):
            for x,m in queue:
                xs.append(x); ys.append(label); ms.append(m)
        temp = self.path.with_suffix('.tmp')
        with temp.open('wb') as f:
            np.savez_compressed(f, version=POLICY_VERSION, signature=self.signature,
                actions=np.array(ACTIONS), w=self.w, mouse_w=self.mouse_w,
                x=np.asarray(xs, np.float32).reshape(-1, self.w.shape[1]), y=np.array(ys,np.int16),
                mouse=np.asarray(ms,np.float32).reshape(-1,2), total_samples=self.total_samples,
                updates=self.updates, reward_total=self.reward_total)
        os.replace(temp, self.path)

    def load(self):
        if not self.path.exists():
            return
        with np.load(self.path, allow_pickle=False) as d:
            if str(d['signature']) != self.signature or d['w'].shape != self.w.shape or d['actions'].tolist()!=ACTIONS:
                raise ValueError('Checkpoint incompatible with this connectome/action vocabulary')
            if int(d['version']) != POLICY_VERSION:
                raise ValueError('Unsupported checkpoint version')
            self.w=d['w'].copy(); self.mouse_w=d['mouse_w'].copy()
            self.total_samples=int(d['total_samples']); self.updates=int(d['updates'])
            self.reward_total=float(d['reward_total'])
            for x,y,m in zip(d['x'],d['y'],d['mouse']):
                self.samples[int(y)].append((x.copy(),m.copy()))
