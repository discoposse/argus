from __future__ import annotations

import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from argus.config import DEFAULT_OLLAMA_HOST, DEFAULT_VISION_MODEL
from argus.database import default_db_path
from argus.dependencies import dependency_report
from argus.progress import load_progress
from argus.scanner import scan_video_files


def build_status_report(
    input_dir: Path,
    output_dir: Path,
    *,
    model: str = DEFAULT_VISION_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
) -> dict:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    items_dir = output_dir / "items"
    manifest_path = output_dir / "manifest.json"

    ingest_files = scan_video_files(input_dir) if input_dir.exists() else []
    item_records = load_item_records(items_dir)
    manifest = load_json(manifest_path)
    db_path = default_db_path(output_dir)
    progress = load_progress(output_dir)

    status_counts = Counter(
        record.get("classification_status", "unknown") for record in item_records
    )
    probe_counts = Counter(
        record.get("media", {}).get("probe_status", "unknown") for record in item_records
    )

    sampled_videos = 0
    frames_written = 0
    frames_captioned = 0
    frame_errors = 0
    sample_status_counts = Counter()

    for record in item_records:
        sample_frames = record.get("sample_frames")
        if not sample_frames:
            continue

        sampled_videos += 1
        sample_status_counts[sample_frames.get("status", "unknown")] += 1
        for frame in sample_frames.get("frames", []):
            if frame.get("status") == "ok":
                frames_written += 1
            if frame.get("caption"):
                frames_captioned += 1
            if frame.get("caption_error"):
                frame_errors += 1

    recent_items = [
        {
            "filename": record.get("filename"),
            "status": record.get("classification_status", "unknown"),
            "probe": record.get("media", {}).get("probe_status", "unknown"),
            "frames": len(record.get("sample_frames", {}).get("frames", [])),
            "captions": sum(
                1
                for frame in record.get("sample_frames", {}).get("frames", [])
                if frame.get("caption")
            ),
            "tags": len(record.get("suggested_tags", [])),
        }
        for record in sorted(
            item_records,
            key=lambda item: item.get("file_modified_at", ""),
            reverse=True,
        )[:8]
    ]

    dependencies = dependency_report(ollama_host=ollama_host, vision_model=model)

    return {
        "generated_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "manifest_exists": manifest is not None,
        "manifest_generated_at": manifest.get("generated_at") if manifest else None,
        "database_exists": db_path.exists(),
        "database_path": str(db_path),
        "progress": progress,
        "ingest_count": len(ingest_files),
        "item_count": len(item_records),
        "inventory_progress": ratio(len(item_records), len(ingest_files)),
        "status_counts": dict(status_counts),
        "probe_counts": dict(probe_counts),
        "sample_status_counts": dict(sample_status_counts),
        "sampled_videos": sampled_videos,
        "frames_written": frames_written,
        "frames_captioned": frames_captioned,
        "frame_errors": frame_errors,
        "dependencies": dependencies,
        "recent_items": recent_items,
    }


def render_status_text(report: dict) -> str:
    lines = []
    lines.append("Argus Status")
    lines.append("=" * 72)
    lines.append(f"Updated:         {report['generated_at']}")
    lines.append(f"Ingest dir:      {report['input_dir']}")
    lines.append(f"Output dir:      {report['output_dir']}")
    lines.append(
        f"Manifest:        {'yes' if report['manifest_exists'] else 'no'}"
        + (
            f" ({report['manifest_generated_at']})"
            if report["manifest_generated_at"]
            else ""
        )
    )
    lines.append(
        f"SQLite index:    {'yes' if report['database_exists'] else 'no'} "
        f"({report['database_path']})"
    )
    lines.append("")

    lines.append("Pipeline")
    lines.append("-" * 72)
    lines.append(
        f"Ingested files:  {report['item_count']}/{report['ingest_count']} "
        f"({percent_text(report['inventory_progress'])})"
    )
    lines.append(f"Probe status:    {format_counter(report['probe_counts'])}")
    lines.append(
        f"Sampling:        {report['sampled_videos']} video(s), "
        f"{report['frames_written']} frame(s) written"
    )
    if report["sample_status_counts"]:
        lines.append(
            f"Sample status:   {format_counter(report['sample_status_counts'])}"
        )
    lines.append(
        f"Captioning:      {report['frames_captioned']} captioned frame(s), "
        f"{report['frame_errors']} error(s)"
    )
    lines.append(f"Item status:     {format_counter(report['status_counts'])}")
    if report["progress"]:
        progress = report["progress"]
        lines.append(
            f"Live job:        {progress['phase']} {progress['status']} | "
            f"items {progress['completed_items']}/{progress['total_items']} | "
            f"frames {progress.get('processed_frames', progress['completed_frames'])}/"
            f"{progress['total_frames']}"
        )
        if progress.get("current_item"):
            lines.append(
                f"Current item:    {progress['current_item']}"
                + (
                    f" (frame {progress['current_frame_index']})"
                    if progress.get("current_frame_index")
                    else ""
                )
            )
    lines.append("")

    deps = report["dependencies"]["dependencies"]
    feature_captioning = report["dependencies"]["features"]["frame_captioning"]
    lines.append("Preflight")
    lines.append("-" * 72)
    lines.append(
        f"ffmpeg:          {deps['ffmpeg']['status']} | "
        f"ffprobe: {deps['ffprobe']['status']}"
    )
    lines.append(
        f"Ollama binary:   {deps['ollama']['status']} | "
        f"API: {deps['ollama_api']['status']} | "
        f"Model: {deps['ollama_model']['status']}"
    )
    if deps["ollama_model"]["status"] == "available":
        lines.append(
            f"Vision model:    {deps['ollama_model'].get('resolved_name')} "
            f"({deps['ollama_model'].get('parameter_size')})"
        )
    elif deps["ollama_model"].get("reason"):
        lines.append(f"Vision model:    {deps['ollama_model']['reason']}")
    lines.append(f"Caption ready:   {'yes' if feature_captioning else 'no'}")
    lines.append("")

    if report["recent_items"]:
        lines.append("Recent Items")
        lines.append("-" * 72)
        lines.append(
            "Status".ljust(18)
            + "Probe".ljust(12)
            + "Frames".rjust(8)
            + "Caps".rjust(8)
            + "Tags".rjust(8)
            + "  File"
        )
        for item in report["recent_items"]:
            lines.append(
                item["status"][:17].ljust(18)
                + item["probe"][:11].ljust(12)
                + str(item["frames"]).rjust(8)
                + str(item["captions"]).rjust(8)
                + str(item["tags"]).rjust(8)
                + "  "
                + str(item["filename"])
            )
    else:
        lines.append("No indexed items yet.")

    lines.append("")
    lines.append("Tip: run `argus status --watch` in one terminal during scan/caption.")
    return "\n".join(lines)


def run_status_tui(
    input_dir: Path,
    output_dir: Path,
    *,
    model: str = DEFAULT_VISION_MODEL,
    ollama_host: str = DEFAULT_OLLAMA_HOST,
    watch: bool = False,
    interval_seconds: float = 2.0,
) -> int:
    while True:
        report = build_status_report(
            input_dir,
            output_dir,
            model=model,
            ollama_host=ollama_host,
        )
        if watch:
            clear_screen()
        print(render_status_text(report))
        if not watch:
            return 0
        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\nStopped watching.")
            return 0


def load_item_records(items_dir: Path) -> list[dict]:
    if not items_dir.exists():
        return []
    return [
        json.loads(item_path.read_text(encoding="utf-8"))
        for item_path in sorted(items_dir.glob("*.json"))
    ]


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def percent_text(value: float) -> str:
    return f"{value * 100:.0f}%"


def format_counter(counter: dict[str, int]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


def clear_screen() -> None:
    print("\033[2J\033[H", end="")
    os.sys.stdout.flush()
