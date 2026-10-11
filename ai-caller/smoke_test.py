"""Quick check that TTS, STT and chat all work with the key in .env."""
import base64, json, os, time
import httpx
from dotenv import load_dotenv

load_dotenv()
KEY = os.environ["SARVAM_API_KEY"].strip()
H = {"api-subscription-key": KEY}
BASE = "https://api.sarvam.ai"

with httpx.Client(timeout=60) as c:
    t = time.time()
    r = c.post(f"{BASE}/text-to-speech", headers=H, json={
        "model": "bulbul:v4-flash", "text": "Namaste ji, main Arnav ki taraf se call kar rahi hoon. Kya room abhi khaali hai?",
        "language_code": "hi-IN", "speaker": "ritu_hi_conversation", "speech_sample_rate": 16000,
    })
    print("TTS", r.status_code, f"{time.time()-t:.2f}s", r.text[:200] if r.status_code != 200 else "")
    wav = base64.b64decode(r.json()["audios"][0])
    open("smoke.wav", "wb").write(wav)

    t = time.time()
    r = c.post(f"{BASE}/speech-to-text", headers=H,
               files={"file": ("smoke.wav", wav, "audio/wav")},
               data={"model": "saaras:v4", "language_code": "unknown"})
    print("STT", r.status_code, f"{time.time()-t:.2f}s", r.text[:300])

    for model in ["sarvam-105b-conversations", "sarvam-105b"]:
        t = time.time()
        r = c.post(f"{BASE}/v1/chat/completions", headers=H, json={
            "model": model, "reasoning_effort": "low", "max_tokens": 400,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Reply only as JSON: {\"say\": <one short Hindi sentence>, \"done\": false}"},
                {"role": "user", "content": "PG owner said: haan room khaali hai, 13 hazaar ka hai."},
            ],
        })
        print("CHAT", model, r.status_code, f"{time.time()-t:.2f}s", r.text[:500])
