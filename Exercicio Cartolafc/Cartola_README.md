# Exercício 2 — Coletor e ETL do Cartola FC para MongoDB

Script Python que consulta o endpoint de mercado da API não oficial do
**Cartola FC** e grava os dados de **clubes**, **atletas** e **status do
mercado** em collections separadas no **MongoDB**.

## Estrutura

```
exercicio_02_cartola_fc/
├── cartola_etl.py       # script principal (ETL)
├── requirements.txt     # dependências
├── .env.example         # modelo de variáveis de ambiente
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
   python cartola_etl.py
   ```

## Banco de dados

- **Database:** `cartola_fc_db`
- **Collections:**
  - `clubes_rodada_atual` — upsert por `_id` (id do clube), evita duplicatas
  - `atletas_rodada_atual` — limpa e reinsere a cada coleta (sempre reflete a rodada atual)
  - `mercado_rodada_atual` — mantém apenas o status de mercado mais recente

## Boas práticas aplicadas

- Retry com backoff exponencial nas chamadas HTTP
- `bulk_write` com `UpdateOne(upsert=True)` para os clubes (idempotência)
- Logging estruturado em UTC (ISO-8601) em cada etapa
- Configuração via `.env` (sem valores sensíveis no código)
- Pronto para ser agendado via `cron` para coletas periódicas
