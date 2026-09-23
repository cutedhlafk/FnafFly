# Sterowanie Vent i Duct

Model ma 43 akcje. Nowe obejmują wybór VENT SYSTEM i DUCT SYSTEM,
trzy pułapki wentylacyjne, dwa zamknięcia kanałów i trzy pozycje wabika.
Kliknięcia są dostępne dopiero po rozpoznaniu właściwej zakładki na dwóch
kolejnych obrazach. Po zmianie zakładki stare rozpoznanie jest unieważniane.

Sekwencja początkowa zamyka przedni wentyl klawiszem W, otwiera monitor,
wybiera lewą pułapkę, zamyka prawy kanał, ustawia lewy wabik i wraca
do kamer oraz biura. Drugie W otwiera przedni wentyl. Limit sekwencji
wynosi 15 sekund; brak potwierdzonego interfejsu przerywa przygotowanie.
To przygotowanie obrony, nie rozpoznawanie położenia przeciwników.

Współrzędne są znormalizowane do układu 16:9. OPEN DUCT otwiera klikniętą
stronę, zamykając przeciwną. Dane referencyjne:
https://www.magicgameworld.com/ultimate-custom-night-ventilation-and-duct-system/
oraz https://steamcommunity.com/sharedfiles/filedetails/?id=1424719028 .
Punkty map wymagają dalszego sprawdzenia w rzeczywistej rozgrywce.

API udostępnia monitor_system, vent_duct_setup i mouse_actions_sent.
Liczniki potwierdzają wysłanie wejścia, nie skuteczne zatrzymanie animatronika.
Migracja modelu zachowuje stare wagi i tworzy kopię wcześniejszego checkpointu.
Testy obejmują blokady złych zakładek, przejścia, limit przygotowania,
semantykę przycisków oraz migrację 33 do 43 akcji.
