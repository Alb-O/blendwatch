"""Utilities for updating linked library paths after files are moved."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Tuple, Union

from blendwatch.blender.backlinks import BacklinkScanner
from blendwatch.blender.library_writer import LibraryPathWriter

log = logging.getLogger(__name__)

Move = Tuple[str, str]


def parse_move_log(log_file: Union[str, Path]) -> List[Move]:
    """Parse a BlendWatch log file and return file move operations."""
    moves: List[Move] = []
    log_path = Path(log_file)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line.strip())
            except json.JSONDecodeError:
                continue
            if event.get("type") in {"file_moved", "file_renamed"}:
                old_path = event.get("old_path")
                new_path = event.get("new_path")
                if old_path and new_path:
                    moves.append((old_path, new_path))
    return moves


def apply_move_log(
    log_file: Union[str, Path],
    search_directory: Union[str, Path],
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Update library paths for all move operations recorded in ``log_file``.

    Parameters
    ----------
    log_file:
        Path to a JSON move log produced by ``blendwatch watch``.
    search_directory:
        Directory containing blend files that reference the moved assets.
    dry_run:
        If True, do not modify any files but report what would change.
    verbose:
        Print information about every update performed.

    Returns
    -------
    int
        Number of library paths updated across all blend files.
    """
    moves = parse_move_log(log_file)
    if not moves:
        return 0

    scanner = BacklinkScanner(search_directory)
    total_updates = 0

    for old_path, new_path in moves:
        results = scanner.find_backlinks_to_file(old_path)
        for result in results:
            writer = LibraryPathWriter(result.blend_file)
            if dry_run:
                current = writer.get_library_paths()
                if old_path in current.values():
                    total_updates += 1
                    if verbose:
                        print(f"Would update {result.blend_file} -> {new_path}")
                continue

            updated = writer.update_library_path(old_path, new_path)
            if updated:
                total_updates += 1
                if verbose:
                    print(f"Updated {result.blend_file} -> {new_path}")

    return total_updates
