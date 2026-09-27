"""
cartola_etl.py
=====================================================================
Exercicio 2 - Coletar e Armazenar Dados do Cartola FC
=====================================================================

ETL (Extracao, Transformacao e Carga) que consulta a API nao-oficial
do Cartola FC (endpoint de mercado) e grava os dados de clubes,
atletas e status do mercado em collections separadas no MongoDB.

Uso:
    python cartola_etl.py

Configuracao:
    Crie um arquivo .env (veja .env.example) com pelo menos:
        MONGO_URI=mongodb://localhost:27017
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
from dotenv import load_dotenv

# ========================================================
# Configuracao de logging
# ========================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logging.Formatter.converter = time.gmtime  # timestamps em UTC no logger

# ========================================================
# Constantes e configuracao
# ========================================================
API_BASE_URL = "https://api.cartola.globo.com"
MERCADO_ENDPOINT = f"{API_BASE_URL}/atletas/mercado"

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "cartola_fc_db")

# Colecoes
COL_CLUBES = "clubes_rodada_atual"
COL_ATLETAS = "atletas_rodada_atual"
COL_MERCADO = "mercado_rodada_atual"


# ========================================================
# Utilidades
# ========================================================
def iso_utc_now() -> str:
    """Retorna timestamp ISO-8601 em UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ========================================================
# Modulo de Conexao
# ========================================================
def conectar_mongodb() -> MongoClient:
    """Estabelece conexao com o MongoDB e retorna o objeto de banco (db)."""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")  # valida a conexao
        db = client[MONGO_DB_NAME]
        logging.info("Conectado ao MongoDB com sucesso.")
        return db
    except Exception as e:
        logging.exception("Falha ao conectar no MongoDB: %s", e)
        raise


# ========================================================
# Modulo de Extracao
# ========================================================
def buscar_dados_mercado(session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """Busca dados do endpoint de mercado no Cartola FC.

    Args:
        session: requests.Session opcional para reuso de conexao.

    Returns:
        dict com o JSON da resposta.
    """
    sess = session or requests.Session()
    headers = {
        "Accept": "application/json",
        "User-Agent": "cartola-etl/1.0 (+https://example.internal)",
    }

    max_tentativas = 3
    for tentativa in range(1, max_tentativas + 1):
        try:
            resp = sess.get(MERCADO_ENDPOINT, headers=headers, timeout=30)
            resp.raise_for_status()
            logging.info("Dados de mercado obtidos com sucesso (tentativa %d).", tentativa)
            return resp.json()
        except requests.RequestException as e:
            logging.warning("Erro na requisicao (tentativa %d/%d): %s", tentativa, max_tentativas, e)
            if tentativa == max_tentativas:
                logging.exception("Falha ao buscar dados do mercado apos %d tentativas.", max_tentativas)
                raise
            time.sleep(2 ** tentativa)  # backoff: 2, 4


# ========================================================
# Modulo de Transformacao e Carga (ETL Core)
# ========================================================
def processar_e_gravar_dados(db, dados_mercado: Dict[str, Any]) -> None:
    """Processa o JSON de mercado e grava nas collections do MongoDB.

    - clubes_rodada_atual: upsert por _id (id do clube).
    - atletas_rodada_atual: substitui documentos pela coleta atual (limpa e insere).
    - mercado_rodada_atual: mantem somente o status mais recente (limpa e insere).
    """
    timestamp = iso_utc_now()

    # --------- 1) Clubes ---------
    logging.info("Gravando dados dos clubes...")
    clubes_obj = dados_mercado.get("clubes", {})
    if isinstance(clubes_obj, dict):
        ops: List[UpdateOne] = []
        for club_id_str, club_data in clubes_obj.items():
            try:
                club_id = int(club_id_str)
            except (TypeError, ValueError):
                club_id = club_data.get("id")
                if club_id is None:
                    logging.warning("Clube com ID invalido sera ignorado: %s", club_data)
                    continue

            doc = {
                "_id": club_id,
                "nome": club_data.get("nome"),
                "abreviacao": club_data.get("abreviacao"),
                "escudos": club_data.get("escudos"),
                "nome_fantasia": club_data.get("nome_fantasia"),
                "timestamp_coleta": timestamp,
            }
            ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True))

        if ops:
            try:
                result = db[COL_CLUBES].bulk_write(ops, ordered=False)
                logging.info(
                    "Clubes upsert: %d, modificados: %d.",
                    result.upserted_count or 0,
                    result.modified_count or 0,
                )
            except PyMongoError as e:
                logging.exception("Erro ao gravar clubes: %s", e)
                raise
    else:
        logging.warning("Campo 'clubes' nao esta no formato esperado (dict).")

    # --------- 2) Atletas ---------
    logging.info("Gravando dados dos atletas...")
    atletas_list = dados_mercado.get("atletas", [])
    if not isinstance(atletas_list, list):
        logging.warning("Campo 'atletas' nao e uma lista. Valor: %s", type(atletas_list))
        atletas_list = []

    for atleta in atletas_list:
        atleta["timestamp_coleta"] = timestamp

    try:
        delete_res = db[COL_ATLETAS].delete_many({})
        logging.info("Removidos %d documentos antigos de atletas.", delete_res.deleted_count)
        if atletas_list:
            db[COL_ATLETAS].insert_many(atletas_list, ordered=False)
            logging.info("Inseridos %d atletas.", len(atletas_list))
        else:
            logging.info("Nenhum atleta para inserir.")
    except PyMongoError as e:
        logging.exception("Erro ao gravar atletas: %s", e)
        raise

    # --------- 3) Status/Mercado ---------
    logging.info("Gravando status do mercado...")
    mercado_doc = {
        "rodada_atual": dados_mercado.get("rodada_atual"),
        "status_mercado": dados_mercado.get("status_mercado"),
        "aviso": dados_mercado.get("aviso"),
        "fechamento": dados_mercado.get("fechamento"),
        "timestamp_coleta": timestamp,
    }

    try:
        db[COL_MERCADO].delete_many({})  # mantem apenas o status mais recente
        db[COL_MERCADO].insert_one(mercado_doc)
        logging.info("Status do mercado gravado com sucesso.")
    except PyMongoError as e:
        logging.exception("Erro ao gravar status do mercado: %s", e)
        raise


# ========================================================
# Orquestracao
# ========================================================
def main() -> int:
    logging.info("Iniciando ETL Cartola FC...")
    try:
        db = conectar_mongodb()
        logging.info("Buscando dados na API do Cartola FC...")
        dados = buscar_dados_mercado()
        logging.info("Processando e gravando dados...")
        processar_e_gravar_dados(db, dados)
        logging.info("Finalizado com sucesso.")
        return 0
    except Exception as e:
        logging.error("Execucao encerrada com erro: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
