"""On-policy actor/critic readout of FlyWire activity; no demonstrations required.

The connectome is a fixed reservoir. Only the motor readout and value baseline learn.
Separate categorical mouse heads allow clicks throughout the entire game window.
"""
from pathlib import Path
import json
import os
import numpy as np

ACTIONS = ['WAIT','A','D','W','F','S','SPACE','Z','X','C','1','2','3','4','5','6','ENTER','CLICK','MOVE','HOLD_CLICK']
SIZES = [len(ACTIONS), 40, 24]

def softmax(x):
    v = np.exp(x - x.max())
    return v / v.sum()

class Learner:
    def __init__(self, features, signature, path, seed=42):
        self.path = Path(path)
        self.signature = signature
        self.rng = np.random.default_rng(seed)
        self.heads = [self.rng.normal(0, .005, (n,features)).astype('float32') for n in SIZES]
        self.heads[0][0,-1] = 1.5
        self.value = np.zeros(features, np.float32)
        self.updates = self.steps = self.episodes = self.wins = 0
        self.best = self.loss = self.entropy = 0.
        self.pending = []
        if self.path.exists():
            with np.load(self.path, allow_pickle=False) as d:
                if str(d['signature']) != signature or d['actions'].tolist() != ACTIONS or int(d['version']) != 1:
                    raise ValueError('Niezgodny checkpoint autotreningu. Zachowaj go i użyj osobnego pliku modelu.')
                for i, head in enumerate(self.heads):
                    if d[f'h{i}'].shape != head.shape:
                        raise ValueError('Niezgodny rozmiar modelu')
                    head[:] = d[f'h{i}']
                self.value[:] = d['value']
                for k in ['updates','steps','episodes','wins']:
                    setattr(self,k,int(d[k]))
                self.best = float(d['best'])
                self.rng.bit_generator.state = json.loads(str(d['rng']))

    def act(self, features):
        x = np.clip(np.asarray(features,np.float32),-3,3).copy()
        x[:-1] /= max(1., float(np.linalg.norm(x[:-1])) / 4.)
        ps = [softmax(h@x) for h in self.heads]
        choices = [int(self.rng.choice(len(p),p=p)) for p in ps]
        mouse = ((choices[1]+.5)/SIZES[1], (choices[2]+.5)/SIZES[2])
        return ACTIONS[choices[0]], mouse, (x, choices, ps, float(self.value@x))

    def record(self, transition, reward=0.):
        self.pending.append([transition,float(reward)])
        self.steps += 1

    def progress(self, seconds):
        # Assign measured game-clock progress to intervening actions, not menu wall time.
        if self.pending and seconds > 0:
            self.pending[-1][1] += min(seconds, 5.) * .08

    def finish(self, result, survived):
        if result not in ('loss','win'):
            self.pending.clear()  # Aborted/uncertain episodes do not teach false results.
            return
        self.episodes += 1
        self.wins += int(result=='win')
        self.best = max(self.best,float(survived))
        if self.pending:
            self.pending[-1][1] += 8. if result=='win' else -1.
            returns=[]; g=0.
            for _,r in reversed(self.pending):
                g=r+.995*g
                returns.append(g)
            returns.reverse()
            grads=[np.zeros_like(h) for h in self.heads]
            vg=np.zeros_like(self.value); errors=[]; ent=[]
            for ((x, choices, ps, baseline), _),target in zip(self.pending,returns):
                advantage=float(np.clip(target-baseline,-5,5))
                vg += advantage*x
                errors.append(advantage**2)
                for i,(p,c) in enumerate(zip(ps,choices)):
                    if i and choices[0] < 17:
                        continue
                    score=-p.copy();score[c]+=1
                    logp=np.log(np.maximum(p,1e-8));entropy=-float(p@logp)
                    # Entropy gradient preserves exploration in all motor heads.
                    grad=advantage*score-.01*p*(logp+entropy)
                    grads[i] += np.outer(grad,x)
                    ent.append(entropy)
            n=len(self.pending)
            for head,grad in zip(self.heads,grads):
                head += .015*np.clip(grad/n,-.5,.5)
                np.clip(head,-10,10,out=head)
            self.value += .025*np.clip(vg/n,-.5,.5)
            self.loss=float(np.mean(errors));self.entropy=float(np.mean(ent))
            self.updates+=1
        self.pending.clear()
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        with temp.open('wb') as f:
            np.savez_compressed(f,version=1,signature=self.signature,actions=np.array(ACTIONS),
                **{f'h{i}':h for i,h in enumerate(self.heads)},value=self.value,
                updates=self.updates,steps=self.steps,episodes=self.episodes,wins=self.wins,
                best=self.best,rng=json.dumps(self.rng.bit_generator.state))
        os.replace(temp,self.path)
