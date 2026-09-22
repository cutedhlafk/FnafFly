"""Bounded on-policy learning from confirmed game time, with checkpoint continuity."""
from pathlib import Path
import json
import os
import shutil
import time
import numpy as np

ACTIONS = ['WAIT','A','D','W','F','S','SPACE','Z','X','C','1','2','3','4','5','6','ENTER','CLICK','MOVE','HOLD_CLICK']
SIZES = [len(ACTIONS), 40, 24]
ROLLOUT = 16

def softmax(x):
    v = np.exp(x - x.max())
    return v / v.sum()

class Learner:
    def __init__(self, features, signature, path, seed=42, extra_features=0):
        self.path = Path(path)
        self.signature = signature
        self.extra_features = extra_features
        self._migration_suffix = '.v1-backup.npz'
        self.rng = np.random.default_rng(seed)
        self.heads = [self.rng.normal(0,.005,(n,features)).astype('float32') for n in SIZES]
        self.heads[0][0,-1] = 1.5
        self.value = np.zeros(features,np.float32)
        self.updates = self.steps = self.episodes = self.wins = 0
        self.continuous_updates = self.guided_steps = 0
        self.best = self.loss = self.entropy = 0.
        self.last_weight_change = 0.
        self.last_update_delta = 0.
        self.pending = []
        self.credited = 0
        self._needs_migration_backup = False
        if self.path.exists():
            with np.load(self.path,allow_pickle=False) as d:
                version=int(d['version'])
                if str(d['signature'])!=signature or d['actions'].tolist()!=ACTIONS or version not in (1,2,3):
                    raise ValueError('Niezgodny checkpoint autotreningu')
                arrays=[d[f'h{i}'] for i in range(len(SIZES))]
                old_value=d['value'].copy()
                old_extra=int(d['extra_features']) if 'extra_features' in d else 0
                migrate=extra_features>0 and old_extra==0 and version<3
                if migrate:
                    if old_value.shape!=(features-extra_features,):
                        raise ValueError('Niezgodny rozmiar migracji audio')
                    arrays=[np.concatenate([a[:,:-1],np.zeros((len(a),extra_features),np.float32),a[:,-1:]],axis=1) for a in arrays]
                    old_value=np.concatenate([old_value[:-1],np.zeros(extra_features,np.float32),old_value[-1:]])
                    self._migration_suffix='.pre-audio-backup.npz'
                elif old_extra!=extra_features:
                    raise ValueError('Niezgodny zestaw cech audio')
                if any(a.shape!=h.shape or not np.isfinite(a).all() for a,h in zip(arrays,self.heads)):
                    raise ValueError('Uszkodzone wagi checkpointu')
                if old_value.shape!=self.value.shape or not np.isfinite(old_value).all():
                    raise ValueError('Uszkodzony estymator wartości')
                self.heads=[a.copy() for a in arrays]
                self.value=old_value
                for k in ['updates','steps','episodes','wins','continuous_updates','guided_steps']:
                    if k in d:setattr(self,k,int(d[k]))
                for k in ['best','loss','entropy','last_weight_change','last_update_delta']:
                    if k in d:setattr(self,k,float(d[k]))
                self.rng.bit_generator.state=json.loads(str(d['rng']))
                self._needs_migration_backup=version==1 or migrate

    def features(self, features):
        x=np.asarray(features,np.float32).copy()
        if x.shape!=self.value.shape or not np.isfinite(x).all():
            raise ValueError('Nieprawidłowe cechy modelu — pominięto aktualizację')
        np.clip(x,-3,3,out=x)
        visual_end=len(x)-1-self.extra_features
        x[:visual_end]/=max(1.,float(np.linalg.norm(x[:visual_end]))/4.)
        return x

    def reset_memory(self):
        self.pending.clear()
        self.credited=0

    def act(self, features):
        x=self.features(features)
        ps=[softmax(h@x) for h in self.heads]
        choices=[int(self.rng.choice(len(p),p=p)) for p in ps]
        mouse=((choices[1]+.5)/SIZES[1],(choices[2]+.5)/SIZES[2])
        return ACTIONS[choices[0]],mouse,(x,choices,ps,float(self.value@x),True)

    def guided(self, features, action, mouse=(.5,.5)):
        """Known UI cue supplies an expert action, never a fictitious policy sample."""
        x=self.features(features)
        choices=[ACTIONS.index(action),
                 min(SIZES[1]-1,max(0,int(mouse[0]*SIZES[1]))),
                 min(SIZES[2]-1,max(0,int(mouse[1]*SIZES[2])))]
        ps=[softmax(h@x) for h in self.heads]
        return action,mouse,(x,choices,ps,float(self.value@x),False)

    def record(self, transition, reward=0., at=None):
        if len(self.pending)>=2048:
            raise RuntimeError('Za długa trajektoria bez potwierdzonego wyniku')
        self.pending.append([transition,float(reward),time.monotonic() if at is None else float(at)])
        self.steps+=1
        if not transition[4]:
            # Supervision is separate from reinforcement updates and clearly counted.
            x,choices,ps,_,_=transition
            for i,(head,p,c) in enumerate(zip(self.heads,ps,choices)):
                if i and choices[0]<17:continue
                error=-p.copy();error[c]+=1
                head += .002*np.outer(error,x)
            self.guided_steps+=1

    def progress(self, seconds, through=None, next_features=None):
        if not np.isfinite(seconds) or seconds<=0:return
        through=float('inf') if through is None else through
        end=self.credited
        while end<len(self.pending) and self.pending[end][2]<through:end+=1
        if end==self.credited:return
        # Share reward across actions observed before this OCR frame. Actions made
        # while OCR was running must not receive credit for earlier game time.
        reward=.08*min(float(seconds),10.)/(end-self.credited)
        for entry in self.pending[self.credited:end]:entry[1]+=reward
        self.credited=end
        if end>=ROLLOUT and next_features is not None:
            bootstrap=float(self.value@self.features(next_features))
            self._learn(self.pending[:end],bootstrap)
            del self.pending[:end]
            self.credited=0
            self.continuous_updates+=1

    def _learn(self, entries, bootstrap=0.):
        if not entries:return
        before=[h.copy() for h in self.heads]+[self.value.copy()]
        # Reuse confirmed samples for three bounded optimization passes. Old
        # behavior probabilities stay fixed so clipping limits stale reinforcement.
        for _ in range(3):self._learn_epoch(entries,bootstrap)
        self.last_update_delta=float(np.sqrt(sum(np.sum((a-b)**2) for a,b in zip([*self.heads,self.value],before))))
        self.last_weight_change=time.time()
        self.updates+=1

    def _learn_epoch(self, entries, bootstrap=0.):
        if not entries:return
        returns=[];g=float(np.clip(bootstrap,-10,10))
        for _,r,_ in reversed(entries):
            g=r+.995*g;returns.append(g)
        returns.reverse()
        grads=[np.zeros_like(h) for h in self.heads]
        counts=[0]*len(self.heads)
        vg=np.zeros_like(self.value);errors=[];ent=[]
        for ((x,choices,old_ps,baseline,actor),_,_),target in zip(entries,returns):
            advantage=float(np.clip(target-float(self.value@x),-5,5))
            vg+=advantage*x;errors.append(advantage**2)
            if not actor:continue
            current_ps=[softmax(h@x) for h in self.heads]
            relevant=range(len(self.heads)) if choices[0]>=17 else range(1)
            # The sampled action includes both mouse coordinates. Clip the joint
            # likelihood, not three unrelated ratios for one composite action.
            log_ratio=sum(np.log(max(float(current_ps[i][choices[i]]),1e-8))-np.log(max(float(old_ps[i][choices[i]]),1e-8)) for i in relevant)
            ratio=float(np.exp(np.clip(log_ratio,-20,20)))
            clipped=(advantage>0 and ratio>1.2) or (advantage<0 and ratio<.8)
            for i,(head,oldp,c) in enumerate(zip(self.heads,old_ps,choices)):
                if i and choices[0]<17:continue
                p=current_ps[i]
                # Avoid reinforcing stale samples outside the conservative ratio bound.
                score=-p.copy();score[c]+=1
                logp=np.log(np.maximum(p,1e-8));entropy=-float(p@logp)
                pg=0. if clipped else float(np.clip(ratio,.8,1.2))*advantage
                grads[i]+=np.outer(pg*score-.01*p*(logp+entropy),x)
                counts[i]+=1;ent.append(entropy)
        new_heads=[]
        for head,grad,count in zip(self.heads,grads,counts):
            grad/=max(1,count)  # Mouse learning is not diluted by keyboard actions.
            grad/=max(1.,float(np.linalg.norm(grad)))
            new_heads.append(np.clip(head+.015*grad,-10,10))
        value_grad=vg/len(entries)
        value_grad/=max(1.,float(np.linalg.norm(value_grad)))
        new_value=np.clip(self.value+.025*value_grad,-10,10)
        if not all(np.isfinite(h).all() for h in [*new_heads,new_value]):
            raise ValueError('Niefinitywna aktualizacja — zachowano poprzednie wagi')
        self.heads=new_heads;self.value=new_value
        self.loss=float(np.mean(errors));self.entropy=float(np.mean(ent)) if ent else 0.

    def finish(self, result, survived):
        if result not in ('loss','win'):
            self.reset_memory()
            return
        self.episodes+=1;self.wins+=int(result=='win')
        self.best=max(self.best,float(survived))
        if self.pending:
            self.pending[-1][1]+=8. if result=='win' else -1.
            self._learn(self.pending)
        self.reset_memory()
        self.save()

    def save(self):
        if not all(np.isfinite(a).all() for a in [*self.heads,self.value]):
            raise ValueError('Odmowa zapisania uszkodzonych wag')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        with temp.open('wb') as f:
            np.savez_compressed(f,version=3 if self.extra_features else 2,extra_features=self.extra_features,signature=self.signature,actions=np.array(ACTIONS),
                **{f'h{i}':h for i,h in enumerate(self.heads)},value=self.value,
                updates=self.updates,steps=self.steps,episodes=self.episodes,wins=self.wins,
                best=self.best,loss=self.loss,entropy=self.entropy,
                last_weight_change=self.last_weight_change,last_update_delta=self.last_update_delta,
                continuous_updates=self.continuous_updates,guided_steps=self.guided_steps,
                rng=json.dumps(self.rng.bit_generator.state))
            f.flush();os.fsync(f.fileno())
        if self.path.exists():
            if self._needs_migration_backup:
                backup=self.path.with_suffix(self._migration_suffix)
                if not backup.exists():shutil.copy2(self.path,backup)
                self._needs_migration_backup=False
            previous=self.path.with_suffix('.previous.npz')
            previous_tmp=self.path.with_suffix('.previous.tmp')
            shutil.copy2(self.path,previous_tmp);os.replace(previous_tmp,previous)
        os.replace(temp,self.path)
