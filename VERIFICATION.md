# Sprawdzenie — 20.09.2026

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
