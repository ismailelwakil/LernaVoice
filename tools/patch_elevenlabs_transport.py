"""ElevenLabs transport policy: stream when allowed, REST when it is the only way.

Verified against the live API: the v4 family rejects the `stream-input` WebSocket
with HTTP 400 for every output format, while REST answers 200 with `pcm_24000`.
So the provider now needs two transports \u2014 and the offline demo needs the wider
language coverage that only v4 has.
"""

P = "app/providers/elevenlabs/tts.py"
s = open(P).read()

s = s.replace(
    'BASE_WS = "wss://api.elevenlabs.io/v1/text-to-speech"',
    'BASE_WS = "wss://api.elevenlabs.io/v1/text-to-speech"\n'
    'BASE_REST = "https://api.elevenlabs.io/v1/text-to-speech"\n'
    "\n"
    "#: Models that only answer over REST (verified live: v4 rejects the stream-input\n"
    "#: WebSocket with HTTP 400 whatever the output format, REST returns 200 PCM).\n"
    'REST_ONLY_MODELS = {"eleven_v4", "eleven_v4_turbo"}\n'
    "\n"
    "#: Low-latency streaming model and the languages it covers well. Outside this set\n"
    "#: nothing is streamed: the configured (wider, slower) model is used over REST\n"
    "#: instead, because a supported voice matters more than a 1.5 s head start.\n"
    'STREAMING_MODEL = "eleven_multilingual_v2"\n'
    "STREAMING_LANGUAGES = {\n"
    '    "en", "ar", "fr", "de", "es", "it", "pt", "pl", "tr", "nl", "sv", "da", "fi",\n'
    '    "cs", "sk", "ru", "uk", "ro", "hu", "el", "bg", "hr", "id", "ms", "vi", "ja",\n'
    '    "ko", "zh", "hi", "ta", "fil", "no",\n'
    "}",
    1,
)

s = s.replace(
    "import base64",
    "import base64\nimport logging",
    1,
)
s = s.replace(
    'logger = logging.getLogger(__name__)', 'logger = logging.getLogger(__name__)', 1
)
if "logger = logging.getLogger" not in s:
    s = s.replace(
        'BASE_REST = "https://api.elevenlabs.io/v1/text-to-speech"',
        'BASE_REST = "https://api.elevenlabs.io/v1/text-to-speech"\n\n'
        "logger = logging.getLogger(__name__)",
        1,
    )

s = s.replace(
    "        self._cancelled = False\n        self._ws: Any = None",
    "        self._cancelled = False\n"
    "        self._ws: Any = None\n"
    "        #: Transport the last line used: \"ws\" or \"rest\" (reported by the tools).\n"
    "        self.last_transport: str | None = None",
    1,
)

# --- replace the single-transport body with a policy plus two transports ------- #
start = s.index("    async def synthesize_stream(")
marker = (
    '        except Exception as exc:\n'
    '            raise classify_exception(exc, "elevenlabs") from exc\n'
    "        finally:\n"
    "            if self._ws is not None:\n"
    "                with contextlib.suppress(Exception):\n"
    "                    await self._ws.close()\n"
    "                self._ws = None\n"
)
tail_start = s.index(marker) + len(marker)

new = '''    async def synthesize_stream(
        self, text: str, language: str, *, voice: str | None = None
    ) -> AsyncIterator[AudioChunk]:
        """Speak `text`: stream over the WebSocket when the model allows it, else REST.

        Both transports deliver identical PCM16 at the session's output rate, so the
        client cannot tell them apart \u2014 only the time to first audio differs
        (~300 ms streaming, ~1.5-2 s for a full line over REST).
        """
        if not PROVIDER_CAPABILITIES["elevenlabs"].supports(Capability.TTS, language):
            raise ProviderUnsupportedError(
                f"ElevenLabs TTS does not cover '{language}'", provider="elevenlabs"
            )
        if not self.settings.elevenlabs_api_key:
            raise ProviderAuthError("ELEVENLABS_API_KEY is not configured", provider="elevenlabs")

        self._cancelled = False
        voice_id = voice or self.settings.elevenlabs_voice_id
        model = self.settings.elevenlabs_tts_model
        wants_stream = language in STREAMING_LANGUAGES and model not in REST_ONLY_MODELS

        if wants_stream:
            self.last_transport = "ws"
            emitted = False
            try:
                async for chunk in self._ws_chunks(text, language, voice_id, model):
                    emitted = True
                    yield chunk
                return
            except Exception as exc:  # noqa: BLE001 - transport problems fall back
                if emitted:
                    raise classify_exception(exc, "elevenlabs") from exc
                logger.warning("ElevenLabs streaming unavailable (%s); using REST", exc)

        self.last_transport = "rest"
        async for chunk in self._rest_chunks(text, language, voice_id, model):
            yield chunk

    async def _ws_chunks(
        self, text: str, language: str, voice_id: str, model: str
    ) -> AsyncIterator[AudioChunk]:
        websockets = require_websockets()
        params = {
            "model_id": model,
            "output_format": f"pcm_{self.settings.output_sample_rate}",
            "inactivity_timeout": 20,
        }
        url = f"{BASE_WS}/{voice_id}/stream-input?{urlencode(params)}"
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    max_size=None,
                ),
                timeout=self.settings.voice_provider_timeout,
            )
            await self._ws.send(
                json.dumps(
                    {
                        "text": " ",
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "speed": 1.0},
                        "generation_config": {"chunk_length_schedule": [120, 160, 250, 290]},
                    }
                )
            )
            await self._ws.send(json.dumps({"text": text, "flush": True}))
            await self._ws.send(json.dumps({"text": ""}))

            async for raw in self._ws:
                if self._cancelled:
                    break
                if isinstance(raw, bytes):
                    yield AudioChunk(data=raw, sample_rate=self.settings.output_sample_rate)
                    continue
                msg = json.loads(raw)
                if msg.get("error"):
                    raise classify_exception(RuntimeError(str(msg)), "elevenlabs")
                audio_b64 = msg.get("audio")
                if audio_b64:
                    yield AudioChunk(
                        data=base64.b64decode(audio_b64), sample_rate=self.settings.output_sample_rate
                    )
                if msg.get("isFinal") or msg.get("is_final"):
                    break
        except Exception as exc:
            raise classify_exception(exc, "elevenlabs") from exc
        finally:
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()
                self._ws = None

    async def _rest_chunks(
        self, text: str, language: str, voice_id: str, model: str
    ) -> AsyncIterator[AudioChunk]:
        """One HTTP call, the whole line back as PCM, re-chunked for the socket."""
        import httpx

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.voice_provider_timeout * 3
            ) as client:
                response = await client.post(
                    f"{BASE_REST}/{voice_id}",
                    headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    params={"output_format": f"pcm_{self.settings.output_sample_rate}"},
                    json={"text": text, "model_id": model},
                )
        except Exception as exc:  # noqa: BLE001
            raise classify_exception(exc, "elevenlabs") from exc

        if response.status_code >= 400:
            detail = response.text[:200]
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"ElevenLabs refused the key ({response.status_code}): {detail}",
                    provider="elevenlabs",
                )
            raise classify_exception(
                RuntimeError(f"HTTP {response.status_code}: {detail}"), "elevenlabs"
            )

        data = response.content
        # ~200 ms per chunk at 24 kHz: the client's scheduler sees the same shape as
        # the streaming transport.
        step = self.settings.output_sample_rate // 5 * 2
        for offset in range(0, len(data), step):
            if self._cancelled:
                return
            yield AudioChunk(
                data=data[offset : offset + step], sample_rate=self.settings.output_sample_rate
            )

'''

s = s[:start] + new + s[tail_start:]
open(P, "w").write(s)
print("transport policy written:", "REST_ONLY_MODELS" in s, "last_transport" in s)
