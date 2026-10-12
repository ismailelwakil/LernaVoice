# Providers

## Azure AI Speech — the official free-tier voice

`AzureTTSProvider` (`app/providers/azure/tts.py`) speaks one HTTP call per line and
returns `riff-<rate>khz-16bit-mono-pcm`, whose 44-byte WAV header is stripped so the
client receives the same PCM16 as every other path. Free tier **F0** allows **0.5M
characters/month** (≈ 8 hours of speech), 20 requests/60 s, 1 concurrent request,
10 minutes max per request; quotas are a hard cap and are not adjustable.

| Language | Voice |
|---|---|
| Arabic (fusHa) | `ar-SA-ZariyahNeural` (or `ar-SA-HamedNeural`) |
| English | `en-US-AvaMultilingualNeural` |
| French | `fr-FR-DeniseNeural` |
| Swahili | `sw-KE-ZuriNeural` |
| Amharic | `am-ET-MekdesNeural` |
| Somali | `so-SO-UbaxNeural` |
| Zulu | `zu-ZA-ThandoNeural` |

Arabic is taught in fusHa and spoken with `ar-SA-ZariyahNeural`
(`AZURE_VOICE_OVERRIDES=ar:ar-SA-HamedNeural` swaps it; an `ar-MSA:` override key
wins over the plain `ar` one). The SSML is written to sound like a tutor, not an
announcement: `mstts:express-as style="cheerful"` (degrades to plain prosody if a
voice refuses it), a `+2%` pitch lift, a short `<break>` at sentence and clause
boundaries, and moderate `<emphasis>` on the English technical terms. Tune with
`AZURE_TTS_STYLE`, `AZURE_TTS_PITCH`, `AZURE_TTS_PAUSES`.

**Coverage is 7 of the 10 mandatory languages** — Hausa, Yoruba and Igbo have no
Azure neural voice (the same catalogue the browser's "Natural" voices come from, and
the same seven that `edge-tts` exposes). Those three keep the Gemini/composed path.
Override any voice with `AZURE_VOICE_OVERRIDES=ar:ar-SA-HamedNeural,en:en-US-JennyNeural`.

With Azure configured, `VOICE_DEMO_VOICE=auto` picks **Azure before ElevenLabs**: 0.5M
characters a month is ~50× the talking time of ElevenLabs' free 10 000 credits.

The demo voice is **coverage-gated** (`CoverageGatedTTS`): a vendor is only asked
to speak a language it actually has a voice for (`vendor_covers_language`). Azure
declines Hausa, Yoruba and Igbo; ElevenLabs declines Igbo and Yoruba. Without the
gate the vendor raises `unsupported`, and on a composed pipeline the router reads
that as a *provider failure* - it fails the pipeline over mid-turn and the answer
arrives silent. With it, those languages simply keep the synthetic voice the
pipeline already had.

## A human voice for the offline demo (`VOICE_DEMO_VOICE`)

The dialogue can run with no vendor at all (offline policy, no paid credentials)
while the **speech** still comes from a real text-to-speech vendor. That is the
difference between a tutor talking and a checklist being read out: same words,
different voice.

| `VOICE_DEMO_VOICE` | Behaviour |
|---|---|
| `auto` (default) | ElevenLabs when `ELEVENLABS_API_KEY` is set, otherwise the synthetic demo voice |
| `elevenlabs` | Require it; a per-turn vendor failure still falls back to the synthetic voice and is counted in `tts_fallbacks` |
| `off` | Never call a vendor from the mock path |

How it is wired: `ProviderFactory.build_pipeline()` calls
`app/voice/demo_voice.attach_demo_voice()`, which attaches the TTS provider to a
**mock** realtime provider (or swaps the TTS leg of a composed mock pipeline) —
so it also covers a failover *into* the mock mid-lesson. Live pipelines are never
touched: `gemini-3.8-live` already is the voice.

The text handed to the vendor is the same `speakable()` form the browser receives,
so the voice says *"mid equals low plus high divided by 2"*, not punctuation
names. `/health` reports `demo_voice: "elevenlabs:eleven_v4_turbo"` (never a key),
the demo screen then plays the service audio, and `GET /voice/voices` lists the
voices on the account so the browser can offer a choice without ever seeing the
key.

Verify it in one command:

```bash
python3 tools/verify_elevenlabs_voice.py --list      # which voices exist
python3 tools/verify_elevenlabs_voice.py ar          # Arabic sample + .wav
python3 tools/verify_elevenlabs_voice.py --all       # every covered language
```

### Two transports, decided per language (verified against the live API)

| | Streamed (`ws`) | One call per line (`rest`) |
|---|---|---|
| Endpoint | `wss://…/{voice}/stream-input` | `POST https://…/{voice}` |
| Model | `eleven_multilingual_v2` | whatever `ELEVENLABS_TTS_MODEL` says (`eleven_v4_turbo`) |
| Languages | the 32 in `STREAMING_LANGUAGES` (en/ar/fr of ours) | everything ElevenLabs covers (adds sw/am/ha/so/zu) |
| First audio | **666–1048 ms** measured (en/ar/fr) | **599–1032 ms** for one short line, ~2 s for a full paragraph |
| Why | fast start matters in a conversation | the v4 family **rejects the stream-input socket with HTTP 400** — verified for every output format |

`ELEVENLABS_TRANSPORT=auto|stream|rest` (default `auto`) chooses; the provider falls
back to REST automatically if a socket is refused, and never restarts a line it has
already begun speaking.

### Free-plan gotchas (found the hard way)

* **Library voices are refused through the API** — `HTTP 402 paid_plan_required:
  "Free users cannot use library voices via the API"`. Rachel, the voice shipped as
  the code default, is one of them. `tools/verify_elevenlabs_voice.py en` probes the
  configured voice and prints working alternatives; the demo runs on *Alice — Clear,
  Engaging Educator*.
* **10 000 credits/month** ≈ 10 minutes of speech (one credit per character on the
  v2/v4 models), non-commercial, no rollover.
* **Igbo and Yoruba are not covered at all** — those two languages keep the
  Gemini/browser voice, as `docs/LANGUAGES.md` records.

### Verify it in one command

```bash
python3 tools/verify_elevenlabs_voice.py --list   # voices on this account
python3 tools/verify_elevenlabs_voice.py ar       # Arabic sample + .wav + latency
python3 tools/check_demo_voice_live.py ar         # what the *running service* sends the browser
```

## Gemini Live configuration

The setup message the provider sends carries, besides the model, system instruction,
tools and transcriptions:

| Field | Setting | Why |
|---|---|---|
| `speech_config` | `GEMINI_VOICE_NAME` (default `Kore`) | the voice the student hears |
| `enable_affective_dialog` | `GEMINI_AFFECTIVE_DIALOG` (default `true`) | native-audio models adapt tone to how the student sounds instead of narrating flatly |
| `proactivity.proactive_audio` | `GEMINI_PROACTIVE_AUDIO` (default `false`) | lets the model speak up unprompted; off by default because a tutor should answer, not fill every silence |

The optional fields are attempted first and dropped automatically if the model or auth
path rejects them (`_looks_like_setup_rejection`), so an older live model still connects;
a genuine network failure is *not* retried and fails over as usual. Both paths are
supported and selected by env:

```
GOOGLE_GENAI_USE_VERTEXAI=true   + GOOGLE_CLOUD_PROJECT + ADC/service account → gemini-3.8-live
GOOGLE_GENAI_USE_VERTEXAI=false  + GEMINI_API_KEY (AIza…)                     → gemini-2.5-flash-native-audio-preview-12-2025
```

## Abstraction

Four narrow interfaces (`app/providers/base.py`):

| Interface | Responsibility |
|---|---|
| `RealtimeVoiceProvider` | One socket that does speech-in → speech-out (Gemini Live). |
| `STTProvider` | Streaming transcription. |
| `LLMProvider` | Streaming text reasoning + tool calls. |
| `TTSProvider` | Streaming synthesis to PCM16 @ 24 kHz. |

A `CascadePipelineProvider` composes STT + LLM + TTS behind the *same*
`RealtimeVoiceProvider`-shaped surface, so `VoiceSession` never knows whether it
is talking to one vendor or three.

Everything is built through `ProviderFactory` (`app/providers/factory.py`),
which is the only place that reads credentials.

## Vendors

### Gemini — primary
* **Realtime:** Live API over stateful WSS. Input PCM16/16 kHz, output PCM16/24 kHz.
  Native VAD, barge-in, input/output transcription, tool calling.
* **Two auth paths, auto-detected:**
  * Vertex AI / Agent Platform — `GOOGLE_GENAI_USE_VERTEXAI=true`, ADC or a
    service account, model `gemini-3.8-live` (`GEMINI_VERTEX_LIVE_MODEL`).
  * Gemini Developer API — `GEMINI_API_KEY`, model
    `gemini-2.5-flash-native-audio-preview-12-2025` (`GEMINI_LIVE_MODEL`).
* **Components:** `gemini-2.5-flash` for the LLM slot, `gemini-3.8-flash-tts`
  for the TTS slot (this is what gives Igbo and Yoruba a voice).

### ElevenLabs — backup #1 (components only, no realtime)
* **STT:** `scribe_v2_realtime` over
  `wss://api.elevenlabs.io/v1/speech-to-text/realtime`, `xi-api-key` header or
  `token` query param. Client frames:
  `{"message_type":"input_audio_chunk","audio_base_64":…,"commit":bool}`;
  server frames: `session_started`, `partial_transcript`, `committed_transcript`,
  `warning`, `error`. Built-in VAD (`commit_strategy=vad`) or manual commit.
  Language is passed as ISO-639-3 (`eng, ara, fra, swa, amh, hau, som, yor, ibo, zul`).
* **TTS:** `eleven_v4` / `eleven_v4_turbo` over the realtime TTS socket; first
  frame carries config + key, `flush: true` forces generation.
  v4 was chosen deliberately: `eleven_v3` omits Amharic, Zulu, Igbo and Yoruba.

### Deepgram — backup #2 (components only)
* **STT:** `wss://api.deepgram.com/v1/listen`, `Authorization: Token <key>`,
  binary linear16 in, JSON out (`Results` with
  `channel.alternatives[0].transcript` + `is_final`, `SpeechStarted`,
  `UtteranceEnd`). Control: `{"type":"Finalize"}`, `{"type":"CloseStream"}`.
  Nova-3 officially supports `en`, `ar` (incl. `ar-EG`), `fr` — and none of the
  other seven mandatory languages.
* **TTS:** `wss://api.deepgram.com/v1/speak`, `{"type":"Speak","text":…}` /
  `{"type":"Flush"}` → binary PCM. Aura-2 is a 7-language model; of our ten only
  `en` and `fr` are covered. The provider **hard-refuses** anything else rather
  than silently speaking English.

### LERNA — LLM component
`app/providers/lerna/llm.py` wraps the Academic OS model pool (Gemini/OpenAI/
Anthropic/Groq, whatever the host app has configured). It exists so a total
Gemini outage still leaves a working cascade. **Not token-streaming:** the
engine returns a complete answer which is chunked into sentences; TTS still
streams sentence by sentence.

### Mock — tests and demos
`app/providers/mock/providers.py` implements every interface with synthetic
audio plus a fault `INJECTOR` (`fail(vendor, kind, times=…)`, `heal()`), which
is how the whole failover matrix is tested without spending a cent.

## Capability registry

`app/providers/capabilities.py` is the single source of truth: per vendor, which
languages it supports for `realtime`, `stt`, `tts`, `llm`. The router reads only
this — no capability knowledge is scattered through the code.

```python
providers_supporting(Capability.TTS, "ig")   # -> ["gemini"]
capability_matrix()["ig"]                    # full per-vendor view
```

`DEFAULT_PRIORITY = ("gemini", "elevenlabs", "deepgram", "lerna")`.

## Provider modes

`VOICE_PROVIDER_MODE`:

| Mode | Vendors the router may use |
|---|---|
| `auto` (default) | all configured, by priority and health |
| `gemini_only` | `gemini` — a language Gemini cannot serve raises `VOICE_LANGUAGE_UNSUPPORTED` (Igbo does) |
| `elevenlabs_only` | `elevenlabs` + `lerna` (EL has no LLM) |
| `deepgram_only` | `deepgram` + `lerna` |

## Adding a provider

1. Implement one or more interfaces from `app/providers/base.py`, normalising
   output audio to PCM16 @ 24 kHz and raising the typed errors in `base.py`.
2. Add a `ProviderCapabilities` entry with the languages you have **verified**
   from vendor documentation — not optimistic guesses.
3. Register builders in `ProviderFactory` and add the key to
   `Settings.configured_providers()`.
4. Add the vendor to `tests/conftest.py::ALL_VENDORS` and register a mock.
5. Run `pytest tests/provider tests/multilingual` — the routing tests will tell
   you immediately what changed.
