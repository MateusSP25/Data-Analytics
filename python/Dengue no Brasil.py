# ============================================================
# PROJETO: Análise Estatística Espacial da Dengue no Brasil
# ANO: 2025
# SCRIPT 01: Download, limpeza, agregação municipal e validação
#
# Fontes:
#   - SINAN/Dengue - OpenDataSUS / Ministério da Saúde
#   - IBGE - API de Agregados/SIDRA (população municipal 2025)
#   - geobr/IBGE - Malha municipal 2025
#
# Objetivo:
#   Construir uma base municipal completa com:
#   - casos prováveis;
#   - casos confirmados;
#   - descartados;
#   - população;
#   - incidência por 100 mil habitantes;
#   - geometria municipal.
# ============================================================

from __future__ import annotations

import csv
import hashlib
import re
import sys
import warnings
import zipfile
from collections import Counter
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from geobr import read_municipality
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ------------------------------------------------------------
# 0. Configurações
# ------------------------------------------------------------

ANO = 2025

URL_DENGUE = (
    "https://s3.sa-east-1.amazonaws.com/"
    "ckan.saude.gov.br/SINAN/Dengue/csv/DENGBR25.csv.zip"
)

URL_POPULACAO = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/"
    "6579/periodos/2025/variaveis/9324"
    "?localidades=N6[all]"
)

DIR_BRUTOS = Path("dados_brutos")
DIR_PROCESSADOS = Path("dados_processados")
DIR_RESULTADOS = Path("resultados")
DIR_FIGURAS = Path("figuras")

for pasta in [DIR_BRUTOS, DIR_PROCESSADOS, DIR_RESULTADOS, DIR_FIGURAS]:
    pasta.mkdir(parents=True, exist_ok=True)

ZIP_DENGUE = DIR_BRUTOS / "DENGBR25.csv.zip"

# Referências nacionais publicadas em documentos oficiais.
# Pequenas diferenças podem ocorrer por data de extração/congelamento.
REF_MS_GESTAO_2025 = 1_665_793
REF_MS_RQPC_2025 = 1_661_001

# População nacional estimada para 1º de julho de 2025.
POP_BRASIL_REF = 213_421_037


# ------------------------------------------------------------
# 1. Sessão HTTP robusta
# ------------------------------------------------------------

def criar_sessao() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )

    sessao = requests.Session()
    sessao.mount("https://", HTTPAdapter(max_retries=retry))
    sessao.headers.update(
        {"User-Agent": "DengueEspacialBrasil2025/1.0"}
    )
    return sessao


SESSION = criar_sessao()


# ------------------------------------------------------------
# 2. Funções auxiliares
# ------------------------------------------------------------

def baixar_arquivo(url: str, destino: Path, chunk_size: int = 1024 * 1024) -> None:
    """Baixa um arquivo grande em blocos, sem carregá-lo inteiro na memória."""
    if destino.exists() and destino.stat().st_size > 0:
        print(f"[OK] Arquivo já existe: {destino}")
        return

    print(f"[DOWNLOAD] {url}")
    with SESSION.get(url, stream=True, timeout=(30, 3600)) as response:
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        baixado = 0

        with destino.open("wb") as f:
            for bloco in response.iter_content(chunk_size=chunk_size):
                if bloco:
                    f.write(bloco)
                    baixado += len(bloco)

                    if total > 0:
                        pct = 100 * baixado / total
                        print(
                            f"\rBaixado: {pct:6.2f}%",
                            end="",
                            flush=True,
                        )

    print()

    if not destino.exists() or destino.stat().st_size == 0:
        raise RuntimeError("Falha no download da base de dengue.")


def md5sum(arquivo: Path) -> str:
    h = hashlib.md5()
    with arquivo.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def detectar_separador(arquivo: Path, encoding: str = "latin1") -> str:
    """Detecta automaticamente ; , tab ou | no CSV."""
    with arquivo.open("r", encoding=encoding, errors="replace") as f:
        amostra = f.read(50_000)

    try:
        dialect = csv.Sniffer().sniff(amostra, delimiters=";,\t|")
        return dialect.delimiter
    except csv.Error:
        warnings.warn(
            "Não foi possível detectar o separador. Será usado ';'."
        )
        return ";"


def somente_digitos_6(series: pd.Series) -> pd.Series:
    x = (
        series.astype("string")
        .str.replace(r"\D", "", regex=True)
        .str.strip()
    )
    return x.where(x.str.len() == 6)


def normalizar_codigo_ibge_7(series: pd.Series) -> pd.Series:
    x = (
        series.astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\D", "", regex=True)
    )
    return x.where(x.str.len() == 7)


def valor_numerico_ibge(x) -> float:
    """Converte valor textual do IBGE para número."""
    if x is None:
        return np.nan

    texto = str(x).strip()

    if texto in {"", "-", "...", "X", "NA", "None"}:
        return np.nan

    # Normalmente a API retorna apenas dígitos.
    texto = texto.replace(" ", "")

    if re.fullmatch(r"\d+", texto):
        return float(texto)

    # Fallback para formatação brasileira.
    texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return np.nan


# ------------------------------------------------------------
# 3. Download da base oficial SINAN/Dengue
# ------------------------------------------------------------

baixar_arquivo(URL_DENGUE, ZIP_DENGUE)

MD5_DENGUE = md5sum(ZIP_DENGUE)
print(f"[OK] MD5: {MD5_DENGUE}")


# ------------------------------------------------------------
# 4. Extrair o maior CSV do ZIP
# ------------------------------------------------------------

with zipfile.ZipFile(ZIP_DENGUE) as z:
    csvs = [
        info
        for info in z.infolist()
        if info.filename.lower().endswith(".csv")
    ]

    if not csvs:
        raise RuntimeError(
            "Nenhum CSV foi encontrado dentro de DENGBR25.csv.zip."
        )

    maior_csv = max(csvs, key=lambda info: info.file_size)
    z.extract(maior_csv, path=DIR_BRUTOS)

CSV_DENGUE = DIR_BRUTOS / maior_csv.filename

if not CSV_DENGUE.exists():
    raise RuntimeError("CSV de dengue não foi extraído corretamente.")

print(f"[OK] CSV selecionado: {CSV_DENGUE}")


# ------------------------------------------------------------
# 5. Detectar separador e ler cabeçalho
# ------------------------------------------------------------

SEP = detectar_separador(CSV_DENGUE)
print(f"[OK] Separador detectado: {repr(SEP)}")

cabecalho = pd.read_csv(
    CSV_DENGUE,
    sep=SEP,
    encoding="latin1",
    nrows=0,
).columns.tolist()

OBRIGATORIAS = {"ID_MN_RESI", "CLASSI_FIN"}

faltantes = OBRIGATORIAS - set(cabecalho)

if faltantes:
    raise RuntimeError(
        "Campos obrigatórios ausentes: "
        + ", ".join(sorted(faltantes))
    )

CAMPOS_DESEJADOS = [
    "NU_NOTIFIC",
    "NU_ANO",
    "DT_NOTIFIC",
    "DT_SIN_PRI",
    "SEM_PRI",
    "SG_UF_NOT",
    "ID_MUNICIP",
    "SG_UF",
    "ID_MN_RESI",
    "CLASSI_FIN",
    "CRITERIO",
    "EVOLUCAO",
    "NDUPLIC_N",
    "ID_AGRAVO",
]

campos_ler = [x for x in CAMPOS_DESEJADOS if x in cabecalho]

if "NDUPLIC_N" not in campos_ler:
    warnings.warn(
        "NDUPLIC_N não está disponível. "
        "Não será possível excluir duplicidades marcadas pelo SINAN."
    )


# ------------------------------------------------------------
# 6. Leitura em chunks + agregação municipal
# ------------------------------------------------------------

print("[PROCESSAMENTO] Lendo e agregando os microdados em blocos...")

chunks_agregados = []
freq_classi = Counter()
classes_observadas = set()

n_raw = 0
n_duplicados = 0
n_validos = 0
n_provaveis_total = 0
n_confirmados_total = 0
n_descartados_total = 0
n_em_investigacao_total = 0
n_residencia_invalida = 0
n_provaveis_residencia_invalida = 0

reader = pd.read_csv(
    CSV_DENGUE,
    sep=SEP,
    encoding="latin1",
    usecols=campos_ler,
    dtype="string",
    na_values=["", "NA", "NULL"],
    keep_default_na=True,
    chunksize=300_000,
    low_memory=False,
)

for i, chunk in enumerate(reader, start=1):
    n_raw += len(chunk)

    for col in [
        "ID_MN_RESI",
        "CLASSI_FIN",
        "NDUPLIC_N",
        "SEM_PRI",
        "NU_ANO",
    ]:
        if col in chunk.columns:
            chunk[col] = chunk[col].str.strip()

    if "NDUPLIC_N" in chunk.columns:
        duplicado = chunk["NDUPLIC_N"].eq("2").fillna(False)
    else:
        duplicado = pd.Series(False, index=chunk.index)

    n_duplicados += int(duplicado.sum())

    base = chunk.loc[~duplicado].copy()
    n_validos += len(base)

    classi = base["CLASSI_FIN"].str.strip()

    descartado = classi.eq("5").fillna(False)
    provavel = ~descartado
    confirmado = classi.isin(["10", "11", "12"]).fillna(False)
    em_investigacao = classi.isna()

    n_provaveis_total += int(provavel.sum())
    n_confirmados_total += int(confirmado.sum())
    n_descartados_total += int(descartado.sum())
    n_em_investigacao_total += int(em_investigacao.sum())

    freq_chunk = (
        classi.fillna("NA/EM BRANCO")
        .value_counts(dropna=False)
        .to_dict()
    )
    freq_classi.update(
        {str(k): int(v) for k, v in freq_chunk.items()}
    )

    classes_observadas.update(
        str(x) for x in classi.dropna().unique().tolist()
    )

    code_muni_6 = somente_digitos_6(base["ID_MN_RESI"])

    residencia_invalida = code_muni_6.isna()

    n_residencia_invalida += int(residencia_invalida.sum())
    n_provaveis_residencia_invalida += int(
        (provavel & residencia_invalida).sum()
    )

    if "SEM_PRI" in base.columns:
        sem_num = (
            base["SEM_PRI"]
            .astype("string")
            .str.replace(r"\D", "", regex=True)
        )
        ano_sem_pri = pd.to_numeric(
            sem_num.str.slice(0, 4),
            errors="coerce",
        )
    else:
        ano_sem_pri = pd.Series(
            np.nan,
            index=base.index,
            dtype=float,
        )

    provavel_inicio_2025 = (
        provavel
        & ano_sem_pri.eq(ANO).fillna(False)
    )

    aux = pd.DataFrame(
        {
            "code_muni_6": code_muni_6,
            "notificacoes_validas": 1,
            "casos_provaveis": provavel.astype("int64"),
            "casos_confirmados": confirmado.astype("int64"),
            "casos_descartados": descartado.astype("int64"),
            "casos_em_investigacao": em_investigacao.astype("int64"),
            "casos_provaveis_inicio_sintomas_2025":
                provavel_inicio_2025.astype("int64"),
        }
    )

    aux = aux.dropna(subset=["code_muni_6"])

    agg_chunk = (
        aux.groupby("code_muni_6", as_index=False)
        .sum(numeric_only=True)
    )

    chunks_agregados.append(agg_chunk)

    print(
        f"  chunk {i:02d}: "
        f"{len(chunk):,} registros; "
        f"acumulado={n_raw:,}"
    )

agg = pd.concat(chunks_agregados, ignore_index=True)

agg = (
    agg.groupby("code_muni_6", as_index=False)
    .sum(numeric_only=True)
)

if agg["code_muni_6"].duplicated().any():
    raise RuntimeError(
        "Erro: a agregação produziu municípios duplicados."
    )

classes_esperadas = {"5", "10", "11", "12"}
classes_inesperadas = sorted(classes_observadas - classes_esperadas)

if classes_inesperadas:
    warnings.warn(
        "CLASSI_FIN fora de 5, 10, 11 e 12: "
        + ", ".join(classes_inesperadas)
        + ". Como a definição de caso provável exclui apenas descartados, "
        "essas categorias foram mantidas como prováveis."
    )


# ------------------------------------------------------------
# 7. Malha municipal oficial 2025 via geobr
# ------------------------------------------------------------

print("[GEOBR] Baixando malha municipal 2025...")

municipios = read_municipality(
    code_muni="all",
    year=2025,
)

if not isinstance(municipios, gpd.GeoDataFrame):
    municipios = gpd.GeoDataFrame(municipios)

# Validade geométrica
try:
    municipios["geometry"] = municipios.geometry.make_valid()
except AttributeError:
    municipios["geometry"] = municipios.geometry.buffer(0)

municipios["code_muni"] = normalizar_codigo_ibge_7(
    municipios["code_muni"]
)

municipios["code_muni_6"] = municipios["code_muni"].str[:6]

n_malha = len(municipios)

if n_malha != 5571:
    warnings.warn(
        f"Esperavam-se 5.571 municípios em 2025; "
        f"foram lidos {n_malha}."
    )

if municipios["code_muni"].duplicated().any():
    raise RuntimeError(
        "A malha municipal contém códigos IBGE duplicados."
    )


# ------------------------------------------------------------
# 8. População municipal 2025 via API oficial do IBGE
# ------------------------------------------------------------

print("[IBGE] Baixando população municipal estimada para 2025...")

resp = SESSION.get(URL_POPULACAO, timeout=(30, 180))
resp.raise_for_status()

dados_pop = resp.json()

if not dados_pop:
    raise RuntimeError(
        "A API do IBGE retornou resposta vazia."
    )

series = []

for item in dados_pop:
    for resultado in item.get("resultados", []):
        for serie in resultado.get("series", []):
            localidade = serie.get("localidade", {})
            valores = serie.get("serie", {})

            code = str(localidade.get("id", "")).strip()
            nome = str(localidade.get("nome", "")).strip()
            valor = valores.get(str(ANO))

            series.append(
                {
                    "code_muni": code,
                    "municipio_ibge_api": nome,
                    "populacao": valor_numerico_ibge(valor),
                }
            )

pop = pd.DataFrame(series)

if pop.empty:
    raise RuntimeError(
        "Não foi possível extrair a população da resposta do IBGE."
    )

pop["code_muni"] = normalizar_codigo_ibge_7(pop["code_muni"])

pop = (
    pop.dropna(subset=["code_muni"])
    .drop_duplicates(subset=["code_muni"])
    .copy()
)

pop["populacao"] = pd.to_numeric(
    pop["populacao"],
    errors="coerce",
)

n_pop = len(pop)
pop_total = float(pop["populacao"].sum(skipna=True))

if n_pop != 5571:
    warnings.warn(
        f"Esperavam-se 5.571 municípios na população 2025; "
        f"foram obtidos {n_pop}."
    )

if abs(pop_total - POP_BRASIL_REF) > 1000:
    warnings.warn(
        f"A soma da população municipal ({pop_total:,.0f}) "
        f"difere do total de referência ({POP_BRASIL_REF:,})."
    )


# ------------------------------------------------------------
# 9. Conferir códigos SINAN x IBGE
# ------------------------------------------------------------

codigos_malha = municipios[
    ["code_muni", "code_muni_6", "name_muni", "abbrev_state"]
].drop_duplicates()

nao_casados_dengue = agg.merge(
    codigos_malha[["code_muni_6"]],
    on="code_muni_6",
    how="left",
    indicator=True,
)

nao_casados_dengue = nao_casados_dengue.loc[
    nao_casados_dengue["_merge"] == "left_only"
].drop(columns="_merge")

nao_casados_dengue.to_csv(
    DIR_RESULTADOS
    / "codigos_dengue_sem_correspondencia_ibge.csv",
    index=False,
    encoding="utf-8-sig",
)


# ------------------------------------------------------------
# 10. Construir base municipal completa
# ------------------------------------------------------------

base_municipal = municipios.merge(
    pop[["code_muni", "populacao"]],
    on="code_muni",
    how="left",
    validate="one_to_one",
)

base_municipal = base_municipal.merge(
    agg,
    on="code_muni_6",
    how="left",
    validate="one_to_one",
)

colunas_casos = [
    "notificacoes_validas",
    "casos_provaveis",
    "casos_confirmados",
    "casos_descartados",
    "casos_em_investigacao",
    "casos_provaveis_inicio_sintomas_2025",
]

# Como o arquivo SINAN anual é nacional, município sem registro associado
# recebe zero para a contagem observada no arquivo extraído.
base_municipal[colunas_casos] = (
    base_municipal[colunas_casos]
    .fillna(0)
    .astype("int64")
)

base_municipal["incidencia_100mil"] = np.where(
    base_municipal["populacao"].gt(0),
    (
        base_municipal["casos_provaveis"]
        / base_municipal["populacao"]
        * 100_000
    ),
    np.nan,
)


# ------------------------------------------------------------
# 11. Validações finais
# ------------------------------------------------------------

if len(base_municipal) != n_malha:
    raise RuntimeError(
        "O número de linhas mudou após os joins."
    )

if base_municipal["code_muni"].duplicated().any():
    raise RuntimeError(
        "Existem municípios duplicados após os joins."
    )

if (
    base_municipal["casos_confirmados"]
    > base_municipal["casos_provaveis"]
).any():
    raise RuntimeError(
        "Casos confirmados maiores que casos prováveis."
    )

inc = base_municipal["incidencia_100mil"]

if np.isinf(inc.dropna()).any():
    raise RuntimeError(
        "A incidência contém valores infinitos."
    )

if (inc.dropna() < 0).any():
    raise RuntimeError(
        "Foi encontrada incidência negativa."
    )

n_pop_missing = int(
    (
        base_municipal["populacao"].isna()
        | base_municipal["populacao"].le(0)
    ).sum()
)


# ------------------------------------------------------------
# 12. Totais e comparação com referências nacionais
# ------------------------------------------------------------

total_provavel_microdados = n_provaveis_total

total_provavel_residencia_valida = int(
    agg["casos_provaveis"].sum()
)

total_provavel_agregado = int(
    base_municipal["casos_provaveis"].sum()
)

dif_ref_gestao_pct = (
    100
    * (
        total_provavel_microdados
        - REF_MS_GESTAO_2025
    )
    / REF_MS_GESTAO_2025
)

dif_ref_rqpc_pct = (
    100
    * (
        total_provavel_microdados
        - REF_MS_RQPC_2025
    )
    / REF_MS_RQPC_2025
)


# ------------------------------------------------------------
# 13. Relatório de controle de qualidade
# ------------------------------------------------------------

qa = pd.DataFrame(
    {
        "indicador": [
            "arquivo_sinan",
            "md5_zip_sinan",
            "registros_raw",
            "duplicidades_NDUPLIC_N_2_excluidas",
            "registros_apos_duplicidade",
            "casos_provaveis_microdados",
            "casos_provaveis_com_residencia_valida",
            "casos_provaveis_sem_residencia_valida",
            "casos_provaveis_agregados_municipios",
            "casos_confirmados",
            "casos_descartados",
            "casos_em_investigacao",
            "municipios_malha_2025",
            "municipios_populacao_2025",
            "municipios_sem_populacao_valida",
            "codigos_dengue_sem_correspondencia_ibge",
            "populacao_total_2025",
            "referencia_MS_gestao_2025",
            "diferenca_percentual_ref_gestao",
            "referencia_MS_RQPC_2025",
            "diferenca_percentual_ref_RQPC",
        ],
        "valor": [
            CSV_DENGUE.name,
            MD5_DENGUE,
            n_raw,
            n_duplicados,
            n_validos,
            total_provavel_microdados,
            total_provavel_residencia_valida,
            n_provaveis_residencia_invalida,
            total_provavel_agregado,
            n_confirmados_total,
            n_descartados_total,
            n_em_investigacao_total,
            n_malha,
            n_pop,
            n_pop_missing,
            len(nao_casados_dengue),
            int(pop_total),
            REF_MS_GESTAO_2025,
            round(dif_ref_gestao_pct, 4),
            REF_MS_RQPC_2025,
            round(dif_ref_rqpc_pct, 4),
        ],
    }
)

qa.to_csv(
    DIR_RESULTADOS / "controle_qualidade_dengue_2025.csv",
    index=False,
    encoding="utf-8-sig",
)

freq_df = pd.DataFrame(
    sorted(
        freq_classi.items(),
        key=lambda x: x[1],
        reverse=True,
    ),
    columns=["CLASSI_FIN", "N"],
)

freq_df.to_csv(
    DIR_RESULTADOS / "frequencia_CLASSI_FIN.csv",
    index=False,
    encoding="utf-8-sig",
)


# ------------------------------------------------------------
# 14. Exportar bases finais
# ------------------------------------------------------------

tabular = pd.DataFrame(
    base_municipal.drop(columns="geometry")
)

tabular.to_csv(
    DIR_PROCESSADOS / "dengue_municipios_brasil_2025.csv",
    index=False,
    encoding="utf-8-sig",
)

base_municipal.to_parquet(
    DIR_PROCESSADOS / "dengue_municipios_brasil_2025.parquet",
    index=False,
)

base_municipal.to_file(
    DIR_PROCESSADOS / "dengue_municipios_brasil_2025.gpkg",
    layer="dengue_2025",
    driver="GPKG",
)


# ------------------------------------------------------------
# 15. Resumo
# ------------------------------------------------------------

print("\n" + "=" * 64)
print("AGREGAÇÃO MUNICIPAL CONCLUÍDA")
print("=" * 64)
print(f"Registros SINAN brutos: {n_raw:,}")
print(f"Duplicidades excluídas: {n_duplicados:,}")
print(
    "Casos prováveis nos microdados: "
    f"{total_provavel_microdados:,}"
)
print(
    "Casos prováveis agregados com residência válida: "
    f"{total_provavel_agregado:,}"
)
print(f"Municípios na malha: {n_malha:,}")
print(
    "Municípios sem população válida: "
    f"{n_pop_missing:,}"
)
print(
    "Códigos de dengue sem correspondência IBGE: "
    f"{len(nao_casados_dengue):,}"
)
print(
    "Diferença vs. referência MS 1.665.793: "
    f"{dif_ref_gestao_pct:.3f}%"
)
print(
    "Diferença vs. referência MS 1.661.001: "
    f"{dif_ref_rqpc_pct:.3f}%"
)
print("=" * 64)
print(
    "Base final: "
    "dados_processados/dengue_municipios_brasil_2025.parquet"
)
