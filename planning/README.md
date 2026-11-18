# OpenMontage URL-to-Clips Architecture & Planning Documentation
## Master Index for Personal Social Media Video Automation

> **Live Status Note (2026-11-18 @ `HEAD 216a604`):** The `planning/` folder is the historical research & design archive from M1–M2. For the **current live implementation ledger** (M1–M6a + Phases 1–5 + Adversarial Backend Hardening + Broadcast Obsidian Pro Studio React 19 UI = **18/20 Build Units COMPLETE**), see [`../architecture/02_EXECUTION_PLAN_AND_ENGINEERING_GOVERNANCE.md`](../architecture/02_EXECUTION_PLAN_AND_ENGINEERING_GOVERNANCE.md) and [`../README.md`](../README.md).

Welcome to the architectural planning and forensic audit repository for enabling automated **URL-to-Shorts / Clips** functionality inside `AI-Video-Lab` using the official **OpenMontage** platform.

---

## Complete Documentation Navigation

| Document | Purpose & Contents |
| :--- | :--- |
| **[01. Existing OpenMontage Capability Audit](01_EXISTING_OPENMONTAGE_CAPABILITY_AUDIT.md)** | **Code-level forensic analysis:** Exact inspection of existing tools (`video_downloader`, `transcriber`, `video_trimmer`, `auto_reframe`, `subtitle_gen`), pipeline manifests (`clip-factory.yaml`), director skills, and Backlot server mechanics. |
| **[02. External Research & Architecture Decision](02_EXTERNAL_RESEARCH_AND_ARCHITECTURE_DECISION.md)** | **Industry research & strategy:** Comparative study of OpusClip, Klap, Munch, and Auto-Editor; deep dive into semantic hook detection, intelligent boundary snapping, speaker-aware 9:16 reframing, local AI feasibility, and trade-offs between Approaches A, B, and C. |
| **[03. Execution-Ready Implementation Roadmap](03_EXECUTION_READY_IMPLEMENTATION_ROADMAP.md)** | **Preliminary engineering blueprint:** Complete system architecture, Mermaid data flows, surgical diff-ready code modifications, 4-phase milestone roadmap, and MVP specifications. |
| **[04. Technical Validation & Research Report](04_TECHNICAL_VALIDATION_AND_RESEARCH_REPORT.md)** | **Deep technical validation:** Resolution of the 6 critical architectural questions (long-form limits, timestamp accuracy, virality scoring, multi-speaker reframing, Backlot state machine verification, and Windows Python 3.14 package compatibility evidence). |
| **[05. Final Architecture & Implementation Blueprint](05_FINAL_ARCHITECTURE_AND_IMPLEMENTATION_BLUEPRINT.md)** | **Definitive implementation specification:** The revised Dedicated URL Intake Adapter architecture, surgical diffs, sequence flows, risk mitigation, and phased MVP execution plan. |

---

## Executive Architectural Summary

### Core Finding: The "Missing" Feature is an Unbridged Intake Path
OpenMontage **already contains ~85% of the machinery needed** to execute automated short-form video extraction:
- **Downloader:** `tools/analysis/video_downloader.py` (production wrapper around `yt_dlp.YoutubeDL`).
- **Instant Transcript Fetcher:** `tools/analysis/transcript_fetcher.py` (`youtube-transcript-api`).
- **Word-Level STT:** `tools/analysis/transcriber.py` (`faster-whisper` / `whisperx`).
- **Acoustic Loudness Profiler:** `tools/analysis/audio_energy.py` (FFmpeg `ebur128` momentary loudness meter).
- **Automatic Jump-Cut / Dead-Air Removal:** `tools/video/silence_cutter.py` (FFmpeg `silencedetect`).
- **Frame-Accurate Video Trimmer:** `tools/video/video_trimmer.py` (FFmpeg `libx264` cut).
- **Karaoke Subtitle Generator:** `tools/subtitle/subtitle_gen.py` (pure-Python SRT/VTT word-highlight cues).
- **Multi-Clip Pipeline:** `pipeline_defs/clip-factory.yaml` (Idea $\rightarrow$ Script $\rightarrow$ Scene Plan $\rightarrow$ Assets $\rightarrow$ Edit $\rightarrow$ Compose $\rightarrow$ Publish).
- **Review & Approval Storyboard:** `backlot/server.py` (FastAPI + Server-Sent Events living board on port `4750`).

### The Revised Architectural Decision: Dedicated Intake Adapter
Instead of mutating `lib/source_media_review.py` (which is shared across 6 other video pipelines), we implement a clean, decoupled **URL Intake Adapter** (`lib/url_ingest.py`):
1. Ingests remote URLs (YouTube, Vimeo, etc.) into `projects/<id>/source/source_video.mp4` with duration and disk-space guards.
2. Hands the local file to `lib/source_media_review.py` for canonical probing without changing any existing function signatures.
3. Unlocks `video_downloader` and `auto_reframe` in `pipeline_defs/clip-factory.yaml`.
4. Leverages Backlot as the live visual monitor while approvals happen natively in chat.

---

## System Requirements & Prerequisites

### 1. Host Executables (Required)
- **FFmpeg & FFprobe:** Must be present on the system `PATH`.
  - Windows installation options: `scoop install ffmpeg` or `winget install ffmpeg`.

### 2. Python Packages (Virtual Environment `.venv`)
- Verified binary wheels are available on PyPI for Windows Python `3.14.10`:
  ```bash
  .\.venv\Scripts\pip.exe install yt-dlp faster-whisper youtube-transcript-api mediapipe opencv-python
  ```

---

*This documentation was prepared in accordance with strict forensic repository analysis standards. No application code or Git history was modified during this audit.*
