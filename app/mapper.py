# app/mapper.py — minimal mapper that normalizes common names
from typing import List, Dict

ALIASES = {
    "minced beef": "ground beef",
    "beef mince": "ground beef",
    "whole milk": "milk (cow)",
    "2% milk": "milk (cow)",
}
def _canon(name: str) -> str:
    n = (name or "").strip().lower()
    return ALIASES.get(n, n)
def map_to_products(items: List[Dict]) -> List[Dict]:
    out = []
    for it in items:
        out.append({"name": _canon(it.get("name")), "qty": float(it.get("qty") or 0), "unit": it.get("unit") or "each"})
    return out


