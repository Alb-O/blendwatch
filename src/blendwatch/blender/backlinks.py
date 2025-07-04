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

from blendwatch.blender.library_writer import LibraryPathWriter, get_blend_file_libraries
# Import block-level optimizations for enhanced performance
from blendwatch.blender.block_level_optimizations import SelectiveBlockReader, batch_scan_libraries
from blendwatch.blender.cache import BlendFileCache
from blendwatch.core.config import Config, load_default_config
from blendwatch.utils.path_utils import resolve_path, is_path_ignored, find_files_by_extension

# Enhanced asset tracking with blender-asset-tracer
from blender_asset_tracer import trace
from blender_asset_tracer.trace import result, progress

log = logging.getLogger(__name__)

class DependencyInfo(NamedTuple):
    """Information about a dependency found by blender-asset-tracer."""
    asset_path: Path
    block_name: str
    is_sequence: bool
    usage_type: str


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
        
        # Initialize high-performance cache
        self.cache = BlendFileCache()
        
        # Cache the blend file list to avoid repeated directory scanning
        self._blend_files_cache: Optional[List[Path]] = None
        self._blend_files_cache_time: float = 0
        self._cache_timeout: float = 300  # 5 minutes
    
    def _should_ignore_directory(self, directory: Path) -> bool:
        """Check if a directory should be ignored based on config patterns.
        
        Args:
            directory: Directory path to check
            
        Returns:
            True if directory should be ignored, False otherwise
        """
        return is_path_ignored(directory, self.config.ignore_dirs)
    
    def find_blend_files(self, force_refresh: bool = False) -> List[Path]:
        """Find all .blend files using the path utilities with caching.
        
        Args:
            force_refresh: If True, ignore cache and re-scan directory
        
        Returns:
            List of paths to .blend files
        """
        # Check if we can use cached results
        current_time = time.time()
        if (not force_refresh and 
            self._blend_files_cache is not None and 
            current_time - self._blend_files_cache_time < self._cache_timeout):
            return self._blend_files_cache
        
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
        
        # Cache the results
        self._blend_files_cache = filtered_files
        self._blend_files_cache_time = current_time
        
        duration = time.time() - start_time
        log.info(f"Found {len(filtered_files)} blend files in {duration:.2f}s")
        return filtered_files
    
    def _check_blend_file_for_target(self, blend_file: Path, target_asset: Path) -> Optional[BacklinkResult]:
        """Check if a blend file links to the target asset using cache.
        
        Args:
            blend_file: Path to the blend file to check
            target_asset: Path to the target asset to look for
            
        Returns:
            BacklinkResult if the blend file links to the target, None otherwise
        """
        try:
            # Use cache to get library paths
            library_paths = self.cache.get_library_paths(blend_file)
            if library_paths is None:
                return None
            
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
                              max_workers: int = 4, 
                              progress_callback: Optional[progress.Callback] = None) -> List[BacklinkResult]:
        """Find all blend files that link to the target asset.
        
        Args:
            target_asset: Path to the asset to find backlinks for
            max_workers: Number of threads to use for parallel processing
            progress_callback: Optional callback function for progress updates
            
        Returns:
            List of BacklinkResult objects for files that link to the target
        """
        target_asset = resolve_path(str(target_asset))
        # Note: We don't check if target_asset exists anymore because for rename operations,
        # the old path is expected to not exist after the rename
        
        start_time = time.time()
        
        # Find all blend files (cached)
        blend_files = self.find_blend_files()
        
        # Filter out the target file itself if it's a blend file
        if target_asset.suffix.lower() == '.blend':
            blend_files = [f for f in blend_files if f.resolve() != target_asset.resolve()]
        
        log.info(f"Checking {len(blend_files)} blend files for backlinks to {target_asset.name}")
        
        # Progress reporting
        if progress_callback:
            # Simple progress notification for now
            log.info(f"Starting backlink scan for {target_asset.name}")
            
        # Use the cache's optimized bulk operation
        processed = 0
        linking_files = self.cache.get_files_linking_to(str(target_asset), blend_files)
        
        # Convert to BacklinkResult objects
        backlinks = []
        for blend_file in linking_files:
            library_paths = self.cache.get_library_paths(blend_file)
            if library_paths is None:
                continue
            
            # Find which libraries match
            matching_libraries = []
            target_name = target_asset.name
            target_str = str(target_asset)
            
            for lib_name, lib_path in library_paths.items():
                if (target_name in lib_path or 
                    target_str in lib_path or
                    str(target_asset) == lib_path):
                    matching_libraries.append(lib_name)
            
            if matching_libraries:
                backlinks.append(BacklinkResult(
                    blend_file=blend_file,
                    library_paths=library_paths,
                    matching_libraries=matching_libraries
                ))
        
        duration = time.time() - start_time
        
        # Log cache performance
        stats = self.cache.get_stats()
        log.info(f"Found {len(backlinks)} backlinks in {duration:.2f}s "
                f"(cache hit rate: {stats['hit_rate_percent']}%)")
        
        return backlinks
    
    def save_cache(self):
        """Save the cache to disk for future use."""
        self.cache.save()
    
    def get_cache_stats(self) -> Dict[str, Union[int, float]]:
        """Get cache performance statistics."""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Clear all cached data."""
        self.cache.clear()
        self._blend_files_cache = None
        self._blend_files_cache_time = 0

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
    
    def find_blend_files_optimized(self, force_refresh: bool = False) -> List[Path]:
        """Find all .blend files with enhanced block-level pre-filtering.
        
        This optimized version uses block-level I/O to quickly identify which
        files actually contain libraries before adding them to the scan list.
        
        Args:
            force_refresh: If True, ignore cache and re-scan directory
        
        Returns:
            List of paths to .blend files that contain libraries
        """
        # First get all blend files using the standard method
        all_blend_files = self.find_blend_files(force_refresh)
        
        if not all_blend_files:
            return []
        
        # Use block-level pre-filtering to only return files with libraries
        files_with_libraries = []
        for blend_file in all_blend_files:
            try:
                if SelectiveBlockReader.has_libraries(blend_file):
                    files_with_libraries.append(blend_file)
            except Exception as e:
                log.debug(f"Error checking {blend_file} for libraries: {e}")
                # Include file in results on error to be safe
                files_with_libraries.append(blend_file)
        
        log.info(f"Pre-filtered {len(all_blend_files)} files to {len(files_with_libraries)} files with libraries")
        return files_with_libraries
    
    def find_backlinks_to_file_optimized(self, target_asset: Union[str, Path], 
                                        max_workers: int = 4, 
                                        use_prefiltering: bool = True) -> List[BacklinkResult]:
        """Find all blend files that link to the target asset with enhanced optimizations.
        
        This version uses advanced block-level optimizations:
        1. Pre-filters files to only scan those with libraries
        2. Uses batch scanning for better I/O efficiency
        3. Implements selective block reading
        
        Args:
            target_asset: Path to the asset to find backlinks for
            max_workers: Number of threads to use for parallel processing
            use_prefiltering: Whether to use block-level pre-filtering
            
        Returns:
            List of BacklinkResult objects for files that link to the target
        """
        target_asset = resolve_path(str(target_asset))
        start_time = time.time()
        
        # Use optimized file discovery if enabled
        if use_prefiltering:
            blend_files = self.find_blend_files_optimized()
        else:
            blend_files = self.find_blend_files()
        
        # Filter out the target file itself if it's a blend file
        if target_asset.suffix.lower() == '.blend':
            blend_files = [f for f in blend_files if f.resolve() != target_asset.resolve()]
        
        log.info(f"Checking {len(blend_files)} blend files for backlinks to {target_asset.name}")
        
        # Use batch scanning for better performance
        if len(blend_files) > 10:  # Use batch scanning for larger file sets
            batch_results = batch_scan_libraries(blend_files, max_workers=max_workers)
            
            # Convert batch results to BacklinkResult objects
            backlinks = []
            target_name = target_asset.name
            target_str = str(target_asset)
            
            for blend_file, library_paths in batch_results.items():
                matching_libraries = []
                for lib_name, lib_path in library_paths.items():
                    if (target_name in lib_path or 
                        target_str in lib_path or
                        str(target_asset) == lib_path):
                        matching_libraries.append(lib_name)
                
                if matching_libraries:
                    backlinks.append(BacklinkResult(
                        blend_file=blend_file,
                        library_paths=library_paths,
                        matching_libraries=matching_libraries
                    ))
        else:
            # Use standard cache-based approach for smaller file sets
            linking_files = self.cache.get_files_linking_to(str(target_asset), blend_files)
            
            # Convert to BacklinkResult objects
            backlinks = []
            for blend_file in linking_files:
                library_paths = self.cache.get_library_paths(blend_file)
                if library_paths is None:
                    continue
                
                # Find which libraries match
                matching_libraries = []
                target_name = target_asset.name
                target_str = str(target_asset)
                
                for lib_name, lib_path in library_paths.items():
                    if (target_name in lib_path or 
                        target_str in lib_path or
                        str(target_asset) == lib_path):
                        matching_libraries.append(lib_name)
                
                if matching_libraries:
                    backlinks.append(BacklinkResult(
                        blend_file=blend_file,
                        library_paths=library_paths,
                        matching_libraries=matching_libraries
                    ))
        
        duration = time.time() - start_time
        
        # Log performance metrics
        stats = self.cache.get_stats() if hasattr(self, 'cache') else {}
        hit_rate = stats.get('hit_rate_percent', 0)
        log.info(f"Found {len(backlinks)} backlinks in {duration:.2f}s "
                f"(cache hit rate: {hit_rate}%, pre-filtering: {use_prefiltering})")
        
        return backlinks

    def find_all_dependencies(self, blend_file: Union[str, Path], 
                             progress_callback: Optional[progress.Callback] = None) -> List[DependencyInfo]:
        """Find all dependencies of a blend file using blender-asset-tracer.
        
        This method provides comprehensive dependency analysis including:
        - Library files (.blend)
        - Image sequences and UDIMs
        - Individual texture files
        - Sound files
        - Other asset types
        
        Args:
            blend_file: Path to the blend file to analyze
            progress_callback: Optional progress callback for long operations
            
        Returns:
            List of DependencyInfo objects describing all dependencies
        """
        blend_file = resolve_path(str(blend_file))
        if not blend_file.exists():
            raise FileNotFoundError(f"Blend file not found: {blend_file}")
        
        dependencies = []
        
        try:
            log.info(f"Analyzing dependencies for {blend_file.name}")
            
            # Use blender-asset-tracer to find all dependencies
            for block_usage in trace.deps(blend_file, progress_callback):
                # Convert BlockUsage to our DependencyInfo format
                # Handle BlendPath to Path conversion
                asset_path = Path(str(block_usage.asset_path))
                
                # Determine usage type based on block information
                usage_type = "unknown"
                if hasattr(block_usage, 'block') and block_usage.block:
                    if hasattr(block_usage.block, 'code'):
                        block_code = block_usage.block.code
                        if block_code == b'LI':
                            usage_type = "library"
                        elif block_code == b'IM':
                            usage_type = "image"
                        elif block_code == b'SO':
                            usage_type = "sound"
                        else:
                            usage_type = block_code.decode('ascii', errors='ignore')
                
                # Handle block_name conversion from bytes to string
                block_name = "unknown"
                if block_usage.block_name:
                    if isinstance(block_usage.block_name, bytes):
                        block_name = block_usage.block_name.decode('utf-8', errors='ignore')
                    else:
                        block_name = str(block_usage.block_name)
                
                dep_info = DependencyInfo(
                    asset_path=asset_path,
                    block_name=block_name,
                    is_sequence=block_usage.is_sequence,
                    usage_type=usage_type
                )
                dependencies.append(dep_info)
            
            log.info(f"Found {len(dependencies)} dependencies in {blend_file.name}")
            
        except Exception as e:
            log.error(f"Error analyzing dependencies for {blend_file}: {e}")
            raise
        
        return dependencies

    def get_dependency_summary(self, blend_file: Union[str, Path]) -> Dict[str, int]:
        """Get a summary of dependency types for a blend file.
        
        Args:
            blend_file: Path to the blend file to analyze
            
        Returns:
            Dictionary with counts of each dependency type
        """
        dependencies = self.find_all_dependencies(blend_file)
        
        summary = {}
        for dep in dependencies:
            dep_type = dep.usage_type
            if dep.is_sequence:
                dep_type += "_sequence"
            summary[dep_type] = summary.get(dep_type, 0) + 1
        
        return summary

    def find_missing_dependencies(self, blend_file: Union[str, Path]) -> List[DependencyInfo]:
        """Find dependencies that are missing from the filesystem.
        
        Args:
            blend_file: Path to the blend file to analyze
            
        Returns:
            List of DependencyInfo objects for missing dependencies
        """
        dependencies = self.find_all_dependencies(blend_file)
        missing = []
        
        for dep in dependencies:
            if not dep.asset_path.exists():
                # For sequences, check if any file in the sequence exists
                if dep.is_sequence:
                    # For now, just mark as missing if the exact path doesn't exist
                    # TODO: Implement proper sequence checking
                    missing.append(dep)
                else:
                    missing.append(dep)
        
        return missing

    def get_blend_file_dependencies_by_type(self, blend_file: Union[str, Path]) -> Dict[str, List[DependencyInfo]]:
        """Get dependencies grouped by type.
        
        Args:
            blend_file: Path to the blend file to analyze
            
        Returns:
            Dictionary mapping dependency types to lists of dependencies
        """
        dependencies = self.find_all_dependencies(blend_file)
        by_type = {}
        
        for dep in dependencies:
            dep_type = dep.usage_type
            if dep.is_sequence:
                dep_type += "_sequence"
            
            if dep_type not in by_type:
                by_type[dep_type] = []
            by_type[dep_type].append(dep)
        
        return by_type
    


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
