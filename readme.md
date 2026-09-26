# GeoLog — Plataforma de Telemetria Logística (Persistência Poliglota)

Desafio Integrador — Tópicos Avançados em Banco de Dados / Arquitetura de Software (UNIPÊ).

## Arquitetura

- **SQLite** (`logitech.db`) — dados transacionais: `motoristas`, `veiculos`.
- **MongoDB** (`geolog_db.telemetria`) — dados de sensores/GPS em GeoJSON, com índice `2dsphere`.
- **Streamlit** — dashboard único que faz o "join poliglota" em memória entre os dois bancos.

Diagrama e detalhamento completo em [`relatorio/relatorio-tecnico-geolog.pdf`](relatorio/relatorio-tecnico-geolog.pdf).

## Módulos implementados

1. **Persistência poliglota + seed** — conexões SQLite/MongoDB, criação de tabelas e coleção, índice `2dsphere`, carga inicial condicional.
2. **Busca geoespacial por raio** — `$geoWithin` + `$centerSphere`, mapa interativo (Folium) com marcadores e raio de busca.
3. **Visão unificada** — join em memória entre cadastro (SQLite) e último registro de telemetria (MongoDB).
4. **Dashboard analítico** — KPIs (frotas ativas, temperatura média, alertas de velocidade) e gráficos (Plotly).
5. **Bônus** — botão "Simular Movimentação" que gera novos pontos de GPS e atualiza o dashboard sem reiniciar a aplicação.

## Passo a passo para rodar

### 1. Pré-requisitos

- Python 3.10+
- MongoDB rodando (local via Docker, instalado na máquina, ou um cluster no Atlas)

### 2. Subir um MongoDB local (se não tiver um)

Com Docker instalado:

```bash
docker run -d --name mongo-geolog -p 27017:27017 mongo:7
```

Isso deixa o Mongo disponível em `mongodb://localhost:27017`, que já é o valor padrão configurado em `app.py`.

Se for usar o **Atlas** (nuvem) em vez de local, edite a constante `MONGO_URI` no topo do `app.py` com a connection string `mongodb+srv://...` fornecida pelo Atlas.

### 3. Ambiente Python

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Rodar a aplicação

```bash
streamlit run app.py
```

O Streamlit abre automaticamente em `http://localhost:8501`. Na primeira execução, o app cria o `logitech.db` (SQLite) e a coleção `telemetria` (MongoDB) e insere os dados de seed do enunciado — nas próximas vezes ele não duplica os dados.

### 5. Usando o app

- **Aba "Busca Geoespacial"**: informe latitude/longitude de referência e um raio em km; o mapa mostra os veículos dentro do raio (marcador vermelho = alerta de velocidade > 80 km/h). Clique em "Simular Movimentação" para gerar novas posições e ver o mapa atualizar.
- **Aba "Visão Unificada"**: tabela cruzando motorista, placa e última telemetria de cada veículo.
- **Aba "Dashboard Analítico"**: histórico de temperatura por veículo e distribuição do status dos motoristas.

## Estrutura do repositório

```
geolog/
├── app.py                              # aplicação Streamlit (todos os módulos)
├── requirements.txt
├── relatorio/
│   └── relatorio-tecnico-geolog.pdf     # relatório técnico com diagrama de arquitetura
└── README.md
```