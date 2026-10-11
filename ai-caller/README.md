# 📞 Mere Liye Call Kar — AI that makes your calls

Tell it what you need ("ask the PG owner if a single room is free under ₹12k, food included?"), put your phone on speaker next to the laptop, and the AI holds the conversation **in Kannada, Hindi, Tamil, Marathi… whatever the other person speaks** — then hands you a summary.

Built on Sarvam AI — the same `sarvam-105b` model family that powers **Indus by Sarvam**.

| Job | Sarvam model |
|---|---|
| Ears (speech → text, code-mix, auto language) | `saaras:v4` |
| Brain (live turns + call planning) | `sarvam-105b-conversations` |
| Post-call summary | `sarvam-105b` |
| Voice (natural Indian voices) | `bulbul:v4-flash` / `bulbul:v3` |

## What it does
- Turns your task into a **checklist** and an opening line
- Talks turn-by-turn: listens (voice activity detection) → transcribes → decides → speaks
- **Follows language switches** (Kannada → Hindi mid-call)
- Plays natural fillers ("haan ji…") to hide thinking time
- Confirms numbers back, **never agrees to pay / share OTPs**, identifies itself as your assistant
- **Take over** button, live bilingual transcript, auto summary with next steps
- Type-only test mode (no mic / no one to call)

## Run
```bash
cd ai-caller
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                             # add SARVAM_API_KEY
.venv/Scripts/python -m uvicorn app:app --port 8000
```
Open http://localhost:8000 in Chrome/Edge and allow the microphone.

## Files
- `app.py` — FastAPI backend: `/api/plan`, `/api/turn`, `/api/summary`, `/api/fillers`
- `static/index.html` — setup → live call → summary UI
- `smoke_test.py` — checks STT, TTS and chat with your key
- `PLAN.md` — design notes

## Next
Real phone calls via **Indus Voice Agents** Instant Outbound API (no speakerphone), barge-in with streaming STT, "call 5 clinics and find a slot" batch mode.
