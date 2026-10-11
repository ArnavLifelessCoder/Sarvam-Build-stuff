# Mere Liye Call Kar

An AI that makes everyday phone calls for you in Indian languages. Tell it what you need, check the plan, and it holds the conversation in whatever language the other person speaks, then hands you a summary.

Built on Sarvam: the same `sarvam-105b` family that powers **Indus by Sarvam**, plus Indus Voice Agents for real calls.

| Job | Model |
|---|---|
| Hearing (speech to text, code-mix, auto language) | `saaras:v4` |
| Planning + live replies | `sarvam-105b-conversations` |
| Post-call summary | `sarvam-105b` (reasoning off) |
| Voice | `bulbul:v4-flash` / `bulbul:v3` |
| Real calls | Indus Voice Agents, Instant Outbound API |

## Flow
1. **Describe**: type the task or say it in any Indian language (translated to English). Add facts it may share.
2. **Review**: it drafts an opening line and a checklist. Edit, remove or add questions before dialing.
3. **Call**:
   - *Speakerphone*: your phone on speaker next to the laptop. The loop is listen, transcribe, decide, speak, with fillers covering the thinking time.
   - *Real call*: Indus dials the number from your Sarvam line. The transcript comes back by webhook.
4. **Summary**: facts, next steps and anything unanswered. Share to WhatsApp, copy, download the transcript, or call again. Every call is kept in history.

## Features
- Follows language switches mid-call (Kannada to Hindi)
- Repeats numbers back to confirm, never agrees to pay or shares OTPs, introduces itself as your assistant
- **Take over / hand back** at any point. **Whisper** an instruction it acts on without the other person hearing it
- **Patience slider**: how long it waits after they stop talking (0.6 to 2.4s)
- Live mic level, checklist progress, bilingual transcript
- Retries Sarvam calls on 429/5xx (the Indus dial is never retried, so a call is never placed twice)
- Remembers your name, language, number, theme and draft; recent numbers autocomplete
- Shortcuts: `Ctrl+Enter` prepare / start, `Space` take over, `Esc` end
- Type-only test mode when there's no mic or no one to call
- Light and dark themes; landing page at `/`, app at `/app`

## Run
```bash
cd ai-caller
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
cp .env.example .env                             # add SARVAM_API_KEY
.venv/Scripts/python -m uvicorn app:app --port 8000
```
Open http://localhost:8000 (landing) or http://localhost:8000/app in Chrome or Edge, and allow the microphone.

For real calls, follow [INDUS_SETUP.md](INDUS_SETUP.md) (one Indus agent, a phone number, a tunnel for the webhook).

## Deploy (Vercel)
1. Import the repo on vercel.com, set **Root Directory** to `ai-caller` (framework preset: Other).
2. Add env var `SARVAM_API_KEY` (and `WEBHOOK_TOKEN` + the `INDUS_*` vars for real calls; `PUBLIC_URL` = your Vercel URL, so no tunnel is needed).
3. Deploy. HTTPS means the mic works on phones too.

Notes: history lives in `/tmp` on Vercel, so it resets on cold starts and isn't shared across instances. For reliable real-call tracking in production, move `calls.json` to Vercel KV or a database. Anyone with the URL can spend your Sarvam credits, so keep the link private.

## API
| Route | Does |
|---|---|
| `POST /api/plan` | Task to callee, checklist and opening line |
| `POST /api/tts` | Text to base64 WAV (opening line is prefetched during review) |
| `POST /api/turn` | One speakerphone turn: audio or text (+ optional whisper) to reply, updated checklist and audio |
| `POST /api/summary` | Transcript to summary; saves the call to history |
| `POST /api/real-call` | Reviewed plan + phone number to an Indus outbound call |
| `POST /api/webhook/indus` | Indus end-of-call webhook (token-checked) to summary |
| `GET/DELETE /api/calls[/{id}]` | Call history (stored in `calls.json`) |
| `POST /api/dictate` | Spoken task in any language to English text |
| `GET /api/fillers`, `/api/languages`, `/api/config` | Filler clips, languages, real-call readiness |

## Files
- `app.py`: FastAPI backend
- `static/landing.html`: landing page
- `static/app.html`: the app (setup, review, call, summary)
- `static/base.css`: shared design tokens (paper and ink, one green accent; IBM Plex + Instrument Serif)
- `INDUS_SETUP.md`: real-call setup
- `smoke_test.py`: checks STT, TTS and chat with your key
- `PLAN.md`: original design notes

## Next
Barge-in with streaming STT, batch mode ("call 5 clinics, find a slot today").
