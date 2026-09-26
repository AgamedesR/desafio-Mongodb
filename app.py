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

RAIO_TERRA_KM = 6378.1  # raio médio da Terra, usado pra converter km em radianos

# DADOS DA SEED

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
        "location": {"type": "Point", "coordinates": [-34.873, -7.115]},
        "temperatura": 4.2,
        "velocidade": 65,
        "timestamp": "2026-09-11T10:00:00Z",
    },
    {
        "veiculo_id": 102,
        "location": {"type": "Point", "coordinates": [-34.832, -7.121]},
        "temperatura": -18.5,
        "velocidade": 85,
        "timestamp": "2026-09-11T10:05:00Z",
    },
    {
        "veiculo_id": 103,
        "location": {"type": "Point", "coordinates": [-34.950, -7.150]},
        "temperatura": 22.0,
        "velocidade": 0,
        "timestamp": "2026-09-11T09:45:00Z",
    },
]

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
        radius=raio_km * 1000,  # folium.Circle usa metros, não km
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

if __name__ == "__main__":
    st.title("Teste Módulo 2")
    conn = get_sqlite_conn()
    col = get_mongo_collection()

    veiculos = buscar_veiculos_por_raio(col, lon=-34.873, lat=-7.115, raio_km=10)
    st.write(f"{len(veiculos)} veículo(s) encontrado(s)")
    render_mapa(veiculos, centro_lat=-7.115, centro_lon=-34.873, raio_km=10)