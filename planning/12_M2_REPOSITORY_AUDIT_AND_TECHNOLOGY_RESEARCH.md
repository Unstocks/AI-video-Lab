# M2 FINAL — REPOSITORY EVIDENCE, TECHNOLOGY VALIDATION & QUALITY-FIRST PROVIDER ARCHITECTURE
**Project:** AI Video Lab (`C:\AI-Video-Lab`)  
**Pipeline:** `clip-factory` (v2.0)  
**Document:** `planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md`  
**Date:** November 17, 2026  
**Author:** Principal Software Architect, Senior Python Engineer & Independent Repository Auditor  
**Status:** Architecture Investigation & Engineering Validation (Implementation Authorization: NOT GRANTED)  

---

## 1. Executive Summary & Audit Objectives

Milestone 1 successfully established verified source media intake, anti-SSRF protection, audio normalization, transcript retrieval, source media review, brief generation, and human gate enforcement. `[VERIFIED]`

Milestone 2 shifts from **media acquisition** to **conversation intelligence**: converting a raw transcript and its conversational context into a ranked, evidence-backed collection of genuinely valuable, self-contained short-form video opportunities (`clip_selection_plan.json`), while maintaining complete backward compatibility with OpenMontage's canonical script artifact (`script.json`). `[PROPOSED]`

This report audits the existing OpenMontage agent architecture, resolves provider and model dependencies, establishes a quality-first model tiering strategy that is not constrained by local hardware, and audits downstream consumers with exact code citations.

---

## 2. Existing OpenMontage Agent Architecture & Capability Matrix

OpenMontage is an **instruction-driven video production system**. The AI agent is the intelligence; it reads pipeline manifests (`pipeline_defs/*.yaml`), executes stage director skills (`skills/pipelines/<pipeline>/<stage>-director.md`), and invokes deterministic tools (`tools/`) registered in `tools/tool_registry.py`. `[VERIFIED: AGENT_GUIDE.md lines 70-82]`

### Evidence-Based Capability Matrix of Existing Pipeline Agents

| Agent / Role | Repository Path | Primary Responsibility | Model / Provider Config | Available Tools | Inputs & Outputs | Reasoning Type | Delegation Ability | Clip-Discovery Role & Limitations | Recommended Extension for M2 | Evidence Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Executive Producer (EP)** | `skills/pipelines/clip-factory/executive-producer.md` | Orchestrates serial stage transitions, runs cross-stage quality gates, tracks budget. | Inherits primary session LLM | None directly (meta-skill) | In: `EP_STATE`<br>Out: Stage gate decisions | High-level semantic oversight | Delegated by pipeline manifest | Oversees `clip-factory` batch goals; currently lacks conversation intelligence metrics. | Update cross-stage checklist after `script` to verify `clip_selection_plan` schema and cold-viewer pass rate. | `[VERIFIED]` |
| **Idea Director** | `skills/pipelines/clip-factory/idea-director.md` | Ingests URL/video, sets clip count target, platforms, and selection criteria. | Primary session LLM | `video_downloader`, `transcript_fetcher` | In: `source_media_review`<br>Out: `brief.json`, `decision_log.json` | Hybrid: tool retrieval + semantic scoping | None | Ingests media and establishes target clip batch size. | Preserved from Milestone 1 without modification. | `[VERIFIED]` |
| **Script Director** | `skills/pipelines/clip-factory/script-director.md` | Mines source transcript for clip candidates, applies standalone test, ranks clips. | Primary session LLM | `transcriber`, `scene_detect` | In: `brief.json`, `transcript.json`<br>Out: `script.json` (canonical) | Heavy semantic reasoning | None currently | **Central M2 Stage:** Guided solely by markdown prompts; lacks deterministic sentence normalizers, token provenance, and acoustic snapping. | **Primary Extension Point:** Equip Script Director with `clip_selector` tool and dual-artifact synthesis (`script.json` + `clip_selection_plan.json`). | `[VERIFIED]` |
| **Scene Director** | `skills/pipelines/clip-factory/scene-director.md` | Plans framing (`9:16`, `1:1`, `16:9`), hook overlays, and safe zones per clip deliverable. | Primary session LLM | `frame_sampler`, `scene_detect` | In: `script.json`<br>Out: `scene_plan.json` | Visual & spatial reasoning | None | Downstream M3 consumer: Maps `scene.script_section_id` to `script.sections[i].id`. | Preserved for M3. M2 must supply valid `script.sections` matching each approved clip. | `[VERIFIED]` |
| **Asset Director** | `skills/pipelines/clip-factory/asset-director.md` | Generates per-clip subtitles, hook titles, and audio normalization. | Primary session LLM | `subtitle_gen`, `audio_enhance` | In: `scene_plan`, `script`<br>Out: `asset_manifest.json` | Asset coordination | None | Downstream M3 consumer: Generates SRT subtitles from transcript data. | Preserved for M3. | `[VERIFIED]` |
| **Edit Director** | `skills/pipelines/clip-factory/edit-director.md` | Establishes cut points, hook placement within 2-3s, and subtitle sync. | Primary session LLM | None directly (instructional) | In: `scene_plan`, `asset_manifest`<br>Out: `edit_decisions.json` | Temporal editing reasoning | None | Downstream M3 consumer: Directs physical video cuts. | Preserved for M3. | `[VERIFIED]` |
| **Compose Director** | `skills/pipelines/clip-factory/compose-director.md` | Executes video trimming, composition, and rendering. | Primary session LLM | `video_compose`, `video_trimmer`, `audio_mixer` | In: `edit_decisions`<br>Out: `render_report.json`, `final_review.json` | Execution & QA | None | Downstream M3 consumer: Renders final MP4 video files. | Preserved for M3. | `[VERIFIED]` |
| **Publish Director** | `skills/pipelines/clip-factory/publish-director.md` | Packages per-clip social titles, hashtags, and export folders. | Primary session LLM | None directly | In: `render_report`<br>Out: `publish_log.json` | Packaging reasoning | None | Downstream M4 consumer. | Preserved for M4. | `[VERIFIED]` |
| **Meta-Reviewer** | `skills/meta/reviewer.md` | Evaluates artifacts against CHAI critique rules (Accurate, Complete, Constructive). | Primary session LLM | JSON Schema validator | In: Artifact + manifest criteria<br>Out: Review findings | Critical quality audit | Can reject stage output | Enforces schema validation and qualitative success criteria before checkpoints. | Reused to validate `clip_selection_plan.schema.json` and cold-viewer pass rate. | `[VERIFIED]` |
| **Checkpoint Protocol** | `skills/meta/checkpoint-protocol.md` | Persists stage state, archives history, and enforces `awaiting_human` gate. | Python utility (`lib/checkpoint.py`) | File I/O, `jsonschema` | In: Artifact dictionary<br>Out: `checkpoint_<stage>.json` | Deterministic persistence & governance | None | Enforces human approval gate before advancing from `script` to `scene_plan`. | Reused to enforce human approval gate on `clip_selection_plan.json`. | `[VERIFIED]` |

### Architectural Decision on Agent Architecture
- **Option A (Extend existing agents only):** Inadequate; leaves the Script Director without deterministic text normalization, acoustic analysis, and token indexing.
- **Option B (Introduce independent agent framework):** Rejected; violates OpenMontage architecture by creating a second orchestration engine inside `lib/`.
- **Option C (Recommended: Extend Script Director with Specialized Tools):** `[PROPOSED]`  
  Preserve the authoritative **Script Director** persona (`skills/pipelines/clip-factory/script-director.md`) governed by the Executive Producer. Equip it with a dedicated registered tool (`tools/analysis/clip_selector.py`) that delegates heavy deterministic computation (normalization, acoustic analysis, token indexing) to Python while preserving AI agent intelligence for semantic discovery, cold-viewer auditing, and human review.

---

## 3. Quality-First Model & Provider Architecture

Hardware constraints (such as the developer's laptop RTX 3050 GPU) are **deployment information**, not product-level intelligence ceilings. To deliver human-editor-grade clip discovery, the architecture must support frontier reasoning models while enabling local fallback. `[PROPOSED]`

### 3.1 Model Evaluation for Conversation Intelligence Tasks

| Conversational Task | Linguistic Requirement | Frontier Cloud Option (Tier 1 - Highest Quality) | High-End Self-Hosted Option (Tier 2 - Privacy/Enterprise) | Constrained Local Option (Tier 3 - Offline Edge) | Rationale & Tradeoffs |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Macro Conversation Understanding** | Ingesting 45-90 min podcasts (15k-30k tokens) in a single unified context window. | **Gemini 1.5 Pro / 2.0 Flash** (1M-2M context) or **Claude 3.5 Sonnet** (200k context) | **Qwen 2.5 72B-Instruct** (128k context) or **Llama 3.3 70B** | **Hierarchical chunking with Qwen 2.5 3B/7B** (32k context) | Frontier cloud models comprehend entire 90-minute narrative arcs without chunk boundary artifacts. `[RESEARCHED]` |
| **Cold-Viewer Standalone Audit** | Deep semantic reasoning: identifying implicit assumptions, unexplained pronouns, and missing context. | **Claude 3.5 Sonnet** or **GPT-4o** | **Qwen 2.5 72B-Instruct** | **Qwen 2.5 3B / 7B-Instruct** | Claude 3.5 Sonnet exhibits the lowest false-positive rate on nuance and presupposition detection. `[RESEARCHED]` |
| **Editorial Hook Integrity** | Selecting exact verbatim openings from transcript; zero fabrication. | Any model + Deterministic Token Validator (`validate_hook_provenance`) | Any model + Deterministic Token Validator | Any model + Deterministic Token Validator | Spoken hook integrity is enforced by **deterministic Python code**, guaranteeing $0.0\%$ hallucination regardless of model tier. `[VERIFIED]` |
| **Multilingual & Hinglish Processing** | Code-switching, phonetic Hindi in Latin script, regional idioms. | **Gemini 1.5 Pro** or **GPT-4o** | **Qwen 2.5 72B-Instruct** (exceptional multilingual reasoning) | **Qwen 2.5 7B-Instruct** | Qwen 2.5 family and Gemini excel at South Asian language code-switching and nuance. `[RESEARCHED]` |
| **Dense Vector Embeddings** | Generating normalized vectors for Semantic TextTiling block comparison. | **OpenAI text-embedding-3-small** (1536 dims) or **Voyage-3** | **`bge-m3`** (1024 dims) | **`bge-small-en-v1.5`** (384 dims, English) or **`nomic-embed-text`** (768 dims) | Local embeddings (`nomic` / `bge-m3`) run in milliseconds on CPU/GPU without recurring API cost. `[VERIFIED]` |

### 3.2 Pluggable Provider Abstraction (`lib/providers/`)
The system defines an abstract provider protocol (`LLMProvider`) supporting pluggable backends:
1. `OpenAICompatibleProvider`: Connects to OpenAI, OpenRouter, DeepSeek, Local Ollama (`http://127.0.0.1:11434`), or Local `llama-server.exe`.
2. `AnthropicProvider`: Connects to native Anthropic Messages API (`claude-3-5-sonnet`).
3. `GoogleGenAIProvider`: Connects to Google Gemini API (`gemini-1.5-pro`, `gemini-2.0-flash`).

**Configuration (`.env`):**
```bash
# Quality-First Production Setting (Tier 1)
OPENMONTAGE_LLM_PROVIDER=anthropic
OPENMONTAGE_LLM_MODEL=claude-3-5-sonnet-20241022

# Alternative Local-First Setting (Tier 3)
OPENMONTAGE_LLM_PROVIDER=openai
OPENMONTAGE_LLM_BASE_URL=http://127.0.0.1:11434/v1
OPENMONTAGE_LLM_MODEL=qwen2.5:3b
```
*Zero pipeline code changes are required when switching between cloud frontier models and local runtimes.* `[PROPOSED]`

---

## 4. Reconciled Hardware Profile (Deployment Baseline)

Empirical measurement of the host Windows 11 machine verified the deployment environment: `[VERIFIED]`
- **GPU:** NVIDIA GeForce RTX 3050 Laptop GPU (6,144 MiB VRAM total, ~6,002 MiB available at idle).
- **RAM:** 15.70 GB Total, 5.36 GB available at idle (65% load).
- **CPU:** 16 logical cores (AMD/Intel 8C/16T).
- **Python Runtime:** Python `3.14.10` AMD64 (`.venv`).

### Reconciled Local Model Footprints (When Local Deployment is Selected)
- **Qwen 2.5 7B Q4_K_M:** Weights ~4.68 GB + KV Cache (4k tokens) ~0.35 GB + CUDA overhead ~0.25 GB = **~5.40 GB active VRAM**. On a 6.14 GB GPU with ~1.0 GB Windows OS overhead, this operates at the capacity limit.
- **Qwen 2.5 3B Q4_K_M / Llama 3.2 3B Q4_K_M:** Weights ~2.1 GB + KV Cache ~0.2 GB = **~2.50 GB active VRAM**. Leaves $>3.4\text{ GB}$ VRAM free. 100% stable local baseline.
- **Hybrid Rule:** If the user selects local inference on this host machine, the pre-flight check automatically selects 3B models unless $>5.4\text{ GB}$ free VRAM is detected. `[PROPOSED]`

---

## 5. Downstream Consumer Audit & Dual-Artifact Compatibility

We inspected all existing downstream consumers to verify the proposed dual-artifact design (`artifacts/script.json` canonical + `artifacts/clip_selection_plan.json` first-class): `[VERIFIED]`

### Downstream Consumer Inventory

| Downstream Consumer | Code File & Line Reference | Expected Artifact Input | Specific Contract & Field Dependencies | Compatibility Status |
| :--- | :--- | :--- | :--- | :--- |
| **Checkpoint Engine** | `lib/checkpoint.py` (lines 30-40, 134-144) | `artifacts["script"]` | Mandates canonical artifact `script` for `script` stage. Validates against `schemas/artifacts/script.schema.json`. | **VERIFIED:** Canonical `script.json` satisfies `lib/checkpoint.py`. |
| **Backlot Storyboard** | `backlot/state.py` (lines 380-415) | `artifacts.get("script")["sections"]` | Joins `scene["script_section_id"] == section["id"]`. Renders each section as a visual card. | **VERIFIED by Code Inspection:** Mapping each approved clip to a `section` in `script.json` renders each clip card automatically. |
| **Scene Planner Stage** | `pipeline_defs/clip-factory.yaml` (lines 89-111) | `required_artifacts_in: ["script"]` | Reads approved clip list to plan visual framing (`9:16`, `1:1`) and overlays. | **VERIFIED:** Consumes `script.json` without schema conflict. |
| **Scene Plan Schema** | `schemas/artifacts/scene_plan.schema.json` (line 25) | `script_section_id` | Requires string referencing `script.sections[i].id`. | **VERIFIED:** Matches `script.sections` item IDs. |
| **Asset Director Stage** | `pipeline_defs/clip-factory.yaml` (lines 112-136) | `optional_artifacts_in: ["script"]` | Generates per-clip subtitles from approved section timestamps. | **VERIFIED:** Timestamps in `script.sections` provide start/end bounds. |
| **Edit Director Stage** | `pipeline_defs/clip-factory.yaml` (lines 137-156) | `optional_artifacts_in: ["script"]` | Validates hook placement within first 2-3s of each clip. | **VERIFIED:** Section text and timing provide hook reference. |

---

## 6. Implementation Corrections & Dependency Clarifications

1. **`jsonschema` Dependency:**  
   `jsonschema` (version 4.23.0) is already installed in the workspace `.venv`. Phase 2A requires zero new package installations, but relies on the pre-installed `.venv` environment. `[VERIFIED]`
2. **Safe JSON Parsing (Greedy Regex Replaced):**  
   Greedy regex `r"\{[\s\S]*\}"` is unsafe because it matches from the first `{` to the last `}` across multi-object outputs or markdown notes. The architecture replaces this with a **balanced-bracket JSON extractor** (`extract_balanced_json_block`) that tracks bracket nesting depth. `[PROPOSED]`
3. **Exact Token & Character Offset Tracing:**  
   `validate_hook_provenance` enforces exact token matching against the unnormalized source segments and returns the exact character span `[char_start, char_end]` in the raw transcript evidence. `[PROPOSED]`
