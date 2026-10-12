# Quickstart — run & test in VS Code

The LERNA Voice AI Service is a standalone FastAPI + WebSocket app. This gets it
running locally in a few minutes.

## 1. Prerequisites
- Python **3.12+** (developed on 3.13).
- VS Code with the Python extension.

## 2. Set up
```bash
cd voice-ai
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then edit .env
```

## 3. Keys (all optional — it runs offline without any)
| You want… | Put in `.env` |
|---|---|
| Lesson "brain" (primary) | `OPENROUTER_API_KEY` |
| Lesson "brain" (fallback) | `GEMINI_API_KEY` |
| Primary voice | `AZURE_SPEECH_KEY` + `AZURE_SPEECH_REGION` |
| **Backup voice (auto-failover)** | `FISH_AUDIO_API_KEY` |
| Persistence | `MONGODB_URI` |

With no keys it still teaches using the offline mock dialogue + mock voice, so you
can exercise the whole flow without spending anything.

## 4. Run the tests
```bash
pytest tests -v          # 412 tests
```

## 5. Run the service
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```
- Catalogue / console: http://127.0.0.1:8080/
- Health + configured providers: http://127.0.0.1:8080/health/providers
- Interactive Streamlit console: `streamlit run streamlit_app/Home.py`

> The browser microphone only works on a **top-level tab** (http/localhost), not
> inside a sandboxed preview iframe.

## 5b. Run on Windows — PowerShell / VS Code

One command does everything (venv + deps + `.env` + start on :3000):

```powershell
.\run.ps1
```

Or step by step (if you prefer, or if `run.ps1` is blocked):

```powershell
cd voice-ai
python -m venv .venv                       # create once
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env                     # runs with ZERO keys on the offline mock
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Then open **http://localhost:3000** (catalogue / console). The microphone needs a
top-level tab, not a sandboxed iframe.

Notes:
- We call `.\.venv\Scripts\python.exe` directly so you never need to "activate"
  (avoids the PowerShell execution-policy prompt). If you do want to activate:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then `.\.venv\Scripts\activate`.
- `.env` with no keys = fully offline (mock tutor + mock voice) — great for testing
  the flow. Add real keys (OpenRouter/Gemini/Azure/Fish) to go live.
- `VOICE_AUTH_REQUIRED=false` by default so the console works locally. Set
  `VOICE_SERVICE_API_KEY` (+ `true`) only when integrating behind your backend.

## 6. What is wired
- **Brain:** OpenRouter primary, Gemini fallback (`LLM_PRIORITY=openrouter,gemini`).
- **Voice:** Azure primary; **Fish Audio fails over automatically** if Azure breaks
  before speaking (Azure → Fish → ElevenLabs → Gemini → Deepgram).
- **Conversation policy:** unclear → ask to repeat (×3) → ask to type → "I didn't
  get your point"; impolite → warn once → end the lesson on the second time.
- **Lessons from uploads:** `POST /voice/material` ingests a student's material and
  returns a `document_id`; send it in the WS `start` frame as `document_ids`.

## 7. Deploy
See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) (Docker / `docker compose up --build`)
and [`deploy/README.md`](deploy/README.md) §1b for **Railway** (Dockerfile path,
`PORT` injection, healthcheck `/health`, variables)
and [`docs/BACKEND_HANDOFF.md`](docs/BACKEND_HANDOFF.md) for the LERNA backend
integration contract (endpoints, tokens, sequence).
