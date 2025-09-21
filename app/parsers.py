# app/parsers.py — OpenAI Vision receipt reader + text fallback
import os, re, base64, json
from typing import List, Dict, Optional

# HTTP + image helpers
try:
    import requests
    from io import BytesIO
    from PIL import Image
except Exception:
    requests = None
    Image = None

# OpenAI client (optional; only used if OPENAI_API_KEY is set)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

# ------------------ Units ------------------
UNIT_ALIASES = {
    'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
    'kilogram': 'kg', 'kilograms': 'kg', 'kgs': 'kg',
    'litre': 'liter', 'liters': 'liter', 'litres': 'liter', 'l': 'liter',
    'gals': 'gallon', 'gal': 'gallon', 'gallons': 'gallon',
    'milliliter': 'ml', 'milliliters': 'ml', 'mL': 'ml',
}
VALID_UNITS = {'lb', 'kg', 'g', 'oz', 'liter', 'ml', 'gallon', 'each'}

def _norm_unit(u: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip().lower()
    u = UNIT_ALIASES.get(u, u)
    return u if u in VALID_UNITS else None

def _split(body: str) -> List[str]:
    # split on commas or newlines
    return [p for p in re.split(r",|\n", body) if p and p.strip()]

ITEM_RE = re.compile(r"^\s*(?P<qty>[\d]+(?:\.[\d]+)?)\s*(?P<unit>[a-zA-Z]+)?\s*(?P<name>.+?)\s*$")

def parse_text(body: str) -> List[Dict]:
    items: List[Dict] = []
    if not body:
        return items
    for part in _split(body):
        m = ITEM_RE.match(part)
        if not m:
            continue
        qty = float(m.group('qty'))
        unit = _norm_unit(m.group('unit'))
        name = m.group('name').strip().lower()
        if not unit:
            # simple heuristics
            if 'egg' in name:
                unit = 'each'
            elif any(w in name for w in ['milk', 'soda', 'water', 'juice', 'beer']):
                unit = 'liter'
            else:
                unit = 'lb'
        if len(name) < 2:
            continue
        items.append({'name': name, 'qty': qty, 'unit': unit})
    return items

# ------------------ Twilio media download ------------------
def _twilio_auth():
    sid = os.getenv('TWILIO_ACCOUNT_SID')
    token = os.getenv('TWILIO_AUTH_TOKEN')
    return (sid, token) if sid and token else None

def _download_image_bytes(url: str) -> Optional[bytes]:
    if not (requests and url):
        return None
    auth = _twilio_auth() if 'api.twilio.com' in url else None
    r = requests.get(url, auth=auth, timeout=30)
    r.raise_for_status()
    return r.content

# ------------------ OpenAI Vision OCR+understanding ------------------
def _openai_client() -> Optional[OpenAI]:
    key = os.getenv("OPENAI_API_KEY")
    if not key or not OpenAI:
        return None
    try:
        return OpenAI(api_key=key)
    except Exception:
        return None

def _image_mime_from_url(url: str) -> str:
    url = (url or "").lower()
    if url.endswith(".png"): return "image/png"
    if url.endswith(".webp"): return "image/webp"
    if url.endswith(".heic") or url.endswith(".heif"): return "image/heic"
    return "image/jpeg"

def _parse_items_json(obj: dict) -> List[Dict]:
    """
    Expecting: {"items":[{"name":"...", "qty":number, "unit":"lb|kg|g|oz|liter|ml|gallon|each"}]}
    """
    out: List[Dict] = []
    items = obj.get("items") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        return out
    for it in items:
        try:
            name = str(it.get("name", "")).strip().lower()
            qty = float(it.get("qty", 0))
            unit = _norm_unit(it.get("unit"))
            if not name or qty <= 0 or not unit:
                continue
            if len(name) < 2:
                continue
            out.append({"name": name, "qty": qty, "unit": unit})
        except Exception:
            continue
    return out

def parse_image_openai(url: str) -> List[Dict]:
    """
    Use OpenAI Vision to extract shopping items from a receipt photo.
    Returns a list of dicts: [{"name","qty","unit"}, ...]
    """
    client = _openai_client()
    if not (client and requests):
        return []

    try:
        img_bytes = _download_image_bytes(url)
        if not img_bytes:
            return []
        b64 = base64.b64encode(img_bytes).decode("ascii")
        mime = _image_mime_from_url(url)
        data_url = f"data:{mime};base64,{b64}"

        system = (
            "You are a precise receipt parser. Extract ONLY purchased grocery items.\n"
            "Return strict JSON with this shape:\n"
            '{ "items": [ { "name": string, "qty": number, "unit": "lb|kg|g|oz|liter|ml|gallon|each" } ] }\n'
            "Rules:\n"
            "- Infer weights/volumes if printed (e.g., 2 lb, 1 gallon). If none, try count for eggs; otherwise skip.\n"
            "- Use only these units: lb, kg, g, oz, liter, ml, gallon, each.\n"
            "- Do NOT include totals, taxes, URLs, card info, or prices.\n"
            "- Keep names generic (e.g., 'ground beef', 'milk', 'eggs')."
        )
        user_text = "Extract the items list from this receipt image as valid JSON only."

        resp = client.chat.completions.create(
            model=os.getenv("VISION_MODEL", "gpt-4o-mini"),
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
        )
        content = resp.choices[0].message.content
        data = json.loads(content)
        items = _parse_items_json(data)
        if items:
            print("OPENAI RECEIPT ITEMS:", items)
        return items
    except Exception as e:
        print("OPENAI RECEIPT ERROR:", repr(e))
        return []

# ------------------ Public entry ------------------
def parse_image(url: str) -> List[Dict]:
    """
    First try OpenAI Vision (if OPENAI_API_KEY is set). If it fails, return [].
    """
    if not url:
        return []
    # Try OpenAI first
    items = parse_image_openai(url)
    if items:
        return items
    # If you want a pure OCR fallback later, you can add pytesseract here.
    return []

def parse_mms_or_text(media_url: str | None, body: str | None) -> List[Dict]:
    body = (body or '').strip()
    # Prefer image if present
    if media_url:
        items = parse_image(media_url)
        if items:
            return items
    # fallback to typed text
    return parse_text(body)


