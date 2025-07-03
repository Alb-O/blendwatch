"""
Advanced block-level I/O optimizations for BlendWatch.

This module provides enhanced performance optimizations using blender-asset-tracer's
block-level access capabilities to read only the necessary data from .blend files.
"""

import logging
import os
from pathlib import Path, PurePath
from typing import Dict, List, Optional, Union, Set
from blender_asset_tracer import blendfile, bpathlib
from blendwatch.utils.path_utils import resolve_path
import time

log = logging.getLogger(__name__)


class FastLibraryReader:
    """Ultra-fast library path reader that minimizes I/O."""
    
    def __init__(self, blend_file: Union[str, Path]):
        self.blend_file = Path(blend_file)
        self._library_paths = None  # Cache for library paths
        self._path_resolution_cache: Dict[bytes, str] = {}
        self._base_dir = bpathlib.BlendPath(str(self.blend_file.parent).encode('utf-8'))
        self._block_index = None  # Cache for block positions
        
    def _build_block_index(self):
        """Build an index of block positions for faster seeking."""
        self._block_index = {}
        try:
            with open(self.blend_file, 'rb') as f:
                # Check if it's a blend file
                magic = f.read(7)
                if magic != b'BLENDER':
                    log.error(f"Not a blend file: {self.blend_file}")
                    return
                
                f.seek(12)  # Skip header
                pos = 12
                while True:
                    block_header = f.read(20)
                    if not block_header or len(block_header) < 20:
                        break
                    block_code = block_header[:4]
                    block_size = int.from_bytes(block_header[4:8], byteorder='little')
                    self._block_index[pos] = (block_code, block_size)
                    pos += 20 + block_size
                    f.seek(pos)
        except Exception as e:
            log.error(f"Error building block index for {self.blend_file}: {e}")
            self._block_index = None
        
    def _resolve_library_path(self, raw_path: bytes) -> str:
        """Resolve a library path using efficient caching."""
        if raw_path in self._path_resolution_cache:
            return self._path_resolution_cache[raw_path]
        
        # Use BlendPath for efficient path resolution
        blend_path = bpathlib.BlendPath(raw_path)
        if not blend_path.is_absolute():
            blend_path = self._base_dir / blend_path
            
        resolved = str(blend_path.absolute())
        self._path_resolution_cache[raw_path] = resolved
        return resolved
        
    def get_library_paths(self) -> Set[str]:
        """Get all library paths from the blend file."""
        if self._library_paths is not None:
            return self._library_paths
            
        libraries = set()
        
        # Build block index if needed
        if self._block_index is None:
            self._build_block_index()
            if self._block_index is None:
                return set()
        
        try:
            with open(self.blend_file, 'rb') as f:
                # Process only library blocks using the index
                for pos, (block_code, block_size) in self._block_index.items():
                    if block_code == b'LI\x00\x00':  # Library block
                        f.seek(pos + 20)  # Skip header
                        block_data = f.read(block_size)
                        if block_data:
                            try:
                                path_end = block_data.index(b'\x00')
                                lib_path = block_data[:path_end]
                                if lib_path:
                                    resolved_path = self._resolve_library_path(lib_path)
                                    libraries.add(resolved_path)
                            except ValueError:
                                pass
                                
        except Exception as e:
            log.error(f"Error reading blend file {self.blend_file}: {e}")
            return set()
            
        self._library_paths = libraries
        return libraries


class StreamingLibraryScanner:
    """Streaming scanner for processing large numbers of blend files efficiently."""
    
    def __init__(self, max_open_files: int = 10):
        """Initialize the streaming scanner.
        
        Args:
            max_open_files: Maximum number of files to keep open simultaneously
        """
        self.max_open_files = max_open_files
        self._open_files: Dict[Path, blendfile.BlendFile] = {}
        self._access_order: List[Path] = []
    
    def scan_libraries_batch(self, blend_files: List[Path]) -> Dict[Path, Dict[str, str]]:
        """Scan multiple blend files for libraries with optimized I/O.
        
        This method implements several optimizations:
        1. Keeps a limited number of files open to reduce open/close overhead
        2. Uses block-level access to read only Library blocks
        3. Processes files in batches to optimize memory usage
        4. Implements intelligent file handle management
        
        Args:
            blend_files: List of blend file paths to scan
            
        Returns:
            Dictionary mapping file paths to their library dictionaries
        """
        results = {}
        
        for blend_file in blend_files:
            try:
                library_paths = self._get_libraries_from_open_file(blend_file)
                if library_paths:
                    results[blend_file] = library_paths
            except Exception as e:
                log.warning(f"Failed to scan {blend_file}: {e}")
                continue
        
        # Clean up any remaining open files
        self._cleanup_open_files()
        return results
    
    def _get_libraries_from_open_file(self, blend_file: Path) -> Dict[str, str]:
        """Get libraries from a file, managing the open file cache."""
        # Get or open the blend file
        bf = self._get_or_open_file(blend_file)
        if not bf:
            return {}
        
        library_paths = {}
        
        try:
            # Use block-level access for efficiency
            library_blocks = bf.code_index.get(b"LI", [])
            
            for lib_block in library_blocks:
                try:
                    # Read fields with minimal I/O
                    try:
                        name = lib_block[b"name"]
                    except KeyError:
                        continue
                    try:
                        filepath = lib_block[b"filepath"]
                    except KeyError:
                        filepath = name
                    
                    if name and filepath:
                        name_str = self._safe_decode(name)
                        filepath_str = self._safe_decode(filepath)
                        library_paths[name_str] = filepath_str
                        
                except Exception as e:
                    log.debug(f"Could not read library block in {blend_file}: {e}")
                    continue
        
        except Exception as e:
            log.warning(f"Failed to access library blocks in {blend_file}: {e}")
        
        return library_paths
    
    def _get_or_open_file(self, blend_file: Path) -> Optional[blendfile.BlendFile]:
        """Get an open blend file or open it, managing the cache."""
        if blend_file in self._open_files:
            # Move to end of access order
            self._access_order.remove(blend_file)
            self._access_order.append(blend_file)
            return self._open_files[blend_file]
        
        # Need to open the file
        try:
            # Check if we need to close old files first
            if len(self._open_files) >= self.max_open_files:
                self._close_oldest_file()
            
            # Open the new file using the cached approach
            bf = blendfile.open_cached(blend_file, mode="rb")
            self._open_files[blend_file] = bf
            self._access_order.append(blend_file)
            return bf
            
        except Exception as e:
            log.warning(f"Failed to open {blend_file}: {e}")
            return None
    
    def _close_oldest_file(self):
        """Close the least recently used file."""
        if not self._access_order:
            return
        
        oldest_file = self._access_order.pop(0)
        if oldest_file in self._open_files:
            try:
                # Note: Don't manually close cached files, let blender-asset-tracer handle it
                del self._open_files[oldest_file]
            except Exception as e:
                log.debug(f"Error removing file from cache: {e}")
    
    def _cleanup_open_files(self):
        """Clean up all open files."""
        self._open_files.clear()
        self._access_order.clear()
    
    def _safe_decode(self, data) -> str:
        """Safely decode bytes to string."""
        if isinstance(data, bytes):
            return data.decode('utf-8', errors='replace').rstrip('\x00')
        return str(data).rstrip('\x00')


class SelectiveBlockReader:
    """Reader that can selectively read only specific block types."""
    
    @staticmethod
    def get_block_types_in_file(blend_file: Path) -> Set[bytes]:
        """Get all block types present in a file without reading block data.
        
        This is useful for quickly determining if a file contains specific
        block types (like libraries) without parsing the entire file.
        
        Args:
            blend_file: Path to the blend file
            
        Returns:
            Set of block type codes present in the file
        """
        block_types = set()
        
        try:
            with blendfile.open_cached(blend_file, mode="rb") as bf:
                # Just get the keys from code_index - this is very fast
                block_types = set(bf.code_index.keys())
        except Exception as e:
            log.warning(f"Failed to read block types from {blend_file}: {e}")
        
        return block_types
    
    @staticmethod
    def has_libraries(blend_file: Path) -> bool:
        """Quick check if a file has any library blocks.
        
        This is much faster than reading the actual library data.
        
        Args:
            blend_file: Path to the blend file
            
        Returns:
            True if file contains library blocks
        """
        try:
            with blendfile.open_cached(blend_file, mode="rb") as bf:
                return b"LI" in bf.code_index
        except Exception:
            return False
    
    @staticmethod
    def count_blocks_by_type(blend_file: Path) -> Dict[bytes, int]:
        """Count blocks by type without reading block data.
        
        Args:
            blend_file: Path to the blend file
            
        Returns:
            Dictionary mapping block types to their counts
        """
        counts = {}
        
        try:
            with blendfile.open_cached(blend_file, mode="rb") as bf:
                for block_type, blocks in bf.code_index.items():
                    counts[block_type] = len(blocks)
        except Exception as e:
            log.warning(f"Failed to count blocks in {blend_file}: {e}")
        
        return counts


# Utility functions for enhanced performance

def get_libraries_ultra_fast(blend_file: Union[str, Path]) -> Dict[str, str]:
    """Get library paths using ultra-fast block-level optimizations.
    
    Args:
        blend_file: Path to the blend file
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    scanner = StreamingLibraryScanner(max_open_files=1)
    results = scanner.scan_libraries_batch([Path(blend_file)])
    scanner._cleanup_open_files()
    return results.get(Path(blend_file), {})


def batch_scan_libraries(blend_files: List[Path], max_workers: int = 4, chunk_size: int = 10) -> Dict[Path, Dict[str, str]]:
    """Process multiple blend files in batches for optimal performance.
    
    Args:
        blend_files: List of blend files to process
        max_workers: Maximum number of parallel workers (unused for now)
        chunk_size: Number of files to process in each batch
        
    Returns:
        Dictionary mapping file paths to their library dictionaries
    """
    results = {}
    
    # Process files in chunks for better memory management
    for i in range(0, len(blend_files), chunk_size):
        chunk = blend_files[i:i + chunk_size]
        scanner = StreamingLibraryScanner(max_open_files=chunk_size)
        chunk_results = scanner.scan_libraries_batch(chunk)
        results.update(chunk_results)
        
        # Force cleanup after each chunk
        scanner._cleanup_open_files()
        
    return results


def is_blend_file_modified_recently(blend_file: Path, threshold_seconds: float = 300) -> bool:
    """Check if a blend file was modified recently.
    
    This can be used to prioritize rescanning of recently modified files.
    
    Args:
        blend_file: Path to the blend file
        threshold_seconds: Time threshold in seconds
        
    Returns:
        True if file was modified within the threshold
    """
    try:
        mtime = blend_file.stat().st_mtime
        return (time.time() - mtime) < threshold_seconds
    except OSError:
        return False
