from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from argus.extractor import extract_sample_frames
from argus.scanner import build_video_record, scan_video_files


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_scan(
    input_dir: Path,
    output_dir: Path,
    *,
    sample_frames: bool = False,
    frame_count: int = 4,
) -> dict:
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    items_dir = output_dir / "items"
    frames_dir = output_dir / "frames"

    input_dir.mkdir(parents=True, exist_ok=True)
    items_dir.mkdir(parents=True, exist_ok=True)
    if sample_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for video_path in scan_video_files(input_dir):
        record = build_video_record(video_path)
        if sample_frames:
            duration_seconds = record.get("media", {}).get("duration_seconds")
            record["sample_frames"] = extract_sample_frames(
                video_path,
                record["id"],
                duration_seconds,
                frames_dir,
                frame_count,
            )
        records.append(record)

        item_path = items_dir / f"{record['id']}.json"
        item_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    manifest_path = output_dir / "manifest.json"
    manifest = {
        "generated_at": utc_now_iso(),
        "root_path": str(input_dir),
        "file_count": len(records),
        "probe_summary": summarize_probe_status(records),
        "manifest_path": str(manifest_path),
        "items_path": str(items_dir),
        "files": records,
    }
    if sample_frames:
        manifest["frames_path"] = str(frames_dir)
        manifest["frame_summary"] = summarize_frame_status(records)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def summarize_probe_status(records: list[dict]) -> dict:
    summary = {
        "ok": 0,
        "unavailable": 0,
        "error": 0,
        "unknown": 0,
    }
    for record in records:
        status = record.get("media", {}).get("probe_status", "unknown")
        if status not in summary:
            summary["unknown"] += 1
            continue
        summary[status] += 1
    return summary


def summarize_frame_status(records: list[dict]) -> dict:
    summary = {
        "videos_attempted": 0,
        "videos_ok": 0,
        "videos_partial": 0,
        "videos_skipped": 0,
        "videos_unavailable": 0,
        "frames_written": 0,
    }
    for record in records:
        frame_info = record.get("sample_frames")
        if not frame_info:
            continue

        summary["videos_attempted"] += 1
        status = frame_info.get("status")
        if status == "ok":
            summary["videos_ok"] += 1
        elif status == "partial":
            summary["videos_partial"] += 1
        elif status == "skipped":
            summary["videos_skipped"] += 1
        elif status == "unavailable":
            summary["videos_unavailable"] += 1

        summary["frames_written"] += sum(
            1 for frame in frame_info.get("frames", []) if frame.get("status") == "ok"
        )
    return summary
