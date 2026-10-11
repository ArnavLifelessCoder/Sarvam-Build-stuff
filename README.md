# Sarvam Build Stuff

Projects built on [Sarvam AI](https://www.sarvam.ai) and **Indus by Sarvam**.

## [Mere Liye Call Kar](ai-caller/): an AI that makes your phone calls

Deployed at: https://mere-liye-call-kar.vercel.app/

Tell it what you need, check the plan, and it calls the PG owner, the clinic or the gas agency in whatever Indian language they speak. It gets the answers and hands you a summary.

- **Two ways to call**: speakerphone (your phone on speaker, the AI runs on your laptop) or **real calls via Indus Voice Agents** (Instant Outbound API, with the transcript returned by webhook)
- **Review before dialing**: it drafts the opening line and checklist, and you edit anything. If a detail only you know is missing (like how much money you need), it asks you first
- **Live call**: follows language switches, confirms numbers, never agrees to pay or shares OTPs. You can take over or whisper instructions it follows silently
- **After the call**: summary of facts, next steps and anything unanswered. Share to WhatsApp, download the transcript, and keep a call history
- Landing page at `/`, app at `/app`

| Job | Sarvam model |
|---|---|
| Hearing | `saaras:v4` (22 Indian languages, code-mix, auto-detect) |
| Planning + live replies | `sarvam-105b-conversations` |
| Summary | `sarvam-105b` |
| Voice | `bulbul:v4-flash` / `bulbul:v3` |
| Real calls | Indus Voice Agents, Instant Outbound API |

### Quick start
```bash
cd ai-caller
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                             # add SARVAM_API_KEY
.venv/Scripts/python -m uvicorn app:app --port 8000
```
Open http://localhost:8000.

- Full docs: [ai-caller/README.md](ai-caller/README.md)
- Real-call setup: [ai-caller/INDUS_SETUP.md](ai-caller/INDUS_SETUP.md)
- Deploying: Vercel, with Root Directory set to `ai-caller`
