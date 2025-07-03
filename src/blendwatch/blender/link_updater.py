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
        
        while True:
            line = f.readline()
            if not line:  # End of file
                break
                
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
    relative: bool = False,
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
    relative:
        If True, write library paths in relative format (default: False).

    Returns
    -------
    Tuple[int, int]
        (Number of library paths updated, new position in log file)
    """
    moves, new_position = parse_move_log(log_file, start_position)
    if not moves:
        return 0, new_position

    # Optimize by collecting unique old paths to avoid redundant backlink searches
    move_map = {}  # old_path -> list of new_paths
    for old_path, new_path in moves:
        if old_path not in move_map:
            move_map[old_path] = []
        move_map[old_path].append(new_path)

    scanner = BacklinkScanner(search_directory)
    total_updates = 0

    # Process each unique old path once
    for old_path, new_paths in move_map.items():
        if verbose:
            print(f"Processing moves for: {old_path} -> {new_paths}")
        
        # Find backlinks once for this old path
        results = scanner.find_backlinks_to_file(old_path)
        
        # Apply updates for each new path (in case there are multiple renames)
        for new_path in new_paths:
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

                    updated = writer.update_library_path(old_path, new_path, relative=relative)
                    if updated:
                        total_updates += 1
                        if verbose:
                            print(f"Updated {result.blend_file} -> {new_path}")
                        
                        # Invalidate cache for modified file
                        scanner.cache.invalidate_file(result.blend_file)
                            
                except Exception as e:
                    log.warning(f"Could not update {result.blend_file}: {e}")

    # Save cache for next time
    scanner.save_cache()
    
    # Log performance stats
    stats = scanner.get_cache_stats()
    if verbose:
        print(f"Cache performance: {stats['cache_hits']} hits, {stats['cache_misses']} misses "
              f"({stats['hit_rate_percent']}% hit rate)")

    return total_updates, new_position


def apply_move_log(
    log_file: Union[str, Path],
    search_directory: Union[str, Path],
    *,
    dry_run: bool = False,
    verbose: bool = False,
    relative: bool = False,
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
    relative:
        If True, write library paths in relative format (default: False).

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

                updated = writer.update_library_path(old_path, new_path, relative=relative)
                if updated:
                    total_updates += 1
                    if verbose:
                        print(f"Updated {result.blend_file} -> {new_path}")
            except Exception as e:
                log.warning(f"Could not update {result.blend_file}: {e}")

    return total_updates
