"""
Library path writer module for BlendWatch.

This module provides functionality to modify linked library paths in Blender files
without opening them in Blender, using optimized block-level I/O operations.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Union
from blender_asset_tracer import blendfile
from blendwatch.utils.path_utils import resolve_path, get_relative_path, bytes_to_string
from .block_level_optimizations import get_libraries_ultra_fast, SelectiveBlockReader

log = logging.getLogger(__name__)


class LibraryPathWriter:
    """Writes/updates library paths in Blender files.
    
    This class allows modifying linked library paths directly in .blend files
    without opening them in Blender, using the blender-asset-tracer library.
    """
    
    def __init__(self, blend_file_path: Union[str, Path]):
        """Initialize the library path writer.
        
        Args:
            blend_file_path: Path to the .blend file to modify
        """
        self.blend_file_path = resolve_path(str(blend_file_path))
        if not self.blend_file_path.exists():
            raise FileNotFoundError(f"Blend file not found: {self.blend_file_path}")
        if not self.blend_file_path.is_file():
            raise ValueError(f"Path must be a file, not a directory: {self.blend_file_path}")
        if not self.blend_file_path.suffix.lower() == '.blend':
            raise ValueError(f"File must be a .blend file: {self.blend_file_path}")
    
    def get_library_paths(self) -> Dict[str, str]:
        """Get all library paths in the blend file using optimized I/O.
        
        Returns:
            Dictionary mapping library names to their file paths
        """
        return get_libraries_ultra_fast(self.blend_file_path, resolve_paths=False)
    
    def update_library_path(self, old_path: str, new_path: str, relative: bool = False) -> bool:
        """Update a single library path.
        
        Args:
            old_path: The current library path to replace
            new_path: The new library path
            relative: If True, convert absolute paths to relative format (default: False)
            
        Returns:
            True if the path was found and updated, False otherwise
        """
        return self.update_library_paths({old_path: new_path}, relative=relative) > 0
    
    def update_library_paths(self, path_mapping: Dict[str, str], relative: bool = False) -> int:
        """Update multiple library paths using optimized matching and I/O.
        
        Args:
            path_mapping: Dictionary mapping old paths to new paths
            relative: If True, convert absolute paths to relative format (default: False)
            
        Returns:
            Number of library paths that were updated
        """
        if not path_mapping:
            log.debug("No path mapping provided")
            return 0

        # Fast pre-check: does this file even have libraries?
        if not SelectiveBlockReader.has_libraries(self.blend_file_path):
            log.debug("File has no libraries, skipping update")
            return 0

        log.debug(f"Updating library paths in {self.blend_file_path}")
        log.debug(f"Path mapping: {path_mapping}")
        
        # First, check what actually needs updating using fast read
        current_paths = self.get_library_paths()
        log.debug(f"Found {len(current_paths)} libraries: {current_paths}")
        
        # Find matches using comprehensive strategy
        libraries_to_update = self._find_matching_libraries(current_paths, path_mapping)
        
        # Only open in write mode if we have updates to make
        if not libraries_to_update:
            log.debug("No libraries found that need updating")
            if log.isEnabledFor(logging.DEBUG):
                self._debug_path_matching(current_paths, path_mapping)
            return 0

        log.info(f"Found {len(libraries_to_update)} libraries to update: {libraries_to_update}")
        
        # Perform the actual updates
        return self._write_library_updates(libraries_to_update, relative)
    
    def update_library_path_by_name(self, library_name: str, new_path: str) -> bool:
        """Update a library path by its name/identifier.
        
        Args:
            library_name: The name/identifier of the library to update
            new_path: The new library path
            
        Returns:
            True if the library was found and updated, False otherwise
        """
        # Use the standard update method with a single mapping
        result = self.update_library_paths({library_name: new_path})
        return result > 0
    
    def make_paths_relative(self, base_path: Optional[Union[str, Path]] = None) -> int:
        """Convert absolute library paths to relative paths.
        
        Args:
            base_path: Base path for relative conversion. If None, uses the blend file's directory.
            
        Returns:
            Number of paths converted to relative
        """
        if base_path is None:
            base_path = self.blend_file_path.parent
        else:
            base_path = resolve_path(str(base_path))
        
        converted_count = 0
        path_mapping = {}
        
        # Get current library paths
        current_paths = self.get_library_paths()
        
        for name, filepath in current_paths.items():
            # Skip if already relative
            if filepath.startswith('//'):
                continue
            try:
                abs_path = resolve_path(filepath)
                rel_path = get_relative_path(abs_path, base_path)
                if rel_path is not None:
                    rel_path = Path('//') / rel_path
                    path_mapping[filepath] = str(rel_path).replace('\\', '/')
                    converted_count += 1
            except (ValueError, OSError):
                log.warning(f"Cannot make path relative: {filepath}")
                continue
        
        # Apply the updates
        if path_mapping:
            self.update_library_paths(path_mapping)
        
        return converted_count
    
    def make_paths_absolute(self, base_path: Optional[Union[str, Path]] = None) -> int:
        """Convert relative library paths to absolute paths.
        
        Args:
            base_path: Base path for absolute conversion. If None, uses the blend file's directory.
            
        Returns:
            Number of paths converted to absolute
        """
        if base_path is None:
            base_path = self.blend_file_path.parent
        else:
            base_path = resolve_path(str(base_path))
        
        converted_count = 0
        path_mapping = {}
        
        # Get current library paths
        current_paths = self.get_library_paths()
        
        for name, filepath in current_paths.items():
            # Only process relative paths (those starting with //)
            if filepath.startswith('//'):
                try:
                    rel_part = filepath[2:]
                    abs_path = resolve_path(str(base_path / rel_part))
                    path_mapping[filepath] = str(abs_path)
                    converted_count += 1
                except (ValueError, OSError):
                    log.warning(f"Cannot make path absolute: {filepath}")
                    continue
        
        # Apply the updates
        if path_mapping:
            self.update_library_paths(path_mapping)
        
        return converted_count

    def _find_matching_libraries(self, current_paths: Dict[str, str], path_mapping: Dict[str, str]) -> Dict[str, tuple]:
        """Find libraries that need updating using comprehensive matching strategies.
        
        Args:
            current_paths: Current library paths in the blend file
            path_mapping: Dictionary mapping old paths to new paths
            
        Returns:
            Dictionary mapping library names to (old_path, new_path) tuples
        """
        libraries_to_update = {}
        
        # Create comprehensive mapping with multiple representations
        flexible_mapping = {}
        normalized_mapping = {}
        
        for old_path, new_path in path_mapping.items():
            if old_path == new_path:
                continue
                
            # Add original mapping
            flexible_mapping[old_path] = new_path
            
            # Add normalized path mapping
            try:
                normalized_old = str(Path(old_path).resolve())
                normalized_mapping[normalized_old] = new_path
                flexible_mapping[normalized_old] = new_path
            except (OSError, ValueError):
                pass
            
            # Add filename-based mapping
            old_filename = None
            if old_path.startswith('//'):
                rel_part = old_path[2:]
                if rel_part:
                    old_filename = Path(rel_part).name
            else:
                old_filename = Path(old_path).name
            
            if old_filename:
                flexible_mapping[old_filename] = new_path
            
            # Add case-insensitive mapping (Windows)
            flexible_mapping[old_path.lower()] = new_path
        
        # Check each library for matches
        for name, current_filepath in current_paths.items():
            new_path = self._find_path_match(current_filepath, path_mapping, normalized_mapping, flexible_mapping)
            if new_path is not None:
                libraries_to_update[name] = (current_filepath, new_path)
        
        return libraries_to_update
    
    def _find_path_match(self, current_filepath: str, path_mapping: Dict[str, str], 
                        normalized_mapping: Dict[str, str], flexible_mapping: Dict[str, str]) -> Optional[str]:
        """Find a matching new path for the current filepath using multiple strategies."""
        
        # Strategy 1: Exact path match
        if current_filepath in path_mapping:
            log.debug(f"Strategy 1 match: {current_filepath} -> {path_mapping[current_filepath]}")
            return path_mapping[current_filepath]
        
        # Strategy 2: Normalized path match
        try:
            if current_filepath.startswith('//'):
                rel_part = current_filepath[2:]
                blend_dir = self.blend_file_path.parent
                normalized_current = str((blend_dir / rel_part).resolve())
            else:
                normalized_current = str(Path(current_filepath).resolve())
            
            if normalized_current in normalized_mapping:
                log.debug(f"Strategy 2 match: {current_filepath} (normalized: {normalized_current}) -> {normalized_mapping[normalized_current]}")
                return normalized_mapping[normalized_current]
        except (OSError, ValueError):
            pass
        
        # Strategy 3: Case-insensitive match
        current_lower = current_filepath.lower()
        if current_lower in flexible_mapping:
            log.debug(f"Strategy 3 match: {current_filepath} (case-insensitive) -> {flexible_mapping[current_lower]}")
            return flexible_mapping[current_lower]
        
        # Strategy 4: Filename match
        current_filename = None
        if current_filepath.startswith('//'):
            rel_part = current_filepath[2:]
            if rel_part:
                current_filename = Path(rel_part).name
        else:
            current_filename = Path(current_filepath).name
        
        if current_filename and current_filename in flexible_mapping:
            log.debug(f"Strategy 4 match: {current_filepath} (filename: {current_filename}) -> {flexible_mapping[current_filename]}")
            return flexible_mapping[current_filename]
        
        # Strategy 5: Resolve relative path and check again
        if current_filepath.startswith('//'):
            try:
                relative_path = current_filepath[2:]
                blend_dir = self.blend_file_path.parent
                resolved_path = (blend_dir / relative_path).resolve()
                resolved_str = str(resolved_path)
                
                if resolved_str in path_mapping:
                    log.debug(f"Strategy 5 match: {current_filepath} (resolved: {resolved_str}) -> {path_mapping[resolved_str]}")
                    return path_mapping[resolved_str]
                elif resolved_str.lower() in flexible_mapping:
                    log.debug(f"Strategy 5 case-insensitive match: {current_filepath} (resolved: {resolved_str}) -> {flexible_mapping[resolved_str.lower()]}")
                    return flexible_mapping[resolved_str.lower()]
            except (OSError, ValueError):
                pass
        
        return None
    
    def _write_library_updates(self, libraries_to_update: Dict[str, tuple], relative: bool) -> int:
        """Write the library updates to the blend file.
        
        Args:
            libraries_to_update: Dictionary mapping library names to (old_path, new_path) tuples
            relative: Whether to convert paths to relative format
            
        Returns:
            Number of libraries updated
        """
        updated_count = 0
        
        with blendfile.BlendFile(self.blend_file_path, mode="r+b") as bf:
            libraries = bf.code_index.get(b"LI", [])
            
            for library in libraries:
                try:
                    # Get current filepath and name
                    try:
                        current_filepath = library[b"filepath"]
                    except KeyError:
                        current_filepath = library[b"name"]
                    
                    current_name = library[b"name"]
                    
                    # Convert to strings
                    current_filepath_str = bytes_to_string(current_filepath) if isinstance(current_filepath, bytes) else str(current_filepath).rstrip('\x00')
                    current_name_str = bytes_to_string(current_name) if isinstance(current_name, bytes) else bytes_to_string(current_name)
                    
                    # Check if this library needs updating
                    if current_name_str in libraries_to_update:
                        old_path, new_path = libraries_to_update[current_name_str]
                        
                        # Convert to relative if requested
                        if relative:
                            new_path = self._convert_to_relative_path(new_path)
                        
                        # Update the library
                        new_path_bytes = new_path.encode('utf-8') + b'\x00'
                        
                        try:
                            library[b"filepath"] = new_path_bytes
                            if not current_name_str.startswith('//'):
                                library[b"name"] = new_path_bytes
                        except KeyError:
                            library[b"name"] = new_path_bytes
                        
                        updated_count += 1
                        log.info(f"Updated library path: {current_filepath_str} -> {new_path}")
                
                except (KeyError, UnicodeDecodeError) as e:
                    log.warning(f"Could not update library: {e}")
                    continue
        
        return updated_count
    
    def _convert_to_relative_path(self, absolute_path: str) -> str:
        """Convert an absolute path to Blender relative format if possible."""
        try:
            new_path_obj = resolve_path(absolute_path)
            blend_dir = self.blend_file_path.parent
            relative_path = get_relative_path(new_path_obj, blend_dir)
            if relative_path is not None:
                return '//' + str(relative_path).replace('\\', '/')
            else:
                return str(new_path_obj)
        except (ValueError, OSError):
            return absolute_path
    
    def _debug_path_matching(self, current_paths: Dict[str, str], path_mapping: Dict[str, str]) -> None:
        """Debug function to show detailed path matching information."""
        log.info(f"=== LIBRARY PATH DEBUG for {self.blend_file_path} ===")
        log.info(f"Found {len(current_paths)} libraries in blend file:")
        
        for name, filepath in current_paths.items():
            log.info(f"  Library '{name}' -> '{filepath}'")
            
        log.info(f"Path mapping contains {len(path_mapping)} entries:")
        for old_path, new_path in path_mapping.items():
            log.info(f"  '{old_path}' -> '{new_path}'")
            
        log.info("=== Attempting matches ===")
        for name, current_filepath in current_paths.items():
            found_match = False
            
            if current_filepath in path_mapping:
                log.info(f"✓ EXACT match for '{current_filepath}' -> '{path_mapping[current_filepath]}'")
                found_match = True
                
            if not found_match:
                try:
                    if current_filepath.startswith('//'):
                        rel_part = current_filepath[2:]
                        blend_dir = self.blend_file_path.parent
                        normalized_current = str((blend_dir / rel_part).resolve())
                    else:
                        normalized_current = str(Path(current_filepath).resolve())
                        
                    if normalized_current in path_mapping:
                        log.info(f"✓ NORMALIZED match for '{current_filepath}' (normalized: '{normalized_current}') -> '{path_mapping[normalized_current]}'")
                        found_match = True
                except (OSError, ValueError) as e:
                    log.info(f"  Could not normalize '{current_filepath}': {e}")
                    
            if not found_match:
                current_filename = None
                if current_filepath.startswith('//'):
                    rel_part = current_filepath[2:]
                    if rel_part:
                        current_filename = Path(rel_part).name
                else:
                    current_filename = Path(current_filepath).name
                    
                if current_filename:
                    for old_path, new_path in path_mapping.items():
                        if old_path.startswith('//'):
                            old_filename = Path(old_path[2:]).name if old_path[2:] else None
                        else:
                            old_filename = Path(old_path).name
                            
                        if old_filename and old_filename == current_filename:
                            log.info(f"✓ FILENAME match for '{current_filepath}' (filename: '{current_filename}') matches '{old_path}' -> '{new_path}'")
                            found_match = True
                            break
                            
            if not found_match:
                log.info(f"✗ NO match found for '{current_filepath}'")
                
        log.info("=== END DEBUG ===")


# Public API Functions
# ===================

def get_blend_file_libraries(blend_file: Union[str, Path]) -> Dict[str, str]:
    """Get all library paths from a blend file.
    
    Uses optimized block-level I/O for maximum performance and returns resolved absolute paths.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary mapping library names to their file paths (resolved to absolute)
    """
    try:
        return get_libraries_ultra_fast(blend_file, resolve_paths=True)
    except FileNotFoundError:
        return {}
    except Exception as e:
        log.warning(f"Error reading library paths from {blend_file}: {e}")
        return {}


def update_blend_file_paths(blend_file: Union[str, Path], 
                          path_mapping: Dict[str, str], 
                          relative: bool = False) -> int:
    """Update library paths in a blend file.
    
    Uses optimized matching strategies and I/O operations for maximum performance.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
        relative: If True, convert absolute paths to relative format (default: False)
        
    Returns:
        Number of library paths that were updated
    """
    try:
        writer = LibraryPathWriter(blend_file)
        return writer.update_library_paths(path_mapping, relative=relative)
    except FileNotFoundError:
        log.warning(f"Blend file not found: {blend_file}")
        return 0
    except Exception as e:
        log.error(f"Error updating library paths in {blend_file}: {e}")
        return 0


def debug_blend_file_libraries(blend_file: Union[str, Path], path_mapping: Dict[str, str]) -> None:
    """Debug function to analyze library paths and mapping for a blend file.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
    """
    try:
        writer = LibraryPathWriter(blend_file)
        current_paths = writer.get_library_paths()
        writer._debug_path_matching(current_paths, path_mapping)
    except Exception as e:
        print(f"Error debugging library paths for {blend_file}: {e}")
