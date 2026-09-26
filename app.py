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