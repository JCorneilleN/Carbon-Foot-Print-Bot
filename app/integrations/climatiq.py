# app/integrations/climatiq.py
from __future__ import annotations
import os, time, requests
from typing import Optional, Dict, Tuple, List

print("[climatiq] module v3.3 loaded")

# --- unit helpers -----------------------------------------------------------
try:
    from ..utils.units import convert_qty, family, normalize
except Exception:
    # Minimal fallback units if app/utils/units.py is missing
    from typing import Optional, Tuple
    MASS = {"lb", "kg", "g", "oz"}
    VOLUME = {"liter", "l", "ml", "gallon", "gal"}
    COUNT = {"each"}
    ALIASES = {
        "lbs": "lb", "pound": "lb", "pounds": "lb",
        "l": "liter", "litre": "liter", "liters": "liter", "litres": "liter",
        "gal": "gallon", "gals": "gallon",
        "item": "each", "items": "each",
    }
    TO_BASE = {
        ("lb", "lb"): 1.0,
        ("kg", "lb"): 2.2046226218,
        ("g",  "lb"): 0.0022046226,
        ("oz", "lb"): 1.0/16.0,
        ("liter",  "liter"): 1.0,
        ("l",      "liter"): 1.0,
        ("ml",     "liter"): 0.001,
        ("gallon", "liter"): 3.78541,
        ("gal",    "liter"): 3.78541,
        ("each", "each"): 1.0,
    }
    FROM_BASE = {
        ("lb", "lb"): 1.0,
        ("lb", "kg"): 0.45359237,
        ("lb", "g"):  453.59237,
        ("lb", "oz"): 16.0,
        ("liter", "liter"): 1.0,
        ("liter", "ml"):    1000.0,
        ("liter", "gallon"): 1.0/3.78541,
        ("liter", "gal"):    1.0/3.78541,
        ("each", "each"): 1.0,
    }
    def normalize(u: Optional[str]) -> str:
        if not u: return "each"
        u = u.strip().lower()
        return ALIASES.get(u, u)
    def family(u: str) -> str:
        u = normalize(u)
        if u in MASS: return "mass"
        if u in VOLUME: return "volume"
        if u in COUNT: return "count"
        return "other"
    def convert_qty(qty: float, src_unit: str, dst_unit: str) -> Optional[Tuple[float, str]]:
        s = normalize(src_unit); d = normalize(dst_unit)
        fs, fd = family(s), family(d)
        if fs != fd:
            return None
        if fs == "mass":
            to_lb = TO_BASE.get((s, "lb")); from_lb = FROM_BASE.get(("lb", d))
            if to_lb is None or from_lb is None: return None
            return qty * to_lb * from_lb, d
        if fs == "volume":
            to_l = TO_BASE.get((s, "liter")); from_l = FROM_BASE.get(("liter", d))
            if to_l is None or from_l is None: return None
            return qty * to_l * from_l, d
        if fs == "count":
            return qty, d
        return None

# --- config ----------------------------------------------------------------
API = "https://api.climatiq.io"
DATA_VERSION = os.getenv("CLIMATIQ_DATA_VERSION", "^3")
REGION = os.getenv("CLIMATIQ_REGION")  # optional; can be too strict for food

# simple in-memory cache
_cache: Dict[str, Tuple[float, dict]] = {}
_TTL = 3600  # 1 hour

# map item names → search keywords
QUERY_HINTS = {
    "ground beef": "beef",
    "beef steak": "beef",
    "lamb": "lamb",
    "chicken breast": "chicken",
    "milk (cow)": "cow milk",
    "milk": "cow milk",
    "plant-based milk": "oat milk",
    "oat milk": "oat milk",
    "yogurt (plain)": "yogurt",
    "cheese (hard)": "cheese",
    "tofu": "tofu",
    "lentils (dry)": "lentils",
    "beans (dry)": "beans",
    "rice (white)": "rice white",
    "bread (loaf)": "bread",
    "pasta (dry)": "pasta",
    "apples": "apples",
    "bananas": "bananas",
    "mandarins": "mandarins",
    "lime": "limes",
    "chocolate": "chocolate",
    "coffee (roasted)": "coffee beans",
    "bottled water": "bottled water",
    "tilapia": "tilapia fillet",
    "salmon": "salmon fillet",
    "cod": "cod fillet",
    "tuna": "tuna (raw)",
    "fish": "fish fillet",
    "whitefish": "whitefish fillet",
    "shrimp": "shrimp (raw)",
}

# --- auth headers -----------------------------------------------------------
def _headers():
    key = os.getenv("CLIMATIQ_API_KEY")
    if not key:
        raise RuntimeError("CLIMATIQ_API_KEY missing")
    return {"Authorization": f"Bearer {key}"}

# --- unit-type normalization & parsing -------------------------------------
def _norm_unit_type(ut: str | None) -> str:
    u = (ut or "").strip().lower()
    # Map everything to Climatiq parameter families
    if u in ("weight", "mass"): return "weight"
    if u in ("volume",): return "volume"
    if u in ("items", "count", "units", "number"): return "number"
    return u

def _parse_factor_unit(raw: str | None, unit_type: str | None) -> str:
    """Turn strings like 'kg/kg' or 'kgCO2e/kg' into 'kg'; default sanely."""
    u = (raw or "").strip().lower().replace(" ", "")
    if "/" in u:
        # take denominator (e.g., kg in kg/kgCO2e or kgCO2e/kg → kg)
        u = u.split("/")[-1]
    if u in ("item", "items", "each"): u = "each"
    if u in ("l", "litre", "litres", "liter", "liters"): u = "liter"
    if u in ("gal", "gals", "gallon", "gallons"): u = "gallon"
    fam = _norm_unit_type(unit_type)
    if fam == "weight" and u not in ("kg", "lb", "g", "oz"): return "kg"
    if fam == "volume" and u not in ("liter", "ml", "gallon"): return "liter"
    return u or ("kg" if fam == "weight" else ("liter" if fam == "volume" else "each"))

# --- density & average-item mass bridges -----------------------------------
# Density (kg per liter): for volume↔mass when factor wants weight but input is volume (or vice-versa)
DENSITY_KG_PER_L: Dict[str, float] = {
    "milk": 1.03,
    "cow milk": 1.03,
    "oat milk": 1.03,
    "water": 1.00,
    "olive oil": 0.91,
}

# Typical retail weights per item (kg) for common produce
AVG_ITEM_MASS_KG: Dict[str, float] = {
    "lime": 0.067,
    "mandarin": 0.088,  "tangerine": 0.095,  "orange": 0.13,
    "banana": 0.12,     "bananas": 0.12,
    "apple": 0.18,      "pear": 0.18,
    "onion": 0.15,      "tomato": 0.12,      "potato": 0.21,
    "lemon": 0.085,
    # add as you see them in receipts…
}

def _density_for(name: str) -> Optional[float]:
    n = (name or "").lower()
    for key, dens in DENSITY_KG_PER_L.items():
        if key in n:
            return dens
    return None

def _avg_item_mass_for(name: str) -> Optional[float]:
    n = (name or "").lower()
    for key, kg in AVG_ITEM_MASS_KG.items():
        if key in n:
            return kg
    return None

def _bridge_volume_mass(name: str, qty: float, src_unit: str, dst_unit: str) -> Optional[Tuple[float, str]]:
    """Convert between volume and mass using density when convert_qty can't."""
    src_fam, dst_fam = family(src_unit), family(dst_unit)
    if src_fam == dst_fam:
        return None
    dens = _density_for(name)
    if not dens:
        return None

    if src_fam == "volume" and dst_fam == "mass":
        conv = convert_qty(qty, src_unit, "liter")
        if not conv: return None
        liters, _ = conv
        kg = liters * dens
        return (kg, "kg") if dst_unit == "kg" else convert_qty(kg, "kg", dst_unit)

    if src_fam == "mass" and dst_fam == "volume":
        conv = convert_qty(qty, src_unit, "kg")
        if not conv: return None
        kg, _ = conv
        liters = kg / dens
        return (liters, "liter") if dst_unit == "liter" else convert_qty(liters, "liter", dst_unit)

    return None

def _bridge_each_to_mass(name: str, qty_each: float, dst_unit: str) -> Optional[Tuple[float, str]]:
    """Convert item count → mass using average single-item weights."""
    kg_per = _avg_item_mass_for(name)
    if not kg_per:
        return None
    kg = qty_each * kg_per
    return (kg, "kg") if dst_unit == "kg" else convert_qty(kg, "kg", dst_unit)

# --- cache helpers ----------------------------------------------------------
def _now() -> float: return time.time()

def _cache_get(k: str):
    v = _cache.get(k)
    if not v: return None
    t, data = v
    if _now() - t > _TTL:
        _cache.pop(k, None)
        return None
    return data

def _cache_set(k: str, data: dict):
    _cache[k] = (_now(), data)

# --- search helpers ---------------------------------------------------------

def _filter_results(results: List[dict]) -> List[dict]:
    # keep only weight/volume/number with a defined unit (avoid Area, Money, etc.)
    keep: List[dict] = []
    for d in results:
        ut = _norm_unit_type(d.get("unit_type"))
        if ut in ("weight", "volume", "number") and d.get("unit"):
            keep.append(d)
    return keep

def _fetch_search(query: str, with_region: bool) -> List[dict]:
    params = {"query": query, "data_version": DATA_VERSION}
    if with_region and REGION:
        params["region"] = REGION
    r = requests.get(f"{API}/data/v1/search", params=params, headers=_headers(), timeout=20)
    r.raise_for_status()
    return r.json().get("results", [])

def _pick_by_unit(results: List[dict], unit_family: Optional[str]) -> Optional[dict]:
    results = _filter_results(results)
    if not results:
        return None
    if not unit_family:
        return results[0]
    want = "weight" if unit_family == "mass" else ("volume" if unit_family == "volume" else "number")
    for d in results:
        ut = _norm_unit_type(d.get("unit_type"))
        if ut == want and d.get("unit"):
            return d
    # fallback: any weight/volume with a unit
    for d in results:
        ut = _norm_unit_type(d.get("unit_type"))
        if ut in ("weight", "volume") and d.get("unit"):
            return d
    return results[0]

def search_factor(query: str, unit_family: str | None = None) -> Optional[dict]:
    q = query.strip().lower()
    if len(q) < 2:
        return None  # avoid junk like 's'
    cache_key = f"search::{q}::{unit_family or ''}::{REGION or ''}::{DATA_VERSION}"
    if (cached := _cache_get(cache_key)):
        return cached

    # 1st pass: with region (if set)
    results = _fetch_search(q, with_region=True)
    doc = _pick_by_unit(results, unit_family)

    # 2nd pass: retry without region (region filters can hide food mass factors)
    if not doc:
        results2 = _fetch_search(q, with_region=False)
        doc = _pick_by_unit(results2, unit_family) or (results2[0] if results2 else None)

    if doc:
        _cache_set(cache_key, doc)
    return doc

# --- estimation -------------------------------------------------------------

def _qty_in_factor_unit(name: str, qty: float, unit: str, factor_unit: str) -> Optional[Tuple[float, str]]:
    # Try same-family conversion first
    conv = convert_qty(qty, unit, factor_unit)
    if conv:
        return conv

    # Try count → mass for produce (e.g., “1 lime”)
    if family(unit) == "count" and factor_unit in ("kg", "lb", "g", "oz"):
        bridged = _bridge_each_to_mass(name, qty, factor_unit)
        if bridged:
            return bridged

    # Try volume↔mass density bridge (e.g., milk gallon → kg)
    bridged = _bridge_volume_mass(name, qty, unit, factor_unit)
    if bridged:
        return bridged

    # heuristic: eggs often provided as count but factors are per mass (~50 g each)
    n = (name or "").lower()
    if "egg" in n and factor_unit in ("kg", "lb", "g", "oz"):
        if factor_unit == "kg": return qty * 0.05, "kg"
        if factor_unit == "lb": return qty * 0.05 * 2.2046226, "lb"
        if factor_unit == "g":  return qty * 50.0, "g"
        if factor_unit == "oz": return qty * 0.05 * 35.2739619, "oz"

    return None

def estimate_for_qty(name: str, qty: float, unit: str) -> Optional[Tuple[float, dict]]:
    if qty <= 0:
        return None
    fam = family(unit)
    hint = QUERY_HINTS.get((name or '').lower(), name)
    doc = search_factor(hint, unit_family=fam if fam in ("mass", "volume", "count") else None)
    if not doc:
        print(f"[climatiq] no factor for {name!r} (hint={hint}, fam={fam})")
        return None

    # Parse and normalize the factor's unit and type
    utype = _norm_unit_type(doc.get("unit_type"))
    factor_unit = normalize(_parse_factor_unit(doc.get("unit"), utype))

    q_conv = _qty_in_factor_unit(name, qty, unit, factor_unit)
    if not q_conv:
        print(
            f"[climatiq] unit mismatch for {name!r}: src={qty} {unit} → "
            f"factor_unit_raw={doc.get('unit')} parsed={factor_unit} ut={doc.get('unit_type')}"
        )
        return None
    qty_in_factor, _ = q_conv

    # Build params using Climatiq's expected keys
    if utype == "weight":
        params = {"weight": qty_in_factor, "weight_unit": factor_unit}
    elif utype == "volume":
        params = {"volume": qty_in_factor, "volume_unit": factor_unit}
    elif utype == "number":
        params = {"number": qty_in_factor}
    else:
        params = {"quantity": qty_in_factor, "unit": factor_unit}

    payload = {
        "emission_factor": {
            "activity_id": doc.get("activity_id"),
            "data_version": DATA_VERSION,
        },
        "parameters": params,
    }

    r = requests.post(f"{API}/data/v1/estimate", json=payload, headers=_headers(), timeout=20)
    try:
        r.raise_for_status()
    except Exception:
        print("[climatiq] estimate error", r.status_code, r.text)
        raise
    data = r.json()
    kg = float(data.get("co2e", 0.0))
    return kg, {"factor": doc, "estimate": data}

# --- intensity helper -------------------------------------------------------

def intensity_for_name(name: str, preferred_unit: str | None = None) -> Optional[Tuple[float, str]]:
    fam = family(preferred_unit) if preferred_unit else None
    doc = search_factor(name, unit_family=fam)
    if not doc:
        return None
    unit = normalize(_parse_factor_unit(doc.get("unit"), _norm_unit_type(doc.get("unit_type"))))
    est = estimate_for_qty(name, 1.0, unit)
    if not est:
        return None
    kg1, _ = est
    return kg1, unit
