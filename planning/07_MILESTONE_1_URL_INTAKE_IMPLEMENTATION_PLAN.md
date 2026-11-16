# MILESTONE 1 IMPLEMENTATION PLAN: OPENMONTAGE URL INTAKE INTEGRATION
## Architecture, Contract Verification & Phased Execution Strategy

**Project:** AI Video Lab (`C:\AI-Video-Lab`)  
**Pipeline:** `clip-factory` (Multi-clip extraction from long-form content)  
**Milestone:** 1 — Source URL Intake & Artifact Materialization  
**Date:** November 16, 2026  
**Status:** Awaiting User Authorization to Execute  

---

## 1. Baseline System & Environment Forensic Audit

| Checkpoint | Inspected Value | Current Status | Impact / Requirement |
| :--- | :--- | :---: | :--- |
| **Git Branch** | `main` | Clean | Safe to proceed |
| **Git Head Commit** | `2e003e6` (*docs: add updated OpenMontage Instagram link*) | Pristine | Upstream history intact |
| **Working Tree** | Clean (only untracked `planning/` folder) | Verified | Zero uncommitted code collisions |
| **Python Runtime** | `3.14.10` (`C:\AI-Video-Lab\.venv\Scripts\python.exe`) | Active | Core packages installed in `.venv` |
| **`yt-dlp`** | Not installed in `.venv` | **BLOCKED** | Required for `VideoDownloader` |
| **`youtube-transcript-api`**| Not installed in `.venv` | **BLOCKED** | Required for `TranscriptFetcher` |
| **`ffmpeg` / `ffprobe`** | Not found on system PATH | **BLOCKED** | Hard prerequisite for media probing, audio extraction, and trimming |
| **Package Managers** | `winget.exe` & `scoop.ps1` available on host | Available | Can be leveraged to install FFmpeg |
| **`ToolRegistry` Discovery**| `registry.discover()` required | Verified | Discovers tools, but reports `ToolStatus.UNAVAILABLE` due to missing packages |
| **Manifest Compatibility** | `pipeline_defs/clip-factory.yaml` `idea` stage has `tools_available: []` | Schema Conforming | Ready to declare `video_downloader` & `transcript_fetcher` |
| **Stage Director Skill** | `skills/pipelines/clip-factory/idea-director.md` | Needs instructions | Ready to add URL intake protocol |

---

## 2. Technical Architecture & Module Design: `lib/url_ingest.py`

### 2.1 Core Architectural Principles
1. **Zero Core Engine Mutation:** `lib/source_media_review.py`, `tools/base_tool.py`, and `tools/analysis/*` remain 100% untouched.
2. **Decoupled Boundary:** `lib/url_ingest.py` acts as an intake boundary adapter. It translates an external remote URL into normalized local files in `projects/<project-id>/source/`:
   - `source_video.mp4`
   - `source_audio.wav`
   - `transcript.json`
   - `source_manifest.json`
3. **Seamless Handoff:** Once files are normalized, `lib/source_media_review.py:review_source_media()` probes `source_video.mp4` exactly as if a local user file had been provided.

### 2.2 Functional Specification for `lib/url_ingest.py`

```python
class URLIntakeAdapter:
    """Acquires remote video into projects/<project-id>/source/ with safety guards."""
```

#### A. URL Security & SSRF Defense
- **Protocol Whitelist:** Enforce `http://` or `https://` only.
- **Domain Whitelist:** Validate netloc against allowed patterns:
  - `^(www\.)?(youtube\.com|youtu\.be)$`
  - `^(www\.)?(vimeo\.com)$`
- **DNS / SSRF Resolution:** Resolve target hostname to IP before socket connection; reject loopback (`127.0.0.0/8`), RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and link-local (`169.254.0.0/16`).

#### B. Dynamic Disk Space Governance
- Query metadata first via `video_downloader` in `metadata_only` mode.
- Calculate minimum required free bytes:
  $$\text{Required Space} = (\text{Estimated Size} \times 2.5) + 1.0\text{ GB safety margin}$$
- Inspect destination disk with `shutil.disk_usage()`; abort cleanly if capacity is insufficient.

#### C. Tool Orchestration & Execution
- Call `registry.ensure_discovered()`.
- Validate tool availability (`video_downloader.get_status() == ToolStatus.AVAILABLE`).
- Execute `video_downloader.execute({"url": url, "output_dir": str(temp_dir), "format": "video", "max_duration_seconds": max_duration})`.
- Handle flawed audio extraction: If `video_downloader` reports `audio_path=None` or a 0-byte file, trigger an explicit fallback audio extraction using FFmpeg CLI (`ffmpeg -y -i <video> -vn -acodec pcm_s16le -ar 16000 -ac 1 <audio>`).

#### D. Transcript Acquisition
- Execute `transcript_fetcher.execute({"url_or_video_id": url})`.
- If captions exist, format and save to `projects/<project-id>/source/transcript.json`.
- If no native captions exist, record `has_native_captions: false` in the manifest without crashing.

#### E. File Normalization & Artifact Contract
- Move/copy downloaded files to target project directory:
  - `projects/<project-id>/source/source_video.mp4`
  - `projects/<project-id>/source/source_audio.wav`
- Emit validated JSON `projects/<project-id>/source/source_manifest.json` conforming to the schema.

---

## 3. Step-by-Step Implementation Roadmap

```
Step 1: Environment Unblocking (Install FFmpeg + pip packages)
   │
   ▼
Step 2: Build `lib/url_ingest.py` (URL Intake Adapter)
   │
   ▼
Step 3: Build Comprehensive Unit Test Suite (`tests/unit/test_url_ingest.py`)
   │
   ▼
Step 4: Pipeline Declarations (`pipeline_defs/clip-factory.yaml` & `idea-director.md`)
   │
   ▼
Step 5: Contract & Integration Testing (Pytest verification)
   │
   ▼
Step 6: Live Smoke Test with Short Public-Domain Video & FFprobe Validation
   │
   ▼
Step 7: Final Milestone 1 Completion Report
```

---

## 4. Test Strategy & Quality Gates

### 4.1 Unit Tests (`tests/unit/test_url_ingest.py`)
- `test_valid_url_schemes()`: YouTube, Shorts, youtu.be accepted.
- `test_invalid_url_schemes()`: `file://`, `ftp://`, invalid protocols rejected.
- `test_ssrf_blocking()`: Loopback and private subnets raise security error.
- `test_disk_space_guard()`: Insufficient disk space triggers graceful abort.
- `test_tool_execution_contract()`: Mocked `video_downloader` ToolResult processed correctly.
- `test_audio_fallback_trigger()`: Missing audio triggers FFmpeg extraction fallback.
- `test_source_manifest_generation()`: Output JSON validates schema.

### 4.2 Integration & Smoke Test
- Run `lib/url_ingest.py` against a known short, legal video.
- Run `ffprobe` to verify `source_video.mp4` and `source_audio.wav` streams.
- Execute `lib/source_media_review.py:review_source_media()` against the generated source video to prove end-to-end compatibility with OpenMontage.

---

## 5. Explicitly Out of Scope for Milestone 1
- Clip candidate ranking algorithms (Milestone 2).
- Local faster-whisper neural transcription (Milestone 2).
- Face detection / active speaker 9:16 reframing (Milestone 3).
- Word-level animated subtitle styling (Milestone 4).
- Social platform auto-publishing (Milestone 5).

---

## 6. User Decision & Authorization Gate

To begin implementation, we require user authorization for:
1. **Unblocking Environment:**
   - Install `ffmpeg` via `winget install Gyan.FFmpeg` (or user installs manually).
   - Install `yt-dlp` and `youtube-transcript-api` in `.venv`.
2. **Proceeding with Step 1 through Step 7 of the implementation plan.**
