# AI VIDEO LAB — COMPLETE PRODUCT, REPOSITORY, CAPABILITY & ENGINEERING INTELLIGENCE REPORT

**Document Path:** `planning/20_AI_VIDEO_LAB_COMPLETE_REPOSITORY_AND_PRODUCT_INTELLIGENCE.md`  
**Project:** AI Video Lab (Built on OpenMontage)  
**Repository:** `https://github.com/Unstocks/AI-video-Lab.git` (`C:\AI-Video-Lab`)  
**Upstream Base:** `https://github.com/OpenMontageInc/OpenMontage.git` (`upstream/main` @ `2e003e6`)  
**Verified Branch:** `main` tracking `origin/main`  
**Verified HEAD Commit SHA:** `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`  
**Audit Date:** November 17, 2026  
**Execution Mode:** Read-Only Forensic Repository Investigation (Zero Production Code Modified)

---

## 1. Product Identity, Vision & Quality Philosophy

**AI Video Lab** is a personal, local-first AI-powered podcast and long-form video intelligence and short-form video production studio built atop the open-source **OpenMontage** engine.

### 1.1 Core Purpose
Transform long-form conversations, podcasts, interviews, keynotes, webinars, and videos into a **small, high-precision collection of independently understandable, publishable short-form vertical (9:16) videos** (plus 1:1 / 16:9 variants where framing requires it).

### 1.2 Explicit Anti-Goals (What AI Video Lab Must Never Become)
The system is explicitly designed NOT to:
- Slice videos at arbitrary fixed intervals (e.g., every 45 or 60 seconds).
- Extract random interesting sentences detached from their setup or conclusion.
- Select clips purely via audio loudness spikes or high-energy heuristics.
- Select clips via naive keyword matching or clickbait word triggers.
- Summarize transcripts generically and turn summaries into synthetic clips.
- Flood the user with large quantities of mediocre, context-broken clips.

### 1.3 Governing Quality Philosophy
> **Three genuinely exceptional, contextually complete, cold-viewer-understandable clips are far more valuable than ten mediocre or confusing clips.**

---

## 2. Intended 20-Stage Product Experience — Verified Implementation Status

Every stage below was audited directly against source code in `C:\AI-Video-Lab` at HEAD `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`. No feature is marked implemented merely because a planning document describes it.

| # | Intended Product Experience Stage | Classification | Verified Source Evidence & Gaps |
|---|---|---|---|
| 1 | User supplies public video URL or local video file | **IMPLEMENTED AND VERIFIED** | Public URLs (YouTube/Vimeo) via `URLIntakeAdapter` (`lib/url_ingest.py`) and local files via `review_source_media()` (`lib/source_media_review.py`) and `idea-director.md`. |
| 2 | System validates and acquires source media | **IMPLEMENTED BUT INCOMPLETELY VERIFIED** | `URLIntakeAdapter.ingest_url()` (`lib/url_ingest.py:299-512`) validates project ID, scheme, domain allowlist, preflight DNS, disk space, and invokes `VideoDownloader` (`tools/analysis/video_downloader.py`). **Gaps:** `yt-dlp` undeclared in `requirements.txt`/`setup.py`; no post-download duration guard when preflight duration is 0/unknown; preflight DNS does not guard redirects/rebinding; sequential `shutil.move` is not transactional; `URLIntakeAdapter` is not registered in `ToolRegistry`. |
| 3 | System inspects source metadata, audio, video, duration, and captions | **IMPLEMENTED AND VERIFIED** | `URLIntakeAdapter.probe_media_file()` + `source_manifest.json` + handoff to `lib/source_media_review.py:review_source_media()` (`audio_probe`, `ffprobe`, `frame_sampler`). Verified empirically in `projects/m1-final-agent-verification/`. |
| 4 | System obtains captions or generates timestamped transcript | **PARTIALLY IMPLEMENTED** | YouTube native/auto captions work via `TranscriptFetcher` (`tools/analysis/transcript_fetcher.py`), verified in `projects/m1-final-agent-verification/source/transcript.json`. **Gaps:** `lib/url_ingest.py:404` hardcodes `languages: ["en"]`; `TranscriptFetcher` ignores `include_auto_generated`; local ASR fallback `Transcriber` (`tools/analysis/transcriber.py`) is **BLOCKED BY A DEPENDENCY** (`faster-whisper` not installed in `.venv` on Python 3.14.10); cloud STT tools (`azure_stt`, `mistral_stt`, `dashscope_asr`) are unconfigured. |
| 5 | System understands complete conversation (macro topology, topics, turns) | **ARCHITECTURALLY PLANNED** | Only prompt instructions exist in `skills/pipelines/clip-factory/script-director.md`. No `lib/transcript_normalizer.py`, `lib/conversation_structure.py`, or `lib/semantic_segmenter.py` exists. |
| 6 | System discovers meaningful candidate moments | **ARCHITECTURALLY PLANNED** | Prompt-only guidance in `script-director.md`. No `lib/clip_discovery_engine.py` or `tools/analysis/clip_selector.py` exists. |
| 7 | System evaluates cold-viewer comprehension | **ARCHITECTURALLY PLANNED** | Conceptual checklist in `script-director.md:35-45` and `planning/13_*`. No `lib/cold_viewer_auditor.py` or structured cold-viewer audit contract exists in code or schemas. |
| 8 | System identifies an authentic, compelling opening (spoken hook) | **ARCHITECTURALLY PLANNED** | No `lib/hook_validator.py`, no immutable raw-to-normalized offset map, no verbatim source-span verification exists. |
| 9 | System reconstructs missing context where necessary | **RESEARCHED BUT NOT IMPLEMENTED** | Antecedent resolution and backward/forward expansion are designed in `planning/13_*`, with zero implementation. |
| 10 | System determines natural beginning and ending boundaries | **PARTIALLY IMPLEMENTED** | Raw signal tools exist (`SilenceCutter` `mode="mark"`, `AudioEnergy`, `SceneDetect`), all FFmpeg-backed and verified available. However, no boundary-refinement engine (`lib/acoustic_profiler.py`), forced alignment (`wav2vec2`/WhisperX), or semantic-closure boundary logic exists. |
| 11 | System evaluates editorial quality | **ARCHITECTURALLY PLANNED** | `lib/scoring.py` exists ONLY for **provider/tool selection** (`ProviderScore`, `ProductionPathScore`), NOT clip editorial evaluation. No `lib/editorial_evaluator.py` exists. |
| 12 | System removes duplicates and weak candidates | **NOT IMPLEMENTED** | No temporal IoU or semantic deduplicator (`lib/deduplicator.py`) exists. |
| 13 | System prepares candidates for review | **PARTIALLY IMPLEMENTED** | Canonical `script.schema.json` exists and supports `metadata`, and `lib/checkpoint.py` persists checkpoints. However, `schemas/artifacts/clip_selection_plan.schema.json` and `lib/models/` do NOT exist; no structured candidate dossier is generated or validated. |
| 14 | User reviews and approves selected clips through supported human-review mechanism | **IMPLEMENTED AND VERIFIED** | OpenMontage human approval gate is enforced in code by `lib/checkpoint.py:487-515` (`awaiting_human`, `human_approved=False`, raises `CheckpointValidationError` on gate violation) and chat-based approval protocol (`skills/meta/checkpoint-protocol.md`). Verified in `projects/m1-final-agent-verification/checkpoint_idea.json`. |
| 15 | System prepares vertical 9:16 compositions | **PARTIALLY IMPLEMENTED** | `tools/video/video_trimmer.py`, `tools/video/auto_reframe.py`, and `tools/video/video_compose.py` exist. **Gaps:** `auto_reframe` is not declared in `pipeline_defs/clip-factory.yaml`; `mediapipe` and `opencv-python` are NOT installed so `auto_reframe` falls back to naive center-crop; no active-speaker detection (ASD) exists for multi-speaker podcasts; `remotion-composer/node_modules` is NOT installed. |
| 16 | System produces synchronized, readable subtitles | **PARTIALLY IMPLEMENTED** | `tools/subtitle/subtitle_gen.py` (SRT/VTT/JSON cues, word-by-word/karaoke, ASR corrections) and `tools/video/remotion_caption_burn.py` exist. **Gaps:** Word-level timing requires ASR word timestamps (`transcriber` unavailable); Remotion burn falls back to FFmpeg subtitle burn because `remotion-composer/node_modules` is absent; YouTube auto-captions lack word-level timing. |
| 17 | User previews result through existing Backlot experience | **IMPLEMENTED AND VERIFIED** | `backlot/server.py` (FastAPI + SSE + media/thumb endpoints) and `backlot/state.py` (`load_board_state`, storyboard join on `scene_plan` × `script.sections` × `asset_manifest`, renders discovery) are implemented and strictly read-only observational. |
| 18 | User can refine composition and boundaries | **PARTIALLY IMPLEMENTED** | Supported only via conversational re-iteration in the IDE agent chat + checkpoint history archival (`projects/<id>/history/`). No interactive timeline/boundary editing UI exists in Backlot (by design, Backlot never writes to project directories). |
| 19 | System exports playable MP4 files | **PARTIALLY IMPLEMENTED** | `tools/video/video_trimmer.py`, `tools/video/video_compose.py`, and `tools/publishers/export_bundle.py` exist and are available via FFmpeg/Python. **Gaps:** End-to-end `clip-factory` multi-clip render from URL intake through `compose` and `publish` has NOT been executed or verified; `remotion-composer` is uninstalled; `export_bundle` is not wired into `pipeline_defs/clip-factory.yaml` `publish.tools_available`. |
| 20 | User manually publishes finished videos | **IMPLEMENTED BUT INCOMPLETELY VERIFIED** | `tools/publishers/export_bundle.py` packages video, subtitles, metadata JSON/TXT, chapters, thumbnails, and emits a schema-valid `publish_log`. Not yet exercised end-to-end for multi-clip `clip-factory` batches. |

---

## 3. Forensic Git & Repository Identity

Inspected directly via `git status -sb`, `git rev-parse`, `git branch -vv`, `git remote -v`, and `git log`:

- **Local Workspace Root:** `C:\AI-Video-Lab` (`C:/AI-Video-Lab`)
- **Active Branch:** `main` tracking `origin/main`
- **Verified HEAD SHA:** `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`
- **HEAD Commit:** `7cf6b52` — `docs: update README with AI Video Lab architecture, M1 intake status, and M2 intelligence roadmap` (2026-11-17 01:32:00 +0530)
- **Configured Remotes:**
  - `origin`: `https://github.com/Unstocks/AI-video-Lab.git` (fetch/push)
  - `upstream`: `https://github.com/OpenMontageInc/OpenMontage.git` (fetch/push)
- **Branch Relationships:**
  - `main` (`7cf6b52`) == `origin/main` (`7cf6b52`) == `origin/openmontage` (`7cf6b52`) — *Note: remote branch name is lowercase `origin/openmontage`, not `OpenMontage`.*
  - `upstream/main` is at `2e003e6` (`docs: add updated OpenMontage Instagram link`).
  - Local `main` is exactly **2 commits ahead** of `upstream/main`:
    1. `428b298` — `feat(m1): implement URL intake integration and conversation intelligence planning` (22 files changed, +5183/-1)
    2. `7cf6b52` — `docs: update README with AI Video Lab architecture, M1 intake status, and M2 intelligence roadmap` (`README.md`, +139/-735)
- **Pre-Existing Uncommitted Working-Tree Changes (MUST BE PRESERVED):**
  - `M planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md`
  - `M planning/13_M2_CONVERSATION_INTELLIGENCE_AND_CLIP_DISCOVERY_ARCHITECTURE.md`
  - `?? planning/15_M2_FINAL_EXECUTION_PLAN_AND_ACCEPTANCE_GATES.md`
- **Production Code Working Tree:** Clean relative to `7cf6b52`.

> **Critical Discrepancy Caught:** `planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md:20` records a **fabricated/corrupted HEAD SHA** (`7cf6b52a514d489116e257eb49b25da1bc92e624`). The genuine verified HEAD SHA is `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`.

---

## 4. Full Repository Architecture & Directory Inventory

### 4.1 Core OpenMontage Execution Architecture (Verified)
OpenMontage is an **instruction-driven, agent-first video production platform** (`docs/ARCHITECTURE.md:5-6`, `AGENT_GUIDE.md:70-82`, `PROJECT_CONTEXT.md:9-19`):

1. **IDE Coding Agent = Control Plane / Orchestrator:** Reads `pipeline_defs/*.yaml`, follows Layer 2 stage director skills (`skills/pipelines/<pipeline>/<stage>-director.md`) and Layer 3 vendor skills (`.agents/skills/`), calls Python tools, synthesizes JSON artifacts, performs CHAI self-review (`skills/meta/reviewer.md`), writes checkpoints, and pauses for human approval.
2. **Python = Deterministic Tools + Persistence:** **No Python orchestrator, no Python runtime general-purpose LLM calls** (`docs/ARCHITECTURE.md:90-102`). `lib/providers/` contains only an empty `__init__.py`. `config.yaml` declares an `llm:` section (`provider: anthropic`), which is parsed by `lib/config_model.py` but has **zero active runtime callers** in `lib/` or `tools/`.
3. **3-Layer Knowledge Architecture:**
   - **Layer 1 (`tools/` + `pipeline_defs/`):** Concrete capabilities (`BaseTool` subclasses, `ToolRegistry`, YAML stage manifests).
   - **Layer 2 (`skills/`):** OpenMontage conventions, stage directors, meta governance (`reviewer.md`, `checkpoint-protocol.md`, `onboarding.md`, `taste-direction.md`, `bespoke-composition.md`).
   - **Layer 3 (`.agents/skills/`):** 93 vendor/technology skill folders linked via `BaseTool.agent_skills`.
4. **BaseTool & ToolRegistry Contract:**
   - All production tools inherit from `BaseTool` (`tools/base_tool.py`) and implement `execute(inputs: dict[str, Any]) -> ToolResult`.
   - `BaseTool.__init_subclass__` automatically wraps `execute()` with Backlot event emission (`events.jsonl`) and content-addressed caching.
   - `ToolRegistry` (`tools/tool_registry.py`) dynamically discovers **164 concrete `BaseTool` instances** across `tools/` via `pkgutil.walk_packages()`. Callers MUST invoke `registry.discover()` or `registry.ensure_discovered()` before `registry.get(...)`.
   - Important: `tools/cost_tracker.py` (`CostTracker`) is a standalone budget governance utility (`estimate -> reserve -> reconcile -> refund`), **NOT** a `BaseTool` and **NOT** registered in `ToolRegistry`.
5. **Checkpoint & Gate Governance (`lib/checkpoint.py`):**
   - Checkpoints live at `projects/<project_id>/checkpoint_<stage>.json` with atomic write (`*.tmp` -> `os.replace`) and automatic history archival (`projects/<project_id>/history/`).
   - `CANONICAL_STAGE_ARTIFACTS` maps each standard stage to its mandatory artifact (`idea -> brief`, `script -> script`, `scene_plan -> scene_plan`, `assets -> asset_manifest`, `edit -> edit_decisions`, `compose -> render_report`, `publish -> publish_log`).
   - **Critical Invariant (`lib/checkpoint.py:134-143`):** Any stage with `status in {"completed", "awaiting_human"}` **MUST** include its canonical artifact in `artifacts` — including `script` during `awaiting_human`!
   - **Gate Enforcement (`lib/checkpoint.py:487-522`):** Reads `human_approval_default` from the YAML manifest; writing `status="completed"` on a gated stage without `human_approved=True` raises `CheckpointValidationError("GATE VIOLATION")`. Also enforces `_enforce_stage_prerequisites` so downstream stages cannot advance before predecessors are `completed` and approved.
6. **Backlot Living Storyboard (`backlot/`):**
   - FastAPI + SSE server (`backlot/server.py`, `backlot/state.py`, `backlot/ui/`).
   - **Strictly read-only observational:** Never writes to `projects/` (`backlot/server.py:5`). Watches `projects/` via `watchfiles.awatch`, broadcasts SSE change notifications, serves `/api/project/{id}/state`, `/media/...`, `/thumb/...`.
   - Protected by `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost"])` and path-traversal guards.
   - Derives storyboard cards via `load_board_state()` -> `_build_storyboard()` by joining `scene_plan.scenes` with `script.sections` (by `script_section_id` or timestamp overlap) and `asset_manifest.assets`.

### 4.2 Directory-by-Directory Inventory

| Directory / File | Responsibility | Key Files / Symbols | Interacts With | Active / Status |
|---|---|---|---|---|
| `lib/` | Core Python runtime infrastructure, config, checkpoints, media review, URL intake, scoring, embeddings | `checkpoint.py` (`init_project`, `write_checkpoint`, `validate_checkpoint`, `get_next_stage`), `pipeline_loader.py`, `source_media_review.py` (`review_source_media`), `url_ingest.py` (`URLIntakeAdapter`), `scoring.py` (`ProviderScore`, `score_provider`), `clip_embedder.py` (`embed_images`, `embed_texts`), `media_profiles.py`, `config_model.py`, `paths.py`, `events.py`, `asset_cache.py`, `corpus.py` | `tools/`, `schemas/`, `backlot/`, `pipeline_defs/` | **Active & Core.** `lib/providers/` is empty/reserved. `lib/models/` does NOT exist yet. |
| `tools/` | 164 auto-discovered `BaseTool` implementations across 10 subpackages + shared helpers | `base_tool.py`, `tool_registry.py`, `cost_tracker.py`; subpackages: `analysis/` (15), `audio/` (32+), `avatar/`, `capture/`, `character/`, `enhancement/`, `graphics/`, `publishers/` (`export_bundle.py`), `subtitle/` (`subtitle_gen.py`), `video/` (50+ including `video_compose.py`, `video_trimmer.py`, `auto_reframe.py`, `silence_cutter.py`, `remotion_caption_burn.py`, `hyperframes_compose.py`) | `lib/`, `remotion-composer/`, external binaries (`ffmpeg`, `ffprobe`) & APIs | **Active & Core.** Many cloud/GPU tools are `UNAVAILABLE` locally due to missing API keys or optional ML packages. |
| `pipeline_defs/` | 13 declarative YAML pipeline manifests | `clip-factory.yaml` (v2.0, beta), `podcast-repurpose.yaml` (v2.0, beta), `talking-head.yaml`, `animated-explainer.yaml`, `screen-demo.yaml`, `cinematic.yaml`, `documentary-montage.yaml`, `animation.yaml`, `character-animation.yaml`, `hybrid.yaml`, `avatar-spokesperson.yaml`, `localization-dub.yaml`, `framework-smoke.yaml` | `lib/pipeline_loader.py`, `lib/checkpoint.py`, `skills/pipelines/` | **Active.** `clip-factory.yaml` updated in M1 (+`video_downloader`, +`transcript_fetcher` in `idea`). |
| `schemas/` | Draft 2020-12 JSON Schemas | `artifacts/` (**20 schemas** registered in `ARTIFACT_NAMES`), `checkpoints/checkpoint.schema.json`, `pipelines/pipeline_manifest.schema.json`, `styles/playbook.schema.json`, `tools/` (7 tool schemas) | `lib/checkpoint.py`, `tests/contracts/` | **Active.** No `clip_selection_plan.schema.json` exists. |
| `skills/` | Layer 2 OpenMontage instruction skills | `pipelines/clip-factory/` (8 files: `executive-producer.md`, `idea-director.md` through `publish-director.md`), `pipelines/podcast-repurpose/` (8 files), `meta/` (11 files: `reviewer.md`, `checkpoint-protocol.md`, etc.), `core/`, `creative/` | Read by IDE coding agent | **Active.** `clip-factory/idea-director.md` updated in M1. `scene-director.md:28` contains a stale note claiming auto-reframe does not exist. |
| `.agents/skills/` | Layer 3 vendor & technology skills | **93 skill directories** (`ffmpeg`, `remotion-best-practices`, `hyperframes-*`, `video-download`, `video-understand`, `speech-to-text`, etc.) | Referenced by `BaseTool.agent_skills` | **Active.** |
| `.codex/` | Codex prompt shortcuts | `.codex/prompts/` (`animated-drawing.md`, `backlot.md`, `ink-art.md`, `README.md`), plus root `CODEX.md` pointing to `AGENT_GUIDE.md` & `PROJECT_CONTEXT.md` | Codex IDE / CLI | **Active (Minimal).** |
| `backlot/` | Local FastAPI + SSE living storyboard UI | `server.py` (`create_app`), `state.py` (`load_board_state`, `_build_storyboard`), `__main__.py`, `ui/` (`board.html`, `board.js`, `board.css`, `index.html`, `library.js`, `lib.js`) | Watches `projects/`, reads `lib/checkpoint.py` outputs | **Active & Verified.** Strictly read-only. |
| `remotion-composer/` | React/TypeScript Remotion video renderer | `package.json` (`remotion ^4.0.484`, `@remotion/captions`), `src/components/`, `SCENE_TYPES.md` | Invoked by `video_compose.py` & `remotion_caption_burn.py` | **Present in source, UNINSTALLED locally (`node_modules` missing).** |
| `ink-theater/` | Hand-drawn ink doodle animation engine + mocap | JS engine for HyperFrames | `animation` / `character-animation` pipelines | **Upstream OpenMontage feature; outside core podcast-clipper path.** |
| `planning/` | AI Video Lab research, audits, M1/M2 design dossier | `01_` through `16_` + `README.md` (18 files; `06_FINAL_IMPLEMENTATION_READINESS_GATE.md` is 0 bytes!) | Engineering governance & planning | **Active planning archive; contains stale/contradictory claims reconciled in §8.** |
| `projects/` | Gitignored local production runs | `clip-factory-live-verification/`, `m1-final-agent-verification/`, `smoke-test-milestone1/`, `test_meta/` | Runtime workspaces watched by Backlot | **Contains verified M1 `idea`-stage artifacts (Me at the zoo, 19.02s); zero M2/M3 renders.** |
| `tests/` | Automated test suites | `contracts/` (45 files), `tools/` (50+ files), `backlot/`, `lib/`, `pipelines/`, `styles/`, `unit/` (`test_url_ingest.py`), `qa/` (`test_url_intake_smoke.py`), `eval/`, `fixtures/` | `pytest`, `.github/workflows/ci.yml`, `Makefile` | **Active.** |
| `.runtime/` | Workspace-local media tool binaries | `.runtime/tools/bin/{ffmpeg.exe,ffprobe.exe,ffplay.exe}` | Fallback PATH lookup in `lib/url_ingest.py:63` | **Local machine runtime artifact.** |
| `.github/` | CI workflow & GitHub templates | `.github/workflows/ci.yml` (Ubuntu, Python 3.11, `apt install ffmpeg`, `make install-dev`, `make lint`, `make test`) | GitHub Actions | **Active.** |

---

## 5. Dependency & Local Environment Inventory

Verified directly against `requirements.txt`, `requirements-dev.txt`, `requirements-gpu.txt`, `setup.py`, `.python-version`, `.node-version`, `remotion-composer/package.json`, and `.venv` inspection (zero packages installed or modified):

### 5.1 Runtime Versions & Drift

| Runtime | Declared / Expected | Actually Installed Locally | Risk / Impact |
|---|---|---|---|
| **Python** | `.python-version`: `3.11`; CI (`ci.yml`): `3.11`; `setup.py`: `>=3.10`; `README.md`: `3.12+` | `.venv`: **Python 3.14.10** | **HIGH:** Several native ML wheels (`faster-whisper`/`ctranslate2`, `whisperx`, `mediapipe`, `torch` CUDA) lag Python 3.14 on Windows, creating environment mismatch vs CI (Python 3.11). |
| **Node.js** | `.node-version`: `22.23.4`; `remotion-composer/package.json`: `^22.23.4 \|\| ^24.22.1 \|\| ^26.12.1` | System PATH: **Node v25.8.1** | **MEDIUM:** Node v25 is an odd-numbered non-LTS release outside `remotion-composer`'s declared `engines` range. |
| **FFmpeg / FFprobe** | Required system binary | `ffmpeg 7.1-essentials_build-www.gyan.dev` in `.venv\Scripts\` AND `.runtime\tools\bin\` | **OK locally**, relies on `.venv\Scripts\` or `ensure_media_tools_on_path()`. |
| **Remotion (`remotion-composer`)** | `remotion ^4.0.484` + `@remotion/captions` | `remotion-composer/node_modules`: **NOT INSTALLED (`False`)** | **HIGH:** `clip-factory` locks `render_runtime="remotion"` for word-level captions, so Remotion renders currently fail or fall back to basic FFmpeg subtitle burn. |
| **Ollama** | Discussed in planning docs as local fallback | **NOT FOUND** on PATH | Not installed; local LLM fallback unverified. |

### 5.2 Python Dependency Matrix & Manifest Inconsistencies

| Package | Installed in `.venv`? | `requirements.txt` | `requirements-dev.txt` | `setup.py` | `requirements-gpu.txt` | Classification / Risk |
|---|---|---|---|---|---|---|
| `pyyaml`, `pydantic`, `jsonschema`, `python-dotenv`, `Pillow`, `requests`, `certifi`, `google-genai`, `openai` | Yes | Declared | Inherited (`-r`) | Declared | No | Core runtime — consistent |
| `numpy`, `google-auth`, `fastapi`, `uvicorn`, `watchfiles`, `websockets`, `pythainlp` | Yes | Declared | Inherited | **MISSING** | No | **Manifest drift:** `pip install .` omits Backlot (`fastapi`/`uvicorn`/`watchfiles`), `numpy`, `google-auth`, `pythainlp` |
| `pytest`, `pytest-asyncio`, `httpx` | Yes (`pytest 9.2.0`) | No | Declared | No | No | Dev-only — consistent |
| **`yt-dlp`** | **Yes (`2026.10.26`)** | **MISSING** | **MISSING** | **MISSING** | No | **CRITICAL M1 REPRODUCIBILITY BUG:** Clean install breaks `VideoDownloader` & `URLIntakeAdapter` |
| **`youtube-transcript-api`** | **Yes (`1.2.5`)** | **MISSING** | **MISSING** | **MISSING** | No | **CRITICAL M1 REPRODUCIBILITY BUG:** Clean install breaks `TranscriptFetcher` |
| `imageio-ffmpeg` | Yes (`0.8.1`) | Missing | Missing | Missing | No | Installed ad-hoc in `.venv`; undocumented |
| `faster-whisper`, `whisperx` | **NOT INSTALLED** | Missing | Missing | Missing | No | Optional local STT/diarization (`Transcriber` is `UNAVAILABLE`) |
| `torch`, `torchaudio`, `torchvision`, `transformers` | **NOT INSTALLED** | Missing | Missing | Missing | `torch*` declared | Optional GPU/VLM (`VideoUnderstand` & `lib/clip_embedder` unavailable) |
| `mediapipe`, `opencv-python`, `scenedetect` | **NOT INSTALLED** | Missing | Missing | Missing | No | Optional CV (`FaceTracker` `UNAVAILABLE`; `AutoReframe` degrades to center-crop; `SceneDetect` degrades to FFmpeg) |

---

## 6. Existing Tool & Reusable Capability Matrix (Verified Against Source)

Live discovery via `ToolRegistry.discover()` registered **164 concrete `BaseTool` subclasses**. Below are all tools relevant to AI Video Lab, verified directly from their source files (correcting numerous signature errors from `planning/12_*` and `planning/16_*`):

| Registered Name | Class & File | Registration | Live Local Status | Verified Inputs (`input_schema`) | Verified Outputs (`ToolResult.data`) | Dependencies | Tests Found | Limitations | Reusability |
|---|---|---|---|---|---|---|---|---|---|
| `video_downloader` | `VideoDownloader`<br>`tools/analysis/video_downloader.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `url`*, `output_dir`*, `format` (`video`/`audio_only`/`subtitles_only`/`metadata_only`), `max_resolution` (`360p`..`1080p`), `max_duration_seconds` (default `600`) | `video_path`, `audio_path`, `subtitle_path`, `metadata`, `platform` | `python:yt_dlp` (undeclared in manifests); Deno recommended for YouTube | Mocked in `test_url_ingest.py`; live in `test_url_intake_smoke.py` | Silently skips duration limit if `metadata["duration"]` is 0/None (line 197); no redirect/protocol lockdown in `ydl_opts` | **M1 Intake (direct reuse)** |
| `transcript_fetcher` | `TranscriptFetcher`<br>`tools/analysis/transcript_fetcher.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `url_or_video_id`*, `languages` (default `["en"]`), `include_auto_generated` (default `True`) | `transcript` (`[{text, start, duration}]`), `full_text`, `language`, `is_auto_generated`, `word_count`, `source`, `video_id`, `segment_count` | `python:youtube_transcript_api` (undeclared) | Mocked in `test_url_ingest.py` | YouTube-only; snippet-level timestamps only (no word timestamps); `include_auto_generated` param is read (line 136) but **never passed/enforced** | **M1 Intake & fast YouTube captions** |
| `transcriber` | `Transcriber`<br>`tools/analysis/transcriber.py` | Auto-discovered (`BaseTool`) | **UNAVAILABLE** | `input_path`*, `model_size` (`tiny`..`large-v3`, default `base`), `language`, `diarize` (bool), `output_dir` | `segments`, `word_timestamps`, `language`, `duration_seconds`, `model_size`, `device`, `compute_type`, `gpu_fallback_reason` | `python:faster_whisper`; optional `whisperx` + `HF_TOKEN` for diarization | `tests/tools/test_transcriber_device_selection.py` (passes) | Not installed in `.venv`; `model_size` enum omits `large-v3-turbo`; diarization silently returns un-diarized segments on error or missing `HF_TOKEN` | **Primary offline STT & word-timestamp backbone (M1/M2/M4)** |
| `audio_probe` | `AudioProbe`<br>`tools/analysis/audio_probe.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `input_path`* | `file`, `duration_seconds`, `format_name`, `size_bytes`, `bit_rate`, `stream_count`, `audio` (`codec`, `sample_rate`, `channels`) | `binary:ffprobe` | Indirect via `source_media_review` | Audio-centric (omits video resolution/fps/codec; `source_media_review.py:61` runs a separate `ffprobe` pass to backfill video fields) | **M1 & M5 media validation** |
| `audio_energy` | `AudioEnergy`<br>`tools/analysis/audio_energy.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `input_path`*, `video_duration_seconds`, `energy_threshold_lufs` (default `-40`) | `file`, `audio_duration_seconds`, `analysis` (`peak_loudness_at_seconds`, `peak_loudness_lufs`, etc.), `recommended_offset_seconds`, `needs_loop`, `energy_profile` (`[{time_seconds, loudness_lufs, active}]`) | `binary:ffmpeg` | Upstream tool tests | Downsamples `ebur128` 100ms output to 1-second buckets; built for music offset selection, not sub-second speech prosody | **M2 supporting vocal-energy signal (1s granularity)** |
| `silence_cutter` | `SilenceCutter`<br>`tools/video/silence_cutter.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `input_path`*, `output_path`, `mode` (`remove`/`speed_up`/`mark`), `silence_threshold_db` (`-35`), `min_silence_duration` (`0.5`), `padding_seconds` (`0.08`), `silence_speed_factor` (`6.0`), `codec`, `crf` | In `mode="mark"`: `data` has counts (`silence_segments`, `speech_segments`) + `output` path to JSON containing `{silences, speech_segments, total_duration}` | `cmd:ffmpeg` | `tests/tools/test_silence_detection_failure.py`, `test_silence_speed_timeline.py` (pass) | Fixed dB threshold (`silencedetect`), no speech/music or prosody awareness; if 0 silences found in `mark` mode, returns early without writing JSON file (lines 129-141) | **M2 advisory pause measurement (`mode="mark"`) & M4 jump-cut option** |
| `scene_detect` | `SceneDetect`<br>`tools/analysis/scene_detect.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** (FFmpeg fallback) | `input_path`*, `method` (`content`/`threshold`/`adaptive`), `threshold`, `min_scene_length_seconds` (`1.0`), `output_path` | `scene_count`, `scenes` (`[{index, start_seconds, end_seconds, duration_seconds}]`), `method` (`pyscenedetect` or `ffmpeg`), `output` | `cmd:ffmpeg`; optional `scenedetect[opencv]` | `tests/tools/test_scene_detect_lavfi_escape.py` | PySceneDetect not installed locally; visual cuts do not align with spoken topic shifts | **M2/M4 camera-cut awareness** |
| `frame_sampler` | `FrameSampler`<br>`tools/analysis/frame_sampler.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `input_path`*, `strategy`* (`interval`/`count`/`timestamps`/`scene_guided`), `interval_seconds`, `count`, `timestamps`, `scene_boundaries`, `max_frames`, `output_dir`, `format`, `quality` | `strategy`, `frame_count`, `frames` (`[{path, timestamp_seconds, index}]`), `output_dir` | `cmd:ffmpeg` | Exercised by `test_url_ingest.py` handoff | Mechanical frame extraction only; `-ss` before `-i` uses fast keyframe seek | **M1 review, M2 visual inspection, M4 framing audit** |
| `face_tracker` | `FaceTracker`<br>`tools/analysis/face_tracker.py` | Auto-discovered (`BaseTool`) | **UNAVAILABLE** | `input_path`*, `output_path`, `sample_fps` (`5`), `min_detection_confidence` (`0.5`) | `output` JSON (`faces: [{frame_index, timestamp_seconds, confidence, bbox}]`), `video_width`, `video_height`, `fps`, `duration_seconds` | `mediapipe` + `opencv-python` (both missing) | None dedicated | Picks only single highest-confidence/largest face per frame (lines 222, 288); **cannot distinguish active speaker in multi-person podcasts** | **M4 single-speaker baseline; must be extended with ASD for multi-speaker** |
| `auto_reframe` | `AutoReframe`<br>`tools/video/auto_reframe.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** (center-crop fallback only) | `input_path`*, `output_path`, `target_aspect` (`portrait`/`square`/`landscape`/`cinematic`/`vertical_4_5`), `target_width`, `target_height`, `face_tracking_json`, `smoothing_window` (`15`), `face_padding` (`0.4`), `sample_fps`, `codec`, `crf` | `input`, `output`, `source_resolution`, `crop_resolution`, `output_resolution`, `method` (`face_tracked` or `center_crop`), `target_aspect` | `cmd:ffmpeg`; optional `mediapipe`+`opencv-python` | Upstream tool tests | Not wired in `clip-factory.yaml`; degrades silently to center-crop without MediaPipe/OpenCV; no active speaker switching or split-screen layout | **M4 vertical 9:16 reframing foundation** |
| `video_trimmer` | `VideoTrimmer`<br>`tools/video/video_trimmer.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `operation`* (`cut`/`speed`/`concat`), `input_path`, `output_path`, `start_seconds`, `end_seconds`, `speed_factor`, `segments`, `codec` (`auto`/`copy`/`libx264`) | `operation`, `input`, `output`, `start_seconds`, `end_seconds` | `cmd:ffmpeg` | `tests/tools/test_video_trimmer_workspaces.py` (passes) | `auto` re-encodes with `libx264` when `start_seconds > 0` for frame accuracy; `concat` stream-copies so mixed codecs fail | **M4 clip extraction (direct reuse)** |
| `subtitle_gen` | `SubtitleGen`<br>`tools/subtitle/subtitle_gen.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `segments`*, `format` (`srt`/`vtt`/`json`), `output_path`, `max_chars_per_line` (`42`), `max_words_per_cue` (`8`), `highlight_style` (`none`/`word_by_word`/`karaoke`), `corrections` | `format`, `cue_count`, `output` | Pure Python | `tests/tools/test_subtitle_timestamps.py`, `test_subtitle_corrections.py`, `test_subtitle_escaping.py` (pass) | Expects `segments` with `words` array (or `start`/`end` keys, NOT YouTube's `start`+`duration` schema without normalization!) | **M4 subtitle generation (direct reuse after timestamp normalization)** |
| `remotion_caption_burn` | `RemotionCaptionBurn`<br>`tools/video/remotion_caption_burn.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** (FFmpeg fallback) | Word-level segments, video path, styling, Thai/Unicode tokenization | Captioned MP4 path | `cmd:ffmpeg`, `cmd:ffprobe`; Remotion for kinetic burn | `tests/tools/test_remotion_caption_burn.py`, `test_unicode_tokenizers.py` | Remotion-only for kinetic captions; degrades to FFmpeg `subtitles` filter when `remotion-composer/node_modules` is absent | **M4 kinetic subtitle burn** |
| `video_compose` | `VideoCompose`<br>`tools/video/video_compose.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** (FFmpeg; Remotion uninstalled; HyperFrames untested/sandbox-blocked) | `operation` (`compose`/`render`/`remotion_render`/`burn_subtitles`/`overlay`/`encode`), `edit_decisions`, `asset_manifest`, `proposal_packet`, `narration_transcript_path`, `subtitle_path`, `subtitle_style` | Rendered MP4 + validation/review data | `cmd:ffmpeg`; Node/Remotion or HyperFrames | `tests/tools/test_video_compose_vertical.py` (passes) | Calling `get_info()` / runtime check invokes `npx` which hangs in no-network sandboxes; silent runtime swaps forbidden by governance | **M4/M5 composition engine** |
| `video_analyzer` | `VideoAnalyzer`<br>`tools/analysis/video_analyzer.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `source`*, `analysis_depth` (`transcript_only`/`standard`/`deep`), `max_keyframes`, `output_dir` | `VideoAnalysisBrief` JSON | `cmd:ffmpeg` + optional `yt-dlp`, `youtube-transcript-api`, `faster-whisper`, `scenedetect` | Upstream tests | Built for reference-video style extraction (not long-form podcast clipping); directly imports sibling tools rather than using registry | **Reference-video analysis; pattern for multi-language caption listing (`ytt.list()`)** |
| `export_bundle` | `ExportBundle`<br>`tools/publishers/export_bundle.py` | Auto-discovered (`BaseTool`) | **AVAILABLE** | `video_path`*, `title`*, `project_name`, `export_dir`, `description`, `tags`, `hashtags`, `chapters`, `subtitles_path`, `thumbnail_path`, `platform`, `visibility` | `publish_log` (validated), `export_path`, `files_written` | Pure Python | Upstream contract tests | Single-video focused (`output.mp4`); needs multi-clip batch loop or wrapper for `clip-factory` N-clip exports | **M5 export packaging** |
| *(Not registered)* `CostTracker` | `CostTracker`<br>`tools/cost_tracker.py` | **NOT a BaseTool** (direct Python import) | **AVAILABLE** | `budget_total_usd`, `reserve_pct`, `single_action_approval_usd`, `mode`, `cost_log_path` | `cost_snapshot()` -> `{total_spent_usd, total_reserved_usd, budget_remaining_usd}` | Pure Python | `tests/contracts/test_phase0_contracts.py` | Not in `ToolRegistry`; checkpoint schema strictly rejects extra keys in `cost_snapshot` | **Budget governance across all paid API stages** |

*(Additional `lib/` utilities audited: `lib/scoring.py` implements `ProviderScore` / `ProductionPathScore` for provider selection, NOT clip editorial scoring; `lib/clip_embedder.py` implements module-level `embed_images`/`embed_texts`/`pool_frames` over CLIP ViT-B/32 with 77-token max length, unsuitable for long conversational transcripts.)*

---

## 7. Detailed Milestone 1 (M1) Forensic Audit

### 7.1 Files Audited
- `lib/url_ingest.py` (528 lines)
- `tests/unit/test_url_ingest.py` (305 lines, 12 tests — **12/12 PASSED** in 5.50s)
- `tests/qa/test_url_intake_smoke.py` (90 lines — **0 tests collected by pytest**)
- `pipeline_defs/clip-factory.yaml` (208 lines; `idea.tools_available` includes `video_downloader`, `transcript_fetcher`)
- `skills/pipelines/clip-factory/idea-director.md` (135 lines; documents `URLIntakeAdapter` Source Acquisition Protocol)
- Live verification project artifacts: `projects/m1-final-agent-verification/` (`source_video.mp4` 320x240 AV1 19.02s, `source_audio.wav` 16kHz mono PCM, `transcript.json`, `source_manifest.json`, `source_media_review.json`, `checkpoint_idea.json` with `status="awaiting_human"`, `human_approved=false`, `decision_log.json`).

### 7.2 Verified M1 Risks, Findings & Remediation Matrix

| ID | Issue | Source Evidence | Severity | Reproduction / Failure Scenario | User Impact | Recommended Correction | Blocks M2 Phase 2A? |
|---|---|---|---|---|---|---|---|
| **M1-F01** | **`yt-dlp` and `youtube-transcript-api` undeclared in dependency manifests** | `requirements.txt:1-20`, `requirements-dev.txt:1-5`, `setup.py:9-19` omit both packages, while `tools/analysis/video_downloader.py:40` and `transcript_fetcher.py:37` require them. | **CRITICAL** | Fresh clone + `pip install -r requirements.txt` -> `VideoDownloader` & `TranscriptFetcher` report `UNAVAILABLE`, breaking `ingest_url()`. | Clean installs and CI cannot run URL intake. | Declare pinned/minimum `yt-dlp` and `youtube-transcript-api` in `requirements.txt` and align `setup.py`. | **NO** (2A is contracts/schemas only), **YES before M1/M2 integration**. |
| **M1-F02** | **Unknown/zero metadata duration silently bypasses `max_duration_seconds`** | `lib/url_ingest.py:338-345` checks `if duration and duration > max_duration_seconds:` (skipped when `duration == 0.0`); line 439 computes `duration_s` from `ffprobe` but **never re-checks `duration_s > max_duration_seconds`**! Same bug in `tools/analysis/video_downloader.py:197`. | **HIGH** | Livestream replay, broken metadata response, or Vimeo URL with missing `duration` downloads an unbounded 5-hour file and finalizes it into `source/`. | Disk exhaustion, massive transcription time/cost, broken duration contract. | Enforce post-probe `if duration_s <= 0 or duration_s > max_duration_seconds:` check in staging before finalization; reject/cleanup staging on violation; pass `match_filter` / filesize cap to `yt-dlp`. | **NO**, must fix in **Phase 1 (M1 Hardening)**. |
| **M1-F03** | **Preflight DNS SSRF check does not guard redirects, DNS rebinding, or offline DNS errors** | `lib/url_ingest.py:135,145-175`: allows `http://`, runs `socket.getaddrinfo()` once before `yt-dlp` makes its own HTTP connections, and silently `pass`es on `socket.gaierror` for any allowlisted domain name (line 173-175). `video_downloader.py:267-274` sets no extractor/protocol restrictions. | **HIGH** | (a) DNS rebinding between preflight and `yt-dlp` connect; (b) HTTP redirect from allowlisted host to private/metadata IP; (c) unencrypted `http://` MITM; (d) `HTTP_PROXY` routing bypass. | Misleading security claim ("Strict SSRF protection" in `README.md:34`). | Tighten scheme policy (prefer HTTPS or document HTTP risk), restrict `yt-dlp` `allowed_extractors` / protocols, fail closed or explicitly mark offline mode on DNS errors, and reframe docs honestly as *application-level hostname allowlisting & preflight IP filtering*. | **NO**, must fix in **Phase 1**. |
| **M1-F04** | **Non-transactional multi-file finalization & stale-artifact carryover** | `lib/url_ingest.py:448-455`: 3 sequential `shutil.move()` calls (`source_video.mp4`, `source_audio.wav`, `transcript.json`) without rollback; if a re-run has `has_native_captions=False`, a pre-existing `transcript.json` from an earlier run stays on disk! | **HIGH** | Windows file lock (e.g. Backlot/media player holding `source_audio.wav`) fails move #2 after move #1 already overwrote `source_video.mp4` -> mismatched video/audio/manifest. | Silent data corruption between video, audio, and transcript. | Stage complete bundle, remove stale optional files (`transcript.json`) when absent in new run, use backup+rollback swap (or versioned immutable source directory + atomic manifest pointer). | **NO**, must fix in **Phase 1**. |
| **M1-F05** | **Hardcoded English-only caption retrieval** | `lib/url_ingest.py:404`: `"languages": ["en"]` hardcoded; ignores Hindi, Hinglish, Spanish, or auto-detected video language. Meanwhile `tools/analysis/video_analyzer.py:272-281` already implements `ytt.list()` language discovery! | **MEDIUM** | Ingesting a Hindi/Hinglish or non-English YouTube podcast returns `has_native_captions=False` even when native captions exist. | Breaks multilingual & Hinglish product goal. | Expose configurable `languages: Optional[list[str]]` and reuse `YouTubeTranscriptApi().list()` discovery prioritizing manual captions in preferred/source languages before auto-generated captions. | **NO**, must fix in **Phase 1**. |
| **M1-F06** | **Raw `audio_path` copied blindly to `.wav` without verifying WAV/PCM format** | `lib/url_ingest.py:381-388`: if `dl_res.data.get("audio_path")` has any audio stream, `shutil.copy2(raw_audio_path, staging_audio_wav)` copies raw bytes to `source_audio.wav` without checking codec (`pcm_s16le`) or sample rate (`16000`). | **MEDIUM** | If `video_downloader` or a future extractor returns `.m4a`/`.opus` as `audio_path`, `source_audio.wav` is actually non-WAV compressed audio. | Downstream WAV/PCM readers fail unexpectedly. | Verify `codec_name == "pcm_s16le"` and `sample_rate == "16000"` and `channels == 1` before copying; otherwise run `extract_audio_fallback()`. | **NO**, must fix in **Phase 1**. |
| **M1-F07** | **QA smoke test uncollected by pytest** | `tests/qa/test_url_intake_smoke.py:18` defines `run_smoke_test()` (no `test_*` function). Verified: `pytest --collect-only tests/qa/test_url_intake_smoke.py` collects `0 items`! Yet `README.md:43,156` claims "2 automated smoke tests" and instructs users to run pytest on it! | **MEDIUM** | Running the `README.md` Quick Start test command fails or silently runs 0 smoke tests. | False confidence in test coverage; broken README instructions. | Wrap in `def test_url_intake_smoke()` decorated with `@pytest.mark.network` (or `@pytest.mark.qa`), register marker in `pyproject.toml`/`pytest.ini`, and fix README. | **NO**, must fix in **Phase 1**. |
| **M1-F08** | **`URLIntakeAdapter` not registered in `ToolRegistry` & hardcodes `"clip-factory"`** | `lib/url_ingest.py:526` hardcodes `"pipeline_type": "clip-factory"`; `URLIntakeAdapter` is a `lib/` helper, not a `BaseTool` in `tools/`. | **MEDIUM** | Tool-calling-only agents (without shell `python -c`) cannot discover `url_intake` via `registry.get()`; `podcast-repurpose` cannot pass its own `pipeline_type`. | Limits tool-first agent portability and pipeline reuse. | Expose thin `BaseTool` wrapper `tools/analysis/url_intake.py` (`name="url_intake"`) delegating to `URLIntakeAdapter`, parameterize `pipeline_type`, and declare in `clip-factory.yaml` & `podcast-repurpose.yaml`. | **NO**, fix in **Phase 1**. |
| **M1-F09** | **No retry/backoff, partial download cleanup, or codec proxy normalization (AV1)** | `lib/url_ingest.py:351` runs one `yt-dlp` call with no retry; `projects/m1-final-agent-verification/source/source_video.mp4` is **AV1** (`codec_name: "av1"`), which `ensure_valid_mp4` accepts without generating an H.264 editing proxy. | **MEDIUM** | Transient network drops fail immediately; AV1 source causes slow/jittery seeking in Remotion `<OffthreadVideo>` and editor tools. | Reduced reliability and downstream render friction. | Add bounded retry on transient network errors and optional H.264/AAC editing proxy (`source_video_h264.mp4`) when master codec != `h264`, preserving pristine master. | **NO**, fix in **Phase 1 / Phase 4**. |

---

## 8. Detailed Milestone 2 (M2) Forensic Audit & Document Contradiction Reconciliation

### 8.1 Actual Code Status of M2
Verified directly on disk (`Test-Path` = `False` for every proposed file):
- `lib/models/` — **DOES NOT EXIST**
- `schemas/artifacts/clip_selection_plan.schema.json` — **DOES NOT EXIST**
- `lib/transcript_normalizer.py` — **DOES NOT EXIST**
- `lib/clip_discovery_engine.py` — **DOES NOT EXIST**
- `lib/hook_validator.py` — **DOES NOT EXIST**
- `lib/acoustic_profiler.py` — **DOES NOT EXIST**
- `lib/semantic_segmenter.py` — **DOES NOT EXIST**
- `lib/editorial_evaluator.py` — **DOES NOT EXIST**
- `lib/deduplicator.py` — **DOES NOT EXIST**
- `lib/cold_viewer_auditor.py` — **DOES NOT EXIST**
- `lib/conversation_structure.py` — **DOES NOT EXIST**
- `tools/analysis/clip_selector.py` — **DOES NOT EXIST**
- `tools/analysis/url_intake.py` — **DOES NOT EXIST**

**Verdict on M2:** **0% implemented in production source code.** Everything for M2 exists strictly in planning/architecture documents (`planning/12_*` through `planning/16_*`).

### 8.2 Critical Contradictions & Inaccuracies Found Across Existing Planning Docs & README
Codex MUST NOT trust prior planning docs blindly. Forensic code comparison uncovered these exact errors:

| Source Document | Erroneous / Stale Claim | Actual Verified Repository Truth |
|---|---|---|
| `planning/12_*` (line 20) | Claims HEAD SHA is `7cf6b52a514d489116e257eb49b25da1bc92e624` | Actual HEAD SHA is `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`. |
| `planning/12_*` (lines 76–86) | Claims `tools/video/scene_detect.py`, `CLIPEmbedder` class, `MultiCriteriaScorer` class, `backlot/state.py:derive_board_state`, and wrong input/output param names (`audio_path`, `video_path`, `silence_intervals`, `transcript_words`) | Actual paths/symbols: `tools/analysis/scene_detect.py`, module functions in `lib/clip_embedder.py`, `ProviderScore`/`score_provider` in `lib/scoring.py`, `backlot/state.py:load_board_state()`, and `input_path` / `segments` / `energy_profile` / `word_timestamps` across tools. |
| `planning/12_*` (lines 152–173) | Lists `claude-3-5-sonnet-20241022`, `gemini-1.5-pro-002`, `gpt-4o-2024-08-06` as "current 2026 standards" | Severely outdated as of Nov 2026 (current frontier lineups are OpenAI GPT-6/6.1, Anthropic Claude 5.5/Fable 5.2, Google Gemini 4/3.8 — detailed with citations in Deliverable 2). |
| `planning/12_*` (line 64) | Claims "all 7 OpenMontage video pipelines" | `pipeline_defs/` contains **13** pipeline manifests. |
| `planning/13_*` (§8.2, line 236) | Claims `script.json` is synthesized *exclusively after human approval* | **Contract conflict!** `lib/checkpoint.py:134-143` strictly REQUIRES `artifacts["script"]` to exist when writing `checkpoint_script.json` with `status="awaiting_human"`. Therefore, `script.json` MUST be populated as a *provisional* canonical artifact at `awaiting_human` and finalized upon `human_approved=True`! |
| `planning/16_*` (lines 33–36, 222) | Records older HEAD `2e003e6` (pre-commit snapshot), wrongly claims `cost_tracker` is auto-discovered by `ToolRegistry`, and describes 3-tier timestamp provenance (superseded by 8-tier in `planning/13_*`) | HEAD is now `7cf6b52f...`; `CostTracker` is NOT a `BaseTool`; `ToolRegistry` discovers 164 tools. |
| `README.md` (lines 4, 34, 35, 43, 61–68, 156) | Claims "22 passed" badge, "Strict SSRF protection", "1800s default", "2 automated smoke tests" in `test_url_intake_smoke.py`, and outdated 3-tier timestamp / hardware-capped wording | `lib/url_ingest.py:304` defaults to `max_duration_seconds=3600` (not 1800); `test_url_intake_smoke.py` has 0 pytest-collectible tests; SSRF is preflight-only. |
| `planning/06_FINAL_IMPLEMENTATION_READINESS_GATE.md` | Listed in `README.md` dossier table | File is **0 bytes (completely empty)**. |
| `skills/pipelines/clip-factory/scene-director.md` (line 28) | Claims "OpenMontage does not yet have first-class auto-reframe." | `tools/video/auto_reframe.py` exists and is registered (`auto_reframe`), though not wired into `clip-factory.yaml` and missing MediaPipe/OpenCV locally. |

---

## 9. Empirical Test Execution Evidence

Executed directly in `.venv` (`Python 3.14.10`, `pytest 9.2.0`) during this read-only audit:

| Command / Target | Result | Evidence Notes |
|---|---|---|
| `pytest tests/unit/test_url_ingest.py -v` | **12 passed in 5.50s** | Covers project ID validation, scheme/domain checks, mocked DNS SSRF blocking, disk headroom, MP4/MKV remux via real FFmpeg, 16kHz mono WAV extraction, mocked full ingest flow, and handoff to `review_source_media`. |
| `pytest --collect-only tests/qa/test_url_intake_smoke.py` | **0 items collected** | Confirms M1-F07: `run_smoke_test()` is not collected by pytest. |
| `pytest tests/tools/test_silence_detection_failure.py tests/tools/test_subtitle_timestamps.py tests/tools/test_video_trimmer_workspaces.py tests/tools/test_video_compose_vertical.py tests/tools/test_scoring.py tests/tools/test_transcriber_device_selection.py -q` | **18 passed in 8.97s** | Confirms core reusable post/analysis tools work in `.venv`. |
| `pytest tests/contracts/test_backlot_contract.py tests/contracts/test_pipeline_catalog.py tests/contracts/test_pipeline_manifest_categories.py tests/contracts/test_phase0_contracts.py tests/lib/ -q` | **175 passed in 235.01s** | Confirms Backlot contract, pipeline catalog, manifest categories, Phase 0 contracts, and `tests/lib/` unit tests all pass cleanly. |
| `pytest tests/contracts/` (unfiltered in no-network sandbox) | **Slow/blocks on `npx` / HyperFrames runtime probe** | Note for Codex: Tests calling `registry.support_envelope()` or `HyperFramesCompose._runtime_check()` spawn `npx` which can stall when network access is disabled or uncached. Run targeted suites first and check `npx` latency in your environment. |

---

## 10. Project History Categorization (Categories A–F)

### Category A — Already Implemented and Present in Source
- Complete upstream OpenMontage platform (`164` registered tools, `13` pipeline manifests, `20` artifact schemas, `93` Layer 3 skills, `lib/checkpoint.py`, `lib/pipeline_loader.py`, `lib/source_media_review.py`, `tools/cost_tracker.py`, `backlot/` FastAPI+SSE UI, `remotion-composer/` React project).
- M1 URL Intake Adapter (`lib/url_ingest.py`) + `clip-factory.yaml` `idea` stage tool wiring + `idea-director.md` Source Acquisition Protocol.
- Reusable media post/analysis tools: `video_downloader`, `transcript_fetcher`, `transcriber`, `audio_probe`, `audio_energy`, `silence_cutter`, `scene_detect`, `frame_sampler`, `face_tracker`, `auto_reframe`, `video_trimmer`, `video_stitch`, `video_compose`, `subtitle_gen`, `remotion_caption_burn`, `audio_mixer`, `audio_enhance`, `color_grade`, `export_bundle`.

### Category B — Implemented and Tested (With Verified Evidence)
- `lib/url_ingest.py`: 12 unit tests passing (`tests/unit/test_url_ingest.py`) + live `idea`-stage verification artifacts in `projects/m1-final-agent-verification/` (`Me at the zoo`, 19.02s).
- Core OpenMontage tools (`silence_cutter`, `subtitle_gen`, `video_trimmer`, `video_compose` vertical path, `lib/scoring.py`, `transcriber` device selection): 18 targeted tests passing.
- Checkpoint gate enforcement (`awaiting_human`, `human_approved=False`) verified empirically in `projects/m1-final-agent-verification/checkpoint_idea.json`.

### Category C — Explored and Researched (Not Implemented)
- Competitive analysis of OpusClip, Klap, Munch, Auto-Editor (`planning/02_*`).
- Long-form conversation intelligence, discourse topology, cold-viewer comprehension testing, context expansion without fabrication (`planning/13_*`).
- 8-tier honest timestamp provenance taxonomy and abolition of blind 400ms silence snapping (`planning/13_*`).
- CTC forced alignment (`wav2vec2`/WhisperX), Silero VAD, pyannote diarization, Active Speaker Detection (`TalkNet`, `Light-ASD`/`LR-ASD`, `LoCoNet`), and late-2026 frontier/open-weight LLM & multilingual embedding stacks (Deliverable 2).
- Human-labelled golden evaluation dataset across 10 content archetypes (`planning/13_*`, refined in Deliverable 2).

### Category D — Architecturally Designed (Contracts Defined, Zero Production Code)
- `schemas/artifacts/clip_selection_plan.schema.json` and `lib/models/{transcript.py, clip_plan.py}` (Phase 2A).
- `lib/transcript_normalizer.py` with NFC Unicode code-point half-open spans `[char_start, char_end)` and bidirectional source mapping (Phase 2B).
- `lib/acoustic_profiler.py` wrapping `SilenceCutter(mode="mark")` and `AudioEnergy` (Phase 2C).
- `lib/conversation_structure.py` (Phase 2D).
- `lib/hook_validator.py`, `lib/cold_viewer_auditor.py`, `lib/deduplicator.py`, `tools/analysis/clip_selector.py` (Phase 2E).
- `tools/analysis/url_intake.py` (`BaseTool` wrapper for `URLIntakeAdapter`, proposed in `planning/11_*`).

### Category E — Previously Attempted but Incomplete / Partially Broken
- `tests/qa/test_url_intake_smoke.py`: written as a manual script (`run_smoke_test()`), fails pytest collection.
- `remotion-composer/`: source exists, `node_modules` never installed locally, Node version (v25.8.1) mismatches declared engines.
- `planning/06_FINAL_IMPLEMENTATION_READINESS_GATE.md`: created as a 0-byte empty placeholder.
- `README.md` & `planning/12_*`: partially updated with unverified claims (corrupted SHA, outdated 2024 models, wrong class/parameter names).

### Category F — New Capabilities Required to Reach Full Product Vision
- **Multi-Speaker Active Speaker Detection (ASD) & Dynamic 9:16 Reframing:** Replacing single-largest-face crop with audio-visual ASD (e.g., TalkNet / Light-ASD / LoCoNet) + smooth speaker switching / split-screen layouts.
- **Word-Level Forced Alignment & Diarization Pipeline:** Reliable offline (`WhisperX` + `wav2vec2` + `pyannote` + `Silero VAD`) and optional managed cloud STT (`Deepgram Nova-3` / `AssemblyAI` / existing `azure_stt`/`mistral_stt`) so captions and boundaries are truly word-accurate, including for Hindi/Hinglish code-switching.
- **Multi-Clip Batch Composition & Export Orchestration:** Extending `clip-factory` `scene_plan -> assets -> edit -> compose -> publish` with automated per-clip trimming, 9:16 safe-zone layout, synchronized word-highlighted captions, AV playback/sync QA, and multi-clip `export_bundle` delivery.
- **Model-Substitutable Evaluation & Optional Headless Inference Seam:** Benchmark harness over real human-labelled podcast episodes to empirically evaluate frontier vs local models without locking the pipeline to one vendor.

---

## 11. Known Technical Debt & Verified Limitations Summary

1. **Packaging / Clean-Install Debt:** `yt-dlp` and `youtube-transcript-api` missing from `requirements.txt`/`setup.py`; `setup.py` lags `requirements.txt` by 7 packages; Python version split (`3.11` in CI/`.python-version` vs `3.14.10` locally).
2. **M1 Intake Safety Gaps:** Missing post-download duration enforcement, non-transactional multi-file moves, English-only captions, raw audio copy without WAV/PCM validation, preflight-only SSRF boundary.
3. **Zero M2 Intelligence Code:** Conversation segmentation, cold-viewer evaluation, spoken-hook provenance, deduplication, and `clip_selection_plan` schema are entirely unimplemented.
4. **Local Runtime Gaps for M2–M5:** `faster-whisper`, `mediapipe`, `opencv-python`, `scenedetect`, `torch`, `ollama`, and `remotion-composer/node_modules` are all absent from this workstation.
5. **Documentation Drift:** Prior planning reports (`12`, `13`, `15`, `16`) and `README.md` contain verifiable factual errors (wrong HEAD SHA, hallucinated symbol names, outdated 2024 model IDs, unaddressed `lib/checkpoint.py` `awaiting_human` script requirement). Deliverables 20, 21, and 22 supersede those stale claims.
