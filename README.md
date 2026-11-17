# AI Video Lab — Local-First AI Video & Social Media Studio
### Powered by OpenMontage | Local-First Architecture

[![Tests](https://img.shields.io/badge/tests-22%20passed-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)]()
[![License: AGPLv3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Architecture](https://img.shields.io/badge/architecture-local--first%20agentic-purple.svg)]()

> **AI Video Lab** is a high-performance, local-first personal AI video production studio built on the official **OpenMontage** platform. It automates the end-to-end transformation of long-form conversations, podcasts, interviews, and video URLs into high-impact, contextually complete short-form clips (9:16 YouTube Shorts / Reels / TikToks).

---

## 🌟 Executive Overview & Architectural Evolution

AI Video Lab adopts **OpenMontage** as its core video production and composition foundation. OpenMontage provides an instruction-driven, agentic video production architecture where the AI agent (Antigravity, Claude Code, Cursor) acts as the creative orchestrator, while Python provides deterministic tools, media processing pipelines, and state persistence.

```
Agent reads pipeline manifest (YAML) ──> reads stage director skill (Markdown)
       │
       ├──> invokes deterministic Python tools (yt-dlp, FFmpeg, Whisper, PyTorch)
       ├──> evaluates quality & self-review gates (CHAI critique protocol)
       ├──> checkpoints stage artifacts (lib/checkpoint.py)
       └──> renders live visual storyboard for human approval (Backlot UI)
```

---

## 📦 Milestone Implementation & Architecture Status

### ✅ Milestone 1: URL Intake & Source Media Acquisition (COMPLETED & ACCEPTED)
Enables OpenMontage's `clip-factory` pipeline to ingest remote video URLs (YouTube, Vimeo, etc.) and acquire ground-truth media:
- **Dedicated URL Intake Adapter (`lib/url_ingest.py`):**
  - Production wrapper integrating OpenMontage's `VideoDownloader` (`yt-dlp`) and `TranscriptFetcher` (`youtube-transcript-api`).
  - Application-level YouTube/Vimeo host allowlisting and preflight IP filtering for private, loopback, link-local, reserved, and multicast destinations. This does not guarantee protection from DNS rebinding or redirects after preflight.
  - Resource guards enforce a 3600-second default maximum duration, recheck duration after probing, and check disk space before download.
  - **Dual Extraction:** Automatically extracts high-quality audio (`source_audio.wav`) and captions (`transcript.json`).
  - Seamless handoff to canonical `lib/source_media_review.py` for duration, resolution, audio track, and speech density probing.
- **Pipeline Integration:**
  - `pipeline_defs/clip-factory.yaml`: Unlocked `video_downloader` and `transcript_fetcher` in stage `idea.tools_available`.
  - `skills/pipelines/clip-factory/idea-director.md`: Documented Source Acquisition Protocol and input schema contract.
- **Test Coverage:**
  - `tests/unit/test_url_ingest.py`: 12 automated unit tests covering URL normalization, SSRF protection, duration guardrails, mock intake flows, and error handling.
  - `tests/qa/test_url_intake_smoke.py`: 2 automated smoke tests verifying live integration and manifest persistence.

---

### 🔬 Milestone 2: Conversation Intelligence, Semantic Moment Discovery & Clip Selection (ARCHITECTURE FROZEN)
Addresses the challenge of extracting viral, coherent, standalone clips from long-form conversations:
- **Comprehensive Forensic Audit (`planning/16_M2_MASTER_REPOSITORY_FORENSIC_AUDIT.md`):**
  - Audited all 10 existing pipeline agents, 26 core repository files, and model/runtime constraints.
  - Established that OpenMontage has **no runtime LLM in Python** (`docs/ARCHITECTURE.md line 100`).
- **Architectural Decision: Option B (Native OpenMontage Extension):**
  - Preserves the **Script Director** (`skills/pipelines/clip-factory/script-director.md`) as the semantic reasoning intelligence.
  - Equips the Script Director with specialized deterministic Python analytical tools:
    1. `transcript_normalizer.py`: Text cleaning, speaker grouping, and bidirectional token-to-source indexing.
    2. `clip_selector.py`: Candidate ranking, silence-snapping boundary refinement, and schema serialization.
    3. `hook_validator.py`: Verbatim spoken hook verification against raw transcript evidence with character offsets `[char_start, char_end]`.
- **Dual-Artifact Pipeline Compatibility:**
  - **Canonical `script.json`:** Approved clips formatted as sections `script.sections`, 100% compatible with `lib/checkpoint.py`, `backlot/state.py` storyboard cards, and downstream `scene_plan` stages.
  - **First-Class `clip_selection_plan.json`:** Comprehensive candidate dossier with virality vectors, hook classifications, and full transcript provenance.
- **3-Tier Timestamp Provenance:**
  - `SOURCE_SEGMENT`: Exact YouTube caption or Whisper segment boundary.
  - `ESTIMATED_INTERPOLATED`: Word-count interpolated boundary.
  - `ACOUSTICALLY_VERIFIED`: Snapped to speech onset/offset via `silence_cutter` (FFmpeg `silencedetect`).
  - Universal fixed padding is abolished in favor of acoustic silence snapping.
- **Hardware Envelope & Model Tiering:**
  - Grounded for consumer workstation hardware (NVIDIA GeForce RTX 3050 Laptop GPU, 6,144 MiB VRAM, 15.7 GB RAM).
  - Tier 1 (Cloud/Frontier LLMs via agent) for full 30k-token conversation intelligence; Tier 2/3 (Local 7B/3B via Ollama) for offline fallback.

---

## 📚 Architectural & Planning Dossier Index

All research, architecture decisions, forensic audits, and verification reports are documented in [`planning/`](planning/):

| Report | Title & Focus |
| :--- | :--- |
| **[01](planning/01_EXISTING_OPENMONTAGE_CAPABILITY_AUDIT.md)** | Existing OpenMontage Capability Audit |
| **[02](planning/02_EXTERNAL_RESEARCH_AND_ARCHITECTURE_DECISION.md)** | External Research & Architecture Decision (OpusClip, Klap, Munch benchmark) |
| **[03](planning/03_EXECUTION_READY_IMPLEMENTATION_ROADMAP.md)** | Execution-Ready Implementation Roadmap |
| **[04](planning/04_TECHNICAL_VALIDATION_AND_RESEARCH_REPORT.md)** | Technical Validation & Research Report (6 Critical Questions) |
| **[05](planning/05_FINAL_ARCHITECTURE_AND_IMPLEMENTATION_BLUEPRINT.md)** | Final Architecture & Implementation Blueprint |
| **[06](planning/06_FINAL_IMPLEMENTATION_READINESS_GATE.md)** | Final Implementation Readiness Gate |
| **[07](planning/07_MILESTONE_1_URL_INTAKE_IMPLEMENTATION_PLAN.md)** | Milestone 1 URL Intake Implementation Plan |
| **[08](planning/08_MILESTONE_1_COMPLETION_REPORT.md)** | Milestone 1 Completion Report |
| **[09](planning/09_POST_MILESTONE_1_VERIFICATION_REPORT.md)** | Post-Milestone 1 Verification Report |
| **[10](planning/10_MILESTONE_1_FINAL_MASTER_VERIFICATION.md)** | Milestone 1 Final Master Verification |
| **[11](planning/11_MILESTONE_1_FINAL_GAP_RESOLUTION.md)** | Milestone 1 Final Gap Resolution |
| **[12](planning/12_M2_REPOSITORY_AUDIT_AND_TECHNOLOGY_RESEARCH.md)** | Milestone 2 Technology & Model Research |
| **[13](planning/13_M2_CONVERSATION_INTELLIGENCE_AND_CLIP_DISCOVERY_ARCHITECTURE.md)** | Conversation Intelligence & Clip Discovery Architecture |
| **[14](planning/14_M2_IMPLEMENTATION_ROADMAP_AND_VERIFICATION_STRATEGY.md)** | M2 Implementation Roadmap & Verification Strategy |
| **[15](planning/15_M2_CONSOLIDATED_EXECUTION_PLAN.md)** | M2 Consolidated Execution Plan |
| **[16](planning/16_M2_MASTER_REPOSITORY_FORENSIC_AUDIT.md)** | **Master Repository Forensic Audit & Source-Code Evidence Dossier** |

---

## 🛠️ Repository Layout

```text
AI-Video-Lab/
├── backlot/                   # Living storyboard web UI & state server (port 4750)
├── docs/                      # Architectural specifications & provider documentation
├── lib/                       # Core library modules
│   ├── checkpoint.py          # State machine, artifact schemas, and human approval gates
│   ├── source_media_review.py # Universal media probing and review
│   └── url_ingest.py          # [M1] URL Intake Adapter (SSRF, yt-dlp, transcript fetching)
├── pipeline_defs/             # Declarative pipeline manifests
│   └── clip-factory.yaml      # Multi-clip production pipeline
├── planning/                  # Complete 16-report architectural & forensic audit dossier
├── remotion-composer/         # React-based programmatic video rendering engine
├── schemas/                   # JSON schemas for stage artifacts
├── skills/                    # Instruction-driven stage director & meta skills
│   └── pipelines/clip-factory/
│       ├── idea-director.md   # [M1] Intake & concept ideation director
│       └── script-director.md # [M2] Semantic moment discovery director
├── tests/                     # Test suites
│   ├── contracts/             # Instruction and pipeline contract integrity tests
│   ├── qa/                    # Quality assurance & smoke tests
│   └── unit/                  # Unit tests (including test_url_ingest.py)
├── tools/                     # Deterministic tool registry & implementations
│   ├── analysis/              # video_downloader, transcriber, transcript_fetcher, audio_energy
│   ├── subtitle/              # subtitle_gen (karaoke style SRT/VTT)
│   └── video/                 # video_trimmer, silence_cutter, auto_reframe
├── AGENT_GUIDE.md             # Complete agent operating manual and contract
└── requirements.txt           # Python dependencies
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.12+**
- **FFmpeg & FFprobe** installed and on `PATH`
- **Node.js 18+** (for Remotion composer and Backlot UI)

### 2. Environment Setup
```bash
git clone https://github.com/Unstocks/AI-video-Lab.git
cd AI-video-Lab

# Create and activate Python virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Verify Tests
Run the test suites to ensure system integrity:
```bash
pytest -m "not network" tests/
```

### 4. Run the Living Storyboard (Backlot)
```bash
python -m backlot.server
```
Visit `http://localhost:4750` to inspect living production projects and review clips.

---

## 🎬 OpenMontage Production Capabilities

OpenMontage supports multiple end-to-end autonomous video production pipelines beyond clip extraction:
- **`cinematic-trailer`**: Multi-scene trailers with Veo / Kling / Sora video, Lyria / ElevenLabs soundtracks, and cinematic titles.
- **`animation-short`**: Animated stories with character consistency, dialogue, Foley sound effects, and karaoke captions.
- **`product-ad`**: Commercial product videos with clean product preservation, camera motion, and brand styling.
- **`explainer`**: Visual essays with diagrammatic animations, stock media integration, and structured educational chapters.
- **`3d-world`**: Continuous 3D world flythroughs built from textured 3D assets and procedural terrain.

---

## 📄 License & Attribution

AI Video Lab is built upon the open-source [OpenMontage](https://github.com/OpenMontageInc/OpenMontage) project and is licensed under the [GNU Affero General Public License v3.0 (AGPLv3)](LICENSE).
