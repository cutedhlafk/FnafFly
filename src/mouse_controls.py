"""UCN mouse affordances, scaled from its 16:9 client area.

Bottom arrows react to entering a region, not to a key or a held click.
Only expose semantic actions while their controls are visible in fresh frames.
"""
import numpy as np

MOUSE_ACTIONS = ['MASK_ON', 'MASK_OFF', 'MONITOR_OPEN', 'MONITOR_CLOSE',
                 'CAM_SYSTEM', *[f'CAM_{n:02d}' for n in range(1, 9)]]
CAMERA_POINTS = dict(zip([f'CAM_{n:02d}' for n in range(1, 9)],
    [(1133/1920,904/1080),(1378/1920,904/1080),(1068/1920,824/1080),
     (1488/1920,764/1080),(1118/1920,669/1080),(1418/1920,589/1080),
     (1278/1920,504/1080),(988/1920,494/1080)]))

class MouseControls:
    def __init__(self):
        self.mode = 'unknown'
        self.candidate = 'unknown'
        self.stable = 0
        self.camera_map_at = -100.
        self.ready_at = 0.
        self.counts = {}

    def reset(self):
        self.mode = self.candidate = 'unknown'
        self.stable = 0
        self.camera_map_at = -100.
        self.ready_at = 0.

    def observe(self, frame, now):
        if now < self.ready_at:return
        a = np.asarray(frame.convert('RGB').resize((960,540)),dtype=np.float32)
        red = a[498:518,222:460]
        white = a[498:518,522:760]
        red_bar = np.mean((red[:,:,0]>45)&(red[:,:,0]>red[:,:,1]*1.25)&(red[:,:,0]>red[:,:,2]*1.2)) > .08
        white_bar = np.mean((white.min(2)>45)&((white.max(2)-white.min(2))<25)) > .12
        mode = ('office' if white_bar else 'mask') if red_bar else ('monitor' if white_bar else 'unknown')
        self.stable = self.stable+1 if mode==self.candidate else 1
        self.candidate = mode
        self.mode = mode if self.stable>=2 else 'unknown'

    def read(self, obs, stamp):
        import re
        text = ''.join(re.sub('[^A-Z0-9]','',t.upper()) for t in obs.texts)
        if 'CAMSYSTEM' in text and sum(f'CAM{n:02d}' in text for n in range(1,9))>=3:
            self.camera_map_at = stamp

    def allowed(self, actions, now):
        # Unstructured clicks remain available in the monitor for game-specific
        # controls. Bottom arrows are reached only by deliberate semantic actions.
        valid = set(actions)-set(MOUSE_ACTIONS)-{'S','CLICK','HOLD_CLICK','MOVE'}
        if now < self.ready_at:return [a=='WAIT' for a in actions]
        if self.mode=='office':valid.update(['MASK_ON','MONITOR_OPEN','MOVE','CLICK'])
        elif self.mode=='mask':valid={'WAIT','MASK_OFF'}
        elif self.mode=='monitor':
            valid.update(['MONITOR_CLOSE','CAM_SYSTEM','CLICK','HOLD_CLICK','MOVE'])
            if now-self.camera_map_at<2.:valid.update(CAMERA_POINTS)
        return [a in valid for a in actions]

    def performed(self, action, now):
        if action in MOUSE_ACTIONS:
            self.counts[action]=self.counts.get(action,0)+1
        if action in MOUSE_ACTIONS[:4]:
            self.ready_at=now+.65
            self.mode=self.candidate='unknown'
            self.stable=0
            self.camera_map_at=-100.

    def physical(self, action, mouse):
        if action in ('MASK_ON','MASK_OFF'):return 'HOVER_ARROW',(.355,.941)
        if action in ('MONITOR_OPEN','MONITOR_CLOSE'):return 'HOVER_ARROW',(.667,.941)
        if action=='CAM_SYSTEM':return 'CLICK',(1466/1920,158/1080)
        if action in CAMERA_POINTS:return 'CLICK',CAMERA_POINTS[action]
        if action in ('MOVE','CLICK','HOLD_CLICK'):
            return action,(mouse[0],min(mouse[1],.90))
        return action,mouse
