# app/main.py
from dotenv import load_dotenv
load_dotenv()  # load .env before anything else

import html, os, traceback
from fastapi import FastAPI, Form, Request
from fastapi.responses import Response

from fastapi import Query
from fastapi.responses import JSONResponse
from .integrations.climatiq import estimate_for_qty
from .parsers import parse_text


# fail fast if required env is missing
def require_env(keys: list[str]) -> None:
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            "Missing required env vars: " + ", ".join(missing) +
            ". Create a .env file in your project root with those keys."
        )

require_env(["CLIMATIQ_API_KEY"])

from .parsers import parse_mms_or_text
from .mapper import map_to_products
from .calculator import compute_co2
from .suggestions import tips_from_breakdown
from .integrations.climatiq import estimate_for_qty

app = FastAPI()

from fastapi.responses import PlainTextResponse
import html

def twiml_message(text: str, media_url: str | None = None) -> PlainTextResponse:
    """Return TwiML <Message> with proper text/xml content type."""
    body = f"<Body>{html.escape(text)}</Body>"
    media = f"<Media>{html.escape(media_url)}</Media>" if media_url else ""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{body}{media}</Message></Response>"
    )
    # Helpful one-liner to see exactly what we return
    print("TWIML OUT:", xml[:300], "...")
    return PlainTextResponse(content=xml, media_type="text/xml")


@app.get("/health")
def health():
    return {"ok": True}

@app.get("/debug/estimate")
def debug_est(name: str = "ground beef", qty: float = 2, unit: str = "lb"):
    try:
        res = estimate_for_qty(name, qty, unit)
        if not res:
            return {"ok": False, "why": "no_factor_or_incompatible_units"}
        kg, meta = res
        return {"ok": True, "kg": kg, "factor_unit": meta["factor"].get("unit"), "activity": meta["factor"].get("activity_id")}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

@app.post("/twilio/sms")
async def twilio_sms(
    request: Request,
    From: str = Form(None),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str = Form(None),
):
    try:
        print(f"INBOUND: From={From} | Body={Body!r} | NumMedia={NumMedia} | MediaUrl0={MediaUrl0}")
        items = parse_mms_or_text(MediaUrl0, Body)
        print(f"PARSED ITEMS: {items}")
        if not items:
            return twiml_message("Send items like: '2 lb ground beef, 1 gallon milk, 6 eggs' — or attach a receipt photo.")

        mapped = map_to_products(items)
        total, breakdown = compute_co2(mapped)
        tips = tips_from_breakdown(breakdown, total)

        lines = [f"Total: {total} kg CO2e"]
        lines += [f"• {b['name']}: {b['kg_co2']} kg" for b in breakdown]
        if tips:
            lines.append("Tips:\n" + tips)

        return twiml_message("\n".join(lines))
    except Exception:
        traceback.print_exc()
        return twiml_message("Sorry—something went wrong. Try a shorter list or a clearer photo.")

from .integrations.climatiq import search_factor

@app.get("/debug/search")
def debug_search(query: str = "beef"):
    try:
        doc = search_factor(query, unit_family="mass")
        if not doc:
            return {"ok": False, "why": "no_results"}
        return {"ok": True, "activity_id": doc.get("activity_id"), "unit_type": doc.get("unit_type"), "unit": doc.get("unit")}
    except Exception as e:
        import traceback; traceback.print_exc()
        return {"ok": False, "error": str(e)}
    

@app.get("/debug/parse")
def debug_parse(body: str = Query("")):
    """Quickly see how the text parser splits items."""
    try:
        items = parse_text(body or "")
        return JSONResponse(items)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/debug/estimate")
def debug_est(name: str, qty: float, unit: str):
    """Call Climatiq for a single item to check units/factor quickly."""
    try:
        res = estimate_for_qty(name, qty, unit)
        if not res:
            return JSONResponse({"ok": False, "why": "no_factor_or_incompatible_units"})
        kg, details = res
        return JSONResponse({"ok": True, "kg_co2e": kg, "factor": details.get("factor", {})})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


