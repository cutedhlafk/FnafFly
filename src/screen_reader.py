"""Local OCR of UCN states. Unknown images never count as survival or a win."""
from dataclasses import dataclass, field
import re
import numpy as np
from PIL import ImageOps

def clean(s):
    return re.sub(r'[^A-Z0-9]', '', s.upper())

@dataclass
class Observation:
    scene: str = 'unknown'
    seconds: float | None = None
    buttons: dict = field(default_factory=dict)
    verified50: bool = False
    texts: list = field(default_factory=list)

def classify(words):
    """Words: (text, normalized center x, center y, confidence). Pure and testable."""
    obs=Observation(texts=[w[0] for w in words])
    normalized=[(clean(t),x,y,p) for t,x,y,p in words if p>=.55]
    menu=[w for w in normalized if 'SETALL' in w[0] and w[1]>.75]
    # UCN draws the label and numeric value on separate lines inside each button.
    for t,x,y,p in menu:
        if t=='SETALL':
            below=[w for w in normalized if w[0]=='20' and abs(w[1]-x)<.06 and 0<w[2]-y<.045]
            if below:obs.buttons['twenty']=(x,(y+below[0][2])/2)
    for t,x,y,p in normalized:
        if t=='GO' and x>.7 and y>.65:obs.buttons['go']=(x,y)
        if t=='SETALL20' and x>.75:obs.buttons['twenty']=(x,y)
        if t in ('CLICKTOCONTINUE','PRESSTOCONTINUE','CONTINUE','RETRY'):obs.buttons['continue']=(x,y)
    joined=' '.join(w[0] for w in normalized)
    if len(menu)>=2:
        obs.scene='menu'
        levels=[t for t,x,y,p in normalized if x<.86 and y<.87 and t=='20']
        # 10,000 is the total configured point value, not the historical high score.
        point_value=any('POINTVALUE10000' in t for t,x,y,p in normalized)
        for t,x,y,p in normalized:
            if t=='POINTVALUE':
                point_value |= any(v=='10000' and abs(vx-x)<.08 and 0<vy-y<.08 for v,vx,vy,vp in normalized)
        obs.verified50=len(levels)>=50 or point_value
    elif 'YOUDIDIT' in joined or any(t=='6AM' and .2<x<.8 and .15<y<.8 for t,x,y,p in normalized):
        obs.scene='win'
    elif 'GAMEOVER' in joined:
        obs.scene='loss'
    elif 'TAKETHISITEMFOR' in joined and 'YOURTROUBLES' in joined:
        obs.scene='bonus'
    elif 'go' in obs.buttons and any(t in joined for t in ('CONTROLS','CLOSEDOOR','FLASHLIGHT','POWERGENERATOR')):
        obs.scene='instructions'
    else:
        for text,x,y,p in words:
            if p<.55 or x<.80 or y>.20:continue
            m=re.search(r'(?<!\d)(\d{1,2})\s*[:;]\s*(\d{2})(?:[.,](\d))?',text)
            if m and int(m[2])<60:
                obs.seconds=int(m[1])*60+int(m[2])+int(m[3] or '0')/10
        if obs.seconds is not None or any(re.fullmatch(r'(12|[1-5])AM',t) and x>.8 and y<.2 for t,x,y,p in normalized):
            obs.scene='playing'
    return obs

class ScreenReader:
    def __init__(self):
        from rapidocr import RapidOCR
        self.ocr=RapidOCR(params={'EngineConfig.onnxruntime.intra_op_num_threads':2,
            'EngineConfig.onnxruntime.inter_op_num_threads':1,'Global.use_cls':False,
            'Global.log_level':'error'})

    def read(self, frame):
        # 1280px retains menu labels and timer without full-HD OCR cost.
        img=frame.convert('RGB');img.thumbnail((1280,720))
        out=self.ocr(np.asarray(img)[:,:,::-1].copy())
        words=[]
        if out.txts is not None:
            for t,b,p in zip(out.txts,out.boxes,out.scores):
                center=np.asarray(b).mean(axis=0)
                words.append((t,float(center[0]/img.width),float(center[1]/img.height),float(p)))
        obs=classify(words)
        if obs.scene=='unknown':
            # Death text fades in dark red; contrast normalization makes it legible
            # without treating a black frame/jumpscare as proof of a loss.
            crop=img.crop((int(img.width*.25),int(img.height*.25),int(img.width*.75),int(img.height*.8)))
            enhanced=ImageOps.autocontrast(crop.convert('L')).convert('RGB')
            terminal=self.ocr(np.asarray(enhanced)[:,:,::-1].copy())
            if terminal.txts is not None:
                for t,b,p in zip(terminal.txts,terminal.boxes,terminal.scores):
                    if float(p)>=.7 and ('GAMEOVER' in clean(t) or 'YOUDIDIT' in clean(t)):
                        obs.scene='loss' if 'GAMEOVER' in clean(t) else 'win'
                        obs.texts.append(t)
                        break
        # Large stylized GO text is sometimes missed. Its green button is distinctive;
        # restrict this fallback to a recognized menu, never arbitrary gameplay.
        if obs.scene=='menu' and 'go' not in obs.buttons:
            arr=np.asarray(img,dtype=np.float32)
            green=(arr[:,:,1]>65)&(arr[:,:,1]>arr[:,:,0]*1.12)&(arr[:,:,1]>arr[:,:,2]*1.3)
            green[:int(img.height*.80),:]=False
            green[:,:int(img.width*.85)]=False
            yy,xx=np.where(green)
            if len(xx)>img.width*img.height*.004:
                obs.buttons['go']=(float(np.median(xx)/img.width),float(np.median(yy)/img.height))
        return obs
