# Carbon Footprint from Receipts (WhatsApp + FastAPI + Climatiq)

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

## 🛠 Technologies Used
- **FastAPI + Uvicorn** → backend & API  
- **Twilio** → WhatsApp messaging & media  
- **Climatiq API** → emission factor search & estimate  
- **OpenAI** → OCR fallback & encouragement line (optional)  
- **Tesseract OCR** → local receipt scanning (optional)  
- **ngrok** → local tunnel for webhook testing  

---

## 📈 Time and Space Complexity
**Time Complexity:** depends on AI response + network latency.  
**Space Complexity:** stores user shopping list and AI-generated suggestions.  
- `O(N + M)` where:  
  - `N` = length of input prompt/list  
  - `M` = length of AI-generated output  

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

Demo presentation slides

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








