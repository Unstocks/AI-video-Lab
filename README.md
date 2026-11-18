# AI Video Lab — Local-First AI Video & Social Media Studio
### Powered by OpenMontage | Local-First Architecture

[![Tests](https://img.shields.io/badge/tests-235%2B%20passed-brightgreen.svg)]()
[![Python 3.11–3.14 core](https://img.shields.io/badge/python-3.11--3.14-blue.svg)]()
[![Studio UI](https://img.shields.io/badge/studio-React%2019%20%2B%20Vite%206%20%2B%20Tailwind%20v4-amber.svg)]()
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

## 📦 Implementation Status (`HEAD 216a604`)

| Layer / Milestone | Status | Key Modules & Verified Capabilities |
| :--- | :---: | :--- |
| **M1 + Phase 1: Hardened Intake & Broadcast GPU** | ✅ **DONE** | `lib/url_ingest.py`, `lib/ssrf_guard.py` (connect-time SSRF), `tools/analysis/url_intake.py`, `lib/ffmpeg_profiles.py` (RTX 3050 `h264_nvenc` + single-pass `-14 LUFS`/`-2.0 dBTP` loudnorm + metadata scrub) |
| **M2 + M3: Conversation Intelligence & Human Gates** | ✅ **DONE** | `lib/models/`, `lib/transcript_normalizer.py`, `lib/conversation_structure.py`, `lib/acoustic_profiler.py`, `lib/hook_validator.py`, `lib/cold_viewer_auditor.py`, `lib/editorial_evaluator.py`, `lib/deduplicator.py`, `tools/analysis/clip_selector.py` (SHA-256 dual-artifact sync with `lib/checkpoint.py`) |
| **M4 + Phase 2: Smart Reframe v2 Cinematography** | ✅ **DONE** | `lib/face_detector.py` (YuNet ONNX), `lib/camera_tracker.py` (`SmoothedCameraman`), `lib/split_layout.py`, `lib/active_speaker.py`, `lib/punch_in.py`, `tools/video/auto_reframe.py` (zero frame drift), `tools/video/vertical_clip_composer.py` |
| **M6a + Phase 3: 8 Presets, `Style: Seam` & Eval Studio** | ✅ **DONE** | `lib/subtitle_styles.py` (8 DirectWrite-verified OFL fonts in `assets/fonts/`, incl. Hinglish Devanagari), `lib/layout_ranges.py`, `tools/subtitle/subtitle_gen.py` (`Style: Seam` center placement for 2-speaker split), `lib/eval_studio.py` |
| **M5 + Phase 5: Broadcast QA, Hard-Gated Export & Gateway** | ✅ **DONE** | `tools/analysis/media_qa.py` & `lib/media_qa.py` (`integrated_lufs`, `true_peak_dbtp`, strict loudnorm window, freeze/black-frame detection), hard-gated batch `tools/publishers/export_bundle.py`, `lib/llm_gateway.py` |
| **Phase 4 + Pro Studio (`216a604`): Broadcast Obsidian Pro UI** | ✅ **DONE** | Loopback + CSRF hardened FastAPI BFF (`studio/` on `127.0.0.1:4760`) + React 19 / TypeScript / Vite 6 / Tailwind v4 SPA (`studio/web/` → `studio/ui/`) covering all 13 pipelines, 169 tools, 6 playbooks, NLE Multi-Track Timeline (PCM waveform, filmstrip, on-canvas Single/Split crop, word-snapped recut), Universal Pipeline Board, Broadcast QA, and persistent `fcc-claude` Executive Producer Dock (`0` console/page/network errors in Playwright Chromium E2E) |
| **Phase 0 (`BU-0.1`) & Phase 6 (`BU-6.1`)** | ⏳ **NEXT** | System-level `free-claude-code` (`127.0.0.1:8082`) install + live end-to-end 2-speaker podcast walkthrough through Pro Studio UI |

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
├── architecture/              # Permanent 3-layer engineering brain (01–03)
├── assets/
│   ├── fonts/                 # 8 bundled DirectWrite-verified OFL subtitle fonts (incl. Devanagari)
│   └── models/                # YuNet ONNX face detection weights
├── backlot/                   # Read-only living storyboard observer server (127.0.0.1:4750)
├── studio/                    # Broadcast Obsidian Pro Studio (127.0.0.1:4760)
│   ├── server.py              # Loopback + CSRF hardened FastAPI BFF & SSE streams
│   ├── catalog.py             # Whole-system 13-pipeline / 169-tool / 6-playbook catalog
│   ├── media_engine.py        # FFmpeg PCM waveform, filmstrip, upload & music engine
│   ├── supervisor.py          # fcc-claude NDJSON stream-json + --resume manager
│   ├── web/                   # React 19 + TypeScript + Vite 6 + Tailwind CSS v4 source
│   └── ui/                    # Compiled static production SPA served by `python -m studio`
├── lib/                       # Deterministic engines (Intake, Reframe v2, Seam Subs, QA, Eval)
├── pipeline_defs/             # 13 declarative YAML pipeline manifests
├── planning/                  # Architectural research, audits & roadmaps
├── remotion-composer/         # React-based programmatic video rendering engine
├── schemas/                   # JSON schemas for all 21 stage artifacts
├── skills/                    # Instruction-driven stage director & meta skills
├── tests/                     # Unit, backlot, contract, hardening & integration suites
├── tools/                     # 169 registered BaseTool implementations across 27 families
├── AGENT_GUIDE.md             # Complete agent operating manual and contract
└── requirements.txt           # Python dependencies
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Core offline studio:** Python 3.11, 3.12, or 3.14 with FFmpeg/FFprobe 7.0 or later (libass and libx264 recommended). Python 3.14 supports the core offline FFmpeg workflows; optional ML wheels may not be available.
- **Optional local ML/GPU:** use a dedicated Python 3.11 or 3.12 environment for faster-whisper, WhisperX, and MediaPipe integrations.
- **Optional Remotion/HyperFrames:** Node.js 22 or 24 LTS. HyperFrames preflight checks the local npm cache and does not fetch packages while checking support. Install project packages separately when network access is available.
- **Optional NVIDIA encoding:** FFmpeg builds with `h264_nvenc` may accelerate encoding; composition falls back to `libx264` when NVENC cannot run.

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

### 4. Run Pro Studio (Interactive NLE & Top Supervisor Cockpit)
```bash
python -m studio
```
Visit `http://127.0.0.1:4760` for the Broadcast Obsidian Pro workstation (Command Hub, Pro NLE Clip & Reframe Studio, Universal Pipeline Board, Broadcast QA & Export, System 169-Tool Matrix, and `fcc-claude` Executive Producer Dock).

*(To rebuild the frontend after editing `studio/web/`, run `pnpm --dir studio/web run build`.)*

### 5. Run the Read-Only Living Storyboard (Backlot)
```bash
python -m backlot.server
```
Visit `http://127.0.0.1:4750` for the strictly read-only project observer board.

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
