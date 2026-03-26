from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from argus.captioner import ollama_model_check
from argus.config import DEFAULT_OLLAMA_HOST, DEFAULT_VISION_MODEL


def dependency_report(
    *,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    vision_model: str = DEFAULT_VISION_MODEL,
) -> dict:
    ffprobe_path = shutil.which("ffprobe")
    ffmpeg_path = shutil.which("ffmpeg")
    ollama_path = shutil.which("ollama")
    ollama_api = ollama_api_status(ollama_host)
    ollama_model = (
        ollama_model_check(vision_model, ollama_host)
        if ollama_api["status"] == "available"
        else {
            "status": "missing",
            "model": vision_model,
            "reason": "Ollama API unavailable",
        }
    )

    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "requested": {
            "ollama_host": ollama_host,
            "vision_model": vision_model,
        },
        "dependencies": {
            "python": {
                "status": "available",
                "version": sys.version.split()[0],
                "path": sys.executable,
            },
            "ffprobe": binary_status("ffprobe", ffprobe_path),
            "ffmpeg": binary_status("ffmpeg", ffmpeg_path),
            "ollama": binary_status("ollama", ollama_path),
            "ollama_api": ollama_api,
            "ollama_model": ollama_model,
        },
        "features": {
            "filesystem_scan": True,
            "media_probe": ffprobe_path is not None,
            "audio_detection": ffprobe_path is not None,
            "frame_extraction": ffmpeg_path is not None,
            "frame_captioning": (
                ollama_api["status"] == "available"
                and ollama_model["status"] == "available"
            ),
        },
    }


def binary_status(name: str, path: str | None) -> dict:
    if path is None:
        return {
            "status": "missing",
            "path": None,
            "version": None,
            "install_hint": "brew install ffmpeg" if name in {"ffmpeg", "ffprobe"} else None,
        }

    return {
        "status": "available",
        "path": path,
        "version": binary_version(path),
        "install_hint": None,
    }


def binary_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "-version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    first_line = completed.stdout.splitlines()
    return first_line[0] if first_line else None


def ollama_api_status(host: str) -> dict:
    version_url = host.rstrip("/") + "/api/version"
    try:
        with urllib.request.urlopen(version_url, timeout=3) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        return {
            "status": "missing",
            "host": host,
            "version": None,
            "reason": str(exc.reason),
        }

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {}

    return {
        "status": "available",
        "host": host,
        "version": payload.get("version"),
        "reason": None,
    }
