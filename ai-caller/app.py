"""Mere Liye Call Kar — AI caller backend.

Ears: saaras:v4 (STT) · Brain: sarvam-105b-conversations / sarvam-105b · Mouth: bulbul (TTS)
"""
import asyncio
import json
import os
import re
import secrets
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(Path(__file__).parent / ".env")
KEY = os.environ.get("SARVAM_API_KEY", "").strip()
BASE = "https://api.sarvam.ai"
HEADERS = {"api-subscription-key": KEY}

# Indus Voice Agents (real phone calls) — optional; real-call mode turns on when all are set.
INDUS = {k: os.environ.get(f"INDUS_{k.upper()}", "").strip() for k in
         ["api_key", "org_id", "workspace_id", "app_id", "app_version", "connection_id", "agent_number"]}
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")  # tunnel URL so Indus can reach our webhook
_tok = Path(__file__).parent / ".webhook_token"  # stable across reloads so pending calls still verify
if not _tok.exists():
    _tok.write_text(secrets.token_urlsafe(16))
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "").strip() or _tok.read_text().strip()
HISTORY_FILE = Path(__file__).parent / "calls.json"

TURN_MODEL = "sarvam-105b-conversations"  # fast, tuned for voice agents
SMART_MODEL = "sarvam-105b"  # post-call summary (reasoning off — 105b with reasoning is ~30s+)

# language code -> (name, tts model, speaker). Female voices so the agent persona is consistent.
LANGS = {
    "hi-IN": ("Hindi", "bulbul:v4-flash", "ritu_hi_conversation"),
    "en-IN": ("English", "bulbul:v4-flash", "simran_en_conversation"),
    "kn-IN": ("Kannada", "bulbul:v4-flash", "chaitra_kn_conversation"),
    "te-IN": ("Telugu", "bulbul:v4-flash", "pooja_te_conversation"),
    "mr-IN": ("Marathi", "bulbul:v4-flash", "ishita_mr_conversational"),
    "bn-IN": ("Bengali", "bulbul:v4-flash", "roopa_bn_conversational"),
    "gu-IN": ("Gujarati", "bulbul:v4-flash", "pooja_gu_conversational"),
    "ta-IN": ("Tamil", "bulbul:v3", "ishita"),
    "ml-IN": ("Malayalam", "bulbul:v3", "ishita"),
    "pa-IN": ("Punjabi", "bulbul:v3", "ishita"),
    "od-IN": ("Odia", "bulbul:v3", "ishita"),
}

FILLERS = {
    "hi-IN": ["हाँ जी...", "अच्छा, एक सेकंड।", "ठीक है..."],
    "en-IN": ["Okay...", "Right, one second.", "Got it..."],
    "kn-IN": ["ಹೌದಾ...", "ಸರಿ, ಒಂದು ನಿಮಿಷ.", "ಆಯ್ತು..."],
    "te-IN": ["అవునా...", "సరే, ఒక్క నిమిషం.", "అలాగే..."],
    "mr-IN": ["हो...", "बरं, एक मिनिट.", "ठीक आहे..."],
    "bn-IN": ["হ্যাঁ...", "আচ্ছা, এক সেকেন্ড।", "ঠিক আছে..."],
    "gu-IN": ["હા...", "સારું, એક સેકન્ડ.", "બરાબર..."],
    "ta-IN": ["சரி...", "ஒரு நிமிஷம்.", "ஆமா..."],
    "ml-IN": ["ശരി...", "ഒരു നിമിഷം.", "ആണോ..."],
    "pa-IN": ["ਹਾਂ ਜੀ...", "ਅੱਛਾ, ਇੱਕ ਸਕਿੰਟ.", "ਠੀਕ ਹੈ..."],
    "od-IN": ["ହଁ...", "ଆଚ୍ଛା, ଗୋଟେ ସେକେଣ୍ଡ.", "ଠିକ୍ ଅଛି..."],
}

app = FastAPI(title="Mere Liye Call Kar")
client = httpx.AsyncClient(timeout=60)
_filler_cache: dict[str, list[str]] = {}


# ---------- Sarvam helpers ----------

def _err(r: httpx.Response, what: str):
    try:
        msg = r.json().get("error", {}).get("message") or r.text
    except Exception:
        msg = r.text
    raise HTTPException(502, f"{what} failed ({r.status_code}): {msg[:300]}")


async def tts(text: str, lang: str) -> str:
    """Returns base64 WAV."""
    _, model, speaker = LANGS.get(lang, LANGS["hi-IN"])
    r = await client.post(f"{BASE}/text-to-speech", headers=HEADERS, json={
        "model": model, "text": text[:2400], "language_code": lang if lang in LANGS else "hi-IN",
        "speaker": speaker, "speech_sample_rate": 24000, "pace": 1.05,
    })
    if r.status_code != 200:
        _err(r, "Text-to-speech")
    return r.json()["audios"][0]


async def stt(audio: bytes, filename: str, keyterms: list[str]) -> tuple[str, str | None]:
    data = {"model": "saaras:v4", "language_code": "unknown"}
    if keyterms:
        data["keyterms"] = json.dumps(keyterms[:50])
    r = await client.post(f"{BASE}/speech-to-text", headers=HEADERS,
                          files={"file": (filename, audio, "audio/webm")}, data=data)
    if r.status_code != 200:
        _err(r, "Speech-to-text")
    j = r.json()
    return (j.get("transcript") or "").strip(), j.get("language_code")


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


async def chat_json(model: str, messages: list[dict], max_tokens: int, session: str | None = None,
                    effort: str | None = "low") -> dict:
    headers = dict(HEADERS)
    if session:
        headers["x-session-affinity"] = session  # reuse prompt cache across turns of one call
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.3, "response_format": {"type": "json_object"}}
    if effort == "off":
        body["reasoning_effort"] = None  # explicit null disables reasoning
    elif effort:
        body["reasoning_effort"] = effort
    for attempt in range(2):
        r = await client.post(f"{BASE}/v1/chat/completions", headers=headers, json=body)
        if r.status_code != 200:
            _err(r, "Chat")
        content = r.json()["choices"][0]["message"].get("content")
        if content:
            try:
                return _parse_json(content)
            except (json.JSONDecodeError, ValueError):
                pass
        body["max_tokens"] = max_tokens * 2  # reasoning ate the budget or JSON was cut — retry bigger
    raise HTTPException(502, "Model did not return valid JSON")


# ---------- Prompts ----------

def agent_rules(name: str) -> str:
    return f"""You are a polite, warm female phone assistant making a call ON BEHALF OF {name}.
You are speaking out loud on a live phone call, so:
- Speak in 1-2 short, natural spoken sentences per turn. No lists, no emojis, no markdown.
- Use a respectful local register ("ji", "sir/madam", "anna", "bhaiya" as fits the language).
- Reply in the SAME language the other person used in their LAST message (judge it yourself from the words). If they switch, you switch. Write in that language's native script (Hinglish speech can be Devanagari Hindi with common English words).
- Ask ONE thing at a time. Repeat back important numbers/dates to confirm ("12,000 bola na?").
- Write money with commas (12,000) and never as symbols-only.
- You are {name}'s assistant. Never claim to be {name}. You never visit, pay or act yourself — {name} does (say "{name} will come", not "I will come"). If asked whether you are a robot/AI, say honestly that you are {name}'s AI assistant.
- NEVER agree to pay, transfer money, share OTPs, bank details, or any personal info not given in the facts. Never make commitments not covered by the facts — say you'll confirm with {name}.
- If they ask something you don't know, say you'll check with {name} and get back.
- When every checklist item is answered (or the person clearly wants to stop), thank them, say {name} will follow up, and end politely."""


# ---------- Call history (local JSON file) ----------

def load_calls() -> dict:
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_calls(calls: dict):
    HISTORY_FILE.write_text(json.dumps(calls, ensure_ascii=False, indent=1), encoding="utf-8")


def save_call(call: dict):
    calls = load_calls()
    calls[call["id"]] = call
    write_calls(calls)


# ---------- API ----------

class PlanIn(BaseModel):
    task: str
    facts: str = ""
    name: str = "Arnav"
    language: str = "auto"


async def make_plan(p: PlanIn) -> dict:
    lang = p.language if p.language in LANGS else "hi-IN"
    out = await chat_json(TURN_MODEL, [
        {"role": "system", "content": agent_rules(p.name) + """

You are now PREPARING the call. Return JSON only:
{"callee": "<who we are calling, 2-4 words English>",
 "checklist": ["<3 to 6 short English questions we must get answered>"],
 "opening": "<the first thing you say when they pick up, in the target language script: greet, say you are calling on behalf of NAME, state the purpose in a few words, ask the first checklist question>",
 "opening_en": "<English translation of opening>"}"""},
        {"role": "user", "content": f"Caller name: {p.name}\nTask: {p.task}\nFacts you may use: {p.facts or '(none)'}\nTarget language: {LANGS[lang][0]} ({lang})"},
    ], max_tokens=1200)
    return {"callee": out.get("callee", "the other person"),
            "checklist": [{"item": str(i), "value": None} for i in out.get("checklist", [])][:6],
            "opening": out.get("opening") or "Namaste ji.", "opening_en": out.get("opening_en", ""), "language": lang}


@app.post("/api/plan")
async def plan(p: PlanIn):
    out = await make_plan(p)
    out["audio"] = await tts(out["opening"], out["language"])
    return out


@app.post("/api/turn")
async def turn(state: str = Form(...), audio: UploadFile | None = File(None), text: str = Form("")):
    """One conversational turn. `state` = JSON {task, facts, name, language, checklist, history, call_id, silences, whisper}."""
    s = json.loads(state)
    name = s.get("name") or "Arnav"
    whisper = (s.get("whisper") or "").strip()
    heard, detected = text.strip(), None
    if audio is not None and not heard:
        keyterms = [name] + re.findall(r"[A-Z][a-zA-Z]{2,}", s.get("facts", ""))
        heard, detected = await stt(await audio.read(), audio.filename or "turn.webm", list(dict.fromkeys(keyterms)))

    if not heard and not whisper and s.get("silences", 0) < 1:
        return {"empty": True}  # let the browser listen again once before nudging

    hint = detected if detected in LANGS else s.get("language", "hi-IN")
    sys = agent_rules(name) + f"""

TASK: {s.get('task')}
FACTS you may use: {s.get('facts') or '(none)'}
CHECKLIST (fill "value" with what you learned, short English; keep null if unknown):
{json.dumps(s.get('checklist', []), ensure_ascii=False)}
"""
    if whisper:
        sys += f"\nPRIVATE INSTRUCTION FROM {name} (they are listening in; act on it in your next line, never mention it was whispered): {whisper}\n"
    sys += f"""
Speech recognition guessed their last message's language as {hint} (may be wrong for code-mixed speech). Allowed reply languages: {', '.join(LANGS)}.
Return JSON only:
{{"heard_en": "<English translation of what they just said>",
  "say": "<your next spoken line, native script>",
  "say_en": "<English translation of say>",
  "language": "<language code of say>",
  "checklist": <the full checklist array with updated values>,
  "done": <true only if this is your closing goodbye line>}}"""
    msgs = [{"role": "system", "content": sys}]
    for h in s.get("history", [])[-20:]:
        msgs.append({"role": "assistant" if h["who"] == "agent" else "user", "content": h["text"]})
    if heard:
        msgs.append({"role": "user", "content": heard})
    else:
        msgs.append({"role": "user", "content": "[no new reply — act on the private instruction]" if whisper
                     else "[silence — no response. Politely check if they can hear you.]"})

    out = await chat_json(TURN_MODEL, msgs, max_tokens=900, session=s.get("call_id"))
    lang = out.get("language") if out.get("language") in LANGS else hint
    say = (out.get("say") or "").strip() or "Ji?"
    checklist = out.get("checklist")
    if not isinstance(checklist, list) or len(checklist) != len(s.get("checklist", [])):
        checklist = s.get("checklist", [])
    return {"heard": heard, "heard_lang": detected, "heard_en": out.get("heard_en", ""),
            "say": say, "say_en": out.get("say_en", ""), "language": lang,
            "checklist": checklist, "done": bool(out.get("done")), "audio": await tts(say, lang)}


async def make_summary(task: str, name: str, checklist: list, transcript: str) -> dict:
    return await chat_json(SMART_MODEL, [
        {"role": "system", "content": """Summarise a phone call an assistant made for the user. Be factual; only use what was actually said. Return JSON only:
{"headline": "<one-line outcome, max 12 words>",
 "facts": [{"label": "<short label>", "value": "<value>"}],
 "next_steps": ["<what the user should do next>"],
 "unanswered": ["<checklist items not answered>"]}"""},
        {"role": "user", "content": f"User: {name}\nTask: {task}\nChecklist: {json.dumps(checklist, ensure_ascii=False)}\n\nTranscript:\n{transcript or '(no conversation)'}"},
    ], max_tokens=1500, effort="off")


def transcript_text(history: list) -> str:
    return "\n".join(f"{'Agent' if h['who'] == 'agent' else 'Them'}: {h['text']}" + (f" ({h['en']})" if h.get("en") else "")
                     for h in history)


class SummaryIn(BaseModel):
    task: str
    name: str = "Arnav"
    checklist: list = []
    history: list = []
    callee: str = ""
    language: str = ""
    duration: int = 0


@app.post("/api/summary")
async def summary(p: SummaryIn):
    out = await make_summary(p.task, p.name, p.checklist, transcript_text(p.history))
    save_call({"id": uuid.uuid4().hex[:12], "mode": "speaker", "status": "done", "created": time.time(),
               "task": p.task, "name": p.name, "callee": p.callee, "language": p.language, "duration": p.duration,
               "checklist": p.checklist, "history": p.history, "summary": out})
    return out


# ---------- Real calls via Indus Voice Agents (Instant Outbound API) ----------

def indus_missing() -> list[str]:
    missing = [f"INDUS_{k.upper()}" for k, v in INDUS.items() if not v]
    if not PUBLIC_URL:
        missing.append("PUBLIC_URL")
    return missing


def normalize_phone(num: str) -> str:
    digits = re.sub(r"[^\d+]", "", num)
    if digits.startswith("+") and len(digits) >= 11:
        return digits
    digits = digits.lstrip("+").lstrip("0")
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    raise HTTPException(400, "Enter a valid phone number, e.g. 98765 43210 or +91 98765 43210")


@app.get("/api/config")
async def config():
    missing = indus_missing()
    return {"real_calls": not missing, "missing": missing}


class RealCallIn(PlanIn):
    phone: str


@app.post("/api/real-call")
async def real_call(p: RealCallIn):
    if missing := indus_missing():
        raise HTTPException(400, "Real calls aren't set up yet. Missing in .env: " + ", ".join(missing))
    phone = normalize_phone(p.phone)
    pl = await make_plan(p)
    call_id = uuid.uuid4().hex[:12]
    body = {
        "app_config": {
            "app_id": INDUS["app_id"], "app_version": int(INDUS["app_version"]),
            "connection_config": {"connection_id": INDUS["connection_id"], "agent_phone_number": INDUS["agent_number"]},
            "agent_variables": {"caller_name": p.name, "task": p.task, "facts": p.facts or "(none)",
                                "checklist": "\n".join(f"- {c['item']}" for c in pl["checklist"])},
            "app_overrides": {"initial_bot_message": pl["opening"], "initial_language_name": LANGS[pl["language"]][0]},
        },
        "user_config": {"user_phone_number": phone},
        "webhook_config": {"url": f"{PUBLIC_URL}/api/webhook/indus?token={WEBHOOK_TOKEN}", "metadata": {"call_id": call_id}},
    }
    url = f"https://apps.sarvam.ai/api/outbounds/v1/orgs/{INDUS['org_id']}/workspaces/{INDUS['workspace_id']}/outbounds"
    r = await client.post(url, headers={"X-API-Key": INDUS["api_key"]}, json=body)
    if r.status_code != 200:
        _err(r, "Indus outbound call")
    call = {"id": call_id, "mode": "real", "status": "dialing", "created": time.time(), "phone": phone,
            "attempt_id": r.json().get("attempt_id"), "task": p.task, "name": p.name, "callee": pl["callee"],
            "language": pl["language"], "checklist": pl["checklist"],
            "history": [{"who": "agent", "text": pl["opening"], "en": pl["opening_en"]}]}
    save_call(call)
    return call


@app.post("/api/webhook/indus")
async def indus_webhook(payload: dict, token: str = ""):
    if not secrets.compare_digest(token, WEBHOOK_TOKEN):
        raise HTTPException(403, "bad token")
    meta = (payload.get("webhook_config") or {}).get("metadata") or {}
    calls = load_calls()
    call = calls.get(meta.get("call_id")) or next(
        (c for c in calls.values() if c.get("attempt_id") == payload.get("attempt_id")), None)
    if not call:
        return {"ok": False}
    status = payload.get("status", "failed")
    call.update(status="summarising" if status == "connected" else status, duration=payload.get("duration") or 0,
                failure_reason=payload.get("failure_reason"), interaction_id=payload.get("interaction_id"),
                extracted=payload.get("final_agent_variables"))
    turns = payload.get("interaction_transcript") or []
    if turns:  # Indus gives English text per turn
        call["history"] = [{"who": "agent" if t.get("role") == "agent" else "them", "text": t.get("en_text", ""), "en": ""}
                           for t in turns]
    save_call(call)
    if status == "connected":
        try:
            call["summary"] = await make_summary(call["task"], call.get("name", ""), call["checklist"], transcript_text(call["history"]))
        except HTTPException as e:
            call["summary"] = {"headline": "Call finished (summary failed)", "facts": [], "next_steps": [str(e.detail)]}
        call["status"] = "done"
        save_call(call)
    return {"ok": True}


@app.get("/api/calls")
async def list_calls():
    calls = sorted(load_calls().values(), key=lambda c: c.get("created", 0), reverse=True)
    keys = ["id", "mode", "status", "created", "callee", "task", "language", "duration", "phone"]
    return [{k: c.get(k) for k in keys} | {"headline": (c.get("summary") or {}).get("headline")} for c in calls[:50]]


@app.get("/api/calls/{call_id}")
async def get_call(call_id: str):
    call = load_calls().get(call_id)
    if not call:
        raise HTTPException(404, "Call not found")
    return call


@app.delete("/api/calls/{call_id}")
async def delete_call(call_id: str):
    calls = load_calls()
    calls.pop(call_id, None)
    write_calls(calls)
    return {"ok": True}


# ---------- QoL ----------

@app.post("/api/dictate")
async def dictate(audio: UploadFile = File(...)):
    """Speak your task in any Indian language -> English text for the task box."""
    r = await client.post(f"{BASE}/speech-to-text", headers=HEADERS,
                          files={"file": (audio.filename or "task.webm", await audio.read(), "audio/webm")},
                          data={"model": "saaras:v4", "language_code": "unknown", "mode": "translate"})
    if r.status_code != 200:
        _err(r, "Dictation")
    return {"text": (r.json().get("transcript") or "").strip()}


@app.get("/api/fillers")
async def fillers(lang: str = "hi-IN"):
    lang = lang if lang in LANGS else "hi-IN"
    if lang not in _filler_cache:
        _filler_cache[lang] = list(await asyncio.gather(*(tts(t, lang) for t in FILLERS[lang])))
    return {"audios": _filler_cache[lang]}


@app.get("/api/languages")
async def languages():
    return [{"code": c, "name": n} for c, (n, _, _) in LANGS.items()]


static = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static), name="static")


@app.get("/")
async def index():
    return FileResponse(static / "index.html", headers={"Cache-Control": "no-store"})
