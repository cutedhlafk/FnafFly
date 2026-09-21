"""Fifty short, sourced defense profiles and grounded UI assistance.

Profiles are knowledge, not evidence that a character was seen. The runtime only
acts on currently supported cues; visual/audio identity detectors are not invented.
"""
from dataclasses import dataclass

SOURCES = [
    'https://steamcommunity.com/sharedfiles/filedetails/?id=1424719028',
    'https://steamcommunity.com/app/871720/allnews/?l=english',
    'https://steamcommunity.com/sharedfiles/filedetails/?id=2310917895',
    'https://steamcommunity.com/sharedfiles/filedetails/?id=2126552739',
    'https://steamcommunity.com/sharedfiles/filedetails/?id=1436014260',
]

# Name | recognition requirement | defense description | semantic action plan.
# Each block cites a different consulted source; descriptions are our own summaries.
ROWS = [
('Freddy Fazbear','lewe drzwi','Zamknij lewe drzwi przy podejściu; ogranicz temperaturę.','close_left,cool'),
('Bonnie','figurka Bonnie','Nie oglądaj Pirate Cove, gdy aktywny jest Bonnie.','avoid_cam05'),
('Chica','odgłos kuchni','Używaj globalnej pozytywki; zmieniaj muzykę dopiero po ucichnięciu kuchni.','music,change_music'),
('Foxy','figurka Foxy','Regularnie sprawdzaj Pirate Cove, kiedy figurka wskazuje Foxy’ego.','cam05'),
('Toy Freddy','minigra','W jego minigrze zamknij drogę, którą nadchodzi Mr. Hugs.','toy_game'),
('Toy Bonnie','postać z prawej','Załóż maskę, gdy wejdzie do biura.','mask'),
('Toy Chica','postać z lewej','Szybko załóż maskę po jej wejściu.','mask'),
('Mangle','radar wentylacji','Przechwyć pułapką; zamknięty przedni wentyl tylko powstrzymuje wejście.','snare,close_front'),
('BB','boczny wentyl','Zamknij boczny wentyl; wtargnięcie blokuje latarkę.','close_side'),
('JJ','boczny wentyl','Zamknij boczny wentyl; wtargnięcie blokuje sterowanie drzwiami.','close_side'),

('Withered Chica','radar wentylacji','Zatrzymaj pułapką lub przednim wentylem, zanim się zaklinuje.','snare,close_front'),
('Withered Bonnie','zniekształcenia biura','Natychmiast załóż maskę, gdy pojawi się w biurze.','mask'),
('Marionette','pozytywka','Pilnuj nakręcenia pozytywki; pomaga też globalna pozytywka.','wind_music,music'),
('Golden Freddy','biuro po monitorze','Szybko podnieś monitor, gdy zobaczysz go w biurze.','monitor_up'),
('Springtrap','twarz we wlocie','Zamknij przedni wentyl po dostrzeżeniu twarzy.','close_front'),
('Phantom Mangle','obraz monitora','Opuść monitor albo przełącz jego system.','monitor_down'),
('Phantom Freddy','materializacja','Przerwij materializację światłem latarki.','flash'),
('Phantom BB','obraz kamery','Zmień kamerę albo szybko opuść monitor.','monitor_down'),
('Nightmare Freddy','Freddles','Rozpraszaj gromadzące się Freddles latarką.','flash'),
('Nightmare Bonnie','prawy korytarz','Kup jego maskotkę w Prize Corner przed atakiem.','buy_bonnie'),

('Nightmare Fredbear','lewe świecące oczy','Zamknij lewe drzwi przed podniesieniem monitora.','close_left'),
('Nightmare','prawe świecące oczy','Zamknij prawe drzwi przed podniesieniem monitora.','close_right'),
('Jack-O-Chica','temperatura','Chłodź biuro; przegrzanie ogranicza skuteczność zamknięcia obu drzwi.','cool,close_both'),
('Nightmare Mangle','prawy korytarz','Kup jej maskotkę w Prize Corner.','buy_mangle'),
('Nightmarionne','położenie sylwetki','Nie zatrzymuj kursora na jego sylwetce.','move_away'),
('Nightmare BB','pozycja ciała','Świeć, gdy siedzi wyprostowany; nie świeć na pochylonego.','conditional_flash'),
('Old Man Consequences','pozycja ryby','Naciśnij C w chwili przecięcia celu przez rybę.','catch_fish'),
('Circus Baby','prawy korytarz','Kup jej maskotkę w Prize Corner.','buy_baby'),
('Ballora','dźwięk stereo','Zamknij drzwi po stronie narastającej muzyki.','audio_door'),
('Funtime Foxy','godzina występu','Oglądaj jego kamerę dokładnie o zapowiedzianej godzinie.','showtime_cam'),

('Ennard','pisk','Przy sygnale ataku zamknij przedni wentyl.','close_front'),
('Trash and the Gang','zakłócenia','Przeczekaj zakłócenia, pilnując pozostałych zagrożeń.','continue'),
('Helpy','postać na biurku','Kliknij go, zanim narobi hałasu.','click_helpy'),
('Happy Frog','radar kanałów','Zatrzymuj wabikiem dźwiękowym; ogrzewanie jej nie odstrasza.','audio_lure'),
('Mr. Hippo','radar kanałów','Użyj wabika dźwiękowego lub ogrzewania.','audio_lure,heat'),
('Pigpatch','radar kanałów','Użyj wabika dźwiękowego lub ogrzewania.','audio_lure,heat'),
('Nedd Bear','radar kanałów','Ogrzewanie odpycha; wabik nie zawsze działa.','heat'),
('Orville Elephant','radar kanałów','Ogrzewanie jest pewniejsze niż zawodny wabik.','heat'),
('Rockstar Freddy','żądanie monet','Zapłać pięć monet albo zakłóć go ogrzewaniem.','pay_five,heat'),
('Rockstar Bonnie','brak gitary','Znajdź gitarę na kamerach i kliknij dwukrotnie.','find_guitar'),

('Rockstar Chica','strona korytarza','Przestaw znak mokrej podłogi na jej stronę.','wet_floor'),
('Rockstar Foxy','papuga','Nie klikaj papugi: pomoc może skończyć się atakiem.','avoid_parrot'),
('Music Man','hałas','Ogranicz hałas urządzeń i innych postaci.','quiet'),
('El Chip','reklama SKIP','Zamknij reklamę klawiszem Enter.','dismiss_ad'),
('Funtime Chica','błyski','Przeczekaj rozpraszające błyski, utrzymując obronę.','continue'),
('Molten Freddy','śmiech','Przed atakiem zamknij przedni wentyl.','close_front'),
('Scrap Baby','ruch postaci','Po wykryciu ruchu użyj kontrolowanego porażenia.','shock'),
('William Afton','huk i miganie','Natychmiast zamknij boczny wentyl.','close_side'),
('Lefty','ciepło i hałas','Ogranicz pobudzenie; uspokajaj globalną pozytywką.','music,quiet,cool'),
('Phone Guy','MUTE CALL','Kliknij aktualnie widoczny przycisk wyciszenia rozmowy.','mute_call'),
]

LIVE = {'dismiss_ad':'OCR', 'mute_call':'OCR', 'cool':'temperatura OCR',
        'music':'profilaktyczny harmonogram zegara'}

def catalog():
    return [dict(id=i+1,name=name,signal=signal,description=description,
                 plan=plan.split(','),source=SOURCES[i//10],
                 automated=[p for p in plan.split(',') if p in LIVE],
                 limitation='Rozpoznawanie konkretnej postaci nie jest zaimplementowane; plan wymaga wskazanego sygnału.')
            for i,(name,signal,description,plan) in enumerate(ROWS)]

@dataclass(frozen=True)
class Advice:
    action: str
    mouse: tuple = (.5,.5)
    reason: str = ''
    key: str = ''

class DefenseAdvisor:
    """Uses fresh OCR facts and the verified game clock, never names in a tooltip."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.alerts={};self.observed_at=-1e9;self.scene='unknown'
        self.last_used={};self.temperature=None;self.seconds=None
        self.last_system=None;self.last_reason='Brak potwierdzonego sygnału'
        self.cooling=False

    def observe(self,obs,captured_at):
        self.alerts=getattr(obs,'alerts',{})
        self.temperature=getattr(obs,'temperature',None)
        self.seconds=obs.seconds
        self.scene=obs.scene;self.observed_at=captured_at

    def suggest(self, now):
        if now-self.observed_at>1.5 or self.scene not in ('playing','interruption'):return None
        def ready(key,interval):return now-self.last_used.get(key,-1e9)>=interval
        if 'mute_call' in self.alerts and ready('mute_call',1.):
            return Advice('CLICK',tuple(self.alerts['mute_call']),'Phone Guy: wyciszenie rozmowy','mute_call')
        if 'skip_ad' in self.alerts and ready('skip_ad',1.):
            return Advice('ENTER',reason='El Chip: zamknięcie reklamy',key='skip_ad')
        if 'reset_vent' in self.alerts and ready('reset_vent',2.):
            return Advice('CLICK',tuple(self.alerts['reset_vent']),'Przywrócenie wentylacji','reset_vent')
        if self.temperature is not None:
            if self.temperature>=85:self.cooling=True
            elif self.temperature<=70:self.cooling=False
        if self.cooling and self.last_system!='4' and ready('cool',3.):
            return Advice('4',reason='Ograniczenie ciepła: Freddy / Jack-O-Chica / Lefty',key='cool')
        # A small prophylactic music window at each 15-second boundary, not a
        # claim to recognize Chica or Lefty. Never rewards using this heuristic.
        if self.seconds is not None and self.seconds%15>=12 and self.last_system!='5' and ready('music',3.):
            return Advice('5',reason='Globalna pozytywka: Chica / Marionette / Lefty',key='music')
        return None

    def performed(self,action,now,advice=None):
        if action in ('1','2','3','4','5','6','X'):self.last_system=action
        if advice:
            self.last_used[advice.key]=now;self.last_reason=advice.reason
