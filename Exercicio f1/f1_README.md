# Exercício 1 — Coletor de Dados da OpenF1 para MongoDB

Script Python que coleta dados de **sessões**, **pilotos** e **voltas** da
API pública [OpenF1](https://api.openf1.org) e grava tudo em um banco
**MongoDB**, de forma modular, configurável e idempotente.

## Estrutura

```
exercicio_01_openf1/
├── f1_data_collector.py   # script principal
├── requirements.txt       # dependências
├── .env.example           # modelo de variáveis de ambiente
└── README.md
```

## Como usar

1. Crie um ambiente virtual e instale as dependências:

   ```bash
   python -m venv venv
   source venv/bin/activate     # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copie `.env.example` para `.env` e ajuste a `MONGO_URI` se necessário:

   ```bash
   cp .env.example .env
   ```

3. Execute:

   ```bash
   python f1_data_collector.py
   ```

## Banco de dados

- **Database:** `openf1_data`
- **Collections:** `sessions`, `drivers`, `laps`
- **Chaves únicas (upsert):**
  - `sessions` → `session_key`
  - `drivers` → `session_key` + `driver_number`
  - `laps` → `session_key` + `driver_number` + `lap_number`

## Caso de uso de demonstração

GP da Itália 2023 em Monza — `session_key=9159`, `meeting_key=1219`,
`year=2023` (configurável via `.env`).
