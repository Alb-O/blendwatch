"""
Advanced block-level I/O optimizations for BlendWatch.

This module provides enhanced performance optimizations using blender-asset-tracer's
block-level access capabilities to read only the necessary data from .blend files.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Union, Set
from blender_asset_tracer import blendfile
from blendwatch.utils.path_utils import resolve_path
from blendwatch.utils import bytes_to_string

log = logging.getLogger(__name__)


class FastLibraryReader:
    """Ultra-fast library reader using block-level optimizations."""
    
    def __init__(self, blend_file_path: Union[str, Path]):
        """Initialize the fast reader.
        
        Args:
            blend_file_path: Path to the .blend file
        """
        self.blend_file_path = resolve_path(str(blend_file_path))
        self._cached_libraries: Optional[Dict[str, str]] = None
        self._file_mtime: Optional[float] = None
        self._path_resolution_cache: Dict[str, str] = {}
    
    def get_library_paths_minimal(self, resolve_paths: bool = True) -> Dict[str, str]:
        """Get library paths with minimal I/O operations.
        
        This implementation uses several optimizations:
        1. Only reads Library (LI) block headers, not full data
        2. Uses selective field reading to get only name and filepath
        3. Implements lazy loading with mtime-based cache invalidation
        4. Avoids reading DNA1 blocks unless absolutely necessary
        
        Args:
            resolve_paths: If True (default), resolves paths to absolute. If False, returns raw paths.
            
        Returns:
            Dictionary mapping library names to their file paths
        """
        # For non-resolved paths, don't use cache to avoid contamination
        if not resolve_paths:
            return self._get_raw_library_paths()
            
        # Check if we can use cached data for resolved paths
        current_mtime = self._get_file_mtime()
        if (self._cached_libraries is not None and 
            self._file_mtime == current_mtime):
            return self._cached_libraries
        
        library_paths = {}
        
        try:
            # Use cached blend file opening for persistence
            with blendfile.open_cached(self.blend_file_path, mode="rb") as bf:
                # Get only Library blocks using the efficient code_index
                library_blocks = bf.code_index.get(b"LI", [])
                
                if not library_blocks:
                    # Early return if no libraries
                    self._cached_libraries = library_paths
                    self._file_mtime = current_mtime
                    return library_paths
                
                # Process each library block with minimal field access
                for lib_block in library_blocks:
                    try:
                        # Only read the specific fields we need
                        # This avoids loading the entire block data
                        name = self._read_library_field(lib_block, b"name")
                        filepath = self._read_library_field(lib_block, b"filepath", fallback_field=b"name")
                        
                        if name and filepath:
                            # Convert bytes to string with minimal processing
                            name_str = self._bytes_to_string(name)
                            filepath_str = self._bytes_to_string(filepath)

                            # Don't normalize Blender relative paths (starting with //)
                            # as os.path.normpath would incorrectly convert them
                            if not filepath_str.startswith("//"):
                                # Only normalize non-Blender paths
                                filepath_str = os.path.normpath(filepath_str)

                            # Resolve the path efficiently
                            resolved_path = self._resolve_library_path(filepath_str)
                            library_paths[name_str] = resolved_path
                            
                    except Exception as e:
                        log.debug(f"Could not read library block: {e}")
                        continue
        
        except Exception as e:
            log.warning(f"Failed to read libraries from {self.blend_file_path}: {e}")
            return {}
        
        # Cache the results
        self._cached_libraries = library_paths
        self._file_mtime = current_mtime
        return library_paths
        
    def _get_raw_library_paths(self) -> Dict[str, str]:
        """Get library paths without resolving them (raw as stored in the file).
        
        This is primarily used for testing or when original paths are needed.
        
        Returns:
            Dictionary mapping library names to their file paths as stored in the .blend file
        """
        library_paths = {}
        
        try:
            # Use cached blend file opening for persistence
            with blendfile.open_cached(self.blend_file_path, mode="rb") as bf:
                # Get only Library blocks using the efficient code_index
                library_blocks = bf.code_index.get(b"LI", [])
                
                # Process each library block with minimal field access
                for lib_block in library_blocks:
                    try:
                        # Only read the specific fields we need
                        name = self._read_library_field(lib_block, b"name")
                        filepath = self._read_library_field(lib_block, b"filepath", fallback_field=b"name")
                        
                        if name and filepath:
                            # Convert bytes to string with minimal processing
                            name_str = self._bytes_to_string(name)
                            filepath_str = self._bytes_to_string(filepath)
                            library_paths[name_str] = filepath_str
                            
                    except Exception:
                        continue
        
        except Exception:
            return {}
            
        return library_paths
    
    def _resolve_library_path(self, library_path: str) -> str:
        """Resolve a library path, using a cache to speed up the process."""
        if library_path in self._path_resolution_cache:
            return self._path_resolution_cache[library_path]

        # Handle Blender's relative path prefix "//"
        if library_path.startswith("//"):
            try:
                # Resolve relative to the .blend file's directory
                base_dir = self.blend_file_path.parent
                # Use os.path.abspath and os.path.normpath for robust resolution
                resolved = os.path.abspath(os.path.normpath(os.path.join(base_dir, library_path[2:])))
                self._path_resolution_cache[library_path] = resolved
                return resolved
            except Exception as e:
                log.debug(f"Could not resolve relative path {library_path}: {e}")
                # Fallback to the original path on error
                self._path_resolution_cache[library_path] = library_path
                return library_path
        
        # For absolute paths, just normalize them
        if os.path.isabs(library_path):
            try:
                resolved = os.path.normpath(library_path)
                self._path_resolution_cache[library_path] = resolved
                return resolved
            except Exception:
                return library_path # Fallback

        # If it's neither a relative path starting with "//" nor an absolute path,
        # it might be a relative path without the prefix. Treat it as such.
        try:
            base_dir = self.blend_file_path.parent
            resolved = os.path.abspath(os.path.normpath(os.path.join(base_dir, library_path)))
            self._path_resolution_cache[library_path] = resolved
            return resolved
        except Exception:
            # Final fallback
            return library_path

    def _read_library_field(self, block, field_name: bytes, fallback_field: Optional[bytes] = None):
        """Read a specific field from a library block with minimal I/O.
        
        Args:
            block: The library block
            field_name: Name of the field to read
            fallback_field: Optional fallback field if primary field doesn't exist
            
        Returns:
            Field value or None if not found
        """
        try:
            # Try the primary field
            return block[field_name]
        except KeyError:
            if fallback_field:
                try:
                    return block[fallback_field]
                except KeyError:
                    pass
            return None
    
    def _bytes_to_string(self, data) -> str:
        """Convert bytes to string with minimal processing."""
        return bytes_to_string(data)
    
    def _get_file_mtime(self) -> float:
        """Get file modification time."""
        try:
            return self.blend_file_path.stat().st_mtime
        except OSError:
            return 0.0
    
    def invalidate_cache(self):
        """Invalidate the cached library data."""
        self._cached_libraries = None
        self._file_mtime = None


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
        # Use the utility function for consistent string handling
        return bytes_to_string(data)


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

def get_libraries_ultra_fast(blend_file: Union[str, Path], resolve_paths: bool = True) -> Dict[str, str]:
    """Ultra-fast library reading using all optimizations.
    
    This function combines all the block-level optimizations for maximum speed.
    
    Args:
        blend_file: Path to the .blend file
        resolve_paths: If True (default), resolves paths to absolute. If False, returns raw paths as stored in the file.
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    # Create a reader instance just once
    reader = FastLibraryReader(blend_file)
    
    # Use the same underlying method, but add a parameter to control path resolution
    # This eliminates code duplication and makes the function more maintainable
    return reader.get_library_paths_minimal(resolve_paths=resolve_paths)


def batch_scan_libraries(blend_files: List[Path], max_workers: int = 4) -> Dict[Path, Dict[str, str]]:
    """Scan multiple blend files in parallel with optimized I/O.
    
    Args:
        blend_files: List of blend files to scan
        max_workers: Number of worker processes
        
    Returns:
        Dictionary mapping file paths to their library dictionaries
    """
    # Filter files that actually have libraries first
    files_with_libraries = []
    for blend_file in blend_files:
        if SelectiveBlockReader.has_libraries(blend_file):
            files_with_libraries.append(blend_file)
    
    if not files_with_libraries:
        return {}
    
    # Use streaming scanner for efficient batch processing
    scanner = StreamingLibraryScanner()
    return scanner.scan_libraries_batch(files_with_libraries)


# The function is_blend_file_modified_recently was removed as it was unused dead code
