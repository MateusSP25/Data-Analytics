import pandas as pd

dados = {
    "cidade": ["Campina Grande", "João Pessoa", "Recife"],
    "vendas": [120, 180, 150]
}

df = pd.DataFrame(dados)

print(df)
print(df.describe())
