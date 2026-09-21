# Sprawdzenie autotreningu — 21.09.2026

## Poprawki ciągłego uczenia, obrony i audio (kolejna sesja)

- 32 testy przeszły, w tym przypisanie nagrody do czasu przechwycenia klatki,
  uczenie przed końcem nocy, rozdzielenie akcji reguł i polityki, pełne 50 profili,
  odróżnienie GAME OVER na monitorze Toy Freddy’ego od końca własnej nocy,
  stereo, pasma, cisza, nieaktualne próbki i migracja wag.
- Pomocnik .NET 8 zbudowany z lokalnego źródła: 0 błędów i ostrzeżeń.
  Windows process loopback działa na tym PC. W rzeczywistym UCN odczytano
  setki pakietów analizy stereo z niezerowymi poziomami i pasmami.
  Nie nagrywano mikrofonu, całego wyjścia systemowego ani plików audio.
- Pomocnik odrzucił PID z niezgodną ścieżką EXE: kod błędu i 0 bajtów PCM.
  Izolacja innych aplikacji opiera się na trybie INCLUDE_TARGET_PROCESS_TREE
  API Windows; nie wykonywano niezależnego testu z drugą grającą aplikacją.
- W sprawdzonym stanie: 37 zakończonych prób łącznie z wcześniejszym treningiem,
  1266 decyzji, 37 aktualizacji, w tym 3 aktualizacje podczas nocy i 2 działania
  reguł. Nadal 0 wygranych. Liczniki rosną podczas dalszej pracy.
- Zapisano checkpoint v3: 570 wejść (554 stare + 16 audio), zachowano
  `auto50_policy.pre-audio-backup.npz`. Norma wag audio przestała być zerowa
  (około 0,0086 w sprawdzonym zapisie), co potwierdza podłączenie do uczenia,
  a nie skuteczne rozpoznawanie konkretnych dźwięków animatroników.
- W przeglądarce: 50 opcji katalogu, poprawne przełączenie opisu na Ballorę,
  działające liczniki i poziomy audio, brak błędów konsoli. Przy viewport 390 px
  dokument miał szerokość przewijania 375 px. To emulacja rozmiaru na PC,
  nie test fizycznego telefonu.
- Opisy są bazą wiedzy, nie automatycznym rozpoznawaniem wszystkich postaci.
  Dźwięk jest dodatkowym wejściem warstwy decyzji; symulacja neuronów nadal
  przetwarza obraz. Nie wykazano poprawy skuteczności ani opanowania 50/20.

## Poprzednia sesja autotreningu

- 17 testów przeszło: rozpoznawanie menu i zegara, odróżnianie punktacji od high score,
  dwie kolejne próby w maszynie stanów, aktualizacja wag, odtwarzanie checkpointu/RNG,
  pomijanie przerwanych prób, blokada wejścia poza UCN i po F12, izolacja podglądu telefonu.
  Dodatkowo: wyłączna rezerwacja portu na Windows oraz bezpieczna pauza po błędzie SendInput.
- Na rzeczywistej instalacji UCN program sam ustawił 50/20, odczytał Point Value 10000,
  uruchamiał noce, rozpoznał co najmniej 6 przegranych i zapisał 6 aktualizacji modelu.
  Na tym etapie zarejestrował 248 decyzji i maksymalny odczytany czas 12,1 s.
- Program sam wracał do menu i uruchamiał kolejne próby. Próba, w której przeoczył wynik
  i zobaczył ekran przedmiotu, została pominięta zamiast otrzymać wymyśloną nagrodę.
- Panel przeglądarkowy wyświetlał aktualny obraz UCN oraz aktywność 5000 punktów
  rzeczywistej anatomii, podczas pracy pełnego grafu 138 639 neuronów.
- Po końcowych poprawkach: checkpoint wczytany, próba nr 11 zakończona i zapisana,
  próba nr 12 rozpoczęta automatycznie. Drugie wywołanie programu odmówiło uruchomienia
  kolejnego trenera na zajętym porcie. W dzienniku 11 wyników i 11 aktualizacji.
- Podgląd otwarto przez adres LAN 192.168.0.110 z tokenem, bez przycisków sterujących.
  Przy szerokości viewportu 390 px dokument miał scrollWidth 375 px — bez poziomego
  przepełnienia; obie kolumny układają się pionowo. Test wykonano w przeglądarce PC.
- Reguła Zapory Windows FlyUCN-Viewer-8766 została włączona dla portu 8766, programu
  bazowego Pythona używanego przez venv i adresów LocalSubnet. Sprawdzono ścieżkę
  rzeczywistego procesu nasłuchującego. Nie zmieniono globalnych ustawień zapory.
- To weryfikacja działania automatyzacji i uczenia. Nie wykazano opanowania 50/20,
  wygranej ani statystycznie istotnej poprawy umiejętności. Połączenie z fizycznego
  telefonu wymaga telefonu w tej samej sieci; test na komputerze go nie zastępuje.

# Wcześniejsze sprawdzenie — 20.09.2026

Wykonano na wskazanym komputerze i instalacji Steam UCN.

- Pobrano dane ze wskazanych w manifeście commitów autorów; sprawdzono zgodność indeksów i root ID.
- Testowano pełną macierz 138 639 × 138 639: 15 091 983 połączenia, dodatnie i ujemne wagi, ograniczona suma wag wejściowych.
- Sprawdzono deterministyczną propagację bodźca obrazu poza neurony wejściowe.
- Sprawdzono uczenie klasyfikatora na oddzielnych, syntetycznych danych testowych; ponad 85/90 prawidłowych decyzji w teście. To test algorytmu, nie wynik w UCN.
- Sprawdzono zapis/odczyt modelu, odrzucanie niezgodnego checkpointu i wpływ nagrody na prawdopodobieństwo akcji.
- Sprawdzono blokadę generowania klawiszy poza UCN oraz zwolnienie klawisza po awaryjnym przerwaniu (test z atrapą wywołań Windows).
- Wszystkie **7 testów jednostkowych przeszło**.
- W prawdziwym UCN sprawdzono obraz na żywo oraz pobudzanie sieci, około **6,2 klatki/s** na CPU. Sprawdzono panel w przeglądarce, model 3D i dane neuronów.
- W prawdziwym UCN zweryfikowano skróty F6 i F12: powstało 47 próbek kalibracyjnych (46 WAIT i 1 klawisz `1`), wykonano 276 aktualizacji. Checkpoint kalibracyjny zachowano osobno, aby nie traktować go jako strategii rozgrywki.

**Nie potwierdzono samodzielnego wygrywania nocy przez model.** Noc bez przeciwników w czasie sprawdzania podglądu nie jest dowodem skuteczności AI. Zakończony etap dostarcza działające środowisko uczenia z podglądem; pozostały reprezentatywne demonstracje / nagrody i ocena skuteczności w wybranym zestawie postaci. Wysyłanie akcji przez autonomiczną politykę wymaga jeszcze próby w grze, oprócz testów adaptera.

W tej wersji nauka nie zmienia wag biologicznych połączeń: uczy się warstwa odczytu aktywności. Przypisanie obrazu do neuronów oraz neuronów do działań jest sztucznym interfejsem do UCN.
