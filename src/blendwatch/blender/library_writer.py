"""
Library path writer module for BlendWatch.

This module provides functionality to modify linked library paths in Blender files
without opening them in Blender, using the blender-asset-tracer library.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from blender_asset_tracer import blendfile
from blendwatch.utils.path_utils import resolve_path, get_relative_path
from blendwatch.utils import bytes_to_string
# Import the new block-level optimizations
from .block_level_optimizations import get_libraries_ultra_fast, FastLibraryReader

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
        """Get all library paths in the blend file.
        
        Returns:
            Dictionary mapping library names to their file paths
        """
        library_paths = {}
        
        # Use cached blend file opening for better performance
        with blendfile.open_cached(self.blend_file_path, mode="rb") as bf:
            # Get all library blocks (LI = Library) efficiently
            libraries = bf.code_index.get(b"LI", [])
            
            for library in libraries:
                try:
                    name = library[b"name"]
                    # Try filepath first, fall back to name if filepath doesn't exist
                    try:
                        filepath = library[b"filepath"]
                    except KeyError:
                        # In newer Blender versions, the library path might be stored in the name field
                        filepath = library[b"name"]
                    
                    # Convert bytes to string if needed
                    if isinstance(name, bytes):
                        name = bytes_to_string(name)
                    if isinstance(filepath, bytes):
                        filepath = bytes_to_string(filepath)
                    
                    library_paths[name] = filepath
                except (KeyError, UnicodeDecodeError) as e:
                    log.warning(f"Could not read library info: {e}")
                    continue
        
        return library_paths
    
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
        """Update multiple library paths.
        
        Args:
            path_mapping: Dictionary mapping old paths to new paths
            relative: If True, convert absolute paths to relative format (default: False)
            
        Returns:
            Number of library paths that were updated
        """
        if not path_mapping:
            return 0

        updated_count = 0
        
        # First, check what actually needs updating using cached read access
        current_paths = self.get_library_paths()  # This uses cached access
        libraries_to_update = {}
        
        # Create a more flexible mapping that includes filename-based matching
        flexible_mapping = {}
        for old_path, new_path in path_mapping.items():
            # Skip if trying to map a path to itself (no change needed)
            if old_path == new_path:
                continue
                
            # Add the original mapping
            flexible_mapping[old_path] = new_path
            
            # Add filename-based mapping for cross-platform compatibility
            # Handle Blender relative paths (starting with //) specially
            if old_path.startswith('//'):
                # For Blender relative paths, extract filename manually
                old_filename = old_path[2:].split('/')[-1].split('\\')[-1]
            else:
                old_filename = Path(old_path).name
            
            if old_filename:  # Only add if filename is not empty
                flexible_mapping[old_filename] = new_path
        
        # Check which libraries need updating
        for name, current_filepath in current_paths.items():
            new_path = None
            
            # Strategy 1: Exact path match
            if current_filepath in path_mapping:
                new_path = path_mapping[current_filepath]
            
            # Strategy 2: Filename match (for cross-platform compatibility)
            if new_path is None:
                # Handle Blender relative paths specially
                if current_filepath.startswith('//'):
                    current_filename = current_filepath[2:].split('/')[-1].split('\\')[-1]
                else:
                    current_filename = Path(current_filepath).name
                
                if current_filename and current_filename in flexible_mapping:
                    new_path = flexible_mapping[current_filename]
            
            # Strategy 3: Relative path resolution
            if new_path is None and current_filepath.startswith('//'):
                # Resolve relative path to absolute
                relative_path = current_filepath[2:]  # Remove '//'
                blend_dir = self.blend_file_path.parent
                resolved_path = (blend_dir / relative_path).resolve()
                if str(resolved_path) in path_mapping:
                    new_path = path_mapping[str(resolved_path)]
            
            if new_path is not None:
                libraries_to_update[name] = (current_filepath, new_path)
        
        # Only open in write mode if we have updates to make
        if not libraries_to_update:
            return 0

        # Now perform the actual updates using write mode
        with blendfile.BlendFile(self.blend_file_path, mode="r+b") as bf:
            # Get all library blocks (LI = Library)
            libraries = bf.code_index.get(b"LI", [])
            
            for library in libraries:
                try:
                    # Try filepath first, fall back to name if filepath doesn't exist
                    try:
                        current_filepath = library[b"filepath"]
                    except KeyError:
                        # In newer Blender versions, the library path might be stored in the name field
                        current_filepath = library[b"name"]
                    
                    current_name = library[b"name"]
                    
                    # Convert bytes to string for comparison
                    if isinstance(current_filepath, bytes):
                        current_filepath_str = bytes_to_string(current_filepath)
                    else:
                        current_filepath_str = str(current_filepath).rstrip('\x00')
                    
                    if isinstance(current_name, bytes):
                        current_name_str = bytes_to_string(current_name)
                    else:
                        current_name_str = bytes_to_string(current_name)
                    
                    # Check if this library needs updating
                    if current_name_str in libraries_to_update:
                        old_path, new_path = libraries_to_update[current_name_str]
                        
                        # Convert path based on relative parameter
                        if relative:
                            # Convert new path to relative format
                            try:
                                new_path_obj = resolve_path(new_path)
                                blend_dir = self.blend_file_path.parent
                                relative_path = get_relative_path(new_path_obj, blend_dir)
                                if relative_path is not None:
                                    # Use Blender's relative path format
                                    new_path = '//' + str(relative_path).replace('\\', '/')
                                else:
                                    # If can't make relative, use absolute path
                                    new_path = str(new_path_obj)
                            except (ValueError, OSError):
                                # If path resolution fails, use original path
                                pass
                        
                        # Convert new path to bytes with null termination
                        new_path_bytes = new_path.encode('utf-8') + b'\x00'
                        
                        # Update both fields - try filepath first, fallback to name only if filepath doesn't exist
                        try:
                            library[b"filepath"] = new_path_bytes
                            # For the name field, keep the original library name/identifier if it was relative
                            if not current_name_str.startswith('//'):
                                library[b"name"] = new_path_bytes
                        except KeyError:
                            # If filepath doesn't exist, update name field (newer Blender versions)
                            library[b"name"] = new_path_bytes
                        
                        updated_count += 1
                        log.info(f"Updated library path: {current_filepath_str} -> {new_path}")
                
                except (KeyError, UnicodeDecodeError) as e:
                    log.warning(f"Could not update library: {e}")
                    continue
        
        return updated_count
    
    def update_library_path_by_name(self, library_name: str, new_path: str) -> bool:
        """Update a library path by its name/identifier.
        
        Args:
            library_name: The name/identifier of the library to update
            new_path: The new library path
            
        Returns:
            True if the library was found and updated, False otherwise
        """
        with blendfile.BlendFile(self.blend_file_path, mode="r+b") as bf:
            # Get all library blocks (LI = Library)
            libraries = bf.code_index.get(b"LI", [])
            
            for library in libraries:
                try:
                    current_name = library[b"name"]
                    
                    # Convert bytes to string for comparison
                    if isinstance(current_name, bytes):
                        current_name_str = bytes_to_string(current_name)
                    else:
                        current_name_str = bytes_to_string(current_name)
                    
                    # Check if this is the library we want to update
                    if current_name_str == library_name:
                        # Convert new path to bytes with null termination
                        new_path_bytes = new_path.encode('utf-8') + b'\x00'
                        
                        # Update both filepath and name fields
                        library[b"filepath"] = new_path_bytes
                        library[b"name"] = new_path_bytes
                        
                        log.info(f"Updated library '{library_name}' path to: {new_path}")
                        return True
                
                except (KeyError, UnicodeDecodeError) as e:
                    log.warning(f"Could not check library: {e}")
                    continue
        
        return False
    
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


def update_blend_file_paths(blend_file: Union[str, Path], 
                          path_mapping: Dict[str, str], 
                          relative: bool = False) -> int:
    """Convenience function to update library paths in a blend file.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
        relative: If True, convert absolute paths to relative format (default: False)
        
    Returns:
        Number of library paths that were updated
    """
    writer = LibraryPathWriter(blend_file)
    return writer.update_library_paths(path_mapping, relative=relative)


def get_blend_file_libraries(blend_file: Union[str, Path]) -> Dict[str, str]:
    """Convenience function to get all library paths from a blend file.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    try:
        writer = LibraryPathWriter(blend_file)
        return writer.get_library_paths()
    except FileNotFoundError:
        # Return an empty dictionary for non-existent files to match test expectations
        return {}
    except Exception as e:
        # Log the error but return an empty dict to be consistent with non-existent file behavior
        print(f"Error reading library paths from {blend_file}: {e}")
        return {}


def get_blend_file_libraries_fast(blend_file: Union[str, Path]) -> Dict[str, str]:
    """Fast convenience function to get all library paths from a blend file.
    
    This version uses the most advanced block-level I/O optimizations available,
    including minimal field reading, selective block access, and intelligent caching.
    It returns absolute paths for all libraries.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    from blendwatch.blender.block_level_optimizations import get_libraries_ultra_fast
    
    try:
        return get_libraries_ultra_fast(blend_file)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Error reading library paths from {blend_file} (fast method): {e}")
        return {}


def update_blend_file_paths_fast(blend_file: Union[str, Path], 
                                path_mapping: Dict[str, str], 
                                relative: bool = False) -> int:
    """Fast convenience function to update library paths in a blend file.
    
    This version checks if updates are needed before opening in write mode.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
        relative: If True, convert absolute paths to relative format (default: False)
        
    Returns:
        Number of library paths that were updated
    """
    # First check if any updates are needed using fast cached read
    current_paths = get_blend_file_libraries_fast(blend_file)
    updates_needed = False
    
    for current_path in current_paths.values():
        if current_path in path_mapping:
            updates_needed = True
            break
        # Also check filename-based mapping
        filename = Path(current_path).name if not current_path.startswith('//') else current_path[2:].split('/')[-1].split('\\')[-1]
        if filename in path_mapping:
            updates_needed = True
            break
    
    if not updates_needed:
        return 0
    
    # Only create writer if updates are actually needed
    writer = LibraryPathWriter(blend_file)
    return writer.update_library_paths(path_mapping, relative=relative)


def get_blend_file_libraries_ultra_fast(blend_file: Union[str, Path]) -> Dict[str, str]:
    """DEPRECATED: Use get_blend_file_libraries_fast instead.
    
    Ultra-fast convenience function using advanced block-level optimizations.
    
    This version uses the most advanced block-level I/O optimizations available,
    including minimal field reading, selective block access, and intelligent caching.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    import warnings
    warnings.warn(
        "get_blend_file_libraries_ultra_fast is deprecated, use get_blend_file_libraries_fast instead",
        DeprecationWarning,
        stacklevel=2
    )
    return get_libraries_ultra_fast(blend_file)


def update_blend_file_paths_with_precheck(blend_file: Union[str, Path], 
                                         path_mapping: Dict[str, str], 
                                         relative: bool = False) -> int:
    """Ultra-fast update function with intelligent pre-checking.
    
    This version uses block-level optimizations to first check if the file
    even has libraries before attempting any updates.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
        relative: If True, convert absolute paths to relative format (default: False)
        
    Returns:
        Number of library paths that were updated
    """
    from .block_level_optimizations import SelectiveBlockReader
    
    # Fast pre-check: does this file even have libraries?
    if not SelectiveBlockReader.has_libraries(Path(blend_file)):
        return 0
    
    # Use the existing fast update function
    return update_blend_file_paths_fast(blend_file, path_mapping, relative=relative)
