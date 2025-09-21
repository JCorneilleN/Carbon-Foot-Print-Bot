# app/suggestions.py — item-aware, quantified tips that praise low-impact shops
import os
from typing import List, Dict, Any, Optional, Tuple

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

from .integrations.climatiq import intensity_for_name
try:
    from .utils.units import convert_qty
except Exception:
    def convert_qty(qty: float, src: str, dst: str):
        return None

MODEL = os.getenv("MODEL", "gpt-4o-mini")

# keywords considered high-impact (for swap prompts)
HIGH_IMPACT_KEYS = {"beef", "lamb", "cheese", "butter", "pork"}

# simple produce micro-tips keyed by name substring
MICROTIPS = {
    "banana": "Bananas are already low-carbon—store at room temp to cut waste.",
    "mandarin": "Citrus is lower-carbon; buying in-season keeps impacts down.",
    "lime": "Choose loose citrus over bagged to avoid packaging emissions.",
    "apple": "Apples store well—buy loose and keep cool to reduce spoilage.",
}

ALTERNATIVES = [
    ("beef", "chicken breast"),
    ("beef", "lentils (dry)"),
    ("lamb", "chicken breast"),
    ("milk", "oat milk"),
    ("cheese", "yogurt (plain)"),
    ("butter", "olive oil"),
]

def _pick_alt(name: str) -> Optional[str]:
    n = (name or "").lower()
    for key, alt in ALTERNATIVES:
        if key in n:
            return alt
    return None

def _is_plant_based(name: str) -> bool:
    n = (name or "").lower()
    animal = {"beef","lamb","pork","chicken","turkey","fish","salmon","tuna","shrimp",
              "egg","milk","cheese","yogurt","butter"}
    return not any(k in n for k in animal)

def _quantified_line(item: Dict[str, Any]) -> Optional[str]:
    name = (item.get("name") or "").lower()
    qty = float(item.get("qty") or 0)
    unit = item.get("unit")
    if qty <= 0 or not unit:
        return None
    alt = _pick_alt(name)
    if not alt:
        return None

    curr = intensity_for_name(name, preferred_unit=unit)
    alt_i = intensity_for_name(alt, preferred_unit=unit)
    if not curr or not alt_i:
        return None
    curr_rate, curr_unit = curr  # kg per curr_unit
    alt_rate, alt_unit = alt_i   # kg per alt_unit

    conv_alt = convert_qty(qty, unit, alt_unit)
    conv_curr = convert_qty(qty, unit, curr_unit)
    if not conv_alt or not conv_curr:
        return None

    qty_alt, _ = conv_alt
    qty_curr, _ = conv_curr
    savings = qty_curr * curr_rate - qty_alt * alt_rate
    if savings <= 0:
        return None
    return f"Swap {name} → {alt}: save ~{round(savings, 2)} kg CO2e."

def tips_from_breakdown(breakdown: List[Dict[str, Any]], total: float) -> str:
    # try quantified swaps for top 3 contributors
    lines: List[str] = []
    for b in sorted(breakdown, key=lambda x: x.get("kg_co2", 0), reverse=True)[:3]:
        line = _quantified_line(b)
        if line:
            lines.append(line)

    names = [(b.get("name") or "").lower() for b in breakdown]
    plant_only = all(_is_plant_based(n) for n in names) if names else False

    # If nothing to swap and it’s already plant-heavy/low total, congratulate + microtips
    if not lines and (plant_only or total <= 1.0):
        lines.append("Nice — this receipt is low-impact and plant-forward. No swaps needed. 🎉")
        # add up to 2 microtips tied to what they bought
        added = 0
        for n in names:
            for key, tip in MICROTIPS.items():
                if key in n:
                    lines.append(tip); added += 1
                    if added >= 2:
                        break
            if added >= 2:
                break

    # If still nothing, provide gentle, non-generic guidance
    if not lines:
        # Prefer packaging/portion/storage tips when there’s no meat/dairy
        if plant_only:
            lines = ["Buy loose produce (skip plastic bags) and store properly to reduce waste."]
        else:
            lines = ["Batch-cook portions to cut leftovers and energy use."]

    # Optional: one short encouragement from OpenAI
    key = os.getenv("OPENAI_API_KEY")
    if key and OpenAI:
        try:
            client = OpenAI(api_key=key)
            msg = f"Receipt total {round(total,2)} kg. Items: {', '.join(names)[:180]}."
            rsp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are a concise eco coach. Reply with ONE short encouragement (<=120 chars)."},
                    {"role": "user", "content": msg},
                ],
                max_tokens=40,
                temperature=0.5,
            )
            extra = rsp.choices[0].message.content.strip()
            if extra:
                lines.append(extra)
        except Exception:
            pass

    return "\n".join(lines)


