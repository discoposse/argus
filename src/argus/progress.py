from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def progress_file_path(output_dir: Path) -> Path:
    return output_dir.resolve() / "progress.json"


def initialize_progress(
    output_dir: Path,
    *,
    phase: str,
    total_items: int,
    total_frames: int,
    model: str | None = None,
) -> dict:
    state = {
        "phase": phase,
        "status": "running",
        "started_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "finished_at": None,
        "total_items": total_items,
        "completed_items": 0,
        "total_frames": total_frames,
        "processed_frames": 0,
        "completed_frames": 0,
        "failed_frames": 0,
        "current_item": None,
        "current_frame_index": None,
        "current_frame_timestamp_seconds": None,
        "model": model,
    }
    write_progress(output_dir, state)
    return state


def update_progress(output_dir: Path, state: dict, **changes: object) -> dict:
    updated = dict(state)
    updated.update(changes)
    updated["updated_at"] = utc_now_iso()
    write_progress(output_dir, updated)
    return updated


def finish_progress(output_dir: Path, state: dict, *, status: str = "completed") -> dict:
    return update_progress(
        output_dir,
        state,
        status=status,
        finished_at=utc_now_iso(),
        completed_items=state.get("total_items", state.get("completed_items", 0)),
        processed_frames=state.get("total_frames", state.get("processed_frames", 0)),
        current_item=None,
        current_frame_index=None,
        current_frame_timestamp_seconds=None,
    )


def load_progress(output_dir: Path) -> dict | None:
    path = progress_file_path(output_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_progress(output_dir: Path, state: dict) -> None:
    path = progress_file_path(output_dir)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
