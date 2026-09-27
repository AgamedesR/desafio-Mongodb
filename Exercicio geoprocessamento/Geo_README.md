# Exercício 3 — Georreferenciamento com MongoDB e GeoJSON

Script Python que baixa um conjunto de **dados abertos georreferenciados**
do governo federal (por padrão, o catálogo de **Unidades Básicas de Saúde
— UBS**, do portal [dados.gov.br](https://dados.gov.br)), converte cada
registro para o formato **GeoJSON (Point)** com `pandas` + `geopandas`, e
grava os dados no **MongoDB** com um índice geoespacial `2dsphere`,
permitindo consultas de proximidade (ex.: "UBS mais próximas de um ponto").

## Estrutura

```
exercicio_03_geo_mongodb/
├── geo_data_collector.py   # script principal
├── requirements.txt        # dependências
├── .env.example            # modelo de variáveis de ambiente
└── README.md
```

## Como usar

1. Crie um ambiente virtual e instale as dependências (o `geopandas`
   depende de bibliotecas geoespaciais do sistema — no Linux normalmente
   basta `pip install`, mas em alguns ambientes pode ser necessário
   `libgdal`/`libgeos` instalados via gerenciador de pacotes do SO):

   ```bash
   python -m venv venv
   source venv/bin/activate     # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copie `.env.example` para `.env` e ajuste `CSV_URL` (ou `CSV_LOCAL_PATH`
   para testes offline) e a `MONGO_URI`:

   ```bash
   cp .env.example .env
   ```

3. Execute:

   ```bash
   python geo_data_collector.py
   ```

## Como funciona

1. **Extração:** baixa o CSV do recurso configurado (ou lê um arquivo
   local), usando `requests` + `pandas`.
2. **Transformação:** detecta automaticamente as colunas de
   latitude/longitude (aceita nomes como `latitude`/`longitude`,
   `lat`/`lon`, `y`/`x`), monta um `GeoDataFrame` com `geopandas`/`shapely`
   e converte cada linha em um documento GeoJSON `Point`.
3. **Carga:** limpa a collection de destino, insere os documentos e cria
   o índice `2dsphere` no campo `geometry`.

## Formato do documento gravado

```json
{
  "type": "Feature",
  "properties": { "...": "demais colunas do CSV" },
  "geometry": {
    "type": "Point",
    "coordinates": [-34.8631, -7.1195]
  }
}
```

## Consulta geoespacial de exemplo

A função `buscar_unidades_proximas(db, longitude, latitude, raio_metros)`
demonstra uma consulta `$nearSphere` usando o índice `2dsphere` criado,
retornando os registros dentro de um raio (em metros) a partir de um
ponto informado.

> **Nota:** o link de recursos do dados.gov.br pode mudar com o tempo.
> Se o download falhar, busque "UBS CSV" no portal, atualize `CSV_URL`
> no `.env` ou aponte `CSV_LOCAL_PATH` para um CSV baixado manualmente.
