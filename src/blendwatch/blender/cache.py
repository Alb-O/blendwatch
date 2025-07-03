"""
Caching system for BlendWatch to improve performance.

This module provides caching mechanisms to avoid redundant file I/O operations
and speed up library path discovery and backlink scanning.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, asdict
from collections import defaultdict

log = logging.getLogger(__name__)


@dataclass
class CachedBlendFile:
    """Cached information about a blend file."""
    path: str
    mtime: float  # Last modified time
    size: int  # File size
    library_paths: Dict[str, str]  # Library name -> library path mapping
    scan_time: float  # When this was last scanned


@dataclass
class LibraryCache:
    """Cache for library path information."""
    files: Dict[str, CachedBlendFile]  # file_path -> cached_info
    version: str = "1.0"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "files": {path: asdict(cached_file) for path, cached_file in self.files.items()}
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'LibraryCache':
        """Create from dictionary (JSON deserialization)."""
        cache = cls(files={})
        if data.get("version") != "1.0":
            log.warning("Cache version mismatch, starting fresh")
            return cache
        
        files_data = data.get("files", {})
        for path, file_data in files_data.items():
            cache.files[path] = CachedBlendFile(**file_data)
        
        return cache


class BlendFileCache:
    """High-performance cache for blend file library information."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize the cache.
        
        Args:
            cache_dir: Directory to store cache files. If None, uses temp directory.
        """
        if cache_dir is None:
            import tempfile
            cache_dir = Path(tempfile.gettempdir()) / "blendwatch_cache"
        
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "library_cache.json"
        
        # In-memory cache
        self._cache: LibraryCache = self._load_cache()
        
        # Performance metrics
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _load_cache(self) -> LibraryCache:
        """Load cache from disk."""
        if not self.cache_file.exists():
            return LibraryCache(files={})
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return LibraryCache.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            log.warning(f"Failed to load cache: {e}, starting fresh")
            return LibraryCache(files={})
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache.to_dict(), f, indent=2)
        except Exception as e:
            log.warning(f"Failed to save cache: {e}")
    
    def _get_file_info(self, file_path: Path) -> Tuple[float, int]:
        """Get file modification time and size."""
        try:
            stat = file_path.stat()
            return stat.st_mtime, stat.st_size
        except OSError:
            return 0.0, 0
    
    def _is_file_changed(self, file_path: Path, cached_file: CachedBlendFile) -> bool:
        """Check if file has changed since last cache."""
        mtime, size = self._get_file_info(file_path)
        return mtime != cached_file.mtime or size != cached_file.size
    
    def get_library_paths(self, blend_file: Path, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        """Get library paths for a blend file, using cache when possible.
        
        Args:
            blend_file: Path to the blend file
            force_refresh: If True, ignore cache and re-scan file
            
        Returns:
            Dictionary of library paths, or None if file can't be read
        """
        file_str = str(blend_file)
        
        # Check cache
        if not force_refresh and file_str in self._cache.files:
            cached_file = self._cache.files[file_str]
            
            # Check if file hasn't changed
            if not self._is_file_changed(blend_file, cached_file):
                self._cache_hits += 1
                return cached_file.library_paths
        
        # Cache miss - need to read file
        self._cache_misses += 1
        
        try:
            from blendwatch.blender.library_writer import LibraryPathWriter
            writer = LibraryPathWriter(blend_file)
            library_paths = writer.get_library_paths()
            
            # Update cache
            mtime, size = self._get_file_info(blend_file)
            self._cache.files[file_str] = CachedBlendFile(
                path=file_str,
                mtime=mtime,
                size=size,
                library_paths=library_paths,
                scan_time=time.time()
            )
            
            return library_paths
            
        except Exception as e:
            log.warning(f"Failed to read {blend_file}: {e}")
            return None
    
    def get_files_linking_to(self, target_path: str, search_files: List[Path]) -> List[Path]:
        """Find all files that link to a target path.
        
        Args:
            target_path: Path to find links to
            search_files: List of blend files to search
            
        Returns:
            List of blend files that link to the target
        """
        linking_files = []
        target_name = Path(target_path).name
        
        for blend_file in search_files:
            library_paths = self.get_library_paths(blend_file)
            if library_paths is None:
                continue
            
            # Check if any library path matches the target
            for lib_path in library_paths.values():
                if self._paths_match(target_path, lib_path, target_name):
                    linking_files.append(blend_file)
                    break
        
        return linking_files
    
    def _paths_match(self, target_path: str, lib_path: str, target_name: str) -> bool:
        """Check if library path matches target path."""
        # Exact match
        if target_path == lib_path:
            return True
        
        # Filename match
        if target_name in lib_path:
            return True
        
        # Try resolving relative paths
        if lib_path.startswith('//'):
            # This is complex and slow, so only do it if needed
            try:
                # Remove the '//' prefix
                relative_part = lib_path[2:]
                # This would need the blend file's directory to resolve properly
                # For now, just do a simple filename comparison
                lib_name = relative_part.split('/')[-1].split('\\')[-1]
                if lib_name == target_name:
                    return True
            except Exception:
                pass
        
        return False
    
    def invalidate_file(self, blend_file: Path):
        """Remove a file from cache (e.g., if it was modified)."""
        file_str = str(blend_file)
        if file_str in self._cache.files:
            del self._cache.files[file_str]
    
    def cleanup_cache(self, max_age_days: int = 30):
        """Remove old cache entries."""
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        to_remove = []
        for file_path, cached_file in self._cache.files.items():
            # Remove if file doesn't exist or cache is too old
            if (not Path(file_path).exists() or 
                cached_file.scan_time < cutoff_time):
                to_remove.append(file_path)
        
        for file_path in to_remove:
            del self._cache.files[file_path]
        
        log.info(f"Cleaned up {len(to_remove)} old cache entries")
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Get cache performance statistics."""
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate_percent": round(hit_rate, 1),
            "cached_files": len(self._cache.files)
        }
    
    def save(self):
        """Save cache to disk."""
        self._save_cache()
    
    def clear(self):
        """Clear all cache data."""
        self._cache = LibraryCache(files={})
        self._cache_hits = 0
        self._cache_misses = 0
