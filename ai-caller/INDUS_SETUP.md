# Real calls via Indus Voice Agents — one-time setup (~10 min)

Speakerphone mode works with just `SARVAM_API_KEY`. For **real calls** (Indus dials the number itself), set up one reusable agent in the Indus dashboard. Each call then passes its own task / facts / checklist into that agent.

## 1. Create the agent
1. Go to **indus.sarvam.ai** → **Build → Agents → Create from Scratch**. Name it `Mere Liye Call Kar`.
2. **Variables tab → Input variables** (any default value is fine):
   `caller_name`, `task`, `facts`, `checklist`
3. **Variables tab → Output variables** (optional, shown in call data):
   - `answers` (String) — "Short English answers to each checklist question"
   - `outcome` (String) — "One-line outcome of the call"
4. **Instructions tab → System prompt** — paste this, inserting each variable with `@` where shown:

```
You are a polite, warm female phone assistant calling ON BEHALF OF @caller_name.

TASK: @task
FACTS you may share: @facts
Find out each of these, one question at a time:
@checklist

Rules:
- Speak 1–2 short natural sentences per turn. Respectful local register (ji, sir/madam, anna, bhaiya).
- Reply in the language the other person speaks; switch if they switch.
- Repeat back numbers and dates to confirm.
- You are @caller_name's assistant — never claim to be them. You never visit or pay yourself; @caller_name does. If asked whether you are an AI, say yes, honestly.
- NEVER agree to pay, transfer money, or share OTPs, bank details or any info not in FACTS. If unsure, say you'll confirm with @caller_name.
- When everything is answered or they want to stop, thank them, say @caller_name will follow up, and end the call.
```

5. **Greeting**: anything short — our app overrides it per call with a generated opening line.
6. **Settings**: languages Hindi, Kannada, Tamil, Telugu, Marathi, Bengali, Gujarati, Malayalam… pick a female conversational voice.
7. **Test agent** once in the dashboard, then **publish** and note the **version number**.

## 2. Get a phone number
**Deploy → Phone Numbers** → rent a number (Sarvam/Vobiz) or bring your own telephony. Note the **number** and its **connection ID**.

## 3. Grab your IDs
- **Settings → API Key** → create an Indus API key (this is different from the `SARVAM_API_KEY`).
- **org_id**, **workspace_id**, **app_id** — visible in the dashboard URL / agent settings.

## 4. Expose the webhook
Indus posts the transcript to our server when the call ends, so it needs a public URL:
```bash
cloudflared tunnel --url http://localhost:8000
```
(or `ngrok http 8000`) and copy the `https://…` URL.

## 5. Fill `.env`
```
INDUS_API_KEY=...
INDUS_ORG_ID=...
INDUS_WORKSPACE_ID=...
INDUS_APP_ID=...
INDUS_APP_VERSION=1
INDUS_CONNECTION_ID=...
INDUS_AGENT_NUMBER=+91XXXXXXXXXX
PUBLIC_URL=https://your-tunnel.trycloudflare.com
```
Restart the server. The **☎️ Real call · Indus** tab unlocks.

## How a real call flows
1. You type the task + number → our app plans the checklist and opening line (`sarvam-105b-conversations`).
2. `POST apps.sarvam.ai/api/outbounds/v1/orgs/{org}/workspaces/{ws}/outbounds` with `agent_variables` + `initial_bot_message` + `initial_language_name`.
3. Indus rings the number and runs the conversation on its own telephony stack.
4. When it ends, Indus calls `PUBLIC_URL/api/webhook/indus` with status, duration, transcript and extracted variables.
5. Our app writes the summary (`sarvam-105b`) and the UI shows it (it polls every 3s).
