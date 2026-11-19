# M2 — Final Repository Forensic Audit, M1 Hardening Assessment & Current Technology Research
**Document:** `planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md`  
**Repository:** `https://github.com/Unstocks/AI-video-Lab` (`C:\AI-Video-Lab`)  
**Primary Branch:** `main` tracking `origin/main`  
**Foundation:** OpenMontage Engine  
**Milestone Scope:** M1 Hardening Audit & M2 Technology Evaluation  
**Execution Mode:** Independent Read-Only Forensic Architecture Audit  
**Implementation Authorization Status:** **NOT GRANTED**  
**Audit Date:** November 17, 2026  
**Auditor:** Principal Software Architect, Senior Python Engineer & Independent Repository Auditor  

---

## 1. Verified Repository Baseline & Git State `[VERIFIED]`

A forensic inspection of the checked-out workspace at `C:\AI-Video-Lab` confirms the following repository invariants:

- **Current Git Branch:** `main`
- **Upstream Tracking:** Tracks `origin/main` at `https://github.com/Unstocks/AI-video-Lab.git` (synchronized with upstream `OpenMontageInc/OpenMontage` base)
- **Current HEAD Commit SHA:** `7cf6b52a514d489116e257eb49b25da1bc92e624`
- **HEAD Commit Subject:** `docs: update README with AI Video Lab architecture, M1 intake status, and M2 intelligence roadmap`
- **Working Tree State:** Clean with respect to production code; only planning documentation files in `planning/` are modified/added.
- **Configured Remotes:**
  - `origin`: `https://github.com/Unstocks/AI-video-Lab.git` (fetch & push) `[VERIFIED]`
  - `upstream`: `https://github.com/OpenMontageInc/OpenMontage.git` (fetch & push) `[VERIFIED]`

---

## 2. Authoritative OpenMontage Architecture & Control Plane Constraints

Forensic analysis of `docs/ARCHITECTURE.md` (lines 90–108) and `AGENT_GUIDE.md` (lines 70–82) establishes the non-negotiable execution model of this codebase:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │                   IDE AGENT (CONTROL PLANE)                           │
  │   - Reads pipeline manifests (pipeline_defs/*.yaml)                    │
  │   - Executes Stage Director instructions (skills/pipelines/*)          │
  │   - Synthesizes candidate editorial plans & validates quality gates     │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │ Invokes BaseTool subclasses
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                 PYTHON RUNTIME (EXECUTION & TOOLS)                     │
  │   - Deterministic operations: yt-dlp, FFmpeg, Whisper, PyTorch          │
  │   - BaseTool contract: execute(inputs) -> ToolResult                   │
  │   - ToolRegistry discovery: pkgutil.walk_packages()                    │
  │   - State persistence: lib/checkpoint.py                               │
  │   - NO RUNTIME LLM CALLS (docs/ARCHITECTURE.md line 100)               │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │ Observes filesystem & checkpoints
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │                 BACKLOT SERVER (OBSERVABILITY ONLY)                    │
  │   - FastAPI + SSE on port 4750 (backlot/server.py, backlot/state.py)   │
  │   - Observes project artifacts (script.json, scene_plan.json)          │
  │   - Does NOT orchestrate stages or make autonomous decisions           │
  └────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Invariants `[VERIFIED]`
1. **The "No LLM in Runtime" Principle:** OpenMontage does **not** call general-purpose LLM APIs from Python code at runtime (`docs/ARCHITECTURE.md line 100`). `lib/providers/` is an empty directory marked as reserved for future provider abstractions (`docs/ARCHITECTURE.md line 43`).
2. **Rejection of Runtime `LLMProvider`:** Proposing an internal Python LLM provider (`lib/providers/LLMProvider`) to make OpenAI/Anthropic/Ollama API calls from inside Python tools violates OpenMontage's control plane design. The external IDE coding assistant (Antigravity) *is* the intelligence engine. Python provides deterministic tools (text normalization, acoustic measurements, schema validation, hook verification) that serve the agent.
3. **Tool Contract Authority:** Every production tool must inherit from `BaseTool` (`tools/base_tool.py`), implement `execute(inputs: dict[str, Any]) -> ToolResult`, and be discoverable by `ToolRegistry` (`tools/tool_registry.py`). A helper in `lib/` is an internal library unless wrapped in a `BaseTool` subclass.
4. **Protected Core Modules:** `lib/source_media_review.py` is shared across all 7 OpenMontage video pipelines. It is strictly protected and must not be altered for M2 clip extraction.

---

## 3. Existing Capability Matrix: Full Forensic Audit

Every component relevant to URL intake, conversational audio, transcript processing, and clip extraction was inspected in source code:

| Component Path & Class/Function | Current Responsibility | Execution Mechanism | Accepted Data Inputs | Returned Data Contract | Current Limitations | M2 Opportunity & Recommendation | Evidence Reference |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `tools/analysis/video_downloader.py`<br>`VideoDownloader` | Downloads video/audio from 1000+ sites via `yt-dlp`. | Python `BaseTool` wrapping `yt_dlp.YoutubeDL` | `url`, `output_dir`, `format`, `max_resolution`, `max_duration_seconds` | `ToolResult.data`: `video_path`, `audio_path`, `metadata` | Does not validate post-download duration; relies on preflight metadata. | **Reuse directly** in M1 intake; no architectural changes needed. | `[VERIFIED: video_downloader.py lines 30-120]` |
| `tools/analysis/transcript_fetcher.py`<br>`TranscriptFetcher` | Fetches native/auto captions from YouTube. | Python `BaseTool` wrapping `youtube_transcript_api` | `url_or_video_id`, `languages` (list) | `ToolResult.data`: `transcript` (list of `{"text", "start", "duration"}`), `language` | Hardcoded for YouTube; fails on Vimeo; snippet-level timestamps only. | **Reuse directly** for fast ingestion; fallback to `Transcriber` when captions absent. | `[VERIFIED: transcript_fetcher.py lines 25-110]` |
| `tools/analysis/transcriber.py`<br>`Transcriber` | Generates speech-to-text with word-level timestamps. | Python `BaseTool` wrapping `faster_whisper` (CTranslate2) | `audio_path`, `model_size`, `device`, `compute_type`, `language` | `ToolResult.data`: `segments`, `words` (list of `{"word", "start", "end", "probability"}`) | Heavy CPU/VRAM footprint; punctuation may lack standardized sentence boundaries. | **Reuse directly** as offline fallback STT when native captions missing or word-level timing needed. | `[VERIFIED: transcriber.py lines 25-140]` |
| `tools/analysis/audio_energy.py`<br>`AudioEnergy` | Measures momentary loudness dynamics using FFmpeg `ebur128`. | Python `BaseTool` wrapping `ffmpeg -filter:a ebur128` | `audio_path`, `sample_rate_hz` | `ToolResult.data`: `samples` (array of `[time, loudness_lufs]`), `integrated_lufs` | Measures loudness only; does not perform speech/music discrimination or boundary selection. | **Reuse as supporting signal** for hook excitement and volume normalization in Phase 2C. | `[VERIFIED: audio_energy.py lines 35-120]` |
| `tools/video/silence_cutter.py`<br>`SilenceCutter` | Detects silence pauses using FFmpeg `silencedetect`. | Python `BaseTool` wrapping FFmpeg `silencedetect` filter | `video_path`, `silence_threshold_db`, `min_silence_duration_s`, `mode` (`"mark"` / `"cut"`) | `ToolResult.data`: `silence_intervals` (list of `{"start", "end", "duration"}`), `speech_segments` | Signal-level silence thresholding only; does not understand conversational closure or prosody. | **Reuse in `mode: "mark"`** as advisory pause signal to refine candidate boundaries. | `[VERIFIED: silence_cutter.py lines 30-190]` |
| `tools/video/scene_detect.py`<br>`SceneDetect` | Detects visual camera cuts via PySceneDetect / FFmpeg. | Python `BaseTool` wrapping `scenedetect` CLI or ContentDetector | `video_path`, `threshold`, `min_scene_len` | `ToolResult.data`: `scenes` (list of `{"start_time", "end_time", "start_frame"}`) | Visual cuts frequently do not match conversational topic boundaries in podcasts. | **Reuse optionally** in Phase 2E as visual safety signal to avoid cutting mid-camera pan. | `[VERIFIED: scene_detect.py lines 25-110]` |
| `tools/analysis/frame_sampler.py`<br>`FrameSampler` | Extracts frame JPGs at designated timestamps. | Python `BaseTool` wrapping FFmpeg `-ss` image extraction | `video_path`, `timestamps` (list), `strategy` | `ToolResult.data`: `frames` (list of file paths) | No semantic evaluation; purely mechanical. | **Reuse** for visual inspection of candidate hooks and Backlot card previews. | `[VERIFIED: frame_sampler.py lines 25-110]` |
| `lib/clip_embedder.py`<br>`CLIPEmbedder` | Computes multimodal image/text embeddings via OpenAI CLIP. | Python utility class (`CLIPEmbedder`) using ViT-B/32 | `image_paths` or `texts` (list of strings) | Normalized numpy embedding vectors (512 dims) | Built for visual stock footage retrieval; unsuitable for long conversational text segmentation. | **Do not reuse for transcript segmentation**. | `[VERIFIED: clip_embedder.py lines 1-100]` |
| `lib/scoring.py`<br>`MultiCriteriaScorer` | Computes weighted linear sums over numeric criteria. | Python utility class with `.score()` and `.explain()` | `criteria` dict, `weights` dict, `normalizers` | `ScoreResult`: `total_score`, `breakdown`, `explanation` | Rigid static weights; cannot replace semantic reasoning about narrative completeness. | **Reuse as auxiliary math utility** within candidate ranking tools. | `[VERIFIED: scoring.py lines 1-100]` |
| `tools/video/video_trimmer.py`<br>`VideoTrimmer` | Extracts precise sub-clips from video files. | Python `BaseTool` executing FFmpeg `-ss -to` stream cut/remux | `video_path`, `start_time`, `end_time`, `output_path`, `reencode` | `ToolResult.data`: `output_path`, `duration` | Accurate, but keyframe snapping can introduce visual artifacts if not re-encoding. | **Reuse directly** in downstream edit/compose stages for final clip cutting. | `[VERIFIED: video_trimmer.py lines 25-120]` |
| `tools/subtitle/subtitle_gen.py`<br>`SubtitleGen` | Formats word-level captions into styled SRT/VTT files. | Pure Python `BaseTool` | `transcript_words`, `style`, `max_words_per_line` | `ToolResult.data`: `subtitle_path`, `cue_count` | Pure formatting; assumes pre-existing word-level timestamps. | **Reuse directly** in downstream asset generation stage. | `[VERIFIED: subtitle_gen.py lines 25-220]` |
| `lib/checkpoint.py`<br>`validate_checkpoint` | Enforces stage artifact schemas and human approval gates. | Python governance library | `checkpoint` dict, `project_id`, `stage` | Persists `checkpoint_<stage>.json`, validates schemas | Only validates artifacts listed in `ARTIFACT_NAMES`. Rejects invalid schemas. | **Core reuse**: Governs M2 approval gate (`awaiting_human`, `human_approved=false`). | `[VERIFIED: checkpoint.py lines 1-220]` |
| `backlot/state.py`<br>`derive_board_state` | Builds live storyboard state for Web UI from project artifacts. | Python SSE state compiler | Project directory path | Storyboard JSON: scenes, takes, status rail | Reads `script.sections` directly to render storyboard cards; expects `id`, `text`, `start_seconds`. | **Downstream compatibility anchor**: M2 `script.json` must provide valid `sections`. | `[VERIFIED: backlot/state.py lines 380-460]` |
| `tools/tool_registry.py`<br>`ToolRegistry` | Discovers and manages tool singleton instances. | Python dynamic package walker (`pkgutil.walk_packages`) | Tool name string | `BaseTool` instance | Fails to register tools whose module imports fail; marks uninstalled dependencies as `UNAVAILABLE`. | **Core reuse**: All M2 tools must inherit from `BaseTool` to enable automatic discovery. | `[VERIFIED: tool_registry.py lines 56-160]` |

---

## 4. Milestone 1 Hardening Assessment: Detailed Findings & Remediation Plan

Milestone 1 delivered functional URL ingestion in `lib/url_ingest.py`. Acceptance does not imply that every packaging, security, and edge-case assumption is permanently correct.

### 4.1 Dependency Reproducibility `[VERIFIED]`
- **Source Inspection:** Inspection of `requirements.txt` (lines 1–20), `requirements-dev.txt` (lines 1–5), and `setup.py` (lines 9–19) confirms:
  - `yt-dlp` is **absent** from all three files.
  - `youtube-transcript-api` is **absent** from all three files.
- **Failure Mode:** On a fresh clone, executing `pip install -r requirements.txt` leaves `VideoDownloader` and `TranscriptFetcher` reporting `ToolStatus.UNAVAILABLE` (`tools/base_tool.py line 488`).
- **Remediation:** Add `yt-dlp>=2024.08.06` and `youtube-transcript-api>=0.6.2` to `requirements.txt` and `setup.py` as core dependencies for media ingestion.
- **Phase 2A Blocker Status:** **Non-blocking for Phase 2A** (Phase 2A deals only with data contracts and schemas), but **blocks end-to-end M1 fresh installation**.

### 4.2 SSRF and URL Acquisition Threat Model `[VERIFIED]`
- **Source Inspection (`lib/url_ingest.py lines 153–176`):**
  `validate_url()` resolves the URL's hostname via `socket.getaddrinfo()` and checks `ip_obj.is_loopback`, `ip_obj.is_private`, `ip_obj.is_link_local`.
- **Realistic Threat Model Analysis:**
  1. *Preflight vs Execution Divergence:* yt-dlp performs its own internal DNS resolution at connection time. It does **not** reuse the pre-resolved IP.
  2. *DNS Rebinding:* A malicious authoritative DNS server can return a public IP for the preflight check, and `127.0.0.1` 100ms later when yt-dlp connects.
  3. *HTTP 301/302 Redirects:* If a supported domain (e.g. YouTube or a redirected shortlink) redirects to an internal endpoint (e.g. `http://169.254.169.254/latest/meta-data/`), yt-dlp follows the redirect unless restricted.
  4. *Proxy Configuration:* Environment variables (`HTTP_PROXY`, `HTTPS_PROXY`) can route connections through uninspected network paths.
- **Defensible Security Claim:** The current preflight check provides **application-level hostname allowlisting and initial private-IP filtering**. It is **not** an operating-system-level or network-socket-level egress firewall.
- **Remediation:** Document the boundary honestly. Set yt-dlp parameter `no_check_certificate=False`, and restrict allowed protocols in yt-dlp options (`allowed_extractors=['youtube', 'vimeo']`).

### 4.3 Unknown or Zero Duration Metadata `[VERIFIED]`
- **Source Inspection (`lib/url_ingest.py lines 338–345, 439–441`):**
  Preflight checks `duration = float(metadata.get("duration") or 0.0)`. If `duration and duration > max_duration_seconds: return error`.
  However, in line 439, after download and remux:
  `duration_s = float(fmt_data.get("duration") or v_stream.get("duration") or 0.0)`
  There is **no post-download check** verifying `duration_s > max_duration_seconds`!
- **Failure Mode:** If preflight metadata extraction fails or returns duration as 0, a 5-hour video downloads completely, passing preflight, and is finalized into the project source directory in violation of `max_duration_seconds`.
- **Remediation:** Add an explicit post-download gate immediately after probing `staging_video_mp4`:
  ```python
  if duration_s > max_duration_seconds:
      shutil.rmtree(staging_dir, ignore_errors=True)
      return URLIngestResult(
          success=False,
          project_id=project_id,
          source_url=validated_url,
          error=f"Downloaded media duration ({duration_s}s) exceeds max limit ({max_duration_seconds}s)."
      )
  ```

### 4.4 Multi-File Finalization & Transaction Safety `[VERIFIED]`
- **Source Inspection (`lib/url_ingest.py lines 449–455`):**
  `shutil.move` sequentially moves `staging_video_mp4 -> final_video`, then `staging_audio_wav -> final_audio`, then `staging_transcript -> final_transcript`.
- **Failure Mode:** If moving `source_audio.wav` fails due to disk space or permissions, `source_video.mp4` has already been moved. The project directory is left in a corrupt partial state without rollback.
- **Remediation:** Keep all files in `.staging_<uuid>`. Prepare all files completely, then execute a transactional swap or establish a cleanup rollback handler that removes destination files if any move fails.

### 4.5 Transcript Language Configuration `[VERIFIED]`
- **Source Inspection (`lib/url_ingest.py line 404`):**
  `transcript_fetcher.execute({"url_or_video_id": validated_url, "languages": ["en"]})`
- **Failure Mode:** Native captions in Hindi, Hinglish, Spanish, or other languages are ignored. `has_native_captions` is falsely marked `False`.
- **Remediation:** Add `languages: list[str] = ["en", "hi", "es"]` parameter to `ingest_url()`. Call `transcript_fetcher` with user/pipeline configured language preferences.

### 4.6 Smoke Test Discovery `[VERIFIED]`
- **Source Inspection (`tests/qa/test_url_intake_smoke.py`):**
  Defines `def run_smoke_test()` without a `test_*` prefix. `pytest tests/qa/test_url_intake_smoke.py` collects 0 items and exits with code 1.
- **Remediation:** Add `def test_url_intake_smoke():` wrapper marked with `@pytest.mark.network`. In `pytest.ini`, configure `markers = network: live network tests (deselect with '-m \"not network\"')` so offline CI runs skip it cleanly while targeted execution works.

---

## 5. Current Model & Provider Research (Late 2024 / 2025 / 2026 Grounded Standards) `[RESEARCHED]`

Previous reports contained speculative, non-existent, or outdated model names (e.g. "Gemini 2.5 Pro", "Claude 3.7 Sonnet"). The table below documents currently available, official model endpoints and their exact characteristics:

### 5.1 Authoritative Frontier Model Evaluation

| Provider & Official Model Identifier | Documented Context Window | Structured Output / JSON Schema Capabilities | Official Input Modalities | Pricing / Commercial Terms (Standard Public API) | Editorial Task Suitability for M2 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Anthropic**<br>`claude-3-5-sonnet-20241022` | **200,000 tokens** | Native Tool Use / Function Calling (`tools` schema parameter). Prompt Caching (5-min TTL). | Text, Image | $3.00 / 1M input ($0.30 cached), $15.00 / 1M output | **Tier 1 Primary Reasoning Model:** Industry-standard nuance in identifying implicit context gaps, resolving pronouns, evaluating cold-viewer standalone comprehension, and selecting punchlines. |
| **Anthropic**<br>`claude-3-5-haiku-20241022` | **200,000 tokens** | Native Tool Use / Function Calling | Text, Image | $0.80 / 1M input, $4.00 / 1M output | **Tier 1 Fast Triage Model:** Rapid initial scan for seed moments across long conversations. |
| **Google Gemini**<br>`gemini-1.5-pro-002` | **2,000,000 tokens** | Native JSON Schema Enforcement (`response_mime_type="application/json"`, `response_schema`). | Text, Audio, Video, Image | $1.25 / 1M input ($\le 128\text{k}$), $2.50 / 1M input ($> 128\text{k}$); $5.00 / 1M output | **Tier 1 Long-Context Specialist:** Capable of ingesting an entire 90-minute raw transcript (30k+ tokens) plus raw audio in a single prompt. Exceptional multilingual/Hinglish comprehension. |
| **Google Gemini**<br>`gemini-1.5-flash-002` | **1,000,000 tokens** | Native JSON Schema (`response_schema`) | Text, Audio, Video, Image | $0.075 / 1M input, $0.30 / 1M output | **Tier 1 Low-Cost Alternative:** Extremely fast candidate extraction across long transcripts. |
| **OpenAI**<br>`gpt-4o-2024-08-06` | **128,000 tokens** | Structured Outputs with 100% adherence to strict JSON Schema (`response_format={"type": "json_schema", "json_schema": {"strict": True, ...}}`). | Text, Image, Audio | $2.50 / 1M input, $10.00 / 1M output | **Tier 1 Structured Extraction Model:** Guaranteed adherence to complex nested schemas (`clip_selection_plan.schema.json`). |
| **OpenAI**<br>`gpt-4o-mini-2024-07-18` | **128,000 tokens** | Structured Outputs with strict JSON Schema | Text, Image | $0.15 / 1M input, $0.60 / 1M output | **Tier 1 Budget Extraction:** Cost-effective candidate drafting. |

### 5.2 Local Specialist & Open-Weight Model Evaluation

| Model Family & Variant | Parameter Scale & Context | Local VRAM / RAM Footprint | License | Multilingual & Hinglish Capability | Role in AI Video Lab Architecture |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Qwen 2.5 7B-Instruct** | 7.6B params<br>128k context | ~5.2 GB VRAM (Q4_K_M quant). Fits within laptop RTX 3050 6GB GPU. | Apache 2.0 | Outstanding tokenization for Hindi, Hinglish, code-switching, and structured JSON. | **Tier 3 Offline Fallback:** Used when no internet or API keys are available, operating on sliding context windows. |
| **Qwen 2.5 72B-Instruct** | 72.7B params<br>128k context | ~42 GB VRAM (Q4_K_M quant). Requires workstation / dual-GPU. | Apache 2.0 | Matches frontier models in reasoning and cross-segment context resolution. | **Tier 2 High-End Self-Hosted:** Ideal for privacy-focused local production. |
| **Faster-Whisper** (`large-v3-turbo`) | 809M params | ~1.5 GB VRAM (CTranslate2 INT8). Runs fast on CPU or laptop GPU. | MIT | 99 languages. Fast, robust word timestamps. | **Core Offline STT Tool:** Integrated via `tools/analysis/transcriber.py`. |

### 5.3 Quality-First Architecture Strategy: Decoupling Intelligence from Local Hardware
- **The Core Rule:** Hardware constraints (RTX 3050 6GB Laptop GPU, 15.7GB RAM) determine **local execution feasibility**, not the ceiling of product intelligence.
- **Execution Architecture:**
  - The IDE agent (Script Director) leverages frontier cloud models (Claude 3.5 Sonnet / Gemini 1.5 Pro) for full-transcript comprehension, cold-viewer auditing, and narrative closure.
  - Python tools execute local deterministic tasks (FFmpeg audio energy, silence detection, token indexing, and schema validation).
  - When working completely offline, the system gracefully falls back to local Qwen 2.5 7B via Ollama with chunked context windows, explicitly logging that offline mode is active.

---

## 6. M1 Hardening Prioritized Action Items Table

| ID | Priority | Area | Issue Description | Proposed Remediation | Blocks Phase 2A? |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M1-H01** | **CRITICAL** | Packaging | `yt-dlp` and `youtube-transcript-api` missing from `requirements.txt` and `setup.py`. | Add `yt-dlp>=2024.08.06` and `youtube-transcript-api>=0.6.2` to `requirements.txt` and `setup.py`. | **NO** (Contracts phase does not invoke downloader). |
| **M1-H02** | **HIGH** | Resource Guard | Post-download duration check omitted if preflight duration was 0 or missing. | Add `if duration_s > max_duration_seconds` post-probe check; delete staging and raise error. | **NO** |
| **M1-H03** | **HIGH** | Security | Preflight DNS resolution does not protect against yt-dlp redirect/rebinding egress. | Document application-level defense boundaries; restrict yt-dlp protocols. | **NO** |
| **M1-H04** | **MEDIUM** | Consistency | Sequential `shutil.move` leaves partial directories on intermediate move failure. | Implement transactional staging directory move with exception rollback cleanup. | **NO** |
| **M1-H05** | **MEDIUM** | Transcript | Hardcoded `languages: ["en"]` ignores native captions on non-English videos. | Expose configurable `languages: list[str]` parameter with multi-language fallback. | **NO** |
| **M1-H06** | **LOW** | QA Tests | `run_smoke_test()` lacks `test_*` prefix, uncollected by pytest. | Wrap in `def test_url_intake_smoke()` and gate with `@pytest.mark.network`. | **NO** |

**Conclusion:** None of the M1 hardening items block Phase 2A (which defines schemas and evidence models). However, they must be resolved before Milestone 2 integration testing.
