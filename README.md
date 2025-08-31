# Documentação do Módulo SEARCH_GOOGLE_TRENDS

## 1. Detalhes Técnicos

Este módulo é um microserviço FastAPI responsável por interagir com a API do Google Trends.

- **Framework:** FastAPI
- **Biblioteca Principal:** `pytrends`
- **Banco de Dados:** Firestore (lê a coleção `trends_terms` e escreve na `google_trends_data`)
- **Containerização:** Docker

## 2. Instruções de Uso e Implantação

### 2.1. Ambiente Local

1.  **Credenciais:** Coloque o arquivo `serviceAccountKey.json` do Firebase na pasta `config/`.
2.  **Variáveis de Ambiente:** Crie um arquivo `.env` e defina a variável `GOOGLE_APPLICATION_CREDENTIALS` apontando para o arquivo de credenciais.
    ```
    GOOGLE_APPLICATION_CREDENTIALS=./config/your-service-account-file.json
    ```
3.  **Instalação e Execução:**
    ```bash
    # Crie e ative um ambiente virtual
    python -m venv venv
    .\venv\Scripts\activate

    # Instale as dependências
    pip install -r requirements.txt

    # Rode o servidor
    uvicorn main:app --reload
    ```

### 2.2. Implantação no Google Cloud Run

```bash
# Substitua [PROJECT_ID]
gcloud builds submit --tag gcr.io/[PROJECT_ID]/search-google-trends ./search_google_trends

gcloud run deploy search-google-trends \
  --image gcr.io/[PROJECT_ID]/search-google-trends \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000
```

## 3. Relação com Outros Módulos

- **Lê de:** `trends_terms` (Firestore) - para saber quais termos monitorar.
- **Escreve em:** `google_trends_data` (Firestore) - para salvar os resultados das coletas.
- **Consumido por:** `ANALYTICS` (via endpoint `/api/compare`) e `Cloud Scheduler` (via endpoints `/tasks/*`).

## 4. Endpoints da API

-   `POST /tasks/run-daily-interest`: Acionado pelo Cloud Scheduler para buscar o interesse dos últimos 7 dias para os termos configurados.
-   `POST /tasks/run-hourly-rising`: Acionado pelo Cloud Scheduler para buscar por pautas em ascensão.
-   `GET /api/compare`: Permite ao módulo `ANALYTICS` solicitar uma comparação direta entre múltiplos termos.

```