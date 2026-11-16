# PART 3: EXECUTION-READY IMPLEMENTATION ROADMAP
## Engineering Blueprint, Surgical Code Changes, Phased Milestones & MVP Specifications

**Workspace:** `C:\AI-Video-Lab`  
**Execution Target:** URL-to-Clips Automation via OpenMontage Architecture  
**Date:** 2026-11-16  

---

## 1. Capability Inventory & Readiness Baseline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       OPENMONTAGE CAPABILITY STATUS                         │
│                                                                             │
│  [VERIFIED & READY]                                                         │
│  ├── Subtitle Generation (tools/subtitle/subtitle_gen.py)                   │
│  ├── Checkpoint Persistence (lib/checkpoint.py)                             │
│  ├── Pipeline Loader (lib/pipeline_loader.py)                               │
│  └── Backlot Storyboard & Media Streaming (backlot/server.py)               │
│                                                                             │
│  [IMPLEMENTED IN CODE — BLOCKED BY HOST ENVIRONMENT]                         │
│  ├── URL Downloader (tools/analysis/video_downloader.py -> needs yt-dlp)    │
│  ├── Local Whisper STT (tools/analysis/transcriber.py -> needs faster-whisper)│
│  ├── Media Probe (lib/source_media_review.py -> needs ffprobe)              │
│  ├── Video Trimmer (tools/video/video_trimmer.py -> needs ffmpeg)          │
│  ├── Silence Cutter (tools/video/silence_cutter.py -> needs ffmpeg)         │
│  └── Audio Energy Profiler (tools/analysis/audio_energy.py -> needs ffmpeg) │
│                                                                             │
│  [IMPLEMENTED IN TOOLS — UNINTEGRATED IN CLIP FACTORY MANIFEST]             │
│  ├── video_downloader (Absent from pipeline_defs/clip-factory.yaml)         │
│  ├── transcript_fetcher (Absent from pipeline_defs/clip-factory.yaml)      │
│  └── auto_reframe (Present in tools, only wired into talking-head.yaml)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Target System Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Intake ["1. INTAKE & URL MATERIALIZATION"]
        URL["Video URL (YouTube/Shorts/Podcast)"] --> IsURL{"Is Source a URL?"}
        IsURL -->|Yes| DL["VideoDownloader (yt-dlp)"]
        IsURL -->|No (Local File)| Direct["Local MP4 File"]
        DL --> MatFile["Materialize in: projects/<id>/source/source_video.mp4"]
        Direct --> MatFile
        MatFile --> SMR["lib/source_media_review.py (ffprobe + frame_sampler)"]
        SMR --> Brief["Artifact: brief.json (clip_count: 5-10, 9:16 target)"]
    end

    subgraph Intelligence ["2. TRANSCRIPTION & HOOK DISCOVERY"]
        Brief --> HasCaptions{"YouTube Captions Available?"}
        HasCaptions -->|Yes| FastSTT["TranscriptFetcher (Instant fetch)"]
        HasCaptions -->|No| Whisper["Transcriber (faster-whisper)"]
        FastSTT --> ScriptDirector["Script Director Agent (LLM)"]
        Whisper --> ScriptDirector
        MatFile -.-> Energy["AudioEnergy (ebur128 peak loudness)"] -.-> ScriptDirector
        ScriptDirector --> Evaluate["Score Candidates: Hook, Coherence, Value, Energy"]
        Evaluate --> Standalone["Apply Standalone Test (No dangling pronouns)"]
        Standalone --> ScriptArtifact["Artifact: script.json (Candidate Moments)"]
    end

    subgraph Assembly ["3. REFRAME, TRIM & CAPTION ASSEMBLY"]
        ScriptArtifact --> SceneDirector["Scene Director (Safe Zones & Framing Plan)"]
        SceneDirector --> SubGen["SubtitleGen (Karaoke/Word-by-Word SRT/VTT)"]
        SubGen --> Trim["VideoTrimmer (FFmpeg libx264 frame-accurate cut)"]
        Trim --> Silence["SilenceCutter (Optional jump-cut dead air removal)"]
        Silence --> Reframe["AutoReframe (MediaPipe Face Track -> 9:16 crop)"]
        Reframe --> Compose["VideoCompose (Burn captions onto 9:16 canvas)"]
        Compose --> Report["Artifact: render_report.json (Output Deliverables)"]
    end

    subgraph Review ["4. STORYBOARD REVIEW & EXPORT"]
        Report --> Backlot["Backlot Web Board (http://127.0.0.1:4750/p/<id>)"]
        Backlot --> UserReview{"Human Checkpoint Gate"}
        UserReview -->|Approved| Final["renders/clip_01.mp4 ... renders/clip_05.mp4"]
        UserReview -->|Rejected| Revision["Re-open Script Stage with Feedback"]
    end
```

---

## 3. Exact Surgical Code Changes (Diff-Ready Specification)

### Change 1: Update Pipeline Manifest (`pipeline_defs/clip-factory.yaml`)
**Goal:** Allow the agent to legally execute `video_downloader`, `transcript_fetcher`, `auto_reframe`, and `silence_cutter` inside `clip-factory`.

```yaml
# In pipeline_defs/clip-factory.yaml around line 46:
stages:
  - name: idea
    skill: pipelines/clip-factory/idea-director
    optional_artifacts_in:
      - source_media_review
    produces:
      - brief
      - decision_log
    # MODIFICATION: Add intake tools
    tools_available:
      - video_downloader
      - transcript_fetcher
    checkpoint_required: true
    human_approval_default: true

  # Around line 135 (edit stage):
  - name: edit
    skill: pipelines/clip-factory/edit-director
    required_artifacts_in:
      - scene_plan
      - asset_manifest
    produces:
      - edit_decisions
    # MODIFICATION: Add silence cutter for jump-cuts
    tools_available:
      - silence_cutter
    checkpoint_required: true
    human_approval_default: false

  # Around line 155 (compose stage):
  - name: compose
    skill: pipelines/clip-factory/compose-director
    required_tools:
      - video_compose
      - video_trimmer
      - audio_mixer
    # MODIFICATION: Add auto_reframe for vertical aspect conversion
    optional_tools:
      - audio_enhance
      - color_grade
      - auto_reframe
    tools_available:
      - video_compose
      - video_trimmer
      - audio_mixer
      - audio_enhance
      - color_grade
      - auto_reframe
```

---

### Change 2: Enhance Media Intake (`lib/source_media_review.py`)
**Goal:** Enable `review_source_media` to accept URL strings seamlessly, downloading the source media into the project directory before probing.

```python
# In lib/source_media_review.py around line 234:

def review_source_media(
    files: list[Path | str],   # Modified to accept strings (URLs)
    context: dict[str, Any],
    tool_registry: Any = None,
) -> dict[str, Any]:
    """Review user-supplied media files or URLs and produce a source_media_review artifact."""
    
    project_dir = Path(context.get("project_dir", "."))
    resolved_paths: list[Path] = []
    
    for item in files:
        item_str = str(item).strip()
        # If the item is an HTTP/HTTPS URL:
        if item_str.startswith(("http://", "https://", "www.")):
            logger.info("URL detected in source media: %s. Materializing...", item_str)
            source_dir = project_dir / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            
            # Invoke video_downloader via tool registry
            downloader = tool_registry.get("video_downloader")
            if downloader:
                dl_result = downloader.execute({
                    "url": item_str,
                    "output_dir": str(source_dir),
                    "max_resolution": "1080p",
                    "max_duration_seconds": 3600,  # 1 hour limit for clips
                })
                if dl_result.success and dl_result.data.get("video_path"):
                    resolved_paths.append(Path(dl_result.data["video_path"]))
                else:
                    logger.error("Download failed: %s", dl_result.error)
        else:
            resolved_paths.append(Path(item))
            
    # Continue existing probe logic using resolved_paths:
    # ...
```

---

### Change 3: Update Director Instructions
1. **`skills/pipelines/clip-factory/idea-director.md`:**
   - Add instructions for intake: If the user passes a URL, run `video_downloader` (or let `source_media_review` materialize it). Confirm the target clip count (default: 5 clips) and platform ratio (default: 9:16 vertical).
2. **`skills/pipelines/clip-factory/scene-director.md`:**
   - Update line 28: Direct the agent to specify `auto_reframe` with `target_aspect: "portrait"` in the scene plan to ensure smooth face-centered cropping.

---

## 4. Phased Implementation Roadmap

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            EXECUTION MILESTONES                             │
│                                                                             │
│  [MILESTONE 1: Environment & Media Foundation]                              │
│  ├── Install FFmpeg and FFprobe binaries on Windows PATH                    │
│  └── Install yt-dlp, faster-whisper, youtube-transcript-api in .venv       │
│  └── Acceptance: ffmpeg -version works; python imports pass without error   │
│                                                                             │
│  [MILESTONE 2: Local Video Clipping Smoke Test]                             │
│  ├── Drop 2-minute test MP4 into projects/_smoke_test/                      │
│  ├── Transcribe with word timestamps via transcriber.py                     │
│  ├── Generate SRT via subtitle_gen.py                                       │
│  ├── Execute frame-accurate cut via video_trimmer.py                        │
│  └── Acceptance: Standalone short clip plays in Backlot UI                  │
│                                                                             │
│  [MILESTONE 3: Pipeline Integration & URL Intake Bridge]                    │
│  ├── Apply manifest update to pipeline_defs/clip-factory.yaml               │
│  ├── Apply URL handler update to lib/source_media_review.py                 │
│  ├── Pass a test YouTube URL to clip-factory pipeline                       │
│  └── Acceptance: Agent acquires video, scores moments, extracts 3 clips     │
│                                                                             │
│  [MILESTONE 4: Auto-Reframing & Subtitle Polish]                            │
│  ├── Install mediapipe & opencv-python in .venv                             │
│  ├── Verify auto_reframe.py face tracking on 16:9 interview footage         │
│  ├── Validate 9:16 portrait export with burned captions                     │
│  └── Acceptance: Backlot renders 9:16 clips with centered speakers          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Milestone Breakdown:

#### Milestone 1: Environment & Media Foundation
- **Goal:** Equip the existing runtime with the executables and libraries required by OpenMontage’s tools without touching source code.
- **Actions:**
  1. Make `ffmpeg.exe` and `ffprobe.exe` available on Windows PATH (e.g. `scoop install ffmpeg` or placing binaries in `C:\tools\ffmpeg\bin`).
  2. Install media packages in `.venv`:
     ```bash
     .\.venv\Scripts\pip.exe install yt-dlp faster-whisper youtube-transcript-api
     ```
- **Acceptance Criteria:**
  - `ffmpeg -version` outputs valid build info.
  - `.\.venv\Scripts\python.exe -c "import yt_dlp, faster_whisper; print('OK')"` outputs `OK`.
  - Re-running `pytest tests/contracts/test_seedance_ark_video.py` passes (resolves earlier `ffprobe` failure).

#### Milestone 2: Local Video Clipping Smoke Test
- **Goal:** Verify the execution of transcription, timing, and trimming on a local test file before attempting network URL downloads.
- **Actions:**
  1. Provide a small 2-minute test `.mp4` video.
  2. Run `Transcriber.execute()` to produce word-level timestamps.
  3. Run `SubtitleGen.execute()` to generate an `.srt` file.
  4. Run `VideoTrimmer.execute({"operation": "cut", "start_seconds": 10.0, "end_seconds": 40.0, "codec": "libx264"})`.
  5. Start Backlot server (`.\.venv\Scripts\python.exe -m uvicorn backlot.server:create_app --port 4750`) and verify playback in browser.
- **Acceptance Criteria:** The trimmed video clip plays smoothly in Backlot with synchronized audio.

#### Milestone 3: Pipeline Integration & URL Intake Bridge
- **Goal:** Achieve zero-friction URL-to-clips execution.
- **Actions:**
  1. Update `pipeline_defs/clip-factory.yaml` (Change 1).
  2. Update `lib/source_media_review.py` (Change 2).
  3. Trigger an agent run: `"Process this YouTube URL with clip-factory: <URL>"`.
- **Acceptance Criteria:**
  - Video and audio are automatically downloaded into `projects/<id>/source/`.
  - The agent identifies and scores candidate moments against the 5 criteria.
  - The pipeline stops at the `awaiting_human` gate with candidate clips ready for preview in Backlot.

#### Milestone 4: Auto-Reframing & Subtitle Polish
- **Goal:** Convert landscape horizontal clips to mobile-ready 9:16 vertical videos.
- **Actions:**
  1. Install `mediapipe` and `opencv-python` into `.venv`.
  2. Wire `auto_reframe` into `skills/pipelines/clip-factory/compose-director.md`.
  3. Validate face-tracked reframing vs center-crop.
- **Acceptance Criteria:** The final deliverables in `projects/<id>/renders/` are 1080x1920 (9:16), with the speaker centered and styled captions burned at the lower third.

---

## 5. Recommended MVP Specification

The minimum viable product (MVP) provides an autonomous personal workflow:

1. **User Input:**
   ```text
   Extract 5 vertical clips (9:16) for YouTube Shorts from this podcast URL:
   https://www.youtube.com/watch?v=EXAMPLE
   ```
2. **Autonomous Execution:**
   - Ingestion: `VideoDownloader` fetches 1080p MP4 + 16kHz WAV into project workspace.
   - Speech: `Transcriber` extracts timestamped transcript.
   - Selection: Script Director identifies top 5 moments passing the Standalone Test.
   - Reframing & Trimming: `AutoReframe` crops to 9:16; `VideoTrimmer` cuts frame-accurate segments.
   - Captions: `SubtitleGen` produces karaoke captions; `VideoCompose` burns them into the MP4.
3. **Review & Approval:**
   - Backlot UI notifies user at `http://127.0.0.1:4750/p/<project_id>`.
   - User watches all 5 clips, clicks approve, and clips are saved in `renders/` ready for social posting.
