# Mere Liye Call Kar — AI Caller (Build Plan)

An AI agent that holds a phone conversation **for you** in Indian languages, gets the info you need, and hands you a summary.
Built on Sarvam's stack — the same `sarvam-105b` family that powers **Indus by Sarvam**.

Demo setup (v1): your phone call is on **speaker** next to the laptop. The laptop is the agent's ears (mic) and mouth (speaker).

---

## 1. Stack

| Job | Sarvam API | Model |
|---|---|---|
| Ears — speech → text (code-mix, auto language detect) | `POST /speech-to-text` | `saaras:v4`, `language_code=unknown` |
| Brain — decide what to say next | `POST /v1/chat/completions` | `sarvam-105b-conversations` (voice-agent variant), `sarvam-105b` for planning + summary |
| Mouth — text → natural Indian voice | `POST /text-to-speech` | `bulbul:v4-flash` |

- Backend: **Python + FastAPI** (keeps API key server-side)
- Frontend: **single `index.html`** (vanilla JS, MediaRecorder + Web Audio for silence detection)
- Auth: `api-subscription-key` header (chat also accepts `Authorization: Bearer`)

## 2. File layout

```
sarvam/
├── .env               # SARVAM_API_KEY=...   (gitignored)
├── .env.example
├── .gitignore
├── requirements.txt   # fastapi, uvicorn, httpx, python-dotenv, python-multipart
├── app.py             # API routes + Sarvam calls + agent prompts
├── static/
│   └── index.html     # setup screen + live call screen + summary
└── PLAN.md
```

## 3. Flow

```
[Setup]  task + your facts + language
   │
   ▼  POST /api/plan  (sarvam-105b)
[Plan]   checklist of info to collect + opening line
   │
   ▼  loop ───────────────────────────────────────────┐
[Speak]  POST /api/tts → play through laptop speaker  │
[Listen] mic ON, record until ~1.2s silence            │
[Hear]   POST /api/turn: STT → transcript + language   │
[Think]  sarvam-105b-conversations → JSON:             │
         {say, say_en, heard_en, checklist_updates,    │
          language, done}                              │
   └───────────── if not done ─────────────────────────┘
   │
   ▼  POST /api/summary  (sarvam-105b)
[Summary] key facts card + full bilingual transcript
```

## 4. Backend endpoints (`app.py`)

| Route | Input | Does | Output |
|---|---|---|---|
| `POST /api/plan` | task, facts, language, your name | LLM builds checklist + opening line | `{checklist[], opening, opening_en}` |
| `POST /api/turn` | audio blob + call state (history, checklist, language) | STT → LLM next move | `{heard, heard_en, say, say_en, checklist, language, done}` |
| `POST /api/tts` | text, language | Bulbul TTS | base64 WAV |
| `POST /api/summary` | full history + checklist | LLM final summary | `{summary_points[], next_steps[]}` |
| `GET /api/fillers` | language | pre-generated "haan ji…", "achha, ek second" clips | base64 WAVs (cached) |

LLM calls use `response_format: json_object` and low `reasoning_effort` on the per-turn call for speed.

## 5. Agent prompt rules (system prompt)

- You are **{name}'s assistant**, calling on their behalf. Say so in the opening line — never pretend to be {name}.
- Short, natural spoken sentences (1–2 per turn). Polite local register ("ji", "saar", "anna" as fits).
- Speak whatever language the other person speaks; switch if they switch.
- Work through the checklist; ask one thing at a time; confirm numbers back ("12,000 bola na?").
- **Never**: agree to pay, share OTP / bank / address details beyond what's in facts, make commitments not in facts.
- If they ask something not in facts → "Main confirm karke batati hoon."
- End politely once checklist is done or the person wants to stop → `done: true`.

## 6. Frontend (`index.html`)

**Screen 1 — Setup**
- Task textbox ("Ask the PG owner if a single room is free under ₹12k, with food?")
- Your facts textbox (name, budget, move-in date, area)
- Language dropdown (Auto / Hindi / Kannada / Tamil / Telugu / Marathi / Bengali / …)
- Example chips: PG enquiry · Gas cylinder booking · Clinic appointment · Tailor/dhobi follow-up
- **Start call** button

**Screen 2 — Live call**
- Big status orb: 🎧 Listening · 🤔 Thinking · 🗣️ Speaking
- Chat bubbles: original language + small English line under each
- Checklist panel: items tick ✅ with the collected value
- Buttons: **Take over** (agent goes silent) · **End call**

**Screen 3 — Summary**
- Key facts card + next steps
- Full transcript, copy button

**Audio mechanics**
- Half-duplex: mic muted while agent speaks (no self-echo)
- Silence detection via `AnalyserNode` RMS threshold, ~1.2s hang time, 20s max per turn
- Filler clip plays immediately after the other person stops → hides LLM + TTS latency

## 7. Build order & timeline (~60 min)

| # | Time | Task | Done when |
|---|---|---|---|
| 1 | 0–8 | Scaffold files, `.env`, venv, install deps | server runs on `localhost:8000` |
| 2 | 8–15 | Smoke-test all 3 Sarvam APIs from Python | STT transcribes a clip, TTS returns audio, chat returns JSON |
| 3 | 15–30 | `/api/plan`, `/api/turn`, `/api/tts`, `/api/summary` + prompts | curl round-trip works |
| 4 | 30–45 | Frontend: setup → live loop → summary | full loop talking to yourself in browser |
| 5 | 45–55 | Fillers, take-over, language follow, polish | feels natural |
| 6 | 55–60 | Real test: call a friend on speaker | summary is correct |

## 8. Known limits (v1)

- Half-duplex — no barge-in (interrupting the agent).
- ~2–4s per turn; filler clips mask most of it.
- Speaker-to-mic audio is lossy; quiet room helps.
- TTS covers 11 languages (bn, en, gu, hi, kn, ml, mr, od, pa, ta, te); STT covers 22.

## 9. v2 ideas

- Real telephony via **Exotel** (Indian numbers) + Sarvam streaming STT/TTS → no speakerphone, true calls.
- Barge-in with streaming STT.
- Batch mode: "call these 5 clinics, tell me who has a slot today."
- Call history + reminders from summaries.

## 10. What's needed from you

1. Sarvam API key → paste into `.env` (never in chat).
2. Python 3.10+.
3. Chrome / Edge (mic permission).
