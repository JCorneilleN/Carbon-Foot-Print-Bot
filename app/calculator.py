# app/calculator.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from .integrations.climatiq import estimate_for_qty

def compute_co2(items: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    total = 0.0
    breakdown: List[Dict[str, Any]] = []

    for it in items:
        name = (it.get("name") or "").strip()
        qty = float(it.get("qty") or 0)
        unit = it.get("unit") or "each"
        try:
            est = estimate_for_qty(name, qty, unit)
        except Exception as e:
            print(f"[calc] estimate error for {name!r}: {e}")
            est = None

        if est:
            kg, details = est
            total += kg
            breakdown.append({
                "name": name,
                "qty": qty,
                "unit": unit,
                "kg_co2": round(kg, 3),
                "details": details,
            })
        else:
            breakdown.append({
                "name": name,
                "qty": qty,
                "unit": unit,
                "kg_co2": 0.0,
                "skipped": True,
            })

    return round(total, 3), breakdown

