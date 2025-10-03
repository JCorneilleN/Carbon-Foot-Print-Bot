# app/ai_router.py
from __future__ import annotations
import os, json
from typing import List, Dict, Any, Optional, Tuple

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

MODEL = os.getenv("MODEL", "gpt-4o-mini")

def _client():
    if not OpenAI:
        raise RuntimeError("openai python package not installed")
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return OpenAI(api_key=key)

# ---------- 1) Normalize items for Climatiq ----------
def normalize_items_llm(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Input: [{'name': '2 lb ground beef', 'qty': 2.0, 'unit': 'lb'}, ...]  (your parsed structure)
    Output: list with canonical names, units, and Climatiq-friendly search terms.
    """
    if not items:
        return []

    client = _client()
    prompt = {
        "instruction": (
            "You are a grocery item normalizer for a carbon calculator that uses Climatiq."
            " For each item, return JSON with:\n"
            " - canonical: generic product name suitable for EF search (e.g., 'ground beef', 'oat milk', 'soft drink', 'tilapia')\n"
            " - qty: number (copy input qty)\n"
            " - unit: one of ['kg','g','lb','oz','liter','ml','gallon','each']\n"
            " - unit_family: 'mass' | 'volume' | 'count'\n"
            " - climatiq_queries: up to 3 search terms to try in order (strings)\n"
            " - density_kg_per_l (optional float) for liquids where helpful (milk/soda/oil, etc.)\n"
            "Only return compact JSON."
        ),
        "items": items,
    }

    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Return ONLY valid JSON. No prose."},
            {"role":"user","content":json.dumps(prompt, ensure_ascii=False)}
        ],
        temperature=0.2,
        max_tokens=700,
    )
    raw = rsp.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        out = data if isinstance(data, list) else data.get("items") or data.get("normalized") or []
        # guarantee required fields fall back to inputs
        fixed = []
        for src, it in zip(items, out if isinstance(out, list) else []):
            name = (it.get("canonical") or src.get("name") or "").strip()
            qty  = float(it.get("qty", src.get("qty", 0) or 0))
            unit = (it.get("unit") or src.get("unit") or "each").strip().lower()
            fam  = it.get("unit_family") or ("mass" if unit in ("kg","g","lb","oz") else "volume" if unit in ("liter","ml","gallon") else "count")
            cq   = it.get("climatiq_queries") or [name]
            dens = it.get("density_kg_per_l")
            fixed.append({
                "name": src.get("name") or name,
                "canonical": name,
                "qty": qty,
                "unit": unit,
                "unit_family": fam,
                "climatiq_queries": [q for q in cq if isinstance(q,str) and q.strip()][:3] or [name],
                "density_kg_per_l": float(dens) if isinstance(dens,(int,float)) else None,
            })
        return fixed or items
    except Exception:
        # If parsing fails, just pass through originals
        return items

# ---------- 2) As-a-last-resort numeric fallback ----------
def fallback_estimate_llm(item: Dict[str, Any]) -> Optional[Tuple[float, str]]:
    """
    Ask the model for a numeric kgCO2e estimate when Climatiq has no factor.
    Return (kg_co2e, explanation). Label this result as 'ai_fallback' in your breakdown.
    """
    client = _client()
    ask = {
        "task": "Estimate total kgCO2e for one grocery line item.",
        "caveat": "If uncertain, give a conservative median and state low confidence.",
        "return": {
            "kg_co2e": "float (total for the given qty/unit)",
            "explanation": "<=160 chars, e.g. 'Used generic farmed white fish per-kg factor'",
            "confidence": "0.0–1.0"
        },
        "item": {
            "canonical": item.get("canonical") or item.get("name"),
            "qty": item.get("qty"),
            "unit": item.get("unit")
        }
    }
    rsp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role":"system","content":"Return ONLY valid JSON with keys: kg_co2e, explanation, confidence."},
            {"role":"user","content":json.dumps(ask, ensure_ascii=False)}
        ],
        temperature=0.2,
        max_tokens=200,
    )
    raw = rsp.choices[0].message.content.strip()
    try:
        data = json.loads(raw)
        kg = float(data.get("kg_co2e", 0))
        expl = str(data.get("explanation") or "AI estimate")
        if kg > 0:
            return kg, expl
        return None
    except Exception:
        return None
