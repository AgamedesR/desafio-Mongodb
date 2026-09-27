"""
GeoLog — Plataforma de Telemetria Logística e Persistência Poliglota
Desafio Integrador — SQLite (transacional) + MongoDB (geoespacial) + Streamlit.
"""

import random
import sqlite3
from datetime import datetime, timezone

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from pymongo import MongoClient
from streamlit_folium import st_folium

SQLITE_PATH = "logitech.db"
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "geolog_db"

RAIO_TERRA_KM = 6378.1  # usado para converter km -> radianos no $centerSphere

# ---------------------------------------------------------------------------
# SEED — dados de teste do enunciado
# ---------------------------------------------------------------------------

MOTORISTAS = [
    (1, "Carlos Andrade", "123456789", "Ativo"),
    (2, "Mariana Silva", "987654321", "Ativo"),
    (3, "Roberto Souza", "456789123", "Em Descanso"),
]

VEICULOS = [
    (101, "ABC-1A23", "Volvo FH 540", 1),
    (102, "XYZ-9876", "Scania R450", 2),
    (103, "KGB-4567", "Mercedes Actros", 3),
]

TELEMETRIA_SEED = [
    {
        "veiculo_id": 101,
        "location": {"type": "Point", "coordinates": [-34.873, -7.115]},  # João Pessoa (Centro)
        "temperatura": 4.2,
        "velocidade": 65,
        "timestamp": "2026-09-11T10:00:00Z",
    },
    {
        "veiculo_id": 102,
        "location": {"type": "Point", "coordinates": [-34.832, -7.121]},  # Cabo Branco
        "temperatura": -18.5,  # Carga Congelada
        "velocidade": 85,  # Alerta de Velocidade
        "timestamp": "2026-09-11T10:05:00Z",
    },
    {
        "veiculo_id": 103,
        "location": {"type": "Point", "coordinates": [-34.950, -7.150]},  # Tibiri / BR-230
        "temperatura": 22.0,
        "velocidade": 0,
        "timestamp": "2026-09-11T09:45:00Z",
    },
]


# ---------------------------------------------------------------------------
# MÓDULO 1 — Persistência Poliglota & Carga Inicial (Seed)
# ---------------------------------------------------------------------------

@st.cache_resource
def get_sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS motoristas (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            cnh TEXT NOT NULL,
            status TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS veiculos (
            id INTEGER PRIMARY KEY,
            placa TEXT NOT NULL,
            modelo TEXT NOT NULL,
            motorista_id INTEGER NOT NULL,
            FOREIGN KEY (motorista_id) REFERENCES motoristas (id)
        )
        """
    )

    if conn.execute("SELECT COUNT(*) FROM motoristas").fetchone()[0] == 0:
        conn.executemany("INSERT INTO motoristas VALUES (?, ?, ?, ?)", MOTORISTAS)
        conn.executemany("INSERT INTO veiculos VALUES (?, ?, ?, ?)", VEICULOS)
        conn.commit()

    return conn


@st.cache_resource
def get_mongo_collection():
    client = MongoClient(MONGO_URI)
    collection = client[MONGO_DB]["telemetria"]

    # Índice geoespacial — obrigatório para $near / $geoWithin funcionarem.
    collection.create_index([("location", "2dsphere")])

    if collection.count_documents({}) == 0:
        collection.insert_many(TELEMETRIA_SEED)

    return collection


# ---------------------------------------------------------------------------
# MÓDULO 2 — Geoprocessamento e Busca por Raio (MongoDB GeoSpatial)
# ---------------------------------------------------------------------------

def buscar_veiculos_por_raio(collection, lon: float, lat: float, raio_km: float):
    raio_radianos = raio_km / RAIO_TERRA_KM
    query = {
        "location": {
            "$geoWithin": {
                "$centerSphere": [[lon, lat], raio_radianos]
            }
        }
    }
    return list(collection.find(query))


def render_mapa(veiculos_no_raio, centro_lat: float, centro_lon: float, raio_km: float):
    mapa = folium.Map(location=[centro_lat, centro_lon], zoom_start=12)

    folium.Marker(
        [centro_lat, centro_lon],
        tooltip="Ponto de referência",
        icon=folium.Icon(color="blue", icon="flag"),
    ).add_to(mapa)

    folium.Circle(
        location=[centro_lat, centro_lon],
        radius=raio_km * 1000,  # folium.Circle usa metros
        color="blue",
        fill=True,
        fill_opacity=0.1,
    ).add_to(mapa)

    for doc in veiculos_no_raio:
        lon, lat = doc["location"]["coordinates"]
        cor = "red" if doc.get("velocidade", 0) > 80 else "green"
        folium.Marker(
            [lat, lon],
            tooltip=(
                f"Veículo {doc['veiculo_id']} | "
                f"{doc.get('temperatura')}°C | {doc.get('velocidade')} km/h"
            ),
            icon=folium.Icon(color=cor, icon="truck", prefix="fa"),
        ).add_to(mapa)

    st_folium(mapa, width=None, height=500, key="mapa_geo")


# ---------------------------------------------------------------------------
# MÓDULO 3 — Visão Unificada (Join Poliglota em Memória)
# ---------------------------------------------------------------------------

def montar_visao_unificada(sqlite_conn, mongo_collection) -> pd.DataFrame:
    query_sql = """
        SELECT m.nome AS motorista, v.placa, v.id AS veiculo_id
        FROM veiculos v
        JOIN motoristas m ON m.id = v.motorista_id
    """
    df_cadastro = pd.read_sql_query(query_sql, sqlite_conn)

    linhas = []
    for _, row in df_cadastro.iterrows():
        ultimo = mongo_collection.find_one(
            {"veiculo_id": row["veiculo_id"]},
            sort=[("timestamp", -1)],
        )
        if ultimo:
            lon, lat = ultimo["location"]["coordinates"]
            linhas.append(
                {
                    "Nome do Motorista": row["motorista"],
                    "Placa": row["placa"],
                    "Última Temperatura": ultimo.get("temperatura"),
                    "Velocidade": ultimo.get("velocidade"),
                    "Coordenadas Atualizadas": f"({lat:.4f}, {lon:.4f})",
                }
            )
        else:
            linhas.append(
                {
                    "Nome do Motorista": row["motorista"],
                    "Placa": row["placa"],
                    "Última Temperatura": None,
                    "Velocidade": None,
                    "Coordenadas Atualizadas": "sem dados",
                }
            )

    return pd.DataFrame(linhas)


# ---------------------------------------------------------------------------
# MÓDULO 4 — Dashboard Analítico
# ---------------------------------------------------------------------------

def calcular_kpis(df_unificado: pd.DataFrame, mongo_collection) -> dict:
    total_frotas = len(df_unificado)
    media_temp = df_unificado["Última Temperatura"].dropna().mean()
    alertas_velocidade = int((df_unificado["Velocidade"].dropna() > 80).sum())
    return {
        "total_frotas": total_frotas,
        "media_temperatura": round(media_temp, 1) if pd.notna(media_temp) else None,
        "alertas_velocidade": alertas_velocidade,
    }


def render_graficos(mongo_collection, sqlite_conn):
    docs = list(mongo_collection.find({}))
    df_telemetria = pd.DataFrame(docs)

    if not df_telemetria.empty:
        fig_temp = px.line(
            df_telemetria.sort_values("timestamp"),
            x="timestamp",
            y="temperatura",
            color="veiculo_id",
            markers=True,
            title="Histórico de Temperatura por Veículo",
        )
        st.plotly_chart(fig_temp, use_container_width=True)

    df_motoristas = pd.read_sql_query("SELECT status FROM motoristas", sqlite_conn)
    if not df_motoristas.empty:
        fig_status = px.pie(
            df_motoristas,
            names="status",
            title="Distribuição do Status dos Motoristas",
        )
        st.plotly_chart(fig_status, use_container_width=True)


# ---------------------------------------------------------------------------
# DESAFIO BÔNUS — Simulador de Telemetria em Tempo Real
# ---------------------------------------------------------------------------

def simular_movimentacao(collection):
    """
    Para cada veículo, pega o último ponto conhecido e gera um novo ponto
    com pequena variação aleatória de coordenadas/velocidade/temperatura,
    inserindo um novo documento (não sobrescreve o histórico).
    """
    veiculo_ids = collection.distinct("veiculo_id")
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    novos_docs = []
    for vid in veiculo_ids:
        ultimo = collection.find_one({"veiculo_id": vid}, sort=[("timestamp", -1)])
        if not ultimo:
            continue
        lon, lat = ultimo["location"]["coordinates"]
        novo_lon = lon + random.uniform(-0.01, 0.01)
        novo_lat = lat + random.uniform(-0.01, 0.01)
        nova_velocidade = max(0, ultimo.get("velocidade", 0) + random.randint(-10, 10))
        nova_temperatura = round(ultimo.get("temperatura", 0) + random.uniform(-0.5, 0.5), 1)

        novos_docs.append(
            {
                "veiculo_id": vid,
                "location": {"type": "Point", "coordinates": [novo_lon, novo_lat]},
                "temperatura": nova_temperatura,
                "velocidade": nova_velocidade,
                "timestamp": agora,
            }
        )

    if novos_docs:
        collection.insert_many(novos_docs)


# ---------------------------------------------------------------------------
# APP PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="GeoLog", layout="wide", page_icon="🚚")
    st.title("🚚 GeoLog — Telemetria Logística e Persistência Poliglota")

    sqlite_conn = get_sqlite_conn()
    mongo_collection = get_mongo_collection()

    df_unificado = montar_visao_unificada(sqlite_conn, mongo_collection)
    kpis = calcular_kpis(df_unificado, mongo_collection)

    st.subheader("📊 Indicadores Principais")
    col1, col2, col3 = st.columns(3)
    col1.metric("Frotas Ativas", kpis["total_frotas"])
    col2.metric("Temp. Média da Carga (°C)", kpis["media_temperatura"])
    col3.metric("Alertas de Velocidade (>80 km/h)", kpis["alertas_velocidade"])

    st.divider()

    tab_mapa, tab_visao, tab_graficos = st.tabs(
        ["🗺️ Busca Geoespacial", "🔗 Visão Unificada", "📈 Dashboard Analítico"]
    )

    with tab_mapa:
        st.subheader("Busca de veículos por raio")

        if st.button("🔄 Simular Movimentação"):
            simular_movimentacao(mongo_collection)
            st.rerun()

        c1, c2, c3 = st.columns(3)
        centro_lat = c1.number_input("Latitude de referência", value=-7.115, format="%.4f")
        centro_lon = c2.number_input("Longitude de referência", value=-34.873, format="%.4f")
        raio_km = c3.slider("Raio de busca (km)", min_value=1, max_value=100, value=10)

        veiculos_no_raio = buscar_veiculos_por_raio(
            mongo_collection, centro_lon, centro_lat, raio_km
        )
        st.write(f"**{len(veiculos_no_raio)}** veículo(s) encontrado(s) no raio de {raio_km} km.")
        render_mapa(veiculos_no_raio, centro_lat, centro_lon, raio_km)

    with tab_visao:
        st.subheader("Join poliglota: cadastro (SQLite) + telemetria (MongoDB)")
        st.dataframe(df_unificado, use_container_width=True)

    with tab_graficos:
        st.subheader("Gráficos analíticos")
        render_graficos(mongo_collection, sqlite_conn)


if __name__ == "__main__":
    main()