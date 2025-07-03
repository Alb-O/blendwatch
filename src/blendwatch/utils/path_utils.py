"""
Path and file utilities for BlendWatch
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Set, Any


def bytes_to_string(data: Any) -> str:
    """Convert bytes to string with minimal processing.
    
    This is a common helper used throughout the module for consistent string handling.
    
    Args:
        data: Data to convert, can be bytes or other types
        
    Returns:
        String representation with null bytes removed
    """
    if isinstance(data, bytes):
        return data.decode('utf-8', errors='replace').rstrip('\x00')
    return str(data).rstrip('\x00')


def resolve_path(path: str) -> Path:
    """Resolve a path to an absolute Path object."""
    return Path(path).resolve()


def is_path_ignored(path: Path, ignore_patterns: List[str]) -> bool:
    """Check if a path should be ignored based on regex patterns."""
    path_str = str(path)
    for pattern in ignore_patterns:
        if re.search(pattern, path_str):
            return True
    return False


def find_files_by_extension(directory: Path, extensions: List[str], recursive: bool = True) -> List[Path]:
    """Find all files with specific extensions in a directory."""
    files = []
    
    if recursive:
        pattern = "**/*"
    else:
        pattern = "*"
    
    for ext in extensions:
        if not ext.startswith('.'):
            ext = '.' + ext
        # Use glob to find matching paths, then filter to only include actual files
        matching_paths = directory.glob(f"{pattern}{ext}")
        files.extend([path for path in matching_paths if path.is_file()])
    
    return files


def normalize_path_separators(path: str) -> str:
    """Normalize path separators for cross-platform compatibility."""
    return path.replace('\\', os.sep).replace('/', os.sep)


def get_relative_path(path: Path, base: Path) -> Optional[Path]:
    """Get relative path from base, return None if not possible."""
    try:
        return path.relative_to(base)
    except ValueError:
        return None


def ensure_directory_exists(directory: Path) -> None:
    """Ensure a directory exists, creating it if necessary."""
    directory.mkdir(parents=True, exist_ok=True)
