import warnings
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks, Body, status
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import logging
import time

# Suprime o FutureWarning específico do pandas dentro do pytrends
warnings.simplefilter(action='ignore', category=FutureWarning)

from schemas import (
    InterestOverTimeDoc, RisingQueriesDoc,
    InterestDataPoint, RisingQueryDataPoint, ComparisonResponse, ComparisonDataPoint,
    TrendTaskRequest, SystemLog
)
from firebase_admin_init import db
from pytrends.request import TrendReq
from pytrends.exceptions import TooManyRequestsError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Social Listening - Search Google Trends API",
    description="Microserviço para coletar e analisar dados do Google Trends.",
    version="1.3.0" # Versão incrementada devido à otimização de requisições
)

# --- Funções Auxiliares ---

def get_pytrends_client():
    """Inicializa e retorna um cliente pytrends de forma segura."""
    try:
        return TrendReq(hl='pt-BR', tz=360)
    except Exception as e:
        logger.error(f"Erro ao inicializar o cliente pytrends: {e}")
        raise HTTPException(status_code=503, detail=f"Erro ao conectar com a API do Google Trends: {e}")

def create_batches(items: List[str], batch_size: int):
    """Cria lotes de um tamanho específico a partir de uma lista."""
    for i in range(0, len(items), batch_size):
        yield items[i:i + batch_size]

# --- Lógica das Tarefas em Background ---

def process_interest_over_time(run_id: str, terms: List[str], timeframe: str, geo: str):
    """Lógica de negócio para buscar e salvar o interesse ao longo do tempo, usando lotes."""
    if not db:
        logger.error(f"Firestore não está disponível para a tarefa {run_id}.")
        return

    log_ref = db.collection('system_logs').document(run_id)
    processed_count = 0
    
    pytrends = TrendReq(hl='pt-BR', tz=360)
    term_batches = list(create_batches(terms, 5)) # Google Trends permite até 5 termos por vez
    
    try:
        for batch in term_batches:
            try:
                pytrends.build_payload(batch, cat=0, timeframe=timeframe, geo=geo, gprop='')
                df = pytrends.interest_over_time()
                
                if not df.empty:
                    for term in batch:
                        if term in df.columns:
                            data_points = [
                                InterestDataPoint(date=idx.to_pydatetime(), value=row[term], formattedValue=str(row[term]))
                                for idx, row in df.iterrows() if not row.empty
                            ]
                            doc_data = InterestOverTimeDoc(term=term, geo=geo, timeframe=timeframe, run_id=run_id, data=data_points)
                            db.collection('google_trends_data').add(doc_data.dict())
                            processed_count += 1
                
                time.sleep(1) # Delay de 1 segundo entre os lotes

            except TooManyRequestsError:
                logger.error(f"Muitas requisições para o lote {batch}. Aguardando e tentando novamente.")
                time.sleep(10) # Espera mais longa em caso de erro
                continue # Tenta o próximo lote
            except Exception as e:
                logger.error(f"Erro ao processar o lote {batch}: {e}")
                continue
        
        log_ref.update({
            'status': 'completed',
            'end_time': datetime.now(timezone.utc),
            'processed_count': processed_count,
            'message': f"Tarefa 'daily_interest_task' concluída. {processed_count} de {len(terms)} termos processados."
        })

    except Exception as e:
        error_msg = f"Erro fatal na tarefa 'daily_interest_task' (Run ID: {run_id}): {e}"
        logger.error(error_msg)
        try:
            log_ref.update({
                'status': 'failed',
                'end_time': datetime.now(timezone.utc),
                'error_message': error_msg,
                'processed_count': processed_count
            })
        except Exception as log_e:
            logger.error(f"Falha ao registrar o erro no log da tarefa {run_id}: {log_e}")

def process_rising_queries(run_id: str, terms: List[str], timeframe: str, geo: str):
    """Lógica de negócio para buscar e salvar buscas em ascensão, usando lotes."""
    if not db:
        logger.error(f"Firestore não está disponível para a tarefa {run_id}.")
        return

    log_ref = db.collection('system_logs').document(run_id)
    processed_count = 0

    pytrends = TrendReq(hl='pt-BR', tz=360)
    
    try:
        for term in terms: # A API de related_queries só aceita um termo por vez
            try:
                pytrends.build_payload([term], cat=0, timeframe=timeframe, geo=geo, gprop='')
                related_queries = pytrends.related_queries()
                rising_df = related_queries.get(term, {}).get('rising')
                
                if rising_df is not None and not rising_df.empty:
                    data_points = [
                        RisingQueryDataPoint(query=row['query'], value=row['value'], formattedValue=f"+{row['value']}%" if row['value'] < 250000 else "Breakout")
                        for _, row in rising_df.iterrows()
                    ]
                    doc_data = RisingQueriesDoc(term=term, geo=geo, timeframe=timeframe, run_id=run_id, data=data_points)
                    db.collection('google_trends_data').add(doc_data.dict())
                    processed_count += 1
                
                time.sleep(1) # Delay de 1 segundo entre cada termo

            except TooManyRequestsError:
                logger.error(f"Muitas requisições para o termo '{term}'. Aguardando e tentando novamente.")
                time.sleep(10)
                continue
            except Exception as e:
                logger.error(f"Erro ao processar o termo '{term}' para rising queries: {e}")
        
        log_ref.update({
            'status': 'completed',
            'end_time': datetime.now(timezone.utc),
            'processed_count': processed_count,
            'message': f"Tarefa 'hourly_rising_task' concluída. {processed_count} de {len(terms)} termos processados."
        })
    except Exception as e:
        error_msg = f"Erro fatal na tarefa 'hourly_rising_task' (Run ID: {run_id}): {e}"
        logger.error(error_msg)
        try:
            log_ref.update({
                'status': 'failed',
                'end_time': datetime.now(timezone.utc),
                'error_message': error_msg,
                'processed_count': processed_count
            })
        except Exception as log_e:
            logger.error(f"Falha ao registrar o erro no log da tarefa {run_id}: {log_e}")

# --- Endpoints ---

@app.get("/", include_in_schema=False)
def read_root():
    return {"message": "Search Google Trends service is running."}

@app.post("/tasks/run-daily-interest", status_code=status.HTTP_202_ACCEPTED, summary="Executa a coleta de interesse ao longo do tempo")
def run_daily_interest_task(background_tasks: BackgroundTasks, request: Optional[TrendTaskRequest] = Body(None)):
    if not db:
        raise HTTPException(status_code=503, detail="Conexão com o Firestore não está disponível.")

    terms_to_process = []
    if request and request.terms:
        terms_to_process = request.terms
    else:
        try:
            terms_ref = db.collection('trends_terms').where('is_active', '==', True).stream()
            terms_to_process = [doc.to_dict()['term'] for doc in terms_ref]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao buscar termos no Firestore: {e}")

    if not terms_to_process:
        return {"status": "accepted", "message": "Nenhum termo ativo para processar.", "run_id": None}

    if request and request.timeframe:
        timeframe = request.timeframe
    else:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        timeframe = f"{start_date.strftime('%Y-%m-%d')} {end_date.strftime('%Y-%m-%d')}"

    geo = request.geo if request and request.geo else 'BR'
    
    log_entry = SystemLog(
        task='Google Trends - Daily Interest',
        start_time=datetime.now(timezone.utc),
        status='started',
        message=f"Iniciando coleta para {len(terms_to_process)} termos."
    )
    
    try:
        _, log_ref = db.collection('system_logs').add(log_entry.dict())
        run_id = log_ref.id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao criar o log da tarefa no Firestore: {e}")

    background_tasks.add_task(process_interest_over_time, run_id, terms_to_process, timeframe, geo)
    
    return {"status": "accepted", "run_id": run_id, "message": "A tarefa de coleta de interesse foi iniciada em segundo plano."}

@app.post("/tasks/run-hourly-rising", status_code=status.HTTP_202_ACCEPTED, summary="Executa a coleta de buscas em ascensão")
def run_hourly_rising_task(background_tasks: BackgroundTasks, request: Optional[TrendTaskRequest] = Body(None)):
    if not db:
        raise HTTPException(status_code=503, detail="Conexão com o Firestore não está disponível.")

    terms_to_process = []
    if request and request.terms:
        terms_to_process = request.terms
    else:
        try:
            terms_ref = db.collection('trends_terms').where('is_active', '==', True).stream()
            terms_to_process = [doc.to_dict()['term'] for doc in terms_ref]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao buscar termos no Firestore: {e}")

    if not terms_to_process:
        return {"status": "accepted", "message": "Nenhum termo ativo para processar.", "run_id": None}

    timeframe = request.timeframe if request and request.timeframe else 'now 1-H'
    geo = request.geo if request and request.geo else 'BR'

    log_entry = SystemLog(
        task='Google Trends - Hourly Rising',
        start_time=datetime.now(timezone.utc),
        status='started',
        message=f"Iniciando coleta para {len(terms_to_process)} termos."
    )
    
    try:
        _, log_ref = db.collection('system_logs').add(log_entry.dict())
        run_id = log_ref.id
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha ao criar o log da tarefa no Firestore: {e}")

    background_tasks.add_task(process_rising_queries, run_id, terms_to_process, timeframe, geo)

    return {"status": "accepted", "run_id": run_id, "message": "A tarefa de coleta de buscas em ascensão foi iniciada em segundo plano."}

@app.get("/api/compare", response_model=ComparisonResponse, summary="Compara o interesse de busca entre múltiplos termos")
def compare_trends(
    pytrends: TrendReq = Depends(get_pytrends_client),
    terms: str = Query(..., description="Termos para comparar, separados por vírgula (máx 5)."),
    start_date: str = Query(..., description="Data de início (YYYY-MM-DD)."),
    end_date: str = Query(..., description="Data de fim (YYYY-MM-DD)."),
    geo: Optional[str] = Query('BR', description="Geografia (ex: BR, BR-SP).")
):
    term_list = [t.strip() for t in terms.split(',')]
    if len(term_list) > 5:
        raise HTTPException(status_code=400, detail="É permitido comparar no máximo 5 termos.")
        
    try:
        timeframe = f"{start_date} {end_date}"
        pytrends.build_payload(term_list, cat=0, timeframe=timeframe, geo=geo, gprop='')
        df = pytrends.interest_over_time()
        
        if df.empty or 'isPartial' in df.columns:
             return {}

        response_data = {}
        for term in term_list:
            if term in df.columns:
                response_data[term] = [
                    ComparisonDataPoint(date=idx.strftime('%Y-%m-%d'), value=row[term])
                    for idx, row in df.iterrows()
                ]
        
        return response_data
    except TooManyRequestsError:
        raise HTTPException(status_code=429, detail="Muitas requisições para a API do Google Trends. Tente novamente mais tarde.")
    except Exception as e:
        logger.error(f"Erro na comparação de termos: {e}")
        raise HTTPException(status_code=500, detail=f"Ocorreu um erro interno: {str(e)}")