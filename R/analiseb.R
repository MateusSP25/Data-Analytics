dados <- data.frame(
  cidade = c("Campina Grande", "João Pessoa", "Recife"),
  vendas = c(120, 180, 150)
)

print(dados)

summary(dados)

media_vendas <- mean(dados$vendas)

print(media_vendas)
