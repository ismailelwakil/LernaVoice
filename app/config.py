"""Central configuration for the LERNA Voice AI Service.

Every secret is read from the environment. Nothing is hardcoded.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderMode = Literal["auto", "gemini_only", "elevenlabs_only", "deepgram_only"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- service ----
    app_env: str = "development"
    service_name: str = "lerna-voice-ai"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8080

    # Service-to-service auth (LERNA backend -> voice service).
    voice_service_api_key: str | None = Field(default=None, repr=False)
    # When false (default in dev) requests without a key are accepted.
    voice_auth_required: bool = False
    voice_enable_mock_providers: bool = False  # demo/dev only: serves synthetic audio

    # ---- Gemini ----
    # Two auth paths are supported and auto-detected:
    #   * Developer API  -> GEMINI_API_KEY  (models: gemini-2.5-flash-native-audio-preview-*)
    #   * Vertex / Agent Platform -> GOOGLE_GENAI_USE_VERTEXAI=true + project/location (ADC)
    gemini_api_key: str | None = Field(default=None, repr=False)
    # OpenRouter (round 25) — an OpenAI-compatible LLM gateway used as an alternative /
    # fallback "brain" for composed pipelines (OpenRouter generates, Azure speaks).
    openrouter_api_key: str | None = Field(default=None, repr=False)
    openrouter_model: str = "openai/gpt-4o-mini"
    #: Which LLM brain is tried first in composed pipelines; the other is the fallback.
    #: Set after the live round-25 benchmark (winner first).
    llm_priority: str = "gemini,openrouter"
    google_genai_use_vertexai: bool = False
    google_cloud_project: str | None = None
    #: Path to a service-account JSON (Vertex). Read here *and* handed to the SDK
    #: explicitly — `.env` does not populate os.environ for third-party libraries.
    google_application_credentials: str | None = None
    google_cloud_location: str = "us-central1"

    gemini_live_model: str = "gemini-2.5-flash-native-audio-preview-12-2025"
    gemini_vertex_live_model: str = "gemini-3.8-live"
    # `gemini-2.5-flash` was retired for new Developer-API accounts (404). `3.6-flash`
    # is verified working on a fresh key; override with GEMINI_TEXT_MODEL if needed.
    gemini_text_model: str = "gemini-3.6-flash"
    gemini_tts_model: str = "gemini-3.8-flash-tts"
    gemini_voice_name: str = "Kore"
    #: Affective dialog lets the native-audio model adapt its tone to how the student
    #: sounds (frustrated, unsure, pleased) instead of delivering flat narration.
    gemini_affective_dialog: bool = True
    #: Proactive audio lets the model speak up when it has something useful to add.
    #: Off by default: a tutor should answer the student, not fill every silence.
    gemini_proactive_audio: bool = False

    # ---- ElevenLabs ----
    elevenlabs_api_key: str | None = Field(default=None, repr=False)
    elevenlabs_stt_model: str = "scribe_v2_realtime"
    elevenlabs_tts_model: str = "eleven_v4_turbo"
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    #: "auto" streams when the language allows it (faster first audio), "rest" always
    #: uses one HTTP call per line (v4-family quality), "stream" forces the socket.
    elevenlabs_transport: str = "auto"
    #: Slightly brisker than an announcement; 1.0 is ElevenLabs' own default.
    elevenlabs_speech_speed: float = 1.05
    #: Voice for the *offline* demo: "auto" (the first configured vendor), "off",
    #: or a vendor name: "elevenlabs" | "azure".
    voice_demo_voice: str = "auto"
    #: Azure AI Speech (free F0 tier: 0.5M characters/month). Region as shown in the
    #: resource's "Keys and Endpoint" page, e.g. "eastus".
    azure_speech_key: str | None = Field(default=None, repr=False)
    azure_speech_region: str | None = None
    azure_speech_speed: float = 1.05
    #: Per-language voice overrides, e.g. "ar:ar-SA-HamedNeural,en:en-US-JennyNeural".
    azure_voice_overrides: str = ""
    #: Fish Audio (round 27) — backup TTS voice. Free `s2.1-pro-free` model,
    #: auto-detects language. Key is a Bearer token; never committed.
    fish_audio_api_key: str | None = Field(default=None, repr=False)
    fish_audio_model: str = "s2.1-pro-free"
    #: Where the learner-profile mirror lives (each student's level) until
    #: LERNA's Progress Profile is wired in. Empty keeps it in memory, which
    #: is what the test suite uses.
    learner_profile_path: str = ""
    #: Humanising the vendor voice: Azure's expressive style, a little pitch lift
    #: and short pauses between sentences. A tutor who breathes is a tutor you
    #: listen to; all three are ignored gracefully if a voice refuses the style.
    azure_tts_style: str = "cheerful"
    azure_tts_style_degree: float = 1.05
    azure_tts_pitch: float = 2.0
    azure_tts_pauses: bool = True

    # ---- Deepgram ----
    deepgram_api_key: str | None = Field(default=None, repr=False)
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model: str = "aura-2-thalia-en"

    # ---- routing / resilience ----
    voice_provider_mode: ProviderMode = "auto"
    voice_fallback_enabled: bool = True
    voice_max_retries: int = 2
    voice_retry_backoff: float = 1.0
    voice_provider_timeout: float = 30.0
    voice_circuit_breaker_threshold: int = 3
    voice_circuit_breaker_cooldown: float = 60.0

    # ---- persistence ----
    # MongoDB is the LERNA persistence layer for voice sessions.
    mongodb_uri: str | None = Field(default=None, repr=False)
    mongodb_username: str | None = Field(default=None, repr=False)
    mongodb_password: str | None = Field(default=None, repr=False)
    mongodb_db: str = "lerna_voice"
    # 'auto' -> mongo when MONGODB_URI is set, else in-memory.
    voice_persistence_backend: Literal["auto", "mongo", "memory"] = "auto"

    # ---- privacy ----
    # Raw audio is NOT retained by default (see docs/VOICE_TUTOR.md#privacy).
    voice_store_raw_audio: bool = False
    voice_store_transcripts: bool = True

    # ---- LERNA integration ----
    # In-process import of the existing Academic OS / LERNA AI engine.
    lerna_ai_service_path: str | None = None
    lerna_backend_url: str | None = None
    lerna_backend_api_key: str | None = Field(default=None, repr=False)
    lerna_integration_mode: Literal["auto", "inprocess", "http", "disabled"] = "auto"
    lerna_rag_top_k: int = 6

    # ---- audio ----
    input_sample_rate: int = 16000
    output_sample_rate: int = 24000

    # ---- dev client ----
    expose_dev_diagnostics: bool = True

    # Comma-separated list of browser origins allowed to call the service.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        items = [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]
        return items or ["*"]

    @property
    def effective_mongodb_uri(self) -> str | None:
        """Credentials may arrive either inside MONGODB_URI or split out into
        MONGODB_USERNAME / MONGODB_PASSWORD; support both."""
        uri = self.mongodb_uri
        if not uri:
            return None
        if self.mongodb_username and "@" not in uri.split("//", 1)[-1]:
            from urllib.parse import quote_plus

            scheme, _, rest = uri.partition("//")
            creds = quote_plus(self.mongodb_username)
            if self.mongodb_password:
                creds += ":" + quote_plus(self.mongodb_password)
            return f"{scheme}//{creds}@{rest}"
        return uri

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("production", "prod")

    @property
    def gemini_configured(self) -> bool:
        if self.google_genai_use_vertexai:
            return bool(self.google_cloud_project)
        return bool(self.gemini_api_key)

    @property
    def elevenlabs_configured(self) -> bool:
        return bool(self.elevenlabs_api_key)

    @property
    def deepgram_configured(self) -> bool:
        return bool(self.deepgram_api_key)

    @property
    def openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def fish_configured(self) -> bool:
        return bool(self.fish_audio_api_key)

    @property
    def azure_configured(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_region)

    #: Round 30 — preferred spoken-voice order: Azure first (with the OpenRouter brain),
    #: then Gemini, then ElevenLabs. Drives which composed pipeline is primary.
    voice_priority: str = "azure,gemini,elevenlabs,fish"

    @property
    def gemini_auth_mode(self) -> str:
        """Which Gemini auth path is wired: vertex, developer_api, or none.

        Reported by `/health` (a name, never a credential) so the demo knows whether a
        real vendor voice is available or it is running on the mock.
        """
        if self.google_genai_use_vertexai:
            # Vertex needs a project (and ADC or a service-account JSON) — an API key
            # alone is not enough, and no key at all is not enough either.
            return "vertex" if (self.google_cloud_project or self.gemini_api_key) else "none"
        return "developer_api" if self.gemini_api_key else "none"

    @property
    def active_gemini_live_model(self) -> str:
        return self.gemini_vertex_live_model if self.google_genai_use_vertexai else self.gemini_live_model

    def configured_providers(self) -> set[str]:
        if self.voice_enable_mock_providers:
            # Demo/dev mode: every vendor is served by a mock implementation.
            return {"gemini", "elevenlabs", "deepgram", "lerna"}
        out: set[str] = set()
        if self.gemini_configured:
            out.add("gemini")
        if self.elevenlabs_configured:
            out.add("elevenlabs")
        if self.deepgram_configured:
            out.add("deepgram")
        if self.openrouter_configured:
            out.add("openrouter")
        if self.fish_configured:
            out.add("fish")
        if self.azure_configured:
            out.add("azure")
        if self.lerna_integration_mode != "disabled":
            # LERNA's own model pool is an LLM component for composed pipelines.
            out.add("lerna")
        return out


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
