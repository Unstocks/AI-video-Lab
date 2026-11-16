"""Real smoke test for Milestone 1: URL Intake Integration.

Ingests a real public video URL, materializes source_video.mp4, source_audio.wav,
source_manifest.json, validates with ffprobe, and executes lib.source_media_review.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from lib.url_ingest import URLIntakeAdapter, ensure_media_tools_on_path
from lib.source_media_review import review_source_media


def run_smoke_test(
    url: str = "https://www.youtube.com/watch?v=jNQXAC9IVRw",
    project_id: str = "smoke-test-milestone1",
) -> dict:
    """Execute end-to-end smoke test."""
    ensure_media_tools_on_path()
    adapter = URLIntakeAdapter()

    print(f"\n[1/5] Ingesting URL: {url} -> project: {project_id}")
    res = adapter.ingest_url(url, project_id, max_duration_seconds=300, preferred_quality="720p")

    if not res.success:
        print(f"FAILED: Ingest returned error: {res.error}")
        return {"success": False, "error": res.error}

    print(f"[2/5] Ingest successful:")
    print(f"  - Video path: {res.video_path}")
    print(f"  - Audio path: {res.audio_path}")
    print(f"  - Transcript path: {res.transcript_path}")
    print(f"  - Manifest path: {res.manifest_path}")
    print(f"  - Duration: {res.duration_seconds}s")
    print(f"  - Resolution: {res.resolution}")
    print(f"  - FPS: {res.fps}")
    print(f"  - Native captions: {res.has_native_captions}")

    # Verify video file with ffprobe
    print("\n[3/5] Validating video container with ffprobe...")
    cmd_v = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", res.video_path,
    ]
    probe_v = json.loads(subprocess.check_output(cmd_v).decode("utf-8"))
    assert any(s.get("codec_type") == "video" for s in probe_v.get("streams", []))
    print("  -> Video stream verified valid.")

    # Verify audio file with ffprobe
    print("\n[4/5] Validating audio file with ffprobe...")
    cmd_a = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", res.audio_path,
    ]
    probe_a = json.loads(subprocess.check_output(cmd_a).decode("utf-8"))
    assert any(s.get("codec_type") == "audio" for s in probe_a.get("streams", []))
    print("  -> Audio stream verified valid.")

    # Verify source_manifest.json
    print("\n[5/5] Validating source_manifest.json and running source_media_review...")
    with open(res.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    print("  -> Manifest contents verified.")

    review_art = adapter.review_ingested_media(res)
    print("  -> source_media_review executed successfully.")
    print(f"  -> Reviewed files count: {len(review_art.get('files', []))}")
    if review_art.get("files"):
        f_info = review_art["files"][0]
        print(f"  -> File summary: {f_info.get('content_summary')}")

    return {
        "success": True,
        "ingest_result": res,
        "manifest": manifest,
        "review_artifact": review_art,
    }


if __name__ == "__main__":
    result = run_smoke_test()
    if result["success"]:
        print("\nALL SMOKE TEST VERIFICATIONS PASSED!")
    else:
        print("\nSMOKE TEST FAILED!")
        exit(1)
