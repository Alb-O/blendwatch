"""
Library path writer module for BlendWatch.

This module provides functionality to modify linked library paths in Blender files
without opening them in Blender, using the blender-asset-tracer library.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Union
from blender_asset_tracer import blendfile

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
        self.blend_file_path = Path(blend_file_path)
        if not self.blend_file_path.exists():
            raise FileNotFoundError(f"Blend file not found: {self.blend_file_path}")
        if not self.blend_file_path.suffix.lower() == '.blend':
            raise ValueError(f"File must be a .blend file: {self.blend_file_path}")
    
    def get_library_paths(self) -> Dict[str, str]:
        """Get all library paths in the blend file.
        
        Returns:
            Dictionary mapping library names to their file paths
        """
        library_paths = {}
        
        with blendfile.BlendFile(self.blend_file_path, mode="rb") as bf:
            # Get all library blocks (LI = Library)
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
                        name = name.decode('utf-8', errors='replace').rstrip('\x00')
                    if isinstance(filepath, bytes):
                        filepath = filepath.decode('utf-8', errors='replace').rstrip('\x00')
                    
                    library_paths[name] = filepath
                except (KeyError, UnicodeDecodeError) as e:
                    log.warning(f"Could not read library info: {e}")
                    continue
        
        return library_paths
    
    def update_library_path(self, old_path: str, new_path: str) -> bool:
        """Update a single library path.
        
        Args:
            old_path: The current library path to replace
            new_path: The new library path
            
        Returns:
            True if the path was found and updated, False otherwise
        """
        return self.update_library_paths({old_path: new_path}) > 0
    
    def update_library_paths(self, path_mapping: Dict[str, str]) -> int:
        """Update multiple library paths.
        
        Args:
            path_mapping: Dictionary mapping old paths to new paths
            
        Returns:
            Number of library paths that were updated
        """
        if not path_mapping:
            return 0
        
        updated_count = 0
        
        # Create a more flexible mapping that includes filename-based matching
        flexible_mapping = {}
        for old_path, new_path in path_mapping.items():
            # Add the original mapping
            flexible_mapping[old_path] = new_path
            
            # Add filename-based mapping for cross-platform compatibility
            old_filename = Path(old_path).name
            flexible_mapping[old_filename] = new_path
        
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
                        current_filepath_str = current_filepath.decode('utf-8', errors='replace').rstrip('\x00')
                    else:
                        current_filepath_str = str(current_filepath).rstrip('\x00')
                    
                    # Check for matches using multiple strategies
                    new_path = None
                    
                    # Strategy 1: Exact path match
                    if current_filepath_str in path_mapping:
                        new_path = path_mapping[current_filepath_str]
                    
                    # Strategy 2: Filename match (for cross-platform compatibility)
                    if new_path is None:
                        current_filename = Path(current_filepath_str).name
                        if current_filename in flexible_mapping:
                            new_path = flexible_mapping[current_filename]
                    
                    # Strategy 3: Relative path resolution
                    if new_path is None and current_filepath_str.startswith('//'):
                        # Resolve relative path to absolute
                        relative_path = current_filepath_str[2:]  # Remove '//'
                        blend_dir = self.blend_file_path.parent
                        resolved_path = (blend_dir / relative_path).resolve()
                        if str(resolved_path) in path_mapping:
                            new_path = path_mapping[str(resolved_path)]
                    
                    if new_path is not None:
                        # Convert new path to bytes with null termination
                        new_path_bytes = new_path.encode('utf-8') + b'\x00'
                        
                        # Update both fields - try filepath first, fallback to name only if filepath doesn't exist
                        try:
                            library[b"filepath"] = new_path_bytes
                            # For the name field, keep the original library name/identifier if it was relative
                            current_name = library[b"name"]
                            if isinstance(current_name, bytes):
                                current_name_str = current_name.decode('utf-8', errors='replace').rstrip('\x00')
                            else:
                                current_name_str = str(current_name).rstrip('\x00')
                            
                            # Only update name if it was an absolute path (not a relative reference like //file.blend)
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
                        current_name_str = current_name.decode('utf-8', errors='replace').rstrip('\x00')
                    else:
                        current_name_str = str(current_name).rstrip('\x00')
                    
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
            base_path = Path(base_path)
        
        converted_count = 0
        path_mapping = {}
        
        # Get current library paths
        current_paths = self.get_library_paths()
        
        for name, filepath in current_paths.items():
            # Skip if already relative
            if filepath.startswith('//'):
                continue
            
            try:
                abs_path = Path(filepath)
                if abs_path.is_absolute():
                    # Convert to relative path
                    rel_path = Path('//') / abs_path.relative_to(base_path)
                    path_mapping[filepath] = str(rel_path).replace('\\', '/')
                    converted_count += 1
            except (ValueError, OSError):
                # Path cannot be made relative
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
            base_path = Path(base_path)
        
        converted_count = 0
        path_mapping = {}
        
        # Get current library paths
        current_paths = self.get_library_paths()
        
        for name, filepath in current_paths.items():
            # Only process relative paths (those starting with //)
            if filepath.startswith('//'):
                try:
                    # Remove the // prefix and make absolute
                    rel_part = filepath[2:]
                    abs_path = base_path / rel_part
                    path_mapping[filepath] = str(abs_path.resolve())
                    converted_count += 1
                except (ValueError, OSError):
                    # Path cannot be made absolute
                    log.warning(f"Cannot make path absolute: {filepath}")
                    continue
        
        # Apply the updates
        if path_mapping:
            self.update_library_paths(path_mapping)
        
        return converted_count


def update_blend_file_paths(blend_file: Union[str, Path], 
                          path_mapping: Dict[str, str]) -> int:
    """Convenience function to update library paths in a blend file.
    
    Args:
        blend_file: Path to the .blend file
        path_mapping: Dictionary mapping old paths to new paths
        
    Returns:
        Number of library paths that were updated
    """
    writer = LibraryPathWriter(blend_file)
    return writer.update_library_paths(path_mapping)


def get_blend_file_libraries(blend_file: Union[str, Path]) -> Dict[str, str]:
    """Convenience function to get all library paths from a blend file.
    
    Args:
        blend_file: Path to the .blend file
        
    Returns:
        Dictionary mapping library names to their file paths
    """
    writer = LibraryPathWriter(blend_file)
    return writer.get_library_paths()
