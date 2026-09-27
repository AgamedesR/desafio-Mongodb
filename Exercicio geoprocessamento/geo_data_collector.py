"""
geo_data_collector.py
=====================================================================
Exercicio 03 - Georreferenciamento com MongoDB e GeoJSON
=====================================================================

Coleta um conjunto de dados abertos georreferenciados (por padrao, o
catalogo de Unidades Basicas de Saude - UBS - do portal dados.gov.br,
em formato CSV com colunas de latitude/longitude), converte cada
registro para o formato GeoJSON (Point) usando pandas + geopandas, e
grava os dados no MongoDB com suporte a indice geoespacial (2dsphere),
permitindo consultas do tipo "unidades proximas a um ponto".

Uso:
    python geo_data_collector.py

Configuracao:
    Crie um arquivo .env (veja .env.example) com pelo menos:
        MONGO_URI=mongodb://localhost:27017
        CSV_URL=<url do recurso CSV no dados.gov.br>

    Alternativamente, para testes offline, aponte CSV_LOCAL_PATH para
    um arquivo CSV local com colunas de latitude/longitude.
"""

import os
import sys
import logging
from io import StringIO
from typing import Dict, List, Optional

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pymongo import MongoClient, GEOSPHERE
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

# ========================================================
# 1. Configuracao e variaveis de ambiente
# ========================================================
load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "dados_abertos_geo")
COLLECTION_NAME = os.getenv("MONGO_COLLECTION", "unidades_basicas_saude")

# Recurso CSV do portal dados.gov.br (catalogo de UBS). O link pode mudar
# com o tempo; caso quebre, busque "UBS CSV" no portal e atualize o .env.
CSV_URL = os.getenv(
    "CSV_URL",
    "http://dados.gov.br/dataset/unidades-basicas-de-saude-ubs/resource/"
    "e8a10748-423c-433a-9523-14c1c2eba6cf",
)
# Alternativa para desenvolvimento/teste sem depender da internet
CSV_LOCAL_PATH = os.getenv("CSV_LOCAL_PATH")

CSV_ENCODING = os.getenv("CSV_ENCODING", "utf-8")
CSV_SEPARATOR = os.getenv("CSV_SEPARATOR", ",")

# Possiveis nomes de colunas de latitude/longitude encontrados em datasets
# do governo federal (variam de orgao para orgao)
LAT_CANDIDATES = ["latitude", "lat", "nu_latitude", "y"]
LON_CANDIDATES = ["longitude", "long", "lon", "nu_longitude", "x"]


# ========================================================
# 2. Modulo de Conexao com o MongoDB
# ========================================================
def conectar_mongodb():
    """Conecta ao MongoDB e retorna o objeto de banco (db)."""
    logging.info("Conectando ao MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")  # valida a conexao
    db = client[MONGO_DB_NAME]
    logging.info("Conectado ao banco '%s' com sucesso.", MONGO_DB_NAME)
    return db


# ========================================================
# 3. Modulo de Extracao (download do CSV)
# ========================================================
def buscar_dados_csv() -> pd.DataFrame:
    """
    Obtem o CSV de dados abertos (via URL configurada ou arquivo local)
    e retorna um DataFrame pandas.
    """
    if CSV_LOCAL_PATH:
        logging.info("Lendo CSV local: %s", CSV_LOCAL_PATH)
        return pd.read_csv(CSV_LOCAL_PATH, sep=CSV_SEPARATOR, encoding=CSV_ENCODING)

    logging.info("Baixando CSV de: %s", CSV_URL)
    try:
        resp = requests.get(CSV_URL, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        logging.error(
            "Falha ao baixar o CSV (%s). O link de recursos do dados.gov.br "
            "pode ter mudado - busque 'UBS CSV' no portal e atualize CSV_URL "
            "no .env, ou informe CSV_LOCAL_PATH para um arquivo local.",
            e,
        )
        raise

    return pd.read_csv(StringIO(resp.text), sep=CSV_SEPARATOR, encoding=CSV_ENCODING)


# ========================================================
# 4. Modulo de Transformacao (CSV -> GeoDataFrame -> GeoJSON)
# ========================================================
def _detectar_coluna(colunas: List[str], candidatos: List[str]) -> Optional[str]:
    """Encontra, sem diferenciar maiusculas/minusculas, a primeira coluna
    do DataFrame que bate com algum dos nomes candidatos."""
    mapa = {c.lower().strip(): c for c in colunas}
    for candidato in candidatos:
        if candidato in mapa:
            return mapa[candidato]
    return None


def transformar_para_geojson(df: pd.DataFrame) -> List[Dict]:
    """
    Recebe um DataFrame tabular com colunas de latitude/longitude e
    retorna uma lista de documentos no formato GeoJSON (Point), prontos
    para serem inseridos no MongoDB.
    """
    col_lat = _detectar_coluna(list(df.columns), LAT_CANDIDATES)
    col_lon = _detectar_coluna(list(df.columns), LON_CANDIDATES)

    if not col_lat or not col_lon:
        raise ValueError(
            f"Nao foi possivel identificar colunas de latitude/longitude. "
            f"Colunas disponiveis: {list(df.columns)}"
        )

    logging.info("Colunas identificadas -> latitude: '%s', longitude: '%s'", col_lat, col_lon)

    # Remove registros sem coordenadas validas
    df = df.dropna(subset=[col_lat, col_lon]).copy()
    df[col_lat] = pd.to_numeric(df[col_lat], errors="coerce")
    df[col_lon] = pd.to_numeric(df[col_lon], errors="coerce")
    df = df.dropna(subset=[col_lat, col_lon])

    geometry = [Point(xy) for xy in zip(df[col_lon], df[col_lat])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

    documentos = []
    propriedades_cols = [c for c in df.columns if c not in (col_lat, col_lon)]

    for _, row in gdf.iterrows():
        propriedades = {col: row[col] for col in propriedades_cols}
        # Converte tipos numpy/pandas para tipos nativos (compatibilidade com BSON)
        for k, v in propriedades.items():
            if pd.isna(v):
                propriedades[k] = None
            elif hasattr(v, "item"):
                propriedades[k] = v.item()

        documento = {
            "type": "Feature",
            "properties": propriedades,
            "geometry": {
                "type": "Point",
                "coordinates": [row.geometry.x, row.geometry.y],
            },
        }
        documentos.append(documento)

    logging.info("%d registros convertidos para GeoJSON.", len(documentos))
    return documentos


# ========================================================
# 5. Modulo de Carga (gravacao + indice geoespacial)
# ========================================================
def gravar_no_mongodb(db, documentos: List[Dict]) -> None:
    """Limpa a collection e insere os documentos GeoJSON, criando o
    indice geoespacial 2dsphere necessario para consultas de proximidade."""
    if not documentos:
        logging.warning("Nenhum documento para gravar.")
        return

    collection = db[COLLECTION_NAME]

    try:
        collection.delete_many({})
        collection.insert_many(documentos, ordered=False)
        collection.create_index([("geometry", GEOSPHERE)])
        logging.info(
            "%d documentos gravados em '%s' e indice 2dsphere criado.",
            len(documentos),
            COLLECTION_NAME,
        )
    except PyMongoError as e:
        logging.exception("Erro ao gravar dados geoespaciais: %s", e)
        raise


# ========================================================
# 6. Exemplo de consulta geoespacial (uso demonstrativo)
# ========================================================
def buscar_unidades_proximas(db, longitude: float, latitude: float, raio_metros: int = 2000) -> List[Dict]:
    """
    Retorna documentos dentro de um raio (em metros) a partir de um
    ponto (longitude, latitude), usando o indice 2dsphere.
    """
    collection = db[COLLECTION_NAME]
    query = {
        "geometry": {
            "$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "$maxDistance": raio_metros,
            }
        }
    }
    return list(collection.find(query))


# ========================================================
# 7. Orquestracao
# ========================================================
def main() -> int:
    logging.info("Iniciando coleta de dados georreferenciados...")
    try:
        db = conectar_mongodb()

        logging.info("Buscando dados de origem (CSV)...")
        df = buscar_dados_csv()
        logging.info("%d linhas lidas do CSV.", len(df))

        logging.info("Transformando dados para GeoJSON...")
        documentos = transformar_para_geojson(df)

        logging.info("Gravando dados no MongoDB...")
        gravar_no_mongodb(db, documentos)

        logging.info("Processo finalizado com sucesso!")
        return 0
    except Exception as e:
        logging.error("Execucao encerrada com erro: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
