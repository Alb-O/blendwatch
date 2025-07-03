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


def parse_move_log(log_file: Union[str, Path], start_position: int = 0) -> Tuple[List[Move], int]:
    """Parse a BlendWatch log file and return file move operations.
    
    Args:
        log_file: Path to the log file
        start_position: Byte position to start reading from
        
    Returns:
        Tuple of (moves list, new position after reading)
    """
    moves: List[Move] = []
    log_path = Path(log_file)
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    with open(log_path, "r", encoding="utf-8") as f:
        f.seek(start_position)
        current_position = start_position
        
        for line in f:
            try:
                event = json.loads(line.strip())
            except json.JSONDecodeError:
                current_position = f.tell()
                continue
            if event.get("type") in {"file_moved", "file_renamed"}:
                old_path = event.get("old_path")
                new_path = event.get("new_path")
                if old_path and new_path:
                    moves.append((old_path, new_path))
            current_position = f.tell()
    
    return moves, current_position


def parse_move_log_simple(log_file: Union[str, Path]) -> List[Move]:
    """Parse a BlendWatch log file and return file move operations."""
    moves, _ = parse_move_log(log_file, 0)
    return moves


def apply_move_log_incremental(
    log_file: Union[str, Path],
    search_directory: Union[str, Path],
    start_position: int = 0,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> Tuple[int, int]:
    """Update library paths for move operations from a specific position in the log.

    Parameters
    ----------
    log_file:
        Path to a JSON move log produced by ``blendwatch watch``.
    search_directory:
        Directory containing blend files that reference the moved assets.
    start_position:
        Byte position to start reading from in the log file.
    dry_run:
        If True, do not modify any files but report what would change.
    verbose:
        Print information about every update performed.

    Returns
    -------
    Tuple[int, int]
        (Number of library paths updated, new position in log file)
    """
    moves, new_position = parse_move_log(log_file, start_position)
    if not moves:
        return 0, new_position

    scanner = BacklinkScanner(search_directory)
    total_updates = 0

    for old_path, new_path in moves:
        if verbose:
            print(f"Processing move: {old_path} -> {new_path}")
        
        results = scanner.find_backlinks_to_file(old_path)
        for result in results:
            try:
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
            except Exception as e:
                log.warning(f"Could not update {result.blend_file}: {e}")

    return total_updates, new_position


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
    moves = parse_move_log_simple(log_file)
    if not moves:
        return 0

    scanner = BacklinkScanner(search_directory)
    total_updates = 0

    for old_path, new_path in moves:
        results = scanner.find_backlinks_to_file(old_path)
        for result in results:
            try:
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
            except Exception as e:
                log.warning(f"Could not update {result.blend_file}: {e}")

    return total_updates
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
