from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mpg", ".mpeg"}


def scan_video_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def build_video_record(video_path: Path) -> dict:
    stat_result = video_path.stat()
    created_ts = getattr(stat_result, "st_birthtime", stat_result.st_ctime)

    record = {
        "id": stable_file_id(video_path, stat_result.st_size, stat_result.st_mtime_ns),
        "filename": video_path.name,
        "path": str(video_path.resolve()),
        "extension": video_path.suffix.lower(),
        "size_bytes": stat_result.st_size,
        "file_created_at": iso_from_timestamp(created_ts),
        "file_modified_at": iso_from_timestamp(stat_result.st_mtime),
        "classification_status": "pending",
        "audio_required": False,
    }
    record["media"] = probe_media(video_path)
    return record


def stable_file_id(video_path: Path, size_bytes: int, modified_ns: int) -> str:
    digest = hashlib.sha256()
    digest.update(str(video_path.resolve()).encode("utf-8"))
    digest.update(str(size_bytes).encode("utf-8"))
    digest.update(str(modified_ns).encode("utf-8"))
    return digest.hexdigest()[:16]


def iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(
        microsecond=0
    ).isoformat()


def probe_media(video_path: Path) -> dict:
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path is None:
        return {
            "probe_status": "unavailable",
            "reason": "ffprobe not installed",
            "has_audio": None,
            "audio_stream_count": None,
            "video_stream_count": None,
        }

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "probe_status": "error",
            "reason": exc.stderr.strip() or "ffprobe failed",
            "has_audio": None,
            "audio_stream_count": None,
            "video_stream_count": None,
        }

    payload = json.loads(completed.stdout)
    streams = payload.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    primary_video = video_streams[0] if video_streams else {}
    format_info = payload.get("format", {})

    return {
        "probe_status": "ok",
        "duration_seconds": parse_float(format_info.get("duration")),
        "container_format": format_info.get("format_name"),
        "bit_rate": parse_int(format_info.get("bit_rate")),
        "has_audio": bool(audio_streams),
        "audio_stream_count": len(audio_streams),
        "video_stream_count": len(video_streams),
        "video": {
            "codec": primary_video.get("codec_name"),
            "width": primary_video.get("width"),
            "height": primary_video.get("height"),
            "frame_rate": parse_fraction(primary_video.get("avg_frame_rate")),
            "creation_time": stream_creation_time(primary_video, format_info),
        },
    }


def parse_float(value: str | None) -> float | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    if value in (None, "N/A", ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_fraction(value: str | None) -> float | None:
    if value in (None, "N/A", "", "0/0"):
        return None
    if "/" not in value:
        return parse_float(value)

    numerator_text, denominator_text = value.split("/", maxsplit=1)
    try:
        numerator = float(numerator_text)
        denominator = float(denominator_text)
    except ValueError:
        return None

    if denominator == 0:
        return None
    return numerator / denominator


def stream_creation_time(primary_video: dict, format_info: dict) -> str | None:
    primary_tags = primary_video.get("tags", {})
    format_tags = format_info.get("tags", {})
    return primary_tags.get("creation_time") or format_tags.get("creation_time")
