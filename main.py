from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Optional
from datetime import datetime
import uuid
import logging

from schemas import (
    InterestOverTimeDoc, RisingQueriesDoc,
    InterestDataPoint, RisingQueryDataPoint, ComparisonResponse, ComparisonDataPoint
)
from firebase_admin_init import db
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Social Listening - Search Google Trends API",
    description="Microserviço para coletar e analisar dados do Google Trends.",
    version="1.0.0"
)

# --- Funções Auxiliares ---

def get_pytrends_client():
    """Inicializa e retorna um cliente pytrends de forma segura."""
    try:
        return TrendReq(hl='pt-BR', tz=360)
    except Exception as e:
        logger.error(f"Erro ao inicializar o cliente pytrends: {e}")
        raise HTTPException(status_code=503, detail=f"Erro ao conectar com a API do Google Trends: {e}")

# --- Endpoints ---

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "Search Google Trends service is running."}

@app.post("/tasks/run-daily-interest", status_code=200, summary="Executa a coleta diária de interesse ao longo do tempo")
def run_daily_interest_task(pytrends: TrendReq = Depends(get_pytrends_client)):
    """
    Acionado pelo Cloud Scheduler.
    Busca o interesse dos últimos 7 dias para todos os termos ativos na coleção `trends_terms`.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"Iniciando tarefa diária de interesse. Run ID: {run_id}")
    
    try:
        terms_ref = db.collection('trends_terms').where('is_active', '==', True).stream()
        active_terms = [doc.to_dict()['term'] for doc in terms_ref]
    except Exception as e:
        logger.error(f"Erro ao buscar termos no Firestore: {e}")
        raise HTTPException(status_code=500, detail="Erro ao acessar o Firestore.")

    if not active_terms:
        logger.info("Nenhum termo ativo encontrado para processar.")
        return {"status": "success", "message": "Nenhum termo ativo para processar."}

    results = {}
    for term in active_terms:
        try:
            pytrends.build_payload([term], cat=0, timeframe='today 7-d', geo='BR', gprop='')
            df = pytrends.interest_over_time()
            
            if not df.empty and term in df.columns:
                data_points = [
                    InterestDataPoint(
                        date=idx.to_pydatetime(),
                        value=row[term],
                        formattedValue=str(row[term])
                    ) for idx, row in df.iterrows() if not row.empty
                ]
                
                doc_data = InterestOverTimeDoc(term=term, geo='BR', timeframe='7-d', run_id=run_id, data=data_points)
                db.collection('google_trends_data').add(doc_data.dict())
                results[term] = "Success"
                logger.info(f"Dados de interesse para o termo '{term}' salvos com sucesso.")
            else:
                results[term] = "No data returned"
                logger.warning(f"Nenhum dado de interesse retornado para o termo '{term}'.")

        except TooManyRequestsError:
            results[term] = "Failed: Too many requests"
            logger.error(f"Muitas requisições para o termo '{term}'. A tarefa será abortada para este termo.")
        except Exception as e:
            results[term] = f"Failed: {str(e)}"
            logger.error(f"Erro inesperado ao processar o termo '{term}': {e}")
            
    logger.info(f"Tarefa diária de interesse concluída. Run ID: {run_id}")
    return {"status": "completed", "run_id": run_id, "results": results}


@app.post("/tasks/run-hourly-rising", status_code=200, summary="Executa a coleta horária de buscas em ascensão")
def run_hourly_rising_task(pytrends: TrendReq = Depends(get_pytrends_client)):
    """
    Acionado pelo Cloud Scheduler.
    Busca por pautas em ascensão para todos os termos ativos na coleção `trends_terms`.
    """
    run_id = str(uuid.uuid4())
    logger.info(f"Iniciando tarefa horária de buscas em ascensão. Run ID: {run_id}")

    try:
        terms_ref = db.collection('trends_terms').where('is_active', '==', True).stream()
        active_terms = [doc.to_dict()['term'] for doc in terms_ref]
    except Exception as e:
        logger.error(f"Erro ao buscar termos no Firestore: {e}")
        raise HTTPException(status_code=500, detail="Erro ao acessar o Firestore.")

    if not active_terms:
        logger.info("Nenhum termo ativo encontrado para processar.")
        return {"status": "success", "message": "Nenhum termo ativo para processar."}

    results = {}
    for term in active_terms:
        try:
            pytrends.build_payload([term], cat=0, timeframe='now 1-H', geo='BR', gprop='')
            related_queries = pytrends.related_queries()
            
            rising_df = related_queries.get(term, {}).get('rising')
            
            if rising_df is not None and not rising_df.empty:
                data_points = [
                    RisingQueryDataPoint(
                        query=row['query'],
                        value=row['value'],
                        formattedValue=f"+{row['value']}%" if row['value'] < 250000 else "Breakout"
                    ) for _, row in rising_df.iterrows()
                ]
                
                doc_data = RisingQueriesDoc(term=term, geo='BR', timeframe='1-h', run_id=run_id, data=data_points)
                db.collection('google_trends_data').add(doc_data.dict())
                results[term] = "Success"
                logger.info(f"Dados de buscas em ascensão para o termo '{term}' salvos com sucesso.")
            else:
                results[term] = "No rising queries found"
                logger.info(f"Nenhuma busca em ascensão encontrada para o termo '{term}'.")

        except TooManyRequestsError:
            results[term] = "Failed: Too many requests"
            logger.error(f"Muitas requisições para o termo '{term}'. A tarefa será abortada para este termo.")
        except Exception as e:
            results[term] = f"Failed: {str(e)}"
            logger.error(f"Erro inesperado ao processar o termo '{term}': {e}")
            
    logger.info(f"Tarefa horária de buscas em ascensão concluída. Run ID: {run_id}")
    return {"status": "completed", "run_id": run_id, "results": results}


@app.get("/api/compare", response_model=ComparisonResponse, summary="Compara o interesse de busca entre múltiplos termos")
def compare_trends(
    pytrends: TrendReq = Depends(get_pytrends_client),
    terms: str = Query(..., description="Termos para comparar, separados por vírgula (máx 5)."),
    start_date: str = Query(..., description="Data de início (YYYY-MM-DD)."),
    end_date: str = Query(..., description="Data de fim (YYYY-MM-DD)."),
    geo: Optional[str] = Query('BR', description="Geografia (ex: BR, BR-SP).")
):
    """
    Permite a um serviço externo (como o de Analytics) solicitar uma comparação direta.
    """
    term_list = [t.strip() for t in terms.split(',')]
    
    if len(term_list) > 5:
        raise HTTPException(status_code=400, detail="É permitido comparar no máximo 5 termos.")
        
    try:
        timeframe = f"{start_date} {end_date}"
        pytrends.build_payload(term_list, cat=0, timeframe=timeframe, geo=geo, gprop='')
        df = pytrends.interest_over_time()
        
        if df.empty or 'isPartial' in df.columns:
             return ComparisonResponse(__root__={})

        response_data = {}
        for term in term_list:
            if term in df.columns:
                response_data[term] = [
                    ComparisonDataPoint(date=idx.strftime('%Y-%m-%d'), value=row[term])
                    for idx, row in df.iterrows()
                ]
        
        return ComparisonResponse(__root__=response_data)

    except TooManyRequestsError:
        raise HTTPException(status_code=429, detail="Muitas requisições para a API do Google Trends. Tente novamente mais tarde.")
    except Exception as e:
        logger.error(f"Erro na comparação de termos: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {str(e)}")
