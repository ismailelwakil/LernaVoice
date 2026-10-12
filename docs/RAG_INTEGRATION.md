# RAG integration

**The voice service does not have a RAG system.** It calls LERNA's.

## Path

```
VoiceSession ──► app/rag/adapter.py ──► app/lerna_bridge.py ──► LERNA Academic OS
                                                                 src/retrieval/service.py
```

`LernaBridge` has three modes (`LERNA_INTEGRATION_MODE`):

| Mode | Behaviour |
|---|---|
| `inprocess` | Imports `build_module()` from `<Lerna>/ai-service/src/integration/service.py` and uses `module.tutor.retrieval.retrieve(...)` directly — same index, same trust scoring, same evidence objects. |
| `http` | Calls the LERNA backend over HTTP (`LERNA_BACKEND_URL` + `LERNA_BACKEND_API_KEY`) for deployments where the engine lives elsewhere. |
| `disabled` | No retrieval. The tutor is instructed to say it has no course evidence rather than to invent some. |
| `auto` | `inprocess` if the import succeeds, else `http` if a URL is set, else `disabled`. |

## Two tiers: the vetted packs, then LERNA

`RAGAdapter.retrieve()` answers from **this service's vetted topic packs first**
(`app/learning/sources.py`, `source_type: "curated"`, `trust_score` 0.98) and
then merges whatever LERNA's own retrieval returns; duplicates are dropped by
normalised text. That ordering is what lets the tutor stay grounded with the
LERNA bridge off — and it is why an Arabic lesson says it would rather check the
course material than invent an answer. `retrieve()` accepts `topic_id` so the
caller does not have to rely on the free-text topic matching a pack.

## When retrieval runs

* Every student question (`question` control message / `POST .../question`).
* Whenever the model calls the `retrieve_course_material` tool.
* On lesson start when a `topic` is supplied, to prime the opening turn.

Results are emitted to the client as `rag.retrieved` (query, chunk count,
sources) so a UI can show citations, and injected into the prompt as an evidence
block.

## Evidence contract

`RetrievalResult` → `EvidenceItem(chunk_id, text, source, score, trust_score,
source_type, source_url, page)`. These mirror LERNA's own retrieval records;
`RETRIEVAL_TOP_K` / `LERNA_RAG_TOP_K` (default 6) and the engine's
`EVIDENCE_MIN_CONFIDENCE` / `TRUST_THRESHOLD` settings continue to apply.

## Grounding rules

The system prompt instructs the tutor to:

1. Prefer retrieved course evidence over its own memory.
2. Say explicitly, in the session language, when the course materials do not
   cover a question — and only then answer from general knowledge, flagged.
3. Never fabricate citations.

## Degradation

If retrieval is unavailable or returns nothing, the session continues: a
`VOICE_RAG_UNAVAILABLE` (recoverable) note is emitted and the prompt tells the
tutor it is answering without course evidence. A voice lesson never dies because
the index is down.

## Document scoping

`document_ids` passed at session creation is forwarded to every retrieval call,
so a lesson can be pinned to specific uploaded materials.
