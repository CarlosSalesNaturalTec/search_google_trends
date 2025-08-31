from pydantic import BaseModel, Field, RootModel
from typing import Optional, List, Dict
from datetime import datetime

# Schema para requisições das tarefas
class TrendTaskRequest(BaseModel):
    terms: Optional[List[str]] = Field(None, description="Lista de termos a serem processados. Se nulo, busca todos os termos ativos.")
    timeframe: Optional[str] = Field(None, description="Timeframe da análise (ex: 'today 7-d', 'now 1-H'). Se nulo, usa o padrão da tarefa.")
    geo: Optional[str] = Field('BR', description="Geografia da análise (ex: 'BR', 'BR-SP').")

# Schema para Log de Sistema
class SystemLog(BaseModel):
    task: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str
    processed_count: int = 0
    error_message: Optional[str] = None
    message: Optional[str] = None

# Schemas para Dados Coletados

# Sub-documento para dados de 'interest_over_time'
class InterestDataPoint(BaseModel):
    date: datetime
    value: int
    formattedValue: str

# Documento principal para 'interest_over_time'
class InterestOverTimeDoc(BaseModel):
    term: str
    geo: str
    type: str = "interest_over_time"
    timeframe: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    data: List[InterestDataPoint]

# Sub-documento para dados de 'rising_queries'
class RisingQueryDataPoint(BaseModel):
    query: str
    value: int
    formattedValue: str

# Documento principal para 'rising_queries'
class RisingQueriesDoc(BaseModel):
    term: str
    geo: str
    type: str = "rising_queries"
    timeframe: str
    run_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    data: List[RisingQueryDataPoint]

# Schema para a resposta do endpoint de comparação
class ComparisonDataPoint(BaseModel):
    date: str # Formato YYYY-MM-DD
    value: int

class ComparisonResponse(RootModel):
    root: Dict[str, List[ComparisonDataPoint]]

    def __iter__(self):
        return iter(self.root)

    def __getitem__(self, item):
        return self.root[item]
