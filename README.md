# Fly / UCN — lokalne laboratorium

## Autotrening 50/20 — aktualizacja 21.09.2026

**Uruchom `START_FLY.bat`.** Otworzy panel na `http://127.0.0.1:8766`, uruchomi UCN,
ustawi wszystkie postacie na 20 i sprawdzi punktację 10 000. Następnie sam rozpoczyna
noce, steruje klawiaturą i myszą, rozpoznaje przegrane/wygrane, aktualizuje model,
zapisuje go i uruchamia następną próbę. Nie wymaga demonstracji ani kalibracji.

- **F12**: zatrzymaj. **F8**: pauza. **F7 w oknie UCN**: wznów.
- Gra musi pozostać aktywna, a pulpit odblokowany. Przełączenie do innego okna
  zatrzymuje wejście i przerywa bieżącą próbę bez uczenia fałszywego wyniku.
- Na telefonie w tej samej sieci Wi-Fi otwórz link z `PHONE_LINK.txt` lub sekcji
  „Oglądaj na telefonie” w panelu PC. Telefon służy do oglądania, nie do sterowania.
  Komputer i UCN pracują także po zamknięciu podglądu.
- `ENABLE_PHONE.bat` jednorazowo dodaje regułę Zapory Windows dla lokalnej podsieci,
  portu 8766 i Pythona tego projektu. Wymaga zgody administratora Windows.
  Regułę można usunąć w administracyjnym PowerShell:
  `Remove-NetFirewallRule -Name FlyUCN-Viewer-8766`.
- Model: `models/auto50_policy.npz`; dziennik prób: `logs/auto50.jsonl`;
  błędy: `logs/autotrainer.log`. Model automatycznie wczytuje się przy starcie.
  Zapis po każdej zakończonej próbie i co 30 s. Przerwane trajektorie są pomijane.
- Dane FlyWire i wcześniejszy `models/fly_policy.npz` pozostają zachowane.
  Starszy tryb demonstracji uruchamia się poleceniem `.venv\Scripts\python.exe src\app.py`.

Nowy tryb używa pełnego grafu 138 639 neuronów jako stałej sieci przetwarzającej obraz.
Uczy warstwę decyzji i estymator wartości metodą actor–critic, z nagrodą za postęp
rozpoznanego zegara gry i końcowy wynik. Klawisze oraz pozycje myszy wybiera model.
Obsługa menu i ponawianie nocy to automatyzacja programu. Uczenie nie wymaga
200 ręcznych przykładów. OCR działa lokalnie, używając RapidOCR i ONNX Runtime.

**To działający autotrening, nie model, który już opanował 50/20.** Krótkie próby
potwierdzają działanie pętli i zmianę wag, nie poprawę skuteczności ani zwycięstwo.
Wejście wzrokowe jest uproszczone, model nie analizuje dźwięku. Wyświetlany czas
przeżycia to ostatni wiarygodnie odczytany zegar; może nie obejmować ostatnich sekund.
Niepewne wyniki nie są uznawane za wygrane. Zmiana rozdzielczości, języka lub wyglądu
gry może wymagać poprawki rozpoznawania. Przy nierozpoznanym ekranie program próbuje
wrócić do menu, bez nagradzania samego czekania.

Testy: `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Starszy tryb ręczny — opis zachowany poniżej

Program łączy obraz **Ultimate Custom Night** z pełną siecią połączeń **FlyWire FAFB v783**. W przeglądarce można obracać model 3D, wybierać neurony i grupy funkcjonalne oraz oglądać ich aktualną aktywność i propozycje akcji.

**To eksperymentalny model uczący się, a nie dostarczony mistrz UCN.** Żadna liczba przykładów sama w sobie nie dowodzi umiejętności wygrywania. W tej wersji decyzje uczą się przez demonstracje oraz ręcznie przyznawane nagrody. Nie ma analizy dźwięku ani automatycznego ustawiania postaci / restartowania nocy.

## Uruchomienie

1. Uruchom `START_FLY.bat`. Otworzy panel na <http://127.0.0.1:8765>.
2. Włącz UCN ze Steam. Ścieżka programu jest ustawiona w `src/windows_game.py` na wskazaną instalację.
3. Wybierz **Obserwuj**, następnie przełącz się do UCN. Aktywność w panelu zacznie odpowiadać obrazowi gry. Najwygodniej oglądać panel na drugim monitorze. Przy jednym ekranie powrót do panelu pokazuje ostatnią klatkę, z jej wiekiem.
4. Wybierz jedną postać na niskim poziomie. Zacznij noc, naciśnij **F6** i pokaż poprawną grę. Nagrywanie obejmuje tylko obsługiwane kontrolki UCN, tylko gdy gra jest aktywna. Nie nagrywamy dowolnego tekstu ani innych aplikacji.
5. **F8** kończy naukę. Model i przykłady zapisują się co 30 sekund oraz przy pauzie / zatrzymaniu. Możesz wykonać dodatkowe dopasowanie przyciskiem „Trenuj zapisane przykłady”.
6. **F7** uruchamia próbę modelu. Próg startowy: minimum 200 zachowanych przykładów, 30 akcji innych niż czekanie i 50 aktualizacji. To blokada startu bez danych, nie ocena skuteczności. Pokaż wiele nocy i sytuacji; kilka losowych naciśnięć nie wystarczy.
7. **F12** natychmiast zatrzymuje sterowanie i zwalnia klawisze. Zmiana aktywnego okna również zatrzymuje autonomiczną próbę.

Zapis gry pozostaje obsługiwany przez samą grę. Program nie modyfikuje jej plików ani pamięci.

## Tryby i skróty

| Tryb / klawisz | Działanie |
| --- | --- |
| Obserwuj | Obraz uruchamia sieć; program nie wysyła akcji |
| F6 | Uczenie nadzorowane z demonstracji gracza |
| F7 | Wybór najbardziej prawdopodobnej akcji wyuczonego modelu |
| Trening z nagrodą | Próbkowanie akcji, również możliwe przed demonstracjami; nagrody nadaje operator |
| F8 | Pauza i zapis |
| F9 / F10 | +1 / −1 za ostatnie decyzje modelu |
| F11 | Oznaczenie zwycięstwa, +5, koniec próby |
| Przegrana w panelu | −5, koniec próby |
| F12 | Stop także poza oknem gry |

Wszystkie pozostałe skróty działają tylko przy aktywnym UCN. Klikanie i przesuwanie myszy przez model trzeba włączyć przełącznikiem w panelu. Uczenie pozycji myszy jest oddzielne od uczenia klawiszy. Akcje są sekwencyjnymi impulsami; nie odwzorowują dowolnych kombinacji ani długich przytrzymań. Latarka ma impuls 140 ms, pozostałe klawisze 65 ms.

Klawisze gry zweryfikowano na ekranie instrukcji: A/D drzwi, W/F wentyle, S monitor, spacja wentylator, Z latarka, X/6 systemy wyłączone, C łowienie, 1–5 urządzenia, Enter reklama. Maska i przyciski kamer wymagają myszy.

## Model i dane

- **138 639 neuronów**, **15 091 983 skierowane pary** i **54 492 922 synapsy** w wybranym zbiorze autorów Shiu et al. Rozmiar tego zbioru różni się od ogólnego katalogu 139 255 neuronów FAFB.
- Połączenia pochodzą z `Connectivity_783.parquet`; identyfikatory wierszy sprawdzane są względem `Completeness_783.csv`. Wagi wejściowe wykorzystują opublikowaną kolumnę `Excitatory x Connectivity`. Znak jest założeniem modelowym opartym na przewidywanym przekaźniku.
- Pełna macierz rzadka pracuje na CPU. Nie jest zastąpiona losową siecią. Dwukrotnie na klatkę wykonywana jest aktualizacja `x += 0.45 * (tanh(W @ x + input) - x)`, z normalizacją sumy bezwzględnych wag wejściowych do 0.92.
- To **uproszczony model aktywności ciągłej**, nie symulator LIF Shiu, wierna emulacja mózgu ani pomiar neuronalny. Czas symulacji nie jest skalibrowany do czasu biologicznego.
- Obraz jest kodowany jako jasność 32×18 i różnica klatek. Stałe, sztucznie przypisane wejścia trafiają do 12 000 neuronów z klas wzrokowych. Nie zakładamy, że współrzędne som definiują pola recepcyjne oka muchy.
- Warstwa decyzji otrzymuje wyłącznie odczyty aktywności wybranych neuronów i średnie klas. Nie ma bezpośredniej drogi z pikseli do klawiszy z pominięciem grafu. Uczone są wagi odczytu i głowica pozycji myszy; topologia i połączenia biologiczne pozostają stałe.
- Nauka demonstracyjna: softmax, minibatch ze zbalansowanym doborem klas, SGD. Nagroda: prosta aktualizacja policy-gradient z zanikiem wstecz dla ostatnich 400 decyzji; nie jest to PPO ani niezawodny autonomiczny trening.
- 3D używa rzeczywistych współrzędnych z adnotacji (woksele 4×4×40 nm). Dla brakującej somy używana jest rzeczywista pozycja referencyjna. 14 neuronów bez kompletu współrzędnych pozostaje w symulacji, ale nie w widoku. Do rysowania wybrano deterministyczną próbkę 5000 punktów. Włączenie „Połączenia” pokazuje ograniczony podzbiór rzeczywistych krawędzi między nimi.
- Kliknij grupę, aby ją wyizolować. „Pobudź wybrany obszar” dodaje sztuczny bodziec tylko w obserwacji; nie wolno mieszać takich przykładów z nauką gry.

## Rozpoznawanie końca nocy

Można zapisać obraz menu, wygranej lub przegranej w panelu, gdy ostatnia klatka ma mniej niż 5 sekund. Dopasowanie używa średniego błędu jasności zmniejszonego obrazu z progiem 0.045. To przybliżona metoda: zmiana rozdzielczości, animacje lub podobne ekrany mogą spowodować pomyłkę. Domyślnie brak wzorców, dlatego operator oznacza wynik. Nie przyznajemy nagrody za sam upływ czasu, który mógłby wynagradzać pozostawanie w menu.

## Pliki i prywatność

- `data/raw/manifest.json`: przypięte adresy źródeł, rozmiary i sumy SHA-256.
- `data/cache/`: macierz, metadane neuronów, anatomia i opcjonalne wzorce ekranów.
- `models/fly_policy.npz`: wyuczone wagi i przykłady aktywność → akcja. Nie zawiera surowych nagrań ekranu.
- `logs/app.log`: zdarzenia i błędy.
- Oryginalny `data/connections.csv` zachowano; nie jest używany przez nowy model.
- Panel nasłuchuje wyłącznie na 127.0.0.1, nie wysyła klatek do usług zewnętrznych. Komendy wymagają losowego tokenu bieżącej sesji i zgodnego pochodzenia.
- Przechwytywana jest widoczna powierzchnia aktywnego UCN. Nakładki Steam lub inne okna nad grą mogą zakłócić obraz; wyłącz nakładki na czas demonstracji. Warto zamknąć menu panelu przed rozpoczęciem faktycznej rozgrywki.

## Odtworzenie środowiska i sprawdzenie

W folderze projektu użyj Python 3.11+ oraz `python -m venv .venv`, następnie `PREPARE_DATA.bat`. Dane są pobierane z publicznych repozytoriów autorów bez logowania. CUDA nie jest wymagana.

Testy: `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

## Źródła

- Shiu et al., **A Drosophila computational brain model reveals sensorimotor processing**, Nature (2024): https://doi.org/10.1038/s41586-024-07763-9
- Dane v783 udostępnione przez autorów: https://github.com/philshiu/Drosophila_brain_model, commit `91bdd1e7dcf193f3e7ca5a8933497fcef63b7960` (repozytorium MIT).
- Schlegel et al., **Whole-brain annotation and multi-connectome cell typing of Drosophila**, Nature (2024): https://doi.org/10.1038/s41586-024-07686-5
- Adnotacje: https://github.com/flyconnectome/flywire_annotations, commit `8587524c1748ce5ef2080822a2fc890fc03bf597`.
- FlyWire Consortium / Dorkenwald et al., **Neuronal wiring diagram of an adult brain**, Nature (2024): https://doi.org/10.1038/s41586-024-07558-y

Zachowaj przypisanie danych autorom. Ten projekt nie jest oficjalnym produktem FlyWire ani autorów UCN.
"# flyfanf" 
"# flyfanf" 
"# cipka" 
"# cipka" 
"# FnafFly" 
