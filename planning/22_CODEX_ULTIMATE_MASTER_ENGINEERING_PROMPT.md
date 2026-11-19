# AI VIDEO LAB — ULTIMATE CODEX MASTER ARCHITECTURE, INVESTIGATION & EXECUTION PROMPT (v2 — BUILD-READY)

> **How to use this prompt:** Copy everything below the horizontal rule and paste it directly into **OpenAI Codex** inside `C:\AI-Video-Lab`.
> This prompt is **100% self-contained** and fuses:
> 1. Verified codebase forensics from `C:\AI-Video-Lab` (`HEAD 7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f`),
> 2. All intelligence, architecture, and roadmap specifications from `planning/20_*` and `planning/21_*`, and
> 3. Strict architectural rigor (orthogonal timestamp/evidence dimensions, true offset-mapped Unicode spans, zero hardcoded transient model IDs, explicit modular boundaries, full end-to-end execution trace, and milestone-gated build execution).

---

# ROLE & OPERATING MANDATE

Act as the **Principal Software Architect, Senior Python Engineer, AI Systems Engineer, Video Infrastructure Engineer, and Technical Auditor** responsible for building the next major engineering evolution of **AI Video Lab** inside `C:\AI-Video-Lab`.

Think and operate like the principal engineer who will own and maintain this system in production — not like an assistant rushing to check boxes.

- **We are extending OpenMontage — NOT replacing it.**
- **Your Turn 1 is strictly READ-ONLY orientation and baseline verification (Section 14).** Do NOT modify any file, install any package, or run destructive Git commands until Turn 1 completes and the user explicitly authorizes the next milestone.
- **After authorization, execute strictly ONE milestone at a time**, following the exact contracts, modularity rules, testing bars, and exit gates in this blueprint.

---

# 1. VERIFIED PROJECT & REPOSITORY CONTEXT

### 1.1 Repository Identity (Verified Snapshot — Re-verify Live in Turn 1)
- **Repository:** `https://github.com/Unstocks/AI-video-Lab.git` (`C:\AI-Video-Lab`)
- **Upstream Base:** `https://github.com/OpenMontageInc/OpenMontage.git` (`upstream/main` @ `2e003e6`)
- **Active Local Branch:** `main` tracking `origin/main`; shared review branch on remote is `origin/openmontage` (pointing at the same commit as `origin/main`).
  - *Branch naming rule:* Both `main` and lowercase `openmontage` are accepted. Do NOT spend time proposing branch renames or treating lowercase branch spelling as an engineering defect. Always verify `git branch -avv` live before acting.
- **Verified HEAD Commit SHA:** `7cf6b52f0b279f50d193f6aab7c25be5f3b8f95f` (`docs: update README with AI Video Lab architecture, M1 intake status, and M2 intelligence roadmap`) — 2 commits ahead of `upstream/main` (`428b298` M1 URL intake + planning docs; `7cf6b52` README update).
- **Pre-Existing Uncommitted Working-Tree Files (MUST BE PRESERVED):**
  - `M planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md`
  - `M planning/13_M2_CONVERSATION_INTELLIGENCE_AND_CLIP_DISCOVERY_ARCHITECTURE.md`
  - `?? planning/15_M2_FINAL_EXECUTION_PLAN_AND_ACCEPTANCE_GATES.md`
  - `?? planning/20_AI_VIDEO_LAB_COMPLETE_REPOSITORY_AND_PRODUCT_INTELLIGENCE.md`
  - `?? planning/21_AI_VIDEO_LAB_TARGET_ARCHITECTURE_AND_IMPLEMENTATION_ROADMAP.md`
  - `?? planning/22_CODEX_ULTIMATE_MASTER_ENGINEERING_PROMPT.md`

### 1.2 Local Hardware & Environment Profile (Local-First, NOT Hardware-Limited)
- **Host:** Windows workstation, NVIDIA GeForce RTX 3050 Laptop GPU (~6 GB VRAM), ~15.7 GB RAM.
- **Python Drift:** `.venv` currently runs **Python 3.14.10** (`pytest 9.2.0`), whereas `.python-version` and `.github/workflows/ci.yml` target **Python 3.11** (`setup.py`: `>=3.10`, `README.md`: `3.12+`). Native ML wheels (`faster-whisper`/`ctranslate2`, `whisperx`, `mediapipe`, `torch` CUDA) often lag Python 3.14 on Windows.
- **Node / Remotion Drift:** System `node` is **v25.8.1**, whereas `.node-version` is `22.23.4` and `remotion-composer/package.json` declares `"node": "^22.23.4 || ^24.22.1 || ^26.12.1"`. `remotion-composer/node_modules` is **NOT installed** locally.
- **FFmpeg / FFprobe:** `ffmpeg 7.1-essentials_build-www.gyan.dev` present in `.venv\Scripts\` and `.runtime\tools\bin\`.
- **Missing Optional Tools Locally:** `faster-whisper`, `whisperx`, `torch`, `transformers`, `mediapipe`, `opencv-python`, `scenedetect`, and `ollama` are **NOT installed**.
- **Rule on Hardware vs. Quality:** Local-first is our operational preference, **NOT a ceiling on editorial intelligence**. Never downgrade conversation reasoning to fit 6 GB VRAM. Support hybrid execution (frontier reasoning models + deterministic local Python tools + optional local specialist models).

### 1.3 Stale / Contradictory Claims in Prior Docs (DO NOT TRUST BLINDLY)
Code is always authoritative over prior planning docs. Forensics already proved these discrepancies:
1. `planning/12_*` contains a corrupted HEAD SHA (`7cf6b52a...`), wrong paths/symbols (`tools/video/scene_detect.py`, `CLIPEmbedder`, `MultiCriteriaScorer`, `derive_board_state`), wrong tool parameter names, and stale 2024 models.
2. `planning/13_*` claimed `script.json` is written only after human approval — contradicting `lib/checkpoint.py:134-143`, which **requires** `"script"` on `awaiting_human` checkpoints for stage `script`.
3. `planning/16_*` wrongly listed `CostTracker` as auto-discovered by `ToolRegistry` (it is a standalone class, NOT a `BaseTool`).
4. `README.md` overstates SSRF protection ("Strict SSRF protection"), states `1800s` default duration (actual `lib/url_ingest.py:304` is `3600`), and claims `tests/qa/test_url_intake_smoke.py` has 2 automated smoke tests (actual pytest collection: **0 items**).
5. `skills/pipelines/clip-factory/scene-director.md:28` claims auto-reframe does not exist (`tools/video/auto_reframe.py` exists).
6. `planning/06_FINAL_IMPLEMENTATION_READINESS_GATE.md` is 0 bytes (empty).

---

# 2. PRODUCT VISION & EDITORIAL CONSTITUTION

### 2.1 Core Product Purpose
Transform long-form conversations, podcasts, interviews, keynotes, webinars, and videos into a **small portfolio of genuinely excellent, independently understandable vertical (9:16) short-form videos** (with honest 1:1 or 16:9 fallback when source visuals like slides/demos cannot survive vertical cropping).

### 2.2 Non-Negotiable Quality Philosophy
> **Three genuinely exceptional, contextually complete, cold-viewer-understandable clips are far more valuable than ten mediocre or confusing clips.**

### 2.3 Explicit Anti-Goals (Strictly Forbidden)
- Fixed-interval or naive time-window slicing as the primary editorial method.
- Extracting isolated punchy sentences stripped of premises, questions, or essential qualifiers.
- Selecting clips solely from audio energy spikes or keyword matching.
- Artificial hooks that fabricate dialogue or rearrange speech to alter meaning.
- Repetitive clips repeating the same argument across the batch.
- Mid-word, mid-thought, or blind silence-snapped boundaries.
- False timestamp precision (claiming millisecond accuracy from coarse captions).
- Generic AI-generated titles masquerading as spoken hooks or disguising weak clips.
- Padding weak candidates to hit an arbitrary clip count quota.

### 2.4 Intended End-to-End Experience (20 Stages) & Verified Current Status
- **Implemented & Verified:** Local/URL intake trigger (`idea-director.md`), source media inspection (`lib/source_media_review.py`), checkpoint human approval gate (`lib/checkpoint.py`), read-only Backlot storyboard (`backlot/`).
- **Implemented But Needs Hardening:** URL validation/acquisition (`lib/url_ingest.py` — 9 verified defects M1-F01..M1-F09).
- **Partially Implemented:** Captions/STT (`transcript_fetcher` works for English YouTube; `transcriber` unavailable locally; cloud STT unconfigured), raw acoustic/cut signals (`silence_cutter`, `audio_energy`, `scene_detect`), vertical trim/reframe/subtitle/compose/export primitives (`video_trimmer`, `auto_reframe` center-crop fallback, `subtitle_gen`, `remotion_caption_burn` FFmpeg fallback, `video_compose`, `export_bundle` single-clip).
- **0% Implemented (M2 Core):** Transcript normalization & reversible offset mapping, macro conversation understanding, semantic candidate discovery, context reconstruction, cold-viewer comprehension audit, spoken-hook provenance verification, natural boundary refinement, editorial eligibility & ranking, temporal/semantic deduplication, `clip_selection_plan.schema.json`, `lib/models/`, `tools/analysis/clip_selector.py`, Active Speaker Detection (ASD), batch multi-clip export & AV QA, and golden-dataset evaluation harness.

---

# 3. VERIFIED OPENMONTAGE EXECUTION ARCHITECTURE & CONTRACTS

### 3.1 Binding Principles
1. **Agent-First Control Plane (`AGENTS.md`, `AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md:5-108`):** The coding assistant (Codex) IS the orchestrator. It reads YAML manifests (`pipeline_defs/`), follows Layer 2 stage director skills (`skills/pipelines/<pipeline>/<stage>-director.md`) and Layer 3 vendor skills (`.agents/skills/` — 93 folders), invokes Python `BaseTool` subclasses via `ToolRegistry`, self-reviews via `skills/meta/reviewer.md`, checkpoints via `lib/checkpoint.py`, and halts at human gates.
2. **No Competing Orchestrator & No Unjustified Runtime LLM Framework:** Python provides deterministic tools, domain libraries, and state persistence (`docs/ARCHITECTURE.md:100`). `lib/providers/` is currently an empty reserved directory. `config.yaml`'s `llm:` block has zero active callers in `lib/` or `tools/`. Do NOT add LangChain/CrewAI/AutoGen or a parallel Python orchestrator.
3. **Strict Modularity Taxonomy:** Maintain clean internal modularity, and ALWAYS distinguish:
   - **Reusable internal domain module (`lib/`):** Pure, testable Python library (e.g., `lib/models/`, `lib/transcript_normalizer.py`, `lib/hook_validator.py`). May be introduced early for sound separation of concerns, **even before direct agent exposure**, but must NEVER be represented as an agent-callable tool until wrapped and registered.
   - **Registered production tool (`tools/`):** Concrete `BaseTool` subclass auto-discovered by `ToolRegistry`.
   - **Pipeline stage (`pipeline_defs/*.yaml`):** Declarative stage contract (`produces`, `required_tools`, `tools_available`, `human_approval_default`).
   - **Stage / Meta skill (`skills/`):** Markdown behavioral instructions for the agent.
   - **Observational UI (`backlot/`):** Strictly read-only FastAPI + SSE server (`backlot/server.py:5` — *"never writes to project directories"*).

### 3.2 Verified End-to-End Execution Trace (Ground Truth)
```text
User Request (URL or local file)
  ↓
Codex Agent reads AGENTS.md -> AGENT_GUIDE.md -> pipeline_defs/clip-factory.yaml (v2.0, 7 stages)
  ↓
Stage Director Skill: skills/pipelines/clip-factory/<stage>-director.md (+ Layer 3 .agents/skills/*)
  ↓
Tool Discovery: tools.tool_registry.registry.discover() / ensure_discovered()
  └─ Walks tools/ via pkgutil.walk_packages() -> registers 164 concrete BaseTool subclasses
  └─ Callers MUST discover before registry.get("<name>")
  ↓
Tool Execution: BaseTool.__init_subclass__ (tools/base_tool.py:414-421)
  └─ Auto-wraps execute() as: _cache_execute(_instrument_execute(impl))
     (Cache is outermost: hit skips live call + Backlot event emission;
      _instrument_execute emits start/finish/error to projects/<id>/events.jsonl)
  └─ check_dependencies() checks cmd:/binary:, env:, python: prefixes
  └─ IMPORTANT: BaseTool does NOT auto-run jsonschema validation on inputs/outputs;
     tools must explicitly validate critical input/output invariants!
  └─ Returns ToolResult(success, data, artifacts, error, cost_usd, duration_seconds, seed, model, from_cache)
  ↓
Artifact Production & Validation: schemas/artifacts/__init__.py
  └─ 20 registered schemas in ARTIFACT_NAMES; validate_artifact(name, data) runs Draft 2020-12 jsonschema
  ↓
Checkpoint Persistence & Gate Governance: lib/checkpoint.py
  └─ write_checkpoint() writes projects/<id>/checkpoint_<stage>.json atomically (*.tmp -> os.replace)
  └─ Archives superseded non-in_progress checkpoint to projects/<id>/history/
  └─ Merges decision_log into projects/<id>/decision_log.json
  └─ HARD INVARIANT (lines 134-143): status in {"completed", "awaiting_human"} MUST include
     CANONICAL_STAGE_ARTIFACTS[stage] (e.g., stage "script" REQUIRES artifacts["script"] even on awaiting_human!)
  └─ HARD GATE (lines 487-515): gated stage (human_approval_default: true) written "completed"
     without human_approved=True raises CheckpointValidationError("GATE VIOLATION")
  └─ PREREQUISITES (lines 304-366): _enforce_stage_prerequisites blocks advancing until all predecessors
     are status="completed" and (if gated) human_approved=True
  ↓
Human Review (Chat Gate) + Backlot Observational Board (backlot/server.py + backlot/state.py)
  └─ watchfiles.awatch("projects/") -> SSE hub -> browser fetches /api/project/{id}/state
  └─ load_board_state() -> _build_storyboard() joins scene_plan.scenes × script.sections
     (by script_section_id or timestamp overlap) × asset_manifest.assets
  └─ Protected by TrustedHostMiddleware(["127.0.0.1", "localhost"]) + path-escape guards
  ↓
Production & Rendering (stages scene_plan -> assets -> edit -> compose -> publish)
  └─ Media profiles: lib/media_profiles.py (Note: YOUTUBE_SHORTS still has legacy max_duration_seconds=60!)
  └─ Tools: video_trimmer (libx264 frame-accurate when start_seconds > 0, zero-rebases PTS),
     auto_reframe (FFmpeg crop/scale; center-crop fallback without mediapipe/opencv),
     subtitle_gen (SRT/VTT/JSON; expects segments with words or start/end, NOT YouTube start+duration),
     remotion_caption_burn (TalkingHead.tsx + CaptionOverlay WordCaption; FFmpeg fallback if node_modules absent),
     video_compose (routes remotion | hyperframes | ffmpeg from edit_decisions.render_runtime; silent swap forbidden),
     export_bundle (single-video export folder + schema-valid publish_log)
  └─ Remotion TalkingHead.tsx (remotion-composer/src/TalkingHead.tsx):
     OffthreadVideo + CaptionOverlay + 9:16 (1080x1920) POSITION_STYLES (lower_third bottom:320 above ~1600px captions);
     Note: remotion-composer/src/fonts/ ships Latin-only woff2 fonts (PlayfairDisplay, SpaceGrotesk) — NO Devanagari font yet!
```

### 3.3 Verified Existing Tool Inventory (Exact Source Contracts — Reuse, Never Duplicate)

| Registered Name | Source Path & Class | Live Local Status | Exact Verified Inputs / Outputs & Key Caveats |
|---|---|---|---|
| `video_downloader` | `tools/analysis/video_downloader.py` (`VideoDownloader`) | **AVAILABLE** | In: `url`*, `output_dir`*, `format`, `max_resolution`, `max_duration_seconds` (`600`). Out: `video_path`, `audio_path`, `subtitle_path`, `metadata`, `platform`. Caveat: `yt-dlp` undeclared in manifests; skips duration check if metadata duration is `0`/None (line 197). |
| `transcript_fetcher` | `tools/analysis/transcript_fetcher.py` (`TranscriptFetcher`) | **AVAILABLE** | In: `url_or_video_id`*, `languages` (`["en"]`), `include_auto_generated` *(BUG: read line 136, unused!)*. Out: `transcript` (`[{text, start, duration}]`), `full_text`, `language`, `is_auto_generated`, `word_count`. YouTube-only; snippet-level timing only. |
| `transcriber` | `tools/analysis/transcriber.py` (`Transcriber`) | **UNAVAILABLE** (`faster-whisper` missing) | In: `input_path`*, `model_size` (`tiny`..`large-v3`; omits `large-v3-turbo`), `language`, `diarize`, `output_dir`. Out: `segments`, `word_timestamps`, `language`, `duration_seconds`. Optional WhisperX+`HF_TOKEN` diarization silently degrades on failure. |
| `audio_probe` | `tools/analysis/audio_probe.py` (`AudioProbe`) | **AVAILABLE** | In: `input_path`*. Out: `duration_seconds`, `format_name`, `size_bytes`, `bit_rate`, `audio{codec, sample_rate, channels}`. Audio-centric (omits video width/height/fps). |
| `audio_energy` | `tools/analysis/audio_energy.py` (`AudioEnergy`) | **AVAILABLE** | In: `input_path`*, `video_duration_seconds`, `energy_threshold_lufs` (`-40`). Out: `energy_profile` (1s downsampled LUFS buckets), `analysis`, `recommended_offset_seconds`, `needs_loop`. |
| `silence_cutter` | `tools/video/silence_cutter.py` (`SilenceCutter`) | **AVAILABLE** | In: `input_path`*, `output_path`, `mode` (`remove`/`speed_up`/`mark`), `silence_threshold_db` (`-35`), `min_silence_duration` (`0.5`), `padding_seconds` (`0.08`). Out in `mark`: counts in `data` + writes `{silences, speech_segments, total_duration}` to `output` JSON. **Caveat (lines 129-141):** if 0 silences detected, returns early WITHOUT writing JSON file! |
| `scene_detect` | `tools/analysis/scene_detect.py` (`SceneDetect`) | **AVAILABLE** (FFmpeg fallback) | In: `input_path`*, `method`, `threshold`, `min_scene_length_seconds`, `output_path`. Out: `scene_count`, `scenes` (`[{index, start_seconds, end_seconds, duration_seconds}]`), `method`. |
| `frame_sampler` | `tools/analysis/frame_sampler.py` (`FrameSampler`) | **AVAILABLE** | In: `input_path`*, `strategy`* (`interval`/`count`/`timestamps`/`scene_guided`), `output_dir`. Out: `frames` (`[{path, timestamp_seconds, index}]`). |
| `face_tracker` | `tools/analysis/face_tracker.py` (`FaceTracker`) | **UNAVAILABLE** (`mediapipe`/`cv2` missing) | Picks only 1 highest-confidence/largest face per frame (lines 222, 288). Cannot distinguish active speaker in multi-person podcasts. |
| `auto_reframe` | `tools/video/auto_reframe.py` (`AutoReframe`) | **AVAILABLE** (center-crop fallback) | In: `input_path`*, `target_aspect` (`portrait`/`square`/`landscape`/`cinematic`/`vertical_4_5`), `face_tracking_json`, `smoothing_window`, `face_padding`. Not wired in `clip-factory.yaml`; no ASD or scene-cut smoothing reset. |
| `video_trimmer` | `tools/video/video_trimmer.py` (`VideoTrimmer`) | **AVAILABLE** | In: `operation`* (`cut`/`speed`/`concat`), `input_path`, `start_seconds`, `end_seconds`, `codec` (`auto`/`copy`/`libx264`). `auto` re-encodes when `start_seconds > 0` and zero-rebases PTS. |
| `subtitle_gen` | `tools/subtitle/subtitle_gen.py` (`SubtitleGen`) | **AVAILABLE** | In: `segments`*, `format` (`srt`/`vtt`/`json`), `output_path`, `max_chars_per_line`, `max_words_per_cue`, `highlight_style` (`none`/`word_by_word`/`karaoke`), `corrections`. Pure Python. |
| `remotion_caption_burn` | `tools/video/remotion_caption_burn.py` (`RemotionCaptionBurn`) | **AVAILABLE** (FFmpeg fallback) | Kinetic word-by-word Remotion burn (`TalkingHead`) or FFmpeg `subtitles` fallback. Includes Thai tokenizer & char-timeline corrections. |
| `video_compose` | `tools/video/video_compose.py` (`VideoCompose`) | **AVAILABLE** (FFmpeg) | Runtime-aware (`remotion` / `hyperframes` / `ffmpeg`). *Warning:* `get_info()` triggers `npx` check which can stall in no-network sandboxes. |
| `export_bundle` | `tools/publishers/export_bundle.py` (`ExportBundle`) | **AVAILABLE** | Packages single render + metadata/chapters/subtitles/thumbnail into export dir and emits validated `publish_log`. Needs batch multi-clip support for `clip-factory`. |
| *(Non-BaseTool)* `CostTracker` | `tools/cost_tracker.py` (`CostTracker`) | **AVAILABLE** | Standalone budget tracker (`estimate -> reserve -> reconcile -> refund`, `cost_snapshot()`). NOT registered in `ToolRegistry`. |

*(Also verified in `lib/`: `lib/scoring.py` scores **providers**, NOT clips; `lib/clip_embedder.py` exposes module-level CLIP ViT-B/32 functions `embed_images`/`embed_texts`/`pool_frames` with 77-token max length — unsuitable for long-transcript conversation segmentation.)*

---

# 4. VERIFIED M1 AUDIT FINDINGS & HARDENING BACKLOG

Preserve working M1 functionality (`lib/url_ingest.py`, 12/12 passing tests in `tests/unit/test_url_ingest.py`, untouched `lib/source_media_review.py`). Fix these 9 verified defects cleanly in **Phase 1**:

| ID | Severity | Release Blocker? | Verified Source Evidence | Failure Consequence | Required Remediation |
|---|---|---|---|---|---|
| **M1-F01** | **CRITICAL** | **YES (Clean Install)** | `requirements.txt:1-20`, `setup.py:9-19` omit `yt-dlp` & `youtube-transcript-api` (`setup.py` also omits 7 other `requirements.txt` packages). | Fresh `pip install -r requirements.txt` breaks `VideoDownloader` & `TranscriptFetcher`. | Declare `yt-dlp` and `youtube-transcript-api` in `requirements.txt` & align `setup.py` with `requirements.txt`. |
| **M1-F02** | **HIGH** | **YES (Resource Safety)** | `lib/url_ingest.py:338-345` skips check when `duration == 0.0`; line 439 `ffprobe` `duration_s` is **never checked against `max_duration_seconds`**! Same bug in `video_downloader.py:197`. | Unknown/zero metadata duration allows unbounded 5-hour downloads past cap. | Enforce post-probe `if duration_s <= 0 or duration_s > max_duration_seconds:` in staging -> cleanup & fail; pass filesize/duration `match_filter` to `yt-dlp`. |
| **M1-F03** | **HIGH** | **YES (Security Honesty)** | `lib/url_ingest.py:135,145-175`: allows `http://`, preflight `socket.getaddrinfo()` only, silently `pass`es on `socket.gaierror`; `video_downloader.py:267-274` sets no extractor/protocol lockdown. | DNS rebinding, redirect to internal/metadata IP, `HTTP_PROXY` bypass, false "Strict SSRF protection" claim in `README.md`. | Prefer/enforce HTTPS (or explicit opt-in), lock `yt-dlp` `allowed_extractors` & protocols (`http,https` only; no `file`/`ftp`), fail closed on unexpected DNS resolution failure (with explicit mock seam for offline unit tests), and document honestly as *application-level host allowlisting & preflight IP filtering*. |
| **M1-F04** | **HIGH** | **YES (Data Integrity)** | `lib/url_ingest.py:449-455`: 3 sequential `shutil.move()` calls with no rollback; re-runs with `has_native_captions=False` leave stale `transcript.json` on disk. | Mid-move Windows file lock leaves mismatched video/audio/transcript/manifest. | Stage complete bundle; delete stale optional files when absent; implement backup-and-rollback transactional commit (or versioned source snapshot + atomic `source_manifest.json` pointer). |
| **M1-F05** | **MEDIUM** | Non-blocking for 2A, **Required for Multilingual** | `lib/url_ingest.py:404` hardcodes `"languages": ["en"]`; `tools/analysis/transcript_fetcher.py:136` ignores `include_auto_generated`. | Hindi, Hinglish, and non-English native captions are missed. | Add configurable `languages: Optional[list[str]]`, reuse `YouTubeTranscriptApi().list()` discovery (manual captions prioritized over auto-generated, as in `video_analyzer.py:272-281`), and fix `include_auto_generated` enforcement in `TranscriptFetcher`. |
| **M1-F06** | **MEDIUM** | Non-blocking for 2A | `lib/url_ingest.py:381-388` copies `raw_audio_path` straight to `source_audio.wav` without checking `pcm_s16le` / `16000` Hz / mono. | Compressed `.m4a`/`.opus` copied as `.wav` breaks downstream PCM tools. | Verify codec/sample_rate/channels via `ffprobe` before copy; otherwise transcode via `extract_audio_fallback()`. |
| **M1-F07** | **MEDIUM** | Non-blocking for 2A | `tests/qa/test_url_intake_smoke.py:18` defines `run_smoke_test()` (no `test_*`); `pytest --collect-only` returns `0 items`. | CI/developers think smoke tests ran when 0 executed. | Add `def test_url_intake_smoke():` marked `@pytest.mark.network`, register marker in `pyproject.toml`/`pytest.ini`, update `README.md`. |
| **M1-F08** | **MEDIUM** | Non-blocking for 2A | `URLIntakeAdapter` is only in `lib/`, not registered in `ToolRegistry`; line 526 hardcodes `"pipeline_type": "clip-factory"`. | Tool-calling-only agents cannot discover `url_intake`; `podcast-repurpose` cannot reuse cleanly. | Add thin `BaseTool` wrapper `tools/analysis/url_intake.py` (`name="url_intake"`), parameterize `pipeline_type`, wire into `clip-factory.yaml` & `podcast-repurpose.yaml`. |
| **M1-F09** | **LOW/MED** | Non-blocking for 2A | Single-attempt download (no transient retry); AV1-in-MP4 sources (`projects/m1-final-agent-verification/`) lack H.264 editing proxy. | Transient drop fails ingest; AV1 causes sluggish Remotion `<OffthreadVideo>` seeking. | Bounded retry/backoff on transient network errors; optional H.264/AAC editing proxy (`source_video_h264.mp4`) preserving pristine master (`master_video_path` + `proxy_video_path` in `source_manifest.json`). |

---

# 5. TARGET CONVERSATION INTELLIGENCE ARCHITECTURE (M2)

Do NOT build a 25-stage pipeline. Map all editorial intelligence cleanly inside OpenMontage's existing `clip-factory` (and `podcast-repurpose`) `script` stage, backed by deterministic Python libraries and registered `BaseTool` modules.

### 5.1 Multi-Stage Editorial Intelligence Flow
```text
Complete Source (raw transcript + audio + optional video cuts)
  ↓ [Deterministic Python: lib/transcript_normalizer.py]
Immutable Raw Transcript (revision_id) + Normalized Editorial Text + Exact Offset-Alignment Map
  ↓ [Deterministic Python: lib/acoustic_profiler.py]
Acoustic Evidence (SilenceCutter mark + AudioEnergy + optional Silero VAD / wav2vec2 alignment + SceneDetect)
  ↓ [Model-Assisted Pass 1: Macro Conversation Topology]
Complete Episode Map (chapters/topic shifts, speaker roles, Q&A pairs, stories, debates, entity glossary)
  ↓ [Model-Assisted Pass 2: High-Recall Moment Discovery + Context Reconstruction]
Candidate Moments across Editorial Archetypes (insight, story, Q&A exchange, explanation, contrarian argument, humor)
  └─ Trace backward for unresolved pronouns/premises/questions; trace forward for payoffs/qualifiers
  ↓ [Hard Gate 1 — Deterministic: lib/hook_validator.py]
Spoken Hook Verbatim Provenance Verification (ZERO tolerance for fabricated/paraphrased/cross-speaker hooks)
  ↓ [Hard Gate 2 — Structured Audit: lib/cold_viewer_auditor.py]
5-Point Cold-Viewer Comprehension Audit (subject, entities, pronouns, premise->payoff, no misleading truncation)
  ↓ [Deterministic Refinement: lib/acoustic_profiler.py + boundary refiner]
Natural Boundary Refinement (editorial thought completion FIRST; adjacent pause <=300ms advisory ONLY; never snap mid-sentence)
  ↓ [Deterministic Evaluation & Suppression: lib/editorial_evaluator.py + lib/deduplicator.py]
Hard Eligibility Filter -> Justified Multi-Criteria Ranking -> Temporal IoU (>0.35) & Semantic Deduplication
  ↓ [Registered BaseTool: tools/analysis/clip_selector.py]
Dual-Artifact Emission: clip_selection_plan.json (dossier) + provisional script.json -> checkpoint_script.json (awaiting_human)
  ↓ [Mandatory Human Gate in Chat + Backlot Read-Only Preview]
Human Approves / Revises / Rejects -> Finalized script.json (approved) -> checkpoint_script.json (completed, human_approved=True)
```

### 5.2 Four Distinct Opening Concepts (Never Conflate)
Every candidate MUST explicitly separate:
1. **`spoken_opening`** — Exact verbatim opening dialogue actually spoken at clip start (`[start_seconds, ...]`), proven via `SourceSpan`s.
2. **`spoken_hook`** — Exact verbatim compelling line spoken within the opening window (typically first 2–5s), verified contiguous from a **single speaker turn** against immutable raw text.
3. **`editorial_title`** — Optional packaging headline/title card (explicitly non-spoken).
4. **`editorial_framing`** — Optional explicitly marked visual context banner (e.g., *"Context: explaining why scaling laws plateau"*) when brief setup aids cold viewers without fabricating speech.

**Non-Fabrication Rule:** Never fabricate spoken dialogue. Never silently delete middle words of a sentence to tighten a hook. If a moment needs prior setup to make sense, expand the start boundary backward into real source dialogue (up to the length ceiling, e.g., 120s) or reject the candidate as inherently episodic.

### 5.3 Hard Eligibility Gates vs. Ranking Preferences
A high ranking score MUST NEVER rescue a clip that fails any hard gate:
- **Hard Eligibility Gates (Binary Pass/Fail):**
  1. `valid_hook_provenance`: 100% verbatim match in raw transcript from a single speaker turn.
  2. `cold_viewer_pass`: Passes all 5 cold-viewer checks (subject grounded in first 3–5s or via explicit framing, entities clear, pronouns resolved in-clip, complete premise->payoff, no misleading qualifier excision).
  3. `thought_completeness`: Natural narrative start and ending; no mid-clause truncation.
  4. `duration_within_bounds`: Configurable platform range (e.g., 15s–90s preferred, hard cap 120s unless explicitly overridden).
  5. `media_usability`: Intelligible audio and non-corrupt source range.
- **Transparent Ranking Preferences (Eligible Candidates Only):**
  - Hook pull, insight/story originality, narrative progression & payoff, vocal/visual delivery suitability, and portfolio diversity across episode timeline, speakers, and clip families.
  - Every dimension carries an **explicit transcript-grounded textual rationale**, NOT opaque uncalibrated magic numbers. Do NOT invent arbitrary score cutoffs without golden-dataset calibration.

---

# 6. ORTHOGONAL TIMESTAMP, UNICODE & SOURCE-SPAN ARCHITECTURE

### 6.1 Separate Orthogonal Timing & Evidence Dimensions (Do NOT Overload One Enum)
Never collapse source, alignment method, evidence quality, transformation, and human review into one ambiguous enum. Represent timing provenance with **independent structured fields**:

```python
# Conceptual contract for lib/models/transcript.py (refine exact typing during Phase 2A)
TimingSource = Literal[
    "creator_caption",
    "auto_caption",
    "asr_segment",
    "asr_word",
    "vad_region",
    "unknown",
]

AlignmentMethod = Literal[
    "none",
    "caption_container",
    "asr_cross_attention",
    "forced_alignment_ctc",
    "vad_energy_or_neural",
    "character_interpolation",
    "human_manual",
]

EvidenceQuality = Literal[
    "high_subframe",        # e.g. CTC phoneme forced alignment (~<=50ms) or human verified
    "medium_word",          # e.g. ASR word attention / VAD region
    "coarse_segment",       # e.g. caption snippet / ASR segment
    "low_estimated",        # e.g. heuristic interpolation
    "unknown",
]

BoundaryTransformation = Literal[
    "raw_unmodified",
    "silence_proximity_adjusted",
    "vad_onset_offset_adjusted",
    "editorial_context_expanded",
    "human_adjusted",
]
```

And every timing record carries:
- `timing_source: TimingSource`
- `alignment_method: AlignmentMethod`
- `evidence_quality: EvidenceQuality`
- `transformation: BoundaryTransformation`
- `uncertainty_seconds: Optional[float] = None` *(never fake `0.0` unless human-verified; `None` when unmeasured)*
- `confidence: Optional[float] = None` *(CRITICAL: NEVER default to `1.0`! Unknown confidence MUST remain `None`)*
- `human_reviewed: bool = False`
- `original_seconds: Optional[float] = None` *(preserves pre-transformation boundary for full auditability)*

### 6.2 Immutable Raw Transcript & True Offset-Mapped Unicode Spans
- **NEVER assume Unicode normalization (NFC/NFKC) preserves character offsets!** Normalization changes code-point lengths (e.g., `e` + `\u0301` [2 code points] -> `é` [1 code point]; Devanagari nukta decompositions; ligatures under NFKC).
- Therefore:
  1. Store immutable raw transcript segments verbatim with a `transcript_revision_id` (e.g., SHA-256 content hash).
  2. When normalizing text (preferring **NFC** for display/matching while keeping raw bytes/code points intact), build an **explicit character/token alignment table DURING transformation** mapping every normalized `[norm_start, norm_end)` span to its exact list of raw `SourceSpan`s.
  3. Every `SourceSpan` MUST explicitly declare:
     - `transcript_revision_id: str`
     - `segment_id: int`
     - `coordinate_system: Literal["unicode_codepoint_half_open"] = "unicode_codepoint_half_open"`
     - `char_start: int` (inclusive), `char_end: int` (exclusive, `char_end >= char_start`)
     - `gap_before: Optional[str] = None` (explicit gap marker if multiple non-contiguous spans exist; forbidden inside `spoken_hook`!)
  4. Round-trip invariant tested across English, Hindi Devanagari, Hinglish, NFD combining marks, and multi-codepoint emoji: slicing `raw_segment.text[span.char_start:span.char_end]` MUST reproduce the exact original characters without drift.

---

# 7. ARTIFACT, CHECKPOINT & APPROVAL CONTRACTS

### 7.1 Dual-Artifact Synchronization Strategy (`clip_selection_plan.json` + `script.json`)
Because `lib/checkpoint.py:134-143` requires `artifacts["script"]` on **both** `awaiting_human` and `completed` checkpoints of stage `script`, and `backlot/state.py:409-456` renders storyboard cards from `script.sections`:
1. **At `awaiting_human` (`human_approved=False`):**
   - `clip_selection_plan.json` is the **authoritative editorial dossier** (all candidates, rejected/deferred records, cold-viewer audits, spoken-hook `SourceSpan`s, orthogonal timing provenance, acoustic evidence, and ranking justifications).
   - `script.json` is generated as a **provisional canonical artifact** from `SELECTED_FOR_REVIEW` candidates (`metadata.approval_status = "provisional"`, `metadata.clip_selection_plan_ref`, `metadata.clip_selection_plan_sha256`), satisfying `lib/checkpoint.py` and enabling Backlot preview.
2. **At Human Approval (`status="completed"`, `human_approved=True`):**
   - `clip_selection_plan.json` is updated with explicit human review decisions (`HUMAN_APPROVED`, `HUMAN_REJECTED`, `HUMAN_REVISED` boundaries with `human_reviewed=True`).
   - `script.json` is regenerated **exclusively** from `HUMAN_APPROVED` clips (`metadata.approval_status = "approved"`, refreshed `clip_selection_plan_sha256`), becoming the **authoritative downstream contract** for `scene_plan`, `assets`, `edit`, `compose`, and `backlot` with 100% schema backward compatibility.
3. **Anti-Drift Invariant:** Downstream consumers or validators check `clip_selection_plan_sha256` and `approval_status == "approved"` so stale or unapproved provisional scripts cannot silently advance to rendering.

### 7.2 Orthogonal Candidate State Separation (Never Mix Technical & Human States)
Track four independent fields per candidate:
1. `validation_state`: `VALID` | `INVALID_TIMESTAMPS` | `INVALID_HOOK_PROVENANCE` | `SCHEMA_ERROR`
2. `eligibility_state`: `ELIGIBLE` | `REJECTED_COLD_VIEWER` | `REJECTED_INCOMPLETE_THOUGHT` | `REJECTED_DURATION_OUT_OF_BOUNDS` | `REJECTED_MEDIA_QUALITY` | `DEFERRED_DUPLICATE`
3. `review_state`: `PENDING_REVIEW` | `SELECTED_FOR_REVIEW` | `AWAITING_HUMAN` | `HUMAN_APPROVED` | `HUMAN_REJECTED` | `HUMAN_REVISED`
4. `production_state`: `NOT_STARTED` | `PLANNED` | `ASSETS_READY` | `RENDERED` | `QA_PASSED` | `QA_FAILED` | `EXPORTED`

**Backlot Rule:** `backlot/server.py` stays strictly read-only observational unless an explicit write/approval API is designed and approved in a future milestone.

---

# 8. PROVIDER & MODEL STRATEGY (VERIFICATION-FIRST, ZERO INVENTED IDS)

1. **Zero Hardcoded or Unverified Model IDs:** NEVER invent or rely on stale model IDs from old docs. Whenever configuring or integrating an external provider (OpenAI, Anthropic, Google Gemini, or managed STT), verify exact live API model identifiers, context windows, modalities, structured-output support, pricing, rate limits, and deprecation status directly against **official provider documentation or live API model catalogues** at integration time, and keep all model IDs configuration-driven.
2. **Never Conflate Access Channels:** Explicitly distinguish:
   - Consumer subscriptions (e.g., ChatGPT Plus/Pro web app) — separate billing from API platform!
   - Models available inside an IDE assistant (Codex / Antigravity / Claude Code)
   - Direct paid API platform access (API keys)
   - Third-party gateways
3. **Task-Based Hybrid Allocation:**
   - **Deterministic Python Tools:** Validation, Unicode span mapping, acoustic pauses/loudness, deduplication math, trimming, reframing, subtitle formatting, media QA.
   - **Frontier Long-Context Reasoning (Codex interactively; optional pluggable API seam only if authorized in Phase 6):** Macro conversation topology, candidate discovery, context reconstruction, cold-viewer auditing, nuanced sarcasm/qualifier preservation, structured plan drafting.
   - **Specialist Audio/Visual Models (Optional / Pluggable):**
     - *Offline STT + Forced Alignment + Diarization:* Silero VAD -> `faster-whisper` -> WhisperX `wav2vec2` CTC alignment -> `pyannote.audio` (note: recommend Python 3.11/3.12 env on Windows if Python 3.14 lacks binary wheels).
     - *Managed Cloud STT Alternative:* Deepgram / AssemblyAI (or existing OpenMontage `azure_stt`, `mistral_stt`, `dashscope_asr`) when native reconciled diarization & word timestamps are prioritized over offline-only operation.
     - *Multilingual Embeddings (Hinglish/Devanagari/English dedup):* `Qwen3-Embedding` or `BAAI BGE-M3` (runnable locally via Ollama or Python).
     - *Active Speaker Detection (Multi-Speaker Podcasts):* Audio-visual ASD (`TalkNet`, `Light-ASD`/`LR-ASD`, `LoCoNet`) to avoid cutting to a silent reacting host.
4. **Do Not Build Empty Provider Abstractions Early:** Only implement `lib/providers/` when an authorized phase genuinely requires runtime model calls outside Codex.

---

# 9. VERTICAL 9:16 VIDEO PRODUCTION & EXPORT ARCHITECTURE

Extend existing OpenMontage infrastructure (`video_trimmer`, `auto_reframe`, `face_tracker`, `scene_detect`, `subtitle_gen`, `remotion_caption_burn`, `TalkingHead.tsx`, `video_compose`, `export_bundle`) rather than building a parallel renderer:
1. **Media Compatibility & Editing Proxy:** Keep pristine `source_video.mp4`; generate H.264/AAC `yuv420p` `+faststart` editing proxy when master is AV1/VP9 for frame-accurate Remotion/FFmpeg seeking. Update `lib/media_profiles.py` (`YOUTUBE_SHORTS` max duration is currently hardcoded to legacy `60s`).
2. **Speaker-Aware 9:16 Reframing:** Upgrade `auto_reframe` to accept shot boundaries (`scene_detect`) so crop smoothing resets cleanly across camera cuts, accept active-speaker tracks (ASD) for multi-person podcasts, and support fallback layouts (stacked 2-speaker split-screen or blurred pillarbox for slides/wide shots).
3. **Synchronized, Readable Subtitles:** Zero-rebase clip timestamps cleanly (`video_trimmer.py:135-149`), normalize YouTube `start+duration` vs ASR `start/end/words` before `subtitle_gen`, enforce mobile safe zones (matching `TalkingHead.tsx` `lower_third bottom: 320` above `~1600px` captions + TikTok/Reels/Shorts right-rail/bottom chrome), and add Devanagari-capable font support alongside `remotion-composer/src/fonts/` (which currently ships Latin-only woff2 fonts).
4. **Preview vs. Final MP4 Verification:** A Backlot preview or zero exit code from FFmpeg/Remotion is NOT proof of correctness. Every exported MP4 MUST pass automated post-render QA (`ffprobe` stream/codec/resolution/fps/duration checks, audio loudness & non-silent check, AV sync drift check, opening non-black frame check via `frame_sampler`, and subtitle cue alignment check -> `final_review.json`).

---

# 10. EDITORIAL QUALITY EVALUATION FRAMEWORK

Technical tests prove stability; human-grounded evaluation proves **editorial excellence**.
- **Strictly Separate:** (1) Initial engineering acceptance criteria, (2) Later empirical quality targets (NEVER invent achieved metrics without a measured dataset), (3) Experimental hypotheses, and (4) Human editorial judgments.
- **12 Evaluation Dimensions Per Clip:** Standalone comprehension, context completeness, strength of actual moment, opening effectiveness, narrative coherence, natural start/end boundaries, factual fidelity to source, audio quality, subtitle correctness, visual quality, portfolio diversity, and non-redundancy.
- **Golden Evaluation Dataset (Local, Gitignored):** Curate representative episodes across 7+ archetypes: (1) technical deep-dive, (2) solo monologue, (3) guest Q&A interview, (4) comedy/banter, (5) heated debate, (6) narrative storytelling, and (7) multilingual/Hinglish (Latin + Devanagari + code-switching). For each episode, annotate both gold-standard clips (with human-verified boundaries & minimum required setup) AND "trap" moments (exciting sentences that fail cold-viewer comprehension). Use inter-annotator/editor notes to measure candidate recall, false-positive rate, boundary delta, standalone pass rate, semantic redundancy, and cross-model comparisons without overfitting proxy scores.

---

# 11. DEPENDENCY-ORDERED IMPLEMENTATION ROADMAP (MILESTONE BY MILESTONE)

Execute **strictly one authorized phase at a time**. Stop at every exit gate for user approval.

| Phase | Objective & Reusable Modularity | Key Files Created / Modified | Mandatory Tests, Verification & Exit Gate |
|---|---|---|---|
| **Phase 0** *(Turn 1)* | **Read-Only Repository Orientation & Baseline Audit** | **NONE (Read-only)** | Verify Git state, live `ToolRegistry`, environment drift, baseline pytest runs, discrepancies vs this prompt; present explicit Phase 1 vs Phase 2A decision. |
| **Phase 1** | **M1 Reliability, Security & Packaging Hardening** (fix M1-F01..M1-F09 without destabilizing working M1 flow) | Create: `tools/analysis/url_intake.py` (`URLIntake(BaseTool)`). Modify: `requirements.txt`, `setup.py`, `lib/url_ingest.py`, `tools/analysis/transcript_fetcher.py`, `tools/analysis/video_downloader.py`, `tests/unit/test_url_ingest.py`, `tests/qa/test_url_intake_smoke.py`, `pipeline_defs/{clip-factory,podcast-repurpose}.yaml`, `skills/pipelines/clip-factory/idea-director.md`, `README.md`. | Unit/failure/security tests for unknown duration, WAV validation, rollback on move failure, stale transcript cleanup, multilingual `ytt.list()`, `include_auto_generated`; `registry.get("url_intake")` verified; `pytest --collect-only tests/qa/test_url_intake_smoke.py` >= 1 test (marked `@pytest.mark.network`); zero regressions. Rollback: pure additive/hardening diffs. |
| **Phase 2A** | **Evidence, Orthogonal Timing & Data Contracts** (zero new external deps) | Create: `schemas/artifacts/clip_selection_plan.schema.json`, `lib/models/__init__.py`, `lib/models/transcript.py` (orthogonal timing/evidence/span models, `confidence: Optional[float] = None`), `lib/models/clip_plan.py` (orthogonal validation/eligibility/review/production states), `tests/contracts/test_clip_selection_plan_schema.py`, `tests/unit/test_evidence_models.py`. Modify: `schemas/artifacts/__init__.py`. | `validate_artifact("clip_selection_plan", ...)` passes valid & rejects malformed; unknown confidence stays `None`; 0 regressions across all 20 existing schemas. |
| **Phase 2B** | **Transcript Intelligence & True Offset-Mapped Normalization** | Create: `lib/transcript_normalizer.py` (YouTube/Whisper/SRT/VTT ingest, immutable `transcript_revision_id`, explicit char/token alignment table built *during* NFC normalization), `lib/conversation_structure.py` (macro turns/blocks/Q&A structure), unit tests. | Lossless round-trip `raw_segment.text[char_start:char_end]` tests across English, Hindi Devanagari, Hinglish, NFD combining marks, multi-codepoint emoji, empty/overlapping/zero-duration segments. |
| **Phase 2C** | **Acoustic Evidence & Non-Destructive Boundary Profiling** | Create: `lib/acoustic_profiler.py` (wraps `SilenceCutter(mode="mark")` safely handling 0-silence early return + `AudioEnergy` + `SceneDetect` + optional VAD/forced-align hook), synthetic-audio unit tests. | Synthetic FFmpeg audio verifies pause accuracy; handles 0-silence gracefully; proves mid-sentence pause is NEVER auto-snapped without semantic completion flag; preserves `original_seconds` & honest uncertainty. |
| **Phase 2D** | **Candidate Verification, Cold-Viewer Gate, Editorial Evaluation, Deduplication & `clip_selector` Tool** | Create: `lib/hook_validator.py`, `lib/cold_viewer_auditor.py`, `lib/editorial_evaluator.py`, `lib/deduplicator.py`, `tools/analysis/clip_selector.py` (`ClipSelector(BaseTool)`), adversarial unit & tool contract tests. | 100% rejection of paraphrased/middle-deleted/cross-speaker hooks; cold-viewer gate rejects unresolved pronouns; temporal IoU & semantic dedup verified; 0-eligible-candidate graceful return; `registry.get("clip_selector")` discovered. |
| **Phase 3** | **Human Review, Checkpoint Integration & Canonical Dual-Artifact Sync** | Modify: `pipeline_defs/clip-factory.yaml`, `skills/pipelines/clip-factory/{script-director.md, executive-producer.md}`, `backlot/state.py` (optional read-only load of `clip_selection_plan`). Create: `tests/integration/test_clip_factory_m2_handoff.py`. | Dual-artifact `awaiting_human` (`clip_selection_plan` + provisional `script`) passes `lib/checkpoint.py` & `load_board_state()`; completing without `human_approved=True` raises `CheckpointValidationError`; post-approval finalized `script.json` (`approved` + matching sha256) joins cleanly with `scene_plan`. |
| **Phase 4** | **Vertical 9:16 Composition, Speaker-Aware Reframing & Synchronized Subtitles** | Modify: `lib/media_profiles.py`, `pipeline_defs/clip-factory.yaml`, `skills/pipelines/clip-factory/{scene,asset,edit,compose}-director.md`, `tools/video/auto_reframe.py` (scene-cut reset + ASD track input + split-screen/pillarbox), `tools/subtitle/subtitle_gen.py` (clip-relative offset helper & safe zones), Remotion font config (Devanagari support if Remotion enabled). Create: vertical production integration tests. | Synthetic 16:9 -> 9:16 (`1080x1920`) trimmed + reframed + captioned MP4 verified via `ffprobe` & sampled frames; clip-relative captions synced; safe-zone compliance checked. |
| **Phase 5** | **Automated Media QA, Backlot Preview & Multi-Clip Export Delivery** | Modify: `tools/publishers/export_bundle.py` (batch multi-clip support), `pipeline_defs/clip-factory.yaml` (`export_bundle` in `publish`), `publish-director.md`. Create: `tests/integration/test_clip_factory_export_qa.py`. | End-to-end URL/local -> approved clips -> rendered 9:16 MP4s -> `ffprobe`/AV-sync/non-black-frame QA (`final_review.json`) -> Backlot preview -> export package + valid `publish_log`. |
| **Phase 6** | **Advanced Multimodal Intelligence & Golden-Dataset Evaluation Studio** | Audio-visual ASD (`Light-ASD`/`LoCoNet`), `WhisperX` CTC alignment + `pyannote`/managed cloud STT, optional opt-in `lib/providers/` eval seam, multimodal audio/video discovery, golden-dataset benchmark harness. | Empirical improvement measured across 12 editorial dimensions on real podcast corpus without regressing architecture or human gates. |

---

# 12. ENGINEERING CONSTITUTION & TESTING DISCIPLINE

1. **Inspect Before Editing:** Never modify a file without reading it and checking all downstream consumers.
2. **Git Safety:** Always check `git status -sb`, branch, and `HEAD` SHA first. Preserve all pre-existing uncommitted files. NEVER run `git reset --hard`, `git clean -fd`, `git checkout -- .`, `git push --force`, or rewrite history. Never commit `.env`, secrets, private media, `projects/`, model weights, or caches. Show `git diff --stat` before any commit; verify commit/push output directly.
3. **Protected Cross-Pipeline Core:** Do NOT alter `lib/source_media_review.py`, `lib/checkpoint.py`, or break `schemas/artifacts/{script,scene_plan,edit_decisions,render_report}.schema.json` unless strictly required and proven zero-regression across all 13 pipelines.
4. **4-Tier Testing Standard (Tests Must Actually Be Collected & Executed):**
   - **Unit:** Normalization, offset alignment, orthogonal timing, hook provenance, cold-viewer audit, eligibility, ranking, deduplication, boundary refinement, schema validation.
   - **Integration:** `ToolRegistry` discovery, `BaseTool.execute()` + caching/events, pipeline stage transitions, `lib/checkpoint.py` gate enforcement, `backlot/state.py:load_board_state()`, renderer input compatibility.
   - **End-to-End:** Local & URL inputs, native captions vs ASR fallback, full analysis -> review -> approval -> 9:16 render -> final MP4 `ffprobe` verification.
   - **Failure & Adversarial:** Missing/empty transcripts, corrupt media, unsupported codecs (AV1/VP9/MKV), unknown/zero duration, network drop, disk exhaustion, partial move lock, malformed structured output, approval not granted, Unicode NFD/NFC combining marks, **Hinglish**, **Devanagari**, multi-codepoint emoji, speaker overlap, mid-sentence dramatic pauses, paraphrased/omitted/cross-speaker hooks, duplicate candidates.
   - *Pytest Warning:* Never claim a test passed without printing exact command + observed result. Note that unfiltered `pytest tests/contracts/` can stall on `npx` / HyperFrames runtime probes when offline — run targeted suites and diagnose any slow test explicitly.
5. **Security & Untrusted Input:** Treat URLs, downloaded media, and transcripts as untrusted. Never construct shell strings with user/media input (use subprocess arg lists; preserve FFmpeg filter escaping). Never log API keys.
6. **Documentation Sync:** Keep schemas, manifests, skills, and `README.md` synchronized with reality. Never describe planned work as shipped.

---

# 13. EXPLICIT OPEN DECISIONS REQUIRING USER APPROVAL

Do NOT silently resolve these — surface them clearly for user sign-off at the appropriate phase gate:
1. **First Implementation Milestone:** Authorize **Phase 1 (M1 Hardening)** first *(recommended for clean-install & duration/transaction safety)* OR **Phase 2A (Evidence & Data Contracts)** first *(zero external dependencies, starts M2 immediately)*.
2. **Python Runtime Standardization:** Keep `.venv` on Python 3.14.10 (requiring cloud STT / deferred local ML wheels) OR provision a Python 3.11/3.12 virtualenv matching `.python-version` & CI so `faster-whisper`, `WhisperX`, `mediapipe`, `opencv-python`, and ASD wheels install cleanly on Windows.
3. **Caption / STT Strategy:** Local offline modular stack (`Silero VAD` + `faster-whisper` + `WhisperX`/`wav2vec2` + `pyannote`) vs. managed cloud STT (Deepgram / AssemblyAI / existing `azure_stt` / `mistral_stt`) vs. hybrid.
4. **Vertical Render Runtime:** Install `remotion-composer/node_modules` on an LTS Node (`22.x`/`24.x`) for Remotion kinetic word-level captions (`TalkingHead.tsx` + `CaptionOverlay`), OR lock explicit `"ffmpeg"` ASS subtitle burn for Phase 4 MVP.
5. **Editorial Language Default:** Confirm default caption/transcript language priority (e.g., auto-detect source language with `["en", "hi"]` preference for English + Hindi/Hinglish podcasts).

---

# 14. FIRST EXECUTION ASSIGNMENT (TURN 1 — STRICTLY READ-ONLY)

**DO NOT MODIFY ANY FILE, INSTALL ANY PACKAGE, OR IMPLEMENT ANY CODE IN TURN 1.**

Execute this exact read-only verification sequence:
1. Run `git status --short --branch`, `git rev-parse HEAD`, `git branch -avv`, `git remote -v` and confirm all pre-existing uncommitted files are intact.
2. Read `AGENTS.md`, `AGENT_GUIDE.md`, `PROJECT_CONTEXT.md`, `pipeline_defs/clip-factory.yaml`, `lib/checkpoint.py`, `lib/url_ingest.py`, and `backlot/state.py`.
3. Inspect `.venv` Python version, `requirements.txt`, `setup.py`, `remotion-composer/node_modules`, and live `ToolRegistry.discover()` availability for all analysis/post/publish tools (avoiding hanging `npx` calls if offline).
4. Run baseline non-network tests and report exact observed output:
   - `.\.venv\Scripts\python.exe -m pytest tests/unit/test_url_ingest.py -v`
   - `.\.venv\Scripts\python.exe -m pytest --collect-only tests/qa/test_url_intake_smoke.py`
   - `.\.venv\Scripts\python.exe -m pytest tests/tools/test_silence_detection_failure.py tests/tools/test_subtitle_timestamps.py tests/tools/test_video_trimmer_workspaces.py tests/tools/test_video_compose_vertical.py tests/tools/test_scoring.py tests/tools/test_transcriber_device_selection.py -q`
5. Report any discrepancy found between this prompt and live repository state.
6. Present the 5 Open Decisions (Section 13) and recommend the exact next authorized milestone (Phase 1 or Phase 2A), then **STOP and wait for explicit user authorization**.

---

# 15. MANDATORY REPORTING PROTOCOL (EVERY TURN & MILESTONE)

Tag every substantive claim with **`[VERIFIED]`**, **`[INFERRED]`**, **`[PROPOSED]`**, **`[UNVERIFIED]`**, **`[OPEN DECISION]`**, or **`[BLOCKED]`**, and include all 11 sections:

1. **Files Inspected** (exact paths + key lines/symbols)
2. **Files Changed** (exact paths, or `NONE`)
3. **Functions / Classes Added or Modified** (exact symbol names, or `NONE`)
4. **Architecture Decisions** (rationale + alternatives rejected)
5. **Existing Contracts Affected** (schemas, manifests, checkpoints, Backlot, skills)
6. **Commands Executed** (exact commands)
7. **Actual Test Results** (exact collected/passed/failed/skipped counts + timings)
8. **Failures & Root Causes** (or `NONE`)
9. **Remaining Risks & Open Decisions**
10. **Git Status & Commit SHA** (`git status --short --branch`, active branch, `HEAD` SHA)
11. **Explicit Milestone Verdict** (`PASS` / `CONDITIONAL PASS` / `FAIL` / `BLOCKED` + next-milestone authorization request)
