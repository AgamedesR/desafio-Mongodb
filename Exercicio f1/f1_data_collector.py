"""
f1_data_collector.py
=====================================================================
Exercicio Pratico 01 - Coletor de Dados da OpenF1 para MongoDB
=====================================================================

Coleta dados de sessoes, pilotos e voltas da API publica OpenF1
(https://api.openf1.org) e grava tudo em um banco MongoDB, de forma
modular, configuravel e idempotente (sem duplicar dados a cada nova
execucao).

Uso:
    python f1_data_collector.py

Configuracao:
    Crie um arquivo .env (veja .env.example) com pelo menos:
        MONGO_URI=mongodb://localhost:27017
"""

import os
import logging
from typing import Dict, List

import requests
from pymongo import MongoClient
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
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "openf1_data")
API_BASE_URL = os.getenv("OPENF1_API_BASE_URL", "https://api.openf1.org/v1")

# Caso de uso de demonstracao: GP da Italia 2023 (Monza)
SESSION_KEY = int(os.getenv("SESSION_KEY", "9159"))
MEETING_KEY = int(os.getenv("MEETING_KEY", "1219"))
YEAR = int(os.getenv("YEAR", "2023"))


# ========================================================
# 2. Modulo de Conexao com o MongoDB
# ========================================================
def conectar_mongodb():
    """Conecta ao MongoDB usando a MONGO_URI do .env e retorna o objeto db."""
    logging.info("Conectando ao MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)
    client.admin.command("ping")  # valida a conexao
    db = client[MONGO_DB_NAME]
    logging.info("Conectado ao banco '%s' com sucesso.", MONGO_DB_NAME)
    return db


# ========================================================
# 3. Modulo de Busca de Dados na API
# ========================================================
def fetch_data(endpoint: str, params: dict) -> List[dict]:
    """
    Faz uma requisicao GET a API OpenF1 e retorna a lista de resultados.

    Args:
        endpoint: nome do endpoint (ex: 'sessions', 'drivers', 'laps')
        params: parametros de query string

    Returns:
        Lista de registros (dicts). Lista vazia em caso de falha.
    """
    url = f"{API_BASE_URL}/{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        logging.info("%d registros obtidos de '%s'.", len(data), endpoint)
        return data
    except requests.RequestException as e:
        logging.error("Falha ao buscar dados de '%s': %s", endpoint, e)
        return []


# ========================================================
# 4. Modulo de Armazenamento (upsert = previne duplicatas)
# ========================================================
def save_to_collection(db, data: List[dict], collection_name: str, unique_keys: List[str]) -> None:
    """
    Insere ou atualiza (upsert) documentos no MongoDB, garantindo
    idempotencia a partir das chaves unicas informadas.

    Args:
        db: objeto de banco de dados (retornado por conectar_mongodb)
        data: lista de registros a gravar
        collection_name: nome da collection de destino
        unique_keys: campos que, combinados, formam a chave unica do registro
    """
    if not data:
        logging.warning("Nenhum dado para gravar em '%s'.", collection_name)
        return

    collection = db[collection_name]
    gravados = 0

    try:
        for record in data:
            query = {key: record.get(key) for key in unique_keys}
            if None in query.values():
                logging.warning("Registro ignorado (chave unica incompleta): %s", record)
                continue
            collection.update_one(query, {"$set": record}, upsert=True)
            gravados += 1
    except PyMongoError as e:
        logging.exception("Erro ao gravar dados em '%s': %s", collection_name, e)
        raise

    logging.info("%d registros processados na collection '%s'.", gravados, collection_name)


# ========================================================
# 5. Execucao Principal
# ========================================================
def main() -> int:
    logging.info("Iniciando coleta de dados da OpenF1...")
    try:
        db = conectar_mongodb()

        # ---- Passo 1: dados da sessao ----
        logging.info("Buscando dados da sessao...")
        sessions_data = fetch_data("sessions", {"year": YEAR, "meeting_key": MEETING_KEY})
        save_to_collection(db, sessions_data, "sessions", ["session_key"])

        # ---- Passo 2: dados dos pilotos ----
        logging.info("Buscando pilotos da sessao...")
        drivers_data = fetch_data("drivers", {"session_key": SESSION_KEY})
        save_to_collection(db, drivers_data, "drivers", ["session_key", "driver_number"])

        # ---- Passo 3: dados das voltas ----
        logging.info("Buscando voltas da sessao...")
        laps_data = fetch_data("laps", {"session_key": SESSION_KEY})
        save_to_collection(db, laps_data, "laps", ["session_key", "driver_number", "lap_number"])

        logging.info("Coleta finalizada com sucesso!")
        return 0
    except Exception as e:
        logging.error("Execucao encerrada com erro: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
