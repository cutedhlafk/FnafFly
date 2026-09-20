import pandas as pd

FILE = "../data/connections.csv"

df = pd.read_csv(FILE)

print("Liczba wierszy:", len(df))
print("\nKolumny:")
print(df.columns.tolist())

print("\nPierwsze 10 rekordów:")
print(df.head(10))

print("\nTypy danych:")
print(df.dtypes)