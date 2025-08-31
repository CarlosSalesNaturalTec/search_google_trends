# Documentação do Módulo SEARCH_GOOGLE_TRENDS

## 1. Detalhes Técnicos

Este módulo é um microserviço FastAPI responsável por interagir com a API do Google Trends.

- **Framework:** FastAPI
- **Biblioteca Principal:** `pytrends`
- **Banco de Dados:** Firestore (lê `trends_terms`, escreve em `google_trends_data` e `system_logs`)
- **Containerização:** Docker
- **Processamento Assíncrono:** Utiliza `BackgroundTasks` para coletas de dados, garantindo que a API responda imediatamente.

## 2. Instruções de Uso e Implantação

### 2.1. Ambiente Local

1.  **Credenciais:** Coloque o arquivo `serviceAccountKey.json` do Firebase na pasta `config/`.
2.  **Variáveis de Ambiente:** Crie um arquivo `.env` e defina a variável `GOOGLE_APPLICATION_CREDENTIALS`.
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
gcloud builds submit --tag gcr.io/[PROJECT_ID]/search-google-trends ./search_google_trends
gcloud run deploy search-google-trends \
  --image gcr.io/[PROJECT_ID]/search-google-trends \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000
```

## 3. Relação com Outros Módulos

- **Lê de:** `trends_terms` (Firestore) - para saber quais termos monitorar (comportamento padrão).
- **Escreve em:**
    - `google_trends_data` (Firestore) - para salvar os resultados das coletas.
    - `system_logs` (Firestore) - para registrar o início, andamento e fim das tarefas em background.
- **Consumido por:**
    - `ANALYTICS` (via endpoint `/api/compare`).
    - `Cloud Scheduler` (via endpoints `/tasks/*`).
    - **Qualquer serviço via API** que queira disparar uma coleta customizada.

## 4. Endpoints da API

### Endpoints de Tarefas Assíncronas

Os endpoints a seguir iniciam tarefas em segundo plano e retornam imediatamente um `HTTP 202 Accepted` com um `run_id` para rastreamento.

-   `POST /tasks/run-daily-interest`: Inicia a coleta de interesse ao longo do tempo.
-   `POST /tasks/run-hourly-rising`: Inicia a coleta de buscas em ascensão.

Ambos os endpoints aceitam um corpo de requisição JSON **opcional** para customizar a execução:

**Payload (Exemplo):**
```json
{
  "terms": ["termo A", "termo B"],
  "timeframe": "today 30-d",
  "geo": "BR-SP"
}
```
- Se o payload for omitido, a tarefa assume o comportamento padrão (busca todos os termos ativos no Firestore com as configurações padrão de tempo e geografia).
- Se o payload for fornecido, a tarefa usará os parâmetros especificados.

**Resposta (Exemplo):**
```json
{
  "status": "accepted",
  "run_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "message": "A tarefa foi iniciada em segundo plano."
}
```

### Endpoint de Comparação Síncrona

-   `GET /api/compare`: Permite ao módulo `ANALYTICS` (ou outro serviço) solicitar uma comparação direta e síncrona entre múltiplos termos. Retorna os dados diretamente na resposta.
    -   **Query Params:** `terms`, `start_date`, `end_date`, `geo`
