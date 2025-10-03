# app/main.py
from dotenv import load_dotenv
load_dotenv()  # load .env before anything else

import os, html, traceback
from fastapi import FastAPI, Form, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

# === AI + Climatiq hybrid ===
from .ai_router import normalize_items_llm, fallback_estimate_llm
from .integrations.climatiq import estimate_for_qty, search_factor

# === Parsers ===
from .parsers import parse_mms_or_text, parse_text

# === Suggestions (kept) ===
from .suggestions import tips_from_breakdown


# ---- Require env (OpenAI + Climatiq) ---------------------------------------
def require_env(keys: list[str]) -> None:
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            "Missing required env vars: " + ", ".join(missing) +
            ". Create a .env file in your project root with those keys."
        )

# OpenAI is required (Vision + suggestions). Climatiq required (factors).
require_env(["OPENAI_API_KEY", "CLIMATIQ_API_KEY"])


# ---- FastAPI app ------------------------------------------------------------
app = FastAPI()


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


# ---- WhatsApp webhook -------------------------------------------------------
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

        # 1) Parse (text or image)
        items = parse_mms_or_text(MediaUrl0, Body)
        print(f"PARSED ITEMS: {items}")
        if not items:
            return twiml_message(
                "Send items like: '2 lb ground beef, 1 gallon milk, 6 eggs' — or attach a receipt photo."
            )

        # 2) Normalize with OpenAI (adds canonical names + alternative queries)
        try:
            norm_items = normalize_items_llm(items)
        except Exception as e:
            print("[ai] normalize failed:", e)
            norm_items = items

        # 3) Hybrid estimate
        total = 0.0
        breakdown = []
        used_ai_fallback = False

        for it in norm_items:
            name = (it.get("canonical") or it.get("name") or "").strip()
            qty  = float(it.get("qty") or 0)
            unit = (it.get("unit") or "each").strip().lower()
            if qty <= 0 or not name:
                continue

            # Try Climatiq with canonical name
            est = estimate_for_qty(name, qty, unit)

            # If not found, try any LLM-suggested queries
            if not est:
                for q in it.get("climatiq_queries", []):
                    if q and q != name:
                        est = estimate_for_qty(q, qty, unit)
                        if est:
                            break

            # Last resort: have OpenAI estimate
            if not est:
                fb = fallback_estimate_llm(it)
                if fb:
                    kg, note = fb
                    total += kg
                    breakdown.append({
                        "name": name,
                        "kg_co2": round(kg, 3),
                        "source": "ai_fallback",
                        "note": note
                    })
                    used_ai_fallback = True
                    continue

            if est:
                kg, _details = est
                total += kg
                breakdown.append({
                    "name": name,
                    "kg_co2": round(kg, 3),
                    "source": "climatiq"
                })

        # 4) Tips (receipt-aware, can be “you’re good”)
        tips = tips_from_breakdown(breakdown, total)

        # 5) Format reply
        lines = [f"Total: {round(total, 3)} kg CO2e"]
        lines += [f"• {b['name']}: {b['kg_co2']} kg" for b in breakdown]
        if tips:
            lines.append("Tips:\n" + tips)
        if used_ai_fallback:
            lines.append("\n(*) Some items estimated by AI when no exact factor was available.")

        return twiml_message("\n".join(lines))

    except Exception:
        traceback.print_exc()
        return twiml_message("Sorry—something went wrong. Try a shorter list or a clearer photo.")


# ---- Debug endpoints --------------------------------------------------------
@app.get("/debug/search")
def debug_search(query: str = "beef"):
    try:
        doc = search_factor(query, unit_family="mass")
        if not doc:
            return {"ok": False, "why": "no_results"}
        return {
            "ok": True,
            "activity_id": doc.get("activity_id"),
            "unit_type": doc.get("unit_type"),
            "unit": doc.get("unit")
        }
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


@app.get("/debug/parse")
def debug_parse(body: str = Query("")):
    try:
        items = parse_text(body or "")
        return JSONResponse(items)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@app.get("/debug/estimate")
def debug_est(name: str = "ground beef", qty: float = 2, unit: str = "lb"):
    """Call Climatiq for a single item to check units/factor quickly."""
    try:
        res = estimate_for_qty(name, qty, unit)
        if not res:
            return JSONResponse({"ok": False, "why": "no_factor_or_incompatible_units"})
        kg, details = res
        return JSONResponse({
            "ok": True,
            "kg_co2e": kg,
            "factor": details.get("factor", {})
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


