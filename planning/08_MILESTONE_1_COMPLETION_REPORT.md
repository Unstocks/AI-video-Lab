# OPENMONTAGE URL INTAKE INTEGRATION — MILESTONE 1 MASTER COMPLETION REPORT

**Project:** AI Video Lab (`C:\AI-Video-Lab`)  
**Pipeline:** `clip-factory` (Multi-clip extraction from long-form content)  
**Milestone:** 1 — URL Ingestion & Source Media Acquisition  
**Date:** November 16, 2026  
**Status:** COMPLETE (All Acceptance Criteria Passed)  

---

# REPORT A — IMPLEMENTATION & ARCHITECTURE

## 1. Files Created and Modified

### 1.1 Files Created (New Additions Only)
- **`lib/url_ingest.py`**: The URL Intake Adapter module. Provides `URLIntakeAdapter` class encapsulating scheme validation, SSRF defense, disk headroom calculation, media acquisition via `VideoDownloader`, explicit container remuxing via FFmpeg, audio extraction fallback, native caption extraction via `TranscriptFetcher`, source manifest emission, and seamless handoff to `lib/source_media_review.py`.
- **`tests/unit/test_url_ingest.py`**: Comprehensive 12-test unit test suite covering project ID security, URL schemes, domain filtering, SSRF blocking (loopback, private subnets, link-local, IPv4/IPv6), disk space limits, container remuxing, audio fallback, end-to-end mocked tool flow, and handoff to `source_media_review`.
- **`tests/qa/test_url_intake_smoke.py`**: Real-world smoke test script ingesting actual video (`https://www.youtube.com/watch?v=jNQXAC9IVRw`), validating container and audio with FFprobe, and running `lib.source_media_review`.

### 1.2 Files Modified (Minimal Manifest & Skill Configuration)
- **`pipeline_defs/clip-factory.yaml`**: Added `video_downloader` and `transcript_fetcher` to the `idea` stage’s `tools_available` list. Validated against `schemas/pipelines/pipeline_manifest.schema.json`.
- **`skills/pipelines/clip-factory/idea-director.md`**: Added `### Source Acquisition Protocol (Remote Video URL vs Local Media)` instructing the agent on how to invoke `lib/url_ingest.py` and pass `source_video.mp4` to `source_media_review` before planning clips.

### 1.3 Upstream Core Modules Preserved 100% Untouched
- `lib/source_media_review.py` (0 lines changed)
- `tools/base_tool.py` (0 lines changed)
- `tools/analysis/video_downloader.py` (0 lines changed)
- `tools/analysis/transcript_fetcher.py` (0 lines changed)
- `tools/tool_registry.py` (0 lines changed)
- `lib/checkpoint.py` (0 lines changed)

---

## 2. Architecture & Data Flow

```
                                  [ User Input: Video URL ]
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │    lib/url_ingest.py          │
                             │    (URL Intake Adapter)       │
                             └───────────────┬───────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
       [ Validated HTTPS Protocol ]                  [ Dynamic Disk Space Check ]
       [ Anti-SSRF IP Validation  ]                  [ (Est*2.5) + 1.0 GB Free  ]
                      │                                             │
                      └──────────────────────┬──────────────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  tools/analysis/              │
                             │  video_downloader.py          │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  Staging Directory Isolation  │
                             │  .staging_<uuid>/             │
                             └───────────────┬───────────────┘
                                             │
                      ┌──────────────────────┴──────────────────────┐
                      ▼                                             ▼
         [ FFprobe Container Check ]                   [ Audio Track Validation ]
         [ Explicit Remux -> MP4   ]                   [ FFmpeg Fallback -> WAV ]
                      │                                             │
                      └──────────────────────┬──────────────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │  tools/analysis/              │
                             │  transcript_fetcher.py        │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             [ Native Captions: transcript.json ]
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │    Atomic Materialization     │
                             │  projects/<id>/source/        │
                             │   ├── source_video.mp4        │
                             │   ├── source_audio.wav        │
                             │   ├── transcript.json         │
                             │   └── source_manifest.json    │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │    lib/source_media_review.py │  <-- 100% UNTOUCHED
                             │    (Probes source_video.mp4)  │
                             └───────────────┬───────────────┘
                                             │
                                             ▼
                             ┌───────────────────────────────┐
                             │    pipeline_defs/             │
                             │    clip-factory.yaml          │
                             │    (idea -> script -> ...)    │
                             └───────────────────────────────┘
```

---

## 3. Actual Contracts Verified

1. **`ToolRegistry` Discovery Contract**:
   `registry.ensure_discovered()` must be invoked before calling `registry.get()`. Both `video_downloader` and `transcript_fetcher` return `ToolStatus.AVAILABLE` once packages and binaries are resolvable.
2. **`BaseTool.execute(inputs: dict) -> ToolResult`**:
   `video_downloader.execute({"url": url, "output_dir": staging_dir, "format": "video", "max_duration_seconds": 3600})` returns `ToolResult(success=True, data={"video_path": ..., "audio_path": ..., "metadata": ...})`.
3. **Audio Extraction Silent Failure Fixed via Adapter**:
   `video_downloader.py` line 298 silently swallows audio extraction errors. `URLIntakeAdapter` inspects `audio_path`, validates audio streams via FFprobe, and triggers explicit fallback extraction via FFmpeg (`-vn -acodec pcm_s16le -ar 16000 -ac 1`) if missing or corrupt.
4. **Container Normalization Contract**:
   Never renames arbitrary containers to `.mp4`. Probes input with `ffprobe`. If container is MKV or WebM, remuxes with `-c copy -movflags +faststart` (or re-encodes to H.264/AAC if streams are incompatible).
5. **Manifest Compatibility Contract**:
   `pipeline_defs/clip-factory.yaml` validates cleanly against `schemas/pipelines/pipeline_manifest.schema.json`.

---

## 4. Integration Evidence & Pipeline Invocation

In OpenMontage's agentic execution model, the Stage Director skill (`skills/pipelines/clip-factory/idea-director.md`) instructs the agent:
```python
from lib.url_ingest import URLIntakeAdapter

adapter = URLIntakeAdapter()
result = adapter.ingest_url(url, project_id, max_duration_seconds=3600)
review_artifact = adapter.review_ingested_media(result)
```
The agent executes this contract, materializing the source files and passing the resulting `source_video.mp4` to `source_media_review.review_source_media()`. The output `source_media_review` artifact is then consumed by the `idea` stage to create the clip extraction `brief`.

---

## 5. Dependency & Environment Changes

- **Host Binaries**: Configured official GyanD FFmpeg 7.1 Essentials (`ffmpeg.exe`, `ffprobe.exe`, `ffplay.exe`) under `C:\AI-Video-Lab\.runtime\tools\bin\` and `C:\AI-Video-Lab\.venv\Scripts\`, and added to User PATH. Verified via `ffmpeg -version` and `ffprobe -version`.
- **Python Packages**: Installed `yt-dlp` (`2026.10.26`), `youtube-transcript-api` (`1.2.5`), `defusedxml` (`0.7.1`), and `imageio-ffmpeg` (`0.8.1`) into `.venv`.

---

## 6. Known Limitations (Milestone 1 Scope)

1. **Domain Whitelist**: Restricts input URLs to YouTube and Vimeo. Additional platforms (TikTok, Instagram, Google Drive) deferred to future iterations.
2. **Native Captions Only**: Transcripts are fetched via YouTube/Vimeo caption APIs. Non-captioned videos record `has_native_captions: false` and defer local neural transcription to Milestone 2 (`faster-whisper`).
3. **Single Aspect Ratio Source**: Ingests original source aspect ratio. Vertical 9:16 reframing and active speaker tracking are deferred to Milestone 3.

---

# REPORT B — TESTING & MILESTONE ACCEPTANCE

## 1. Test Commands and Exact Results

### 1.1 Unit Test Suite (`tests/unit/test_url_ingest.py`)
**Command:**
```powershell
& C:\AI-Video-Lab\.venv\Scripts\python.exe -m pytest tests/unit/test_url_ingest.py -v
```
**Results:** **12 passed in 6.39s**
- `test_validate_project_id_valid` -> **PASSED**
- `test_validate_project_id_invalid` -> **PASSED**
- `test_validate_url_schemes` -> **PASSED**
- `test_validate_url_domains` -> **PASSED**
- `test_validate_url_ssrf_blocking` -> **PASSED**
- `test_check_disk_headroom_sufficient` -> **PASSED**
- `test_check_disk_headroom_insufficient` -> **PASSED**
- `test_ensure_valid_mp4` -> **PASSED**
- `test_ensure_valid_mp4_remux_from_mkv` -> **PASSED**
- `test_extract_audio_fallback` -> **PASSED**
- `test_ingest_url_full_flow` -> **PASSED**
- `test_handoff_to_source_media_review` -> **PASSED**

### 1.2 Pipeline Manifest Schema Validation
**Command:**
```powershell
& C:\AI-Video-Lab\.venv\Scripts\python.exe -c "import yaml, json, jsonschema; from pathlib import Path; schema = json.loads(Path('schemas/pipelines/pipeline_manifest.schema.json').read_text(encoding='utf-8')); manifest = yaml.safe_load(Path('pipeline_defs/clip-factory.yaml').read_text(encoding='utf-8')); jsonschema.validate(instance=manifest, schema=schema); print('Manifest schema validation: PASSED')"
```
**Results:** **Manifest schema validation: PASSED**

### 1.3 Contract Test Regression Check
**Command:**
```powershell
& C:\AI-Video-Lab\.venv\Scripts\python.exe -m pytest tests/contracts/test_seedance_ark_video.py
```
**Results:** **46 passed in 1.30s** (Unblocked by FFprobe availability)

---

## 2. Real Smoke-Test Evidence

**Command:**
```powershell
& C:\AI-Video-Lab\.venv\Scripts\python.exe tests/qa/test_url_intake_smoke.py
```
**Target URL:** `https://www.youtube.com/watch?v=jNQXAC9IVRw` (First video on YouTube, 19.021s)  
**Execution Log:**
```text
[1/5] Ingesting URL: https://www.youtube.com/watch?v=jNQXAC9IVRw -> project: smoke-test-milestone1
[download] 100% of 218.53KiB in 00:00:00 at 504.60KiB/s
[download] 100% of 246.27KiB in 00:00:00 at 293.02KiB/s

[2/5] Ingest successful:
  - Video path: C:\AI-Video-Lab\projects\smoke-test-milestone1\source\source_video.mp4
  - Audio path: C:\AI-Video-Lab\projects\smoke-test-milestone1\source\source_audio.wav
  - Transcript path: C:\AI-Video-Lab\projects\smoke-test-milestone1\source\transcript.json
  - Manifest path: C:\AI-Video-Lab\projects\smoke-test-milestone1\source\source_manifest.json
  - Duration: 19.021s
  - Resolution: (320, 240)
  - FPS: 15.0
  - Native captions: True

[3/5] Validating video container with ffprobe...
  -> Video stream verified valid.

[4/5] Validating audio file with ffprobe...
  -> Audio stream verified valid.

[5/5] Validating source_manifest.json and running source_media_review...
  -> Manifest contents verified.
  -> source_media_review executed successfully.
  -> Reviewed files count: 1
  -> File summary: Video file: 19.0s at 320x240, with audio

ALL SMOKE TEST VERIFICATIONS PASSED!
```

---

## 3. FFprobe Validation Details

### Video Stream (`source_video.mp4`):
```json
{
  "codec_name": "av1",
  "codec_type": "video",
  "width": 320,
  "height": 240,
  "r_frame_rate": "15/1",
  "avg_frame_rate": "15/1",
  "duration": "19.021000",
  "bit_rate": "92014"
}
```

### Audio Stream (`source_audio.wav`):
```json
{
  "codec_name": "pcm_s16le",
  "codec_type": "audio",
  "sample_rate": "16000",
  "channels": 1,
  "channel_layout": "mono",
  "duration": "19.021000",
  "bits_per_sample": 16
}
```

---

## 4. Source Manifest Artifact Example

Generated at `projects/smoke-test-milestone1/source/source_manifest.json`:
```json
{
  "version": "1.0",
  "project_id": "smoke-test-milestone1",
  "source_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
  "acquired_at": "2026-11-16T17:26:48.232508+00:00",
  "duration_seconds": 19.021,
  "resolution": [320, 240],
  "fps": 15.0,
  "video_codec": "av1",
  "audio_codec": "pcm_s16le",
  "sample_rate": 16000,
  "channels": 1,
  "file_size_bytes": 475973,
  "has_native_captions": true,
  "video_path": "C:\\AI-Video-Lab\\projects\\smoke-test-milestone1\\source\\source_video.mp4",
  "audio_path": "C:\\AI-Video-Lab\\projects\\smoke-test-milestone1\\source\\source_audio.wav",
  "transcript_path": "C:\\AI-Video-Lab\\projects\\smoke-test-milestone1\\source\\transcript.json",
  "metadata": {
    "title": "Me at the zoo",
    "duration": 19,
    "uploader": "jawed",
    "upload_date": "20050424",
    "view_count": 448684902,
    "resolution": "320x240",
    "fps": 15
  }
}
```

---

## 5. Git Diff & Repository Integrity

`git status` confirms:
- **Modified files:**
  - `pipeline_defs/clip-factory.yaml` (+2 lines in `idea.tools_available`)
  - `skills/pipelines/clip-factory/idea-director.md` (+23 lines in `Source Acquisition Protocol`)
- **Untracked files:**
  - `lib/url_ingest.py`
  - `tests/unit/test_url_ingest.py`
  - `tests/qa/test_url_intake_smoke.py`
  - `planning/`
- Zero upstream core files touched. Upstream git history pristine.

---

## 6. Milestone 1 Acceptance Criteria Checklist

| Acceptance Criterion | Result | Evidence |
| :--- | :---: | :--- |
| **URL Parsing & Protocol Validation** | **PASS** | Rejects `file://`, `ftp://`, accepts `http://`, `https://` (`test_validate_url_schemes`) |
| **Domain Whitelisting** | **PASS** | Restricts to YouTube/Vimeo (`test_validate_url_domains`) |
| **SSRF & Private Network Defense** | **PASS** | Blocks loopback, RFC 1918, link-local, IPv4/IPv6 (`test_validate_url_ssrf_blocking`) |
| **Project ID Sanitization** | **PASS** | Blocks `../traversal`, path separators (`test_validate_project_id_invalid`) |
| **Dynamic Disk Space Protection** | **PASS** | Enforces $(\text{est} \times 2.5) + 1.0\text{ GB}$ headroom (`test_check_disk_headroom_insufficient`) |
| **ToolRegistry Discovery & Contracts** | **PASS** | Invokes `video_downloader` and `transcript_fetcher` via `.execute()` |
| **Container Remuxing (Never Blind Rename)** | **PASS** | FFprobe container inspection + FFmpeg remux (`test_ensure_valid_mp4_remux_from_mkv`) |
| **Audio Verification & FFmpeg Fallback** | **PASS** | Detects missing audio, extracts 16kHz mono WAV (`test_extract_audio_fallback`) |
| **Native Caption Acquisition** | **PASS** | Captures timestamped snippets into `transcript.json` (`test_ingest_url_full_flow`) |
| **Source Manifest Generation** | **PASS** | Emits schema-compliant `source_manifest.json` (`test_ingest_url_full_flow`) |
| **Clean Handoff to Source Media Review** | **PASS** | Executes `review_source_media()` against acquired media (`test_handoff_to_source_media_review`) |
| **Real Short-Video Smoke Test** | **PASS** | Ingested `jNQXAC9IVRw` (19s), verified streams, verified review artifact |
| **Upstream Codebase Preservation** | **PASS** | 0 lines modified in `source_media_review.py` or `base_tool.py` |

---

## 7. Rollback Instructions

To roll back Milestone 1 completely:
```bash
git checkout pipeline_defs/clip-factory.yaml skills/pipelines/clip-factory/idea-director.md
rm -rf lib/url_ingest.py tests/unit/test_url_ingest.py tests/qa/test_url_intake_smoke.py
```
Total rollback time: < 15 seconds. Zero disruption to existing engine capabilities.

---

## 8. Binding Completion Status

**MILESTONE 1 IS FULLY COMPLETE.**

Per instructions, execution has halted. Milestone 2 (Clip Candidate Discovery & Scoring) will not commence without separate authorization.
