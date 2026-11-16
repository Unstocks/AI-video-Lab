# PART 1: EXISTING OPENMONTAGE CAPABILITY AUDIT
## Forensic Deep Dive into Installed OpenMontage Source Code for URL-to-Clips Automation

**Workspace:** `C:\AI-Video-Lab`  
**Repository Upstream:** `https://github.com/OpenMontageInc/OpenMontage.git`  
**Git Branch & Commit:** `main` @ `2e003e65fa99a0f329478a2c1cdcf26bc481933a`  
**Audit Date:** 2026-11-16  

---

## 1. Executive Summary & Core Findings

OpenMontage is an **instruction-driven, agent-first video production platform**. Python in this codebase exists strictly for **tool execution, file persistence, and local validation**, while all high-level orchestration, editorial judgment, hook scoring, stage transitions, and human review gates live in YAML manifests and Markdown director skills.

### Key Forensic Discoveries:
1. **URL Downloading Exists, But Disconnected from Clipping:**
   - `tools/analysis/video_downloader.py` provides a production-grade wrapper around `yt_dlp.YoutubeDL`. It extracts metadata, downloads 720p/1080p video, extracts 16kHz WAV audio, and fetches subtitles.
   - However, `video_downloader` was authored exclusively for **Reference Video Analysis** (`skills/meta/video-reference-analyst.md` — *"make me a video like this"*).
   - In contrast, the multi-clip production pipeline (`clip-factory`) is classified as a **Footage-Led** pipeline. Its manifest (`pipeline_defs/clip-factory.yaml`) only permits `source_media_review` in the intake stage, which strictly expects local file paths on disk.
2. **Dedicated Multi-Clip Extraction Pipeline Exists:**
   - `pipeline_defs/clip-factory.yaml` and its 8 director skills (`skills/pipelines/clip-factory/`) are fully realized. They define the exact workflow to mine long-form content (webinars, streams, podcasts) for $N$ independent short-form social deliverables.
3. **Moment Selection is 100% Agent-Driven:**
   - There is no algorithmic ranking heuristic or ML scoring model in Python. The AI agent inspects word-level timestamps from `transcriber.py` (Whisper), evaluates 5 criteria (`hook`, `coherence`, `value`, `energy`, `platform_fit`), subjects them to the **Standalone Test**, and stores candidate clips in `script.metadata["candidate_clips"]`.
4. **Trimming & Subtitles are Production-Ready:**
   - `tools/video/video_trimmer.py` executes microsecond-accurate cuts using FFmpeg (`codec="libx264"`).
   - `tools/subtitle/subtitle_gen.py` is a pure-Python module producing `.srt`, `.vtt`, and JSON cues with karaoke/word-by-word highlights.
5. **Living Storyboard Server Operates Independently:**
   - `backlot/server.py` is a lightweight, read-only FastAPI service that watches `projects/` and renders real-time previews, thumbnails, and human approval gates on port `4750`.
6. **Immediate System & Environment Blockers:**
   - `ffmpeg` and `ffprobe` are missing from the host machine's `PATH`.
   - Core Python dependencies (`requirements.txt`) are installed in `.venv` (Python `3.14.10`), but media processing packages (`yt-dlp`, `faster-whisper`, `scenedetect`, `mediapipe`) have not been installed yet.

---

## 2. Directory & Module Inventory

| Directory / File | Type | Architectural Responsibility |
| :--- | :--- | :--- |
| `pipeline_defs/clip-factory.yaml` | YAML Manifest | Declarative pipeline definition for multi-clip extraction. |
| `pipeline_defs/podcast-repurpose.yaml` | YAML Manifest | Declarative pipeline definition for podcast-to-video repurposing. |
| `skills/pipelines/clip-factory/` | Markdown Skills | 8 Stage Director skills governing the agent through Idea $\rightarrow$ Publish. |
| `skills/meta/video-reference-analyst.md`| Meta Skill | Protocol for analyzing external reference video URLs. |
| `lib/source_media_review.py` | Python Engine | Media intake probe; runs `audio_probe`, `frame_sampler`, `transcriber`. |
| `lib/media_profiles.py` | Python Specs | Platform specifications (`youtube_shorts`, `instagram_reels`, `tiktok`). |
| `lib/checkpoint.py` | Python Engine | State machine persistence; reads and writes `checkpoint.json`. |
| `tools/analysis/video_downloader.py` | Python BaseTool | Media downloading from YouTube, Shorts, TikTok, Reels via `yt-dlp`. |
| `tools/analysis/transcript_fetcher.py`| Python BaseTool | Zero-compute YouTube transcript fetcher via `youtube-transcript-api`. |
| `tools/analysis/transcriber.py` | Python BaseTool | Local STT with word-level timestamps via `faster-whisper` / `whisperx`. |
| `tools/analysis/audio_energy.py` | Python BaseTool | Loudness profiling via FFmpeg `ebur128` to detect peak energy windows. |
| `tools/video/video_trimmer.py` | Python BaseTool | FFmpeg frame-accurate cutting, trimming, speed adjustment, and concat. |
| `tools/video/auto_reframe.py` | Python BaseTool | 16:9 to 9:16 aspect ratio conversion with MediaPipe face tracking. |
| `tools/video/silence_cutter.py` | Python BaseTool | Jump cuts and dead-air removal via FFmpeg `silencedetect`. |
| `tools/subtitle/subtitle_gen.py` | Python BaseTool | Pure-Python generator for SRT, VTT, and JSON word-highlight cues. |
| `tools/video/video_compose.py` | Python BaseTool | Master composition orchestrator; delegates to Remotion or FFmpeg. |
| `backlot/server.py` | FastAPI Server | Living storyboard web server; SSE events, media streaming, thumbnails. |
| `backlot/state.py` | Python Engine | Read-only board state derivation and media scanner for `projects/`. |

---

## 3. Detailed Trace: URL Ingestion vs. Local Footage Ingestion

### A. The Reference Video Ingestion Path (`tools/analysis/video_downloader.py`)
- **Class:** `VideoDownloader(BaseTool)`
- **Runtime:** `ToolRuntime.LOCAL` (Tier: `SOURCE`, Provider: `yt-dlp`)
- **Platform Regexes (`_detect_platform` lines 136–151):**
  - YouTube: `youtube.com`, `youtu.be`
  - Shorts: `youtube.com/shorts`
  - Instagram: `instagram.com`
  - TikTok: `tiktok.com`
  - Vimeo: `vimeo.com`
  - Twitter/X: `twitter.com`, `x.com`
- **Execution Flow (`execute` lines 181–256):**
  1. Calls `_extract_metadata()` with `skip_download=True`. Queries title, duration, uploader, view count, resolution, and fps.
  2. Enforces duration safety: Rejects videos exceeding `max_duration_seconds` (default: 600s / 10 minutes).
  3. Calls `_download_video()` (line 258):
     - Sets `format: "bestvideo[height<=720]+bestaudio/best[height<=720]/best"`.
     - Merges output into `reference_video.mp4` using `outtmpl`.
     - Executes FFmpeg sub-command (lines 286–295) to extract `reference_audio.wav` at 16kHz mono (`-acodec pcm_s16le -ar 16000 -ac 1`) specifically formatted for speech recognizers.
- **Architectural Isolation:** `video_downloader` is not declared in `pipeline_defs/clip-factory.yaml` or `pipeline_defs/podcast-repurpose.yaml`. It is only referenced under `reference_video.analysis_tools` in `cinematic.yaml`, `animation.yaml`, and `animated-explainer.yaml`.

### B. The Local Media Intake Path (`lib/source_media_review.py`)
- **Entry Point:** `review_source_media(files: list[Path], context: dict, tool_registry)` (line 234)
- **Supported File Types (lines 24–27):**
  - Video: `.mp4`, `.mov`, `.webm`, `.avi`, `.mkv`, `.m4v`
  - Audio: `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.m4a`, `.opus`
  - Images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`, `.svg`
- **Execution Sequence:**
  1. Identifies file type by extension.
  2. Executes `ffprobe` (lines 64–85) to extract duration, resolution (`width x height`), fps, video codec, audio codec, sample rate, audio channels, and bitrate.
  3. Calls `frame_sampler` (lines 92–116) to capture 4 representative frames across the timeline.
  4. Flags quality risks: Low resolution (<720x480), mono audio, or short duration (<3s).
  5. Produces canonical `source_media_review.json` artifact conforming to `schemas/artifacts/source_media_review.schema.json`.
- **Limitation:** Does not accept string URLs (`http://`, `https://`). If passed a URL, `Path(url).suffix` fails to classify the media, leading to unhandled intake errors.

---

## 4. Deep Inspection: The Clip Factory Pipeline (`clip-factory`)

```
STAGE 1: idea
├── Skill: skills/pipelines/clip-factory/idea-director.md
├── Input: optional source_media_review.json
├── Output: brief.json, decision_log.json
├── Human Approval Gate: REQUIRED (human_approval_default: true)
└── Key Rule: Establish target yield (e.g. 5-10 clips) and 9:16 platform mix.

STAGE 2: script
├── Skill: skills/pipelines/clip-factory/script-director.md
├── Input: brief.json
├── Output: script.json
├── Required Tools: transcriber (faster-whisper)
├── Optional Tools: scene_detect (FFmpeg / PySceneDetect)
├── Human Approval Gate: REQUIRED (human_approval_default: true)
└── Key Rule: Full transcript generation -> 5-aspect candidate moment scoring
              -> Standalone Test validation -> Store candidate clips in metadata.

STAGE 3: scene_plan
├── Skill: skills/pipelines/clip-factory/scene-director.md
├── Input: script.json, brief.json
├── Output: scene_plan.json
├── Tools Available: frame_sampler
├── Human Approval Gate: REQUIRED (human_approval_default: true)
└── Key Rule: Plan 9:16 layout, top hook safe zone, center speaker zone,
              bottom subtitle safe zone. Note auto_reframe requirements.

STAGE 4: assets
├── Skill: skills/pipelines/clip-factory/asset-director.md
├── Input: scene_plan.json, script.json
├── Output: asset_manifest.json
├── Required Tools: subtitle_gen
├── Optional Tools: audio_enhance
├── Human Approval Gate: REQUIRED (human_approval_default: true)
└── Key Rule: Generate per-clip SRT/VTT subtitles with word timestamps;
              prepare hook cards and branding lower-thirds.

STAGE 5: edit
├── Skill: skills/pipelines/clip-factory/edit-director.md
├── Input: scene_plan.json, asset_manifest.json, script.json
├── Output: edit_decisions.json
├── Tools Available: silence_cutter (jump cuts)
├── Human Approval Gate: AUTOMATIC (human_approval_default: false)
└── Key Rule: First 2-3s hook optimization; trim trailing pauses; clean boundaries.

STAGE 6: compose
├── Skill: skills/pipelines/clip-factory/compose-director.md
├── Input: edit_decisions.json, asset_manifest.json
├── Output: render_report.json, final_review.json
├── Required Tools: video_compose, video_trimmer, audio_mixer
├── Optional Tools: audio_enhance, color_grade
├── Human Approval Gate: AUTOMATIC (human_approval_default: false)
└── Key Rule: Execute FFmpeg frame-accurate cuts for each clip; burn subtitles;
              verify resolution, duration, audio levels; record in render_report.

STAGE 7: publish
├── Skill: skills/pipelines/clip-factory/publish-director.md
├── Input: render_report.json, final_review.json
├── Output: publish_log.json
├── Human Approval Gate: REQUIRED (human_approval_default: true)
└── Key Rule: Generate platform-specific titles, hooks, descriptions, hashtags;
              organize final deliverables in export package.
```

---

## 5. Tool Evaluation & Status Matrix

| Tool Name | File Path | Status | Missing Requirement | Functionality in Clipping Workflow |
| :--- | :--- | :--- | :--- | :--- |
| **`video_downloader`** | `tools/analysis/video_downloader.py` | Unavailable | `yt-dlp` package, `ffmpeg` binary | Downloads YouTube video & extracts 16kHz WAV audio. |
| **`transcript_fetcher`**| `tools/analysis/transcript_fetcher.py` | Unavailable | `youtube-transcript-api` package | Instant YouTube transcript extraction without video download. |
| **`transcriber`** | `tools/analysis/transcriber.py` | Unavailable | `faster-whisper` package | Transcribes audio with exact word-level timestamps. |
| **`audio_energy`** | `tools/analysis/audio_energy.py` | Unavailable | `ffmpeg` binary | Detects peak energy and loudness changes via `ebur128`. |
| **`scene_detect`** | `tools/analysis/scene_detect.py` | Unavailable | `ffmpeg` binary, `scenedetect` package | Detects shot boundaries to avoid visual cuts mid-sentence. |
| **`frame_sampler`** | `tools/analysis/frame_sampler.py` | Unavailable | `ffmpeg` binary | Extracts keyframes for visual layout inspection. |
| **`auto_reframe`** | `tools/video/auto_reframe.py` | Unavailable | `ffmpeg` binary, `mediapipe` package | Smooths face trajectory and crops 16:9 to 9:16 vertical. |
| **`silence_cutter`** | `tools/video/silence_cutter.py` | Unavailable | `ffmpeg` binary | Automatically removes pauses and dead air (jump-cut edits). |
| **`video_trimmer`** | `tools/video/video_trimmer.py` | Unavailable | `ffmpeg` binary | Frame-accurate cut (`libx264`), speed adjust, and concat. |
| **`subtitle_gen`** | `tools/subtitle/subtitle_gen.py` | **AVAILABLE** | None (Pure Python) | Produces SRT, VTT, and JSON word-highlight cues. |
| **`video_compose`** | `tools/video/video_compose.py` | Unavailable | `ffmpeg` binary, Node Remotion deps | Burns captions and renders final MP4 files. |

---

## 6. Backlot Living Storyboard Integration

- **Server Architecture (`backlot/server.py`):**
  - Runs on FastAPI using an asynchronous lifespan context.
  - Watches `projects/` using `watchfiles`. When files change, it pushes real-time Server-Sent Events (SSE) to browser clients via `/api/project/{id}/events`.
- **Media Serving & Thumbnails (`backlot/server.py` lines 253–286):**
  - `/media/{project_id}/{file_path}`: Serves video files with complete HTTP range-request support (`206 Partial Content`), enabling fluid scrubbing in browser players.
  - `/thumb/{project_id}/{file_path}`: Generates cached JPEG poster frames on disk (`THUMB_WIDTHS = (320, 640, 960)`) using PIL.
- **Media Scanner (`backlot/state.py` lines 513–546):**
  - Automatically discovers deliverables in `projects/<id>/renders/` and `.mp4` files at project root.
  - Generates the UI dashboard (`http://127.0.0.1:4750/p/<project_id>`) where candidate clips are displayed side-by-side with transcripts, hook text, and approve/reject controls.

---

## 7. Audit Conclusions

1. **OpenMontage already contains all necessary tools to cut videos, generate captions, and present clips.**
2. **The gap is architectural orchestration, not missing code:** `video_downloader` was never connected to `clip-factory.yaml` because the author separated "Reference Video Analysis" from "Local Footage Editing".
3. **The environment must be unblocked:** Adding `ffmpeg`/`ffprobe` to PATH and installing `yt-dlp` + `faster-whisper` in `.venv` immediately activates the dormant tools.
