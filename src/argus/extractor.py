from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def extract_sample_frames(
    video_path: Path,
    video_id: str,
    duration_seconds: float | None,
    frames_root: Path,
    frame_count: int,
) -> dict:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is None:
        return {
            "status": "unavailable",
            "reason": "ffmpeg not installed",
            "frames": [],
        }

    if duration_seconds is None or duration_seconds <= 0:
        return {
            "status": "skipped",
            "reason": "video duration unavailable",
            "frames": [],
        }

    if frame_count < 1:
        return {
            "status": "skipped",
            "reason": "frame_count must be >= 1",
            "frames": [],
        }

    video_frames_dir = frames_root / video_id
    video_frames_dir.mkdir(parents=True, exist_ok=True)

    timestamps = evenly_spaced_timestamps(duration_seconds, frame_count)
    frames = []

    for index, timestamp in enumerate(timestamps, start=1):
        frame_name = f"frame_{index:02d}_{timestamp_slug(timestamp)}.jpg"
        output_path = video_frames_dir / frame_name
        result = extract_frame(ffmpeg_path, video_path, output_path, timestamp)

        frame_record = {
            "index": index,
            "timestamp_seconds": round(timestamp, 3),
            "path": str(output_path),
            "status": result["status"],
        }
        if result["status"] != "ok":
            frame_record["reason"] = result["reason"]

        frames.append(frame_record)

    overall_status = "ok" if all(frame["status"] == "ok" for frame in frames) else "partial"
    return {
        "status": overall_status,
        "frame_count_requested": frame_count,
        "frames": frames,
    }


def evenly_spaced_timestamps(duration_seconds: float, frame_count: int) -> list[float]:
    segment = duration_seconds / (frame_count + 1)
    return [segment * index for index in range(1, frame_count + 1)]


def timestamp_slug(timestamp: float) -> str:
    return f"{timestamp:07.3f}s".replace(".", "_")


def extract_frame(
    ffmpeg_path: str,
    video_path: Path,
    output_path: Path,
    timestamp_seconds: float,
) -> dict:
    command = [
        ffmpeg_path,
        "-y",
        "-v",
        "error",
        "-i",
        str(video_path),
        "-ss",
        f"{timestamp_seconds:.3f}",
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_path),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "reason": exc.stderr.strip() or "ffmpeg frame extraction failed",
        }

    if not output_path.exists():
        return {
            "status": "error",
            "reason": "ffmpeg completed without writing the frame",
        }

    return {"status": "ok", "reason": None}
