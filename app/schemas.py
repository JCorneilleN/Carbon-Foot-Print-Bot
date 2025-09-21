from pydantic import BaseModel
from typing import List, Optional

class LineItem(BaseModel):
    name: str
    quantity: float
    unit: str  # normalized (lb, kg, liter, each)

class Basket(BaseModel):
    items: List[LineItem]

class CalcResult(BaseModel):
    total_kg_co2: float
    breakdown: list  # [{name, qty, unit, kg_co2}]
    suggestions: Optional[str] = None