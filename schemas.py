from pydantic import BaseModel, Field, RootModel
from typing import Optional, List, Dict, Any
from datetime import datetime

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
