# Carbon Footprint from Receipts (Twilio + OpenAI + FastAPI + Climatiq)

Turn any grocery list or receipt photo you WhatsApp to your Twilio number into a total CO₂e footprint, an itemized breakdown, and smart, quantified swap suggestions (e.g., “Swap beef → lentils: save ~4.2 kg CO₂e”).

Built with **FastAPI**, **Twilio WhatsApp**, **Climatiq** (emission factors), **OpenAI** (Vision OCR + suggestions).

---

## 🚀 Features
- **Two input modes:**  
  - Typed list: `2 lb ground beef, 1 gallon milk, 6 eggs`  
  - Receipt photo: OCR extracts line items
- Accurate CO₂e calculation via **Climatiq**  
- Smart unit conversions: lb↔kg, oz↔g, volume↔mass for liquids  
- Itemized breakdown + total CO₂e  
- Quantified suggestions: top contributors with alternative swaps & CO₂e saved  
- WhatsApp replies via TwiML  
- Debug endpoints for local testing  

---
# Requirements

- OS: Windows, macOS, or Linux

- Python: 3.11+ (3.12/3.13 fine)

- pip/venv

- ngrok: v3.7.0+ (free plan OK)

- Tesseract OCR (optional, for image receipts; OpenAI Vision fallback available)

- Twilio: Account + WhatsApp sandbox or an approved WhatsApp number

- Climatiq: Free API key (developer plan)

- OpenAI: API key (optional: OCR fallback + encouragement line)

## 🛠 Technologies Used
- **FastAPI + Uvicorn** → backend & API  
- **Twilio** → WhatsApp messaging & media  
- **Climatiq API** → emission factor search & estimate  
- **OpenAI** → OCR fallback & encouragement line (optional)  
- **Tesseract OCR** → local receipt scanning (optional)  
- **ngrok** → local tunnel for webhook testing  

---

## 👥 Authors
- Dorcas Osangiri  
- Corneille Ngoy  

---

## ✨ Future Improvements
- Web dashboard → history & footprint trends  
- Expand swap suggestions → more foods & lifestyle items  
- SMS/MMS + multilingual support  
- Voice input/output for chatbot  

---

# Resources
[View Presentation](https://docs.google.com/presentation/d/1-5rTSPqwiaoWCs2kIfVloWJKbg0t5Akwyx47hN7TwLU/edit?usp=sharing)


## 📝 Quick Start
```bash
# 1) Create & activate venv
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# OR
.\.venv\Scripts\Activate.ps1  # Windows PowerShell

# 2) Install dependencies
pip install -r requirements.txt

# 3) Set up .env with keys (Twilio, Climatiq, OpenAI optional)

# 4) Run API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 5) Expose with ngrok
ngrok http 8000

# 6) Configure Twilio WhatsApp webhook
# POST https://<ngrok-url>/twilio/sms
```
# Getting Started
1) Create & activate venv
python -m venv .venv
..venv\Scripts\Activate.ps1

2) Install deps
pip install -r requirements.txt

3) Create .env (see template below) at project root
(Same folder where you run uvicorn from)
4) Run the API
$env:PORT=8000
python -m uvicorn app.main:app --host 0.0.0.0 --port $env:PORT --reload

5) Expose with ngrok (in another terminal)
ngrok http 8000
Copy the https URL shown, e.g. https://abcd1234.ngrok-free.app/
6) Twilio webhook (POST)
WhatsApp Sandbox or Messaging Service → Inbound Settings → Request URL:
https://abcd1234.ngrok-free.app/twilio/sms
Method: POST
7) Health check
Open in browser: https://abcd1234.ngrok-free.app/health  → {"ok": true}

## Acknowledgements

- Climatiq for high‑quality emission factors

- Twilio for WhatsApp APIs

- FastAPI

- Tesseract OCR
- OpenAI














