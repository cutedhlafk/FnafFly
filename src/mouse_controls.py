"""UCN mouse affordances, scaled from its 16:9 client area.

Bottom arrows react to entering a region, not to a key or a held click.
Only expose semantic actions while their controls are visible in fresh frames.
"""
import numpy as np

MOUSE_ACTIONS = ['MASK_ON', 'MASK_OFF', 'MONITOR_OPEN', 'MONITOR_CLOSE',
                 'CAM_SYSTEM', *[f'CAM_{n:02d}' for n in range(1, 9)]]
BASE_MOUSE_ACTIONS = MOUSE_ACTIONS.copy()
SYSTEM_POINTS = {'CAM_SYSTEM':(.764,.146), 'VENT_SYSTEM':(.764,.245), 'DUCT_SYSTEM':(.764,.344)}
# Normalized reference layout: see docs/vent_duct.md. Duct commands name the
# CLOSED side: selecting OPEN DUCT on the opposite side closes this side.
VENT_POINTS = {'VENT_SNARE_LEFT':(.281,.588), 'VENT_SNARE_CENTER':(.334,.488),
               'VENT_SNARE_RIGHT':(.381,.588)}
DUCT_POINTS = {'DUCT_SEAL_LEFT':(.518,.769), 'DUCT_SEAL_RIGHT':(.17,.769),
               'DUCT_LURE_LEFT':(.193,.427), 'DUCT_LURE_CENTER':(.335,.427),
               'DUCT_LURE_RIGHT':(.475,.427)}
MOUSE_ACTIONS += ['VENT_SYSTEM','DUCT_SYSTEM',*VENT_POINTS,*DUCT_POINTS]
CAMERA_POINTS = dict(zip([f'CAM_{n:02d}' for n in range(1, 9)],
    [(1133/1920,904/1080),(1378/1920,904/1080),(1068/1920,824/1080),
     (1488/1920,764/1080),(1118/1920,669/1080),(1418/1920,589/1080),
     (1278/1920,504/1080),(988/1920,494/1080)]))

def frame_mode(frame):
    a = np.asarray(frame.convert('RGB').resize((960,540)),dtype=np.float32)
    red = a[498:518,222:460]
    white = a[498:518,522:760]
    red_bar = np.mean((red[:,:,0]>45)&(red[:,:,0]>red[:,:,1]*1.25)&(red[:,:,0]>red[:,:,2]*1.2)) > .08
    white_bar = np.mean((white.min(2)>45)&((white.max(2)-white.min(2))<25)) > .12
    return ('office' if white_bar else 'mask') if red_bar else ('monitor' if white_bar else 'unknown')

def monitor_system(frame):
    """The selected tab is teal; all three labels are visible in every tab."""
    a=np.asarray(frame.convert('RGB').resize((960,540)),dtype=np.float32)
    selected=[]
    for name,(_,y) in SYSTEM_POINTS.items():
        patch=a[int((y-.018)*540):int((y+.018)*540),int(.72*960):int(.80*960)]
        teal=(patch[:,:,1]>70)&(patch[:,:,1]>patch[:,:,0]*1.3)&(patch[:,:,1]>patch[:,:,2]*1.08)
        if np.mean(teal)>.50:selected.append(name)
    return selected[0] if len(selected)==1 else 'unknown'

class MouseControls:
    def __init__(self):
        self.mode = 'unknown'
        self.candidate = 'unknown'
        self.stable = 0
        self.camera_map_at = -100.
        self.ready_at = 0.
        self.counts = {}
        self.observed_at = -100.
        self.system = 'unknown'
        self.system_candidate = 'unknown'
        self.system_stable = 0
        self.setup_index = None
        self.setup_started = 0.
        self.setup_note = 'Oczekiwanie na początek nocy'

    def reset(self):
        self.mode = self.candidate = 'unknown'
        self.stable = 0
        self.camera_map_at = -100.
        self.ready_at = 0.
        self.observed_at = -100.
        self.system = self.system_candidate = 'unknown'
        self.system_stable = 0
        self.setup_index = None
        self.setup_note = 'Oczekiwanie na początek nocy'

    def observe(self, frame, now):
        if now < self.ready_at:return
        self.observed_at = now
        mode = frame_mode(frame)
        self.stable = self.stable+1 if mode==self.candidate else 1
        self.candidate = mode
        self.mode = mode if self.stable>=2 else 'unknown'
        system=monitor_system(frame) if self.mode=='monitor' else 'unknown'
        self.system_stable=self.system_stable+1 if system==self.system_candidate else 1
        self.system_candidate=system
        self.system=system if self.system_stable>=2 else 'unknown'
        if self.system!='CAM_SYSTEM':self.camera_map_at=-100.

    def read(self, obs, stamp):
        if stamp < self.ready_at:return
        import re
        text = ''.join(re.sub('[^A-Z0-9]','',t.upper()) for t in obs.texts)
        if self.system=='CAM_SYSTEM' and sum(f'CAM{n:02d}' in text for n in range(1,9))>=3:
            self.camera_map_at = stamp

    def allowed(self, actions, now):
        # Unstructured clicks remain available in the monitor for game-specific
        # controls. Bottom arrows are reached only by deliberate semantic actions.
        valid = set(actions)-set(MOUSE_ACTIONS)-{'S','CLICK','HOLD_CLICK','MOVE'}
        if now < self.ready_at:return [a=='WAIT' for a in actions]
        if now-self.observed_at>1.:return [a in valid for a in actions]
        if self.mode=='office':valid.update(['MASK_ON','MONITOR_OPEN','MOVE','CLICK'])
        elif self.mode=='mask':valid={'WAIT','MASK_OFF'}
        elif self.mode=='monitor':
            valid.update(['MONITOR_CLOSE',*SYSTEM_POINTS,'CLICK','HOLD_CLICK','MOVE'])
            valid.discard(self.system)
            if self.system=='CAM_SYSTEM' and now-self.camera_map_at<2.:valid.update(CAMERA_POINTS)
            elif self.system=='VENT_SYSTEM':valid.update(VENT_POINTS)
            elif self.system=='DUCT_SYSTEM':valid.update(DUCT_POINTS)
        return [a in valid for a in actions]

    def performed(self, action, now):
        if action in MOUSE_ACTIONS:
            self.counts[action]=self.counts.get(action,0)+1
        if action in MOUSE_ACTIONS[:4] or action in SYSTEM_POINTS:
            self.ready_at=now+.65
            self.mode=self.candidate='unknown'
            self.stable=0
            self.camera_map_at=-100.
            self.system=self.system_candidate='unknown'
            self.system_stable=0
        elif action in ('CLICK','HOLD_CLICK'):
            self.camera_map_at=-100.
            self.system=self.system_candidate='unknown'
            self.system_stable=0
        if self.setup_index is not None and action==self.SETUP[self.setup_index]:
            self.setup_index+=1
            if self.setup_index==len(self.SETUP):
                self.setup_index=None
                self.setup_note='Wysłano ustawienie pułapki i wabika; dalsze decyzje podejmuje model'

    SETUP = ('W','MONITOR_OPEN','VENT_SYSTEM','VENT_SNARE_LEFT','DUCT_SYSTEM',
             'DUCT_SEAL_RIGHT','DUCT_LURE_LEFT','CAM_SYSTEM','MONITOR_CLOSE','W')

    def begin_night(self, now):
        self.setup_index=0
        self.setup_started=now
        self.setup_note='Przygotowanie pułapki i wabika'

    def setup_action(self, actions, now):
        """Bounded initial defense; fresh interface recognition gates each step."""
        if self.setup_index is None:return None
        if now-self.setup_started>15:
            self.setup_index=None
            self.setup_note='Przerwano przygotowanie: nie potwierdzono interfejsu w 15 s'
            return None
        wanted=self.SETUP[self.setup_index]
        # An interrupted transition may already have reached its destination.
        if wanted=='MONITOR_OPEN' and self.mode=='monitor':
            self.setup_index+=1
            wanted=self.SETUP[self.setup_index]
        if wanted in SYSTEM_POINTS and self.system==wanted:
            self.setup_index+=1
            wanted=self.SETUP[self.setup_index]
        allowed=self.allowed(actions,now)
        return wanted if allowed[actions.index(wanted)] else 'WAIT'

    def physical(self, action, mouse):
        if action in ('MASK_ON','MASK_OFF'):return 'HOVER_ARROW',(.355,.941)
        if action in ('MONITOR_OPEN','MONITOR_CLOSE'):return 'HOVER_ARROW',(.667,.941)
        if action in SYSTEM_POINTS:return 'CLICK',SYSTEM_POINTS[action]
        if action in VENT_POINTS:return 'CLICK',VENT_POINTS[action]
        if action in DUCT_POINTS:return 'CLICK',DUCT_POINTS[action]
        if action in CAMERA_POINTS:return 'CLICK',CAMERA_POINTS[action]
        if action in ('MOVE','CLICK','HOLD_CLICK'):
            return action,(mouse[0],min(mouse[1],.90))
        return action,mouse
