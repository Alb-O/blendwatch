"""
Backlinks module for BlendWatch.

This module provides functionality to find reverse dependencies (backlinks) - 
which blend files link to a given asset or library file.
"""

import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Union, Set, NamedTuple, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed

from blendwatch.blender.library_writer import LibraryPathWriter
from blendwatch.core.config import Config, load_default_config
from blendwatch.utils.path_utils import resolve_path, is_path_ignored, find_files_by_extension

log = logging.getLogger(__name__)

class BacklinkResult(NamedTuple):
    """Result of a backlink search."""
    blend_file: Path
    library_paths: Dict[str, str]
    matching_libraries: List[str]


class BacklinkScanner:
    """Scanner for finding backlinks to blend files and assets."""
    
    def __init__(self, search_directory: Union[str, Path], config: Optional[Config] = None):
        """Initialize the backlink scanner.
        
        Args:
            search_directory: Directory to search for blend files
            config: Configuration object with ignore patterns. If None, uses default config.
        """
        self.search_directory = resolve_path(str(search_directory))
        if not self.search_directory.exists():
            raise FileNotFoundError(f"Search directory not found: {self.search_directory}")
        if not self.search_directory.is_dir():
            raise ValueError(f"Search path must be a directory: {self.search_directory}")
        
        # Use provided config or load default
        self.config = config if config is not None else load_default_config()
        
        # Compile regex patterns for ignore directories
        self.ignore_patterns = []
        for pattern in self.config.ignore_dirs:
            try:
                self.ignore_patterns.append(re.compile(pattern))
            except re.error as e:
                log.warning(f"Invalid ignore pattern '{pattern}': {e}")
    
    def _should_ignore_directory(self, directory: Path) -> bool:
        """Check if a directory should be ignored based on config patterns.
        
        Args:
            directory: Directory path to check
            
        Returns:
            True if directory should be ignored, False otherwise
        """
        return is_path_ignored(directory, self.config.ignore_dirs)
    
    def find_blend_files(self) -> List[Path]:
        """Find all .blend files using the path utilities.
        
        Returns:
            List of paths to .blend files
        """
        start_time = time.time()
        
        # Use the utility function to find blend files
        blend_files = find_files_by_extension(self.search_directory, ['.blend'], recursive=True)
        
        # Filter out files in ignored directories
        filtered_files = []
        for blend_file in blend_files:
            # Check if any parent directory should be ignored
            should_ignore = False
            for parent in blend_file.parents:
                if parent == self.search_directory:
                    break  # Don't check the search directory itself
                if self._should_ignore_directory(parent):
                    should_ignore = True
                    break
            
            if not should_ignore:
                filtered_files.append(blend_file)
        
        duration = time.time() - start_time
        log.info(f"Found {len(filtered_files)} blend files in {duration:.2f}s")
        return filtered_files
    
    def _check_blend_file_for_target(self, blend_file: Path, target_asset: Path) -> Optional[BacklinkResult]:
        """Check if a blend file links to the target asset.
        
        Args:
            blend_file: Path to the blend file to check
            target_asset: Path to the target asset to look for
            
        Returns:
            BacklinkResult if the blend file links to the target, None otherwise
        """
        try:
            writer = LibraryPathWriter(blend_file)
            library_paths = writer.get_library_paths()
            
            # Look for matches in library paths
            matching_libraries = []
            target_name = target_asset.name
            target_str = str(target_asset)
            
            for lib_name, lib_path in library_paths.items():
                # Check for exact filename matches or path matches
                if (target_name in lib_path or 
                    target_str in lib_path or
                    target_asset.resolve() == Path(lib_path).resolve()):
                    matching_libraries.append(lib_name)
            
            if matching_libraries:
                return BacklinkResult(
                    blend_file=blend_file,
                    library_paths=library_paths,
                    matching_libraries=matching_libraries
                )
            
        except Exception as e:
            log.warning(f"Could not check {blend_file}: {e}")
        
        return None
    
    def find_backlinks_to_file(self, target_asset: Union[str, Path], 
                              max_workers: int = 4) -> List[BacklinkResult]:
        """Find all blend files that link to the target asset.
        
        Args:
            target_asset: Path to the asset to find backlinks for
            max_workers: Number of threads to use for parallel processing
            
        Returns:
            List of BacklinkResult objects for files that link to the target
        """
        target_asset = resolve_path(str(target_asset))
        # Note: We don't check if target_asset exists anymore because for rename operations,
        # the old path is expected to not exist after the rename
        
        start_time = time.time()
        
        # Find all blend files
        blend_files = self.find_blend_files()
        
        # Filter out the target file itself if it's a blend file
        if target_asset.suffix.lower() == '.blend':
            blend_files = [f for f in blend_files if f.resolve() != target_asset.resolve()]
        
        log.info(f"Checking {len(blend_files)} blend files for backlinks to {target_asset.name}")
        
        # Check files in parallel
        backlinks = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {
                executor.submit(self._check_blend_file_for_target, blend_file, target_asset): blend_file
                for blend_file in blend_files
            }
            
            # Collect results
            for future in as_completed(future_to_file):
                result = future.result()
                if result is not None:
                    backlinks.append(result)
        
        duration = time.time() - start_time
        log.info(f"Found {len(backlinks)} backlinks in {duration:.2f}s")
        
        return backlinks
    
    def find_backlinks_to_multiple_files(self, target_assets: Sequence[Union[str, Path]], 
                                       max_workers: int = 4) -> Dict[Path, List[BacklinkResult]]:
        """Find backlinks for multiple target assets.
        
        Args:
            target_assets: List of assets to find backlinks for
            max_workers: Number of threads to use for parallel processing
            
        Returns:
            Dictionary mapping target assets to their backlink results
        """
        target_assets = [resolve_path(str(asset)) for asset in target_assets]
        results = {}
        
        # Find all blend files once
        blend_files = self.find_blend_files()
        
        for target_asset in target_assets:
            log.info(f"Finding backlinks for {target_asset.name}")
            
            # Filter out the target file itself if it's a blend file
            files_to_check = blend_files
            if target_asset.suffix.lower() == '.blend':
                files_to_check = [f for f in blend_files if f.resolve() != target_asset.resolve()]
            
            backlinks = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self._check_blend_file_for_target, blend_file, target_asset): blend_file
                    for blend_file in files_to_check
                }
                
                for future in as_completed(future_to_file):
                    result = future.result()
                    if result is not None:
                        backlinks.append(result)
            
            results[target_asset] = backlinks
            log.info(f"Found {len(backlinks)} backlinks for {target_asset.name}")
        
        return results


def find_backlinks(target_asset: Union[str, Path], 
                  search_directory: Union[str, Path],
                  max_workers: int = 4,
                  config: Optional[Config] = None) -> List[BacklinkResult]:
    """Convenience function to find backlinks to a target asset.
    
    Args:
        target_asset: Path to the asset to find backlinks for
        search_directory: Directory to search for blend files
        max_workers: Number of threads to use for parallel processing
        config: Configuration object with ignore patterns. If None, uses default config.
        
    Returns:
        List of BacklinkResult objects for files that link to the target
    """
    scanner = BacklinkScanner(search_directory, config=config)
    return scanner.find_backlinks_to_file(target_asset, max_workers=max_workers)
