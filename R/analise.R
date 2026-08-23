#################### Carregando pacotes ####################

if(!require(dplyr))
  install.packages("dplyr")
library(dplyr)

if(!require(psych))
  install.packages("psych")
library(psych)


############### Carregando o banco de dados ###############

# Passo 1: selecionar o diret?rio de trabalho (working directory)
## Session > Set Working Directory > Choose Directory


# Passo 2: carregar o banco de dados

dados <- read.csv('Banco de Dados 2.csv', sep = ';', dec = ',', stringsAsFactors = T)

dados <- read.csv2('Banco de Dados 2.csv', stringsAsFactors = T)

############### Visualizando o banco de dados ###############

View(dados)
glimpse(dados)


###### Tabelas de frequ?ncias de vari?veis categ?ricas ######

# Frequ?ncias absolutas:

table(dados$Genero)

table(dados$Grau_de_Instru?ao)

## Tabela cruzada com frequ?ncias absolutas:

table(dados$Genero, dados$Grau_de_Instru?ao)


# Frequ?ncias relativas:

prop.table(table(dados$Genero))

prop.table(table(dados$Grau_de_Instru?ao))

prop.table(table(dados$Genero, dados$Grau_de_Instru?ao))




############## Medidas para vari?veis quantitativas ##############

# Tabela de frequ?ncias:

## Vari?veis discretas:
table(dados$N_Filhos)
prop.table(table(dados$N_Filhos))

## Vari?veis cont?nuas:

# Necess?rio criar categorias que correspondam a faixas de valores:

## Passo 1: analisar a amplitude
range(dados$Salario)

## Passo 2 (opcional): avaliar a quantidade de categorias adequada (m?todo Sturges)
nclass.Sturges(dados$Salario)

## Passo 3: cria??o da tabela com as faixas
table(cut(dados$Salario, seq(0, 6, l = 7)))


# Fun??o summary - fornece m?dia, mediana, quartis e valores m?n e m?x

summary(dados$N_Filhos)

summary(dados$Salario)


# Fun??es describe e describe.by (pacote 'psych') - m?dia, desvio, erro, mediana

describe(dados$Salario)

describeBy(dados$Salario, group = dados$Genero)

describeBy(dados$Salario, group = dados$Genero:dados$Grau_de_Instruçao)

# Usando o group_by do pacote dplyr

tabela <- dados %>% group_by(Genero, Grau_de_Instruçao) %>% 
  summarise(media = mean(Salario),
            DP = sd(Salario),
            mediana = median(Salario))
tabela
