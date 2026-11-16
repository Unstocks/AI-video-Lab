# PART 2: EXTERNAL TECHNICAL RESEARCH & ARCHITECTURE DECISION
## Comparative Analysis, Industry State of the Art, Local AI Feasibility & Structural Strategy

**Workspace:** `C:\AI-Video-Lab`  
**Focus:** Long-Form to Short-Form Video Repurposing Architecture  
**Date:** 2026-11-16  

---

## 1. Industry State of the Art: How Modern Clipping Systems Work

Commercial tools (OpusClip, Klap, Munch, Vizard, Vidyo.ai) have popularized automated video repurposing. Beneath their user interfaces, all commercial systems employ a 4-tier pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                   COMMERCIAL AI CLIPPING ARCHITECTURE                       │
│                                                                             │
│  1. INGESTION      Audio Demuxing (FFmpeg) + Scribe (Whisper/Deepgram)       │
│                           │                                                 │
│                           ▼                                                 │
│  2. INTELLIGENCE   Multi-Modal Virality Scorer                              │
│                    ├── Semantic Hook Scoring (LLM: curiosity, controversy)  │
│                    ├── Acoustic Energy Peaks (ebur128 / Pitch / Cadence)    │
│                    └── Visual Engagement (Face presence, slide detection)   │
│                           │                                                 │
│                           ▼                                                 │
│  3. REFRAMING      Speaker-Aware Tracking                                   │
│                    ├── Face Tracking (YOLO / MediaPipe)                     │
│                    ├── Active Speaker Audio-Visual Diarization              │
│                    └── Layout Selector (Dynamic Pan / Split Screen)         │
│                           │                                                 │
│                           ▼                                                 │
│  4. ASSEMBLY       Remotion / WebGL / FFmpeg Composition                    │
│                    ├── Sentence-boundary snapping & silence trimming        │
│                    └── Word-level animated karaoke captions                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Detailed Breakdown of Market Leaders:

| Platform | Primary Moment Scoring Method | Reframing Technology | Caption / Styling Engine | Licensing & Deployment |
| :--- | :--- | :--- | :--- | :--- |
| **OpusClip** | "ClipGenius" virality score (Semantic hook + emotional valence + speaker cadence) | Active speaker tracking + dynamic camera switching + 2-speaker vertical split-screen | WebGL / Remotion-based animated captions with emoji auto-insertion | Proprietary SaaS ($19–$49/mo); no self-hosted option. |
| **Klap.app** | LLM transcript analysis (focusing on standalone story units) | Face-tracking crop centered on detected speaker | Kinetic animated text overlays | Proprietary SaaS ($29–$79/mo); cloud-only. |
| **Munch** | SEO & Trend matching (correlates transcript topics against trending social keywords) | AI smart-crop keeping subjects in frame | Built-in subtitle burn | Proprietary SaaS ($49/mo+); cloud-only. |
| **Auto-Editor** | Pure acoustic thresholding (FFmpeg volume & silence detection) | None (maintains original aspect ratio) | None | **Open Source (Free)**; Python CLI tool. |
| **OpenMontage (Current)** | Agentic 5-aspect prompt scoring (`hook`, `coherence`, `value`, `energy`, `fit`) | MediaPipe face tracking + temporal smoothing (`auto_reframe.py`) | Pure-Python SRT (`subtitle_gen.py`) + Remotion caption burn | **Open Source (AGPL-3.0)**; 100% self-hosted local. |

---

## 2. Technical Deep Dive: The 4 Core Engineering Challenges

### 2.1 Clip Intelligence: Finding the "Viral" Moments
Why do naive transcript search scripts fail? Because transcript-only analysis often picks calm monologues or summaries rather than engaging social hooks.

To identify high-retention clips locally, the system must evaluate three orthogonal signals:
1. **Semantic Tension (The Hook):** The first 3 seconds must create a curiosity gap, challenge conventional wisdom, or deliver a strong thesis. OpenMontage’s `skills/pipelines/clip-factory/script-director.md` explicitly models this with the `hook` and `energy` scoring dimensions.
2. **Acoustic Loudness Profiling (`AudioEnergy`):** Humans raise vocal intensity, increase cadence, or laugh during engaging moments. OpenMontage’s `tools/analysis/audio_energy.py` uses FFmpeg’s `ebur128` loudness filter to measure momentary loudness at 100ms intervals. Correlating high acoustic energy with transcript sections pinpoints exact peak moments.
3. **The "Standalone Test" (Context Preservation):** A clip is worthless if it starts with a dangling reference ("*And as we saw earlier, that’s why...*") or cuts off before the conclusion. The agent must reject candidate timestamps if:
   - The opening sentence contains an unresolved pronoun (`he`, `she`, `they`, `this`).
   - The final sentence does not conclude the thematic premise.

### 2.2 Intelligent Boundary Refinement & Timestamp Snapping
Cutting at raw timestamp intervals (e.g., exactly at 01:15.00) results in clipped words, severed syllables, and unnatural pauses.

**The Golden Boundary Rules:**
1. **Word-Level Timestamp Snapping:** Candidate in/out points must align with the exact start and end timestamps of words provided by Whisper.
2. **VAD (Voice Activity Detection) Buffering:**
   - Pre-roll padding: Add **150ms** before the first word to preserve the speaker's vocal attack / breathing.
   - Post-roll padding: Add **300ms** after the last word to let the vocal decay finish naturally.
   - *OpenMontage implementation:* `tools/video/silence_cutter.py` (lines 78–82) already implements `padding_seconds = 0.08` to prevent speech clipping.
3. **Visual Scene Boundary Check:** `tools/analysis/scene_detect.py` uses FFmpeg's `select='gt(scene,0.3)'` filter. If a scene change occurs within 0.5s of the chosen in-point, snap the cut to the visual cut to eliminate jarring visual flashes.

### 2.3 Speaker-Aware Vertical Reframing (16:9 to 9:16)
When taking a 1920x1080 horizontal video and cropping to 1080x1920 vertical, 66% of the horizontal pixels are discarded.

```
Original 16:9 Landscape (1920x1080):
┌──────────────────────────────────────────────┐
│                  [SPEAKER]                   │
│                                              │
└──────────────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
Static Center-Crop:         Face-Tracked Reframe (auto_reframe.py):
┌─────────────────┐         ┌─────────────────┐
│     [Blank]     │         │                 │
│                 │         │    [SPEAKER]    │  <- Centered smoothly
│     [Speaker]   │         │                 │     via MediaPipe trajectory
│     (Half Cut)  │         │                 │
└─────────────────┘         └─────────────────┘
```

**Local Reframing Mechanics in OpenMontage (`tools/video/auto_reframe.py`):**
- **Detector:** Uses Google MediaPipe Face Mesh / OpenCV Haar Cascades to locate the speaker's bounding box `(x, y, w, h)` across sampled frames.
- **Trajectory Smoothing (lines 94–98):** Applies a moving average filter over `smoothing_window = 15` frames. This prevents camera jitter while smoothly panning across the horizontal canvas if the speaker leans or shifts.
- **FFmpeg Filter Assembly:** Converts smoothed trajectories into dynamic FFmpeg crop filters:
  ```bash
  ffmpeg -i source.mp4 -vf "crop=608:1080:x_pos:0,scale=1080:1920" -c:v libx264 -crf 20 out_9x16.mp4
  ```
- **Podcast Split-Screen Enhancement:** For two-person interviews, OpenMontage can apply a stacked vertical split: Speaker A on top, Speaker B on bottom, fitting both into a single 9:16 canvas.

### 2.4 Captions, Typography & Audio Post-Processing
- **Word-Level Highlighting:** Standard subtitles show full sentences, which encourages viewers to read ahead. Social short-form clips require **karaoke-style active word highlighting** (bright yellow/green highlight on the current word).
  - OpenMontage’s `tools/subtitle/subtitle_gen.py` implements pure-Python formatting for `highlight_style="karaoke"` and `highlight_style="word_by_word"`.
- **Dynamic Rendering Engine:** OpenMontage integrates Remotion (`remotion-composer/`) using React and `@remotion/captions`. Remotion renders SVG and CSS typography natively over video frames at full 60fps frame accuracy.
- **Audio Preservation & Normalization:** `tools/audio/audio_enhance.py` applies FFmpeg’s `loudnorm` filter (EBU R128 standard: `-16 LUFS` for mobile social feeds).

---

## 3. Local-First AI Stack: Running at Zero Recurring Cost

| Component | Local Open-Source Tool | License | Hardware Envelope | API Cost | Suitability for AI-Video-Lab |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Media Ingestion** | `yt-dlp` | Unlicense | Negligible CPU | $0.00 | **Native match**; wrapped by `video_downloader.py`. |
| **Core Media Engine** | `ffmpeg` + `ffprobe` | LGPL 2.1+ | 1–2 CPU cores | $0.00 | **Critical requirement**; foundation of all video tools. |
| **Speech-to-Text** | `faster-whisper` (CTranslate2) | MIT | 2GB RAM (CPU) / 2GB VRAM (CUDA) | $0.00 | **Native match**; wrapped by `transcriber.py`. |
| **Zero-Compute STT**| `youtube-transcript-api` | MIT | Negligible CPU | $0.00 | **Native match**; wrapped by `transcript_fetcher.py`. |
| **Hook Scoring** | Local Ollama (Llama 3.1 8B / Qwen 2.5) | MIT / Apache 2.0 | 8GB–16GB RAM | $0.00 | Supported via `config.yaml` (`llm.provider: ollama`). |
| **Face Tracking** | Google MediaPipe / OpenCV | Apache 2.0 | CPU: 1 core | $0.00 | **Native match**; wrapped by `auto_reframe.py`. |
| **Dead-Air Removal**| FFmpeg `silencedetect` | LGPL 2.1+ | 1 CPU core | $0.00 | **Native match**; wrapped by `silence_cutter.py`. |
| **Animated Captions**| Remotion Composer | Remotion Public | Node.js runtime | $0.00* | Native composer in `remotion-composer/`. (*Free for individuals / small teams). |

---

## 4. Evaluation of the Three Architectural Approaches

### Approach A: Reuse OpenMontage Strictly As-Is
- **How it works:** The user manually downloads the YouTube video to a local `.mp4`, drops it into `projects/<id>/`, manually runs `source_media_review`, and lets `clip-factory` run without URL ingestion.
- **Pros:** Zero modifications to upstream files.
- **Cons:** High manual friction. Does not answer the user's requirement ("paste a URL and extract clips automatically"). Center-crop only (no dynamic reframing).
- **Verdict:** **REJECTED** (Too much manual overhead).

### Approach B: Extend OpenMontage via Minimal First-Class Bridges (RECOMMENDED)
- **How it works:**
  1. Add `video_downloader` and `transcript_fetcher` into `pipeline_defs/clip-factory.yaml`.
  2. Enhance `lib/source_media_review.py` to detect URL strings and automatically download the media into the project workspace before running the probe.
  3. Install the required host binaries (`ffmpeg`) and Python packages (`yt-dlp`, `faster-whisper`) in `.venv`.
- **Pros:**
  - Preserves OpenMontage’s architecture, Git history, and contracts 100%.
  - Uses existing, already-written tools (`VideoDownloader`, `Transcriber`, `VideoTrimmer`, `SubtitleGen`).
  - Minimal code delta (~20 lines of code across 2 files).
  - Fully local, free, and automated.
- **Cons:** Requires installing missing Python packages in `.venv` and FFmpeg on the host.
- **Verdict:** **SELECTED (Optimal Architectural Path)**.

### Approach C: Integrate External Microservice / Containerized Tool
- **How it works:** Run an external open-source clipping daemon (e.g., an Auto-Editor container or a custom FastAPI microservice) alongside OpenMontage.
- **Pros:** Isolates clipping logic from OpenMontage.
- **Cons:** Massive architectural duplication. Bypasses OpenMontage’s Backlot review board, pipeline state machine, and checkpoint protocol. Introduces heavy maintenance overhead.
- **Verdict:** **REJECTED** (Unnecessary complexity).

---

## 5. Architectural Recommendation

We recommend **Approach B**. 

OpenMontage already contains all the constituent components. The "missing" URL-to-clips feature is simply an unbridged intake path: `clip-factory` needs permission to call `video_downloader`, and `source_media_review` needs to accept URL strings. Bridging these two points completes the entire automated URL-to-clips loop.
