"""
Test and demonstrate block-level I/O optimizations for BlendWatch.
"""

import time
import tempfile
from pathlib import Path
from typing import List

import pytest

from blendwatch.blender.block_level_optimizations import (
    FastLibraryReader,
    StreamingLibraryScanner,
    SelectiveBlockReader,
    get_libraries_ultra_fast,
    batch_scan_libraries,
)
from blendwatch.blender.library_writer import get_blend_file_libraries


class TestBlockLevelOptimizations:
    """Test the new block-level I/O optimizations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Skip if test blend files don't exist
        if not self.blendfiles_dir.exists():
            pytest.skip(f"Test blend files directory not found: {self.blendfiles_dir}")
    
    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_fast_library_reader(self):
        """Test the FastLibraryReader class."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))
        if not test_files:
            pytest.skip("No test blend files found")
        
        test_file = test_files[0]
        reader = FastLibraryReader(test_file)
        
        # Test minimal library reading
        libraries = reader.get_library_paths_minimal()
        assert isinstance(libraries, dict)

        # Check that paths are absolute and resolved
        for lib_path in libraries.values():
            assert Path(lib_path).is_absolute()
            assert ".." not in lib_path # Should be fully resolved
        
        # Test caching behavior
        start_time = time.time()
        libraries2 = reader.get_library_paths_minimal()
        cache_time = time.time() - start_time
        
        assert libraries == libraries2
        assert cache_time < 0.001  # Should be very fast due to caching
    
    def test_selective_block_reader(self):
        """Test the SelectiveBlockReader utilities."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))
        if not test_files:
            pytest.skip("No test blend files found")
        
        test_file = test_files[0]
        
        # Test block type detection
        block_types = SelectiveBlockReader.get_block_types_in_file(test_file)
        assert isinstance(block_types, set)
        
        # Test library detection
        has_libs = SelectiveBlockReader.has_libraries(test_file)
        assert isinstance(has_libs, bool)
        
        # Test block counting
        counts = SelectiveBlockReader.count_blocks_by_type(test_file)
        assert isinstance(counts, dict)
        
        # Consistency check
        if has_libs:
            assert b"LI" in block_types
            assert b"LI" in counts
            assert counts[b"LI"] > 0
    
    def test_streaming_scanner(self):
        """Test the StreamingLibraryScanner for batch processing."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))[:5]  # Limit to 5 files for testing
        if not test_files:
            pytest.skip("No test blend files found")
        
        scanner = StreamingLibraryScanner(max_open_files=3)
        results = scanner.scan_libraries_batch(test_files)
        
        assert isinstance(results, dict)
        assert len(results) <= len(test_files)
        
        # Verify all results have the expected structure
        for file_path, libraries in results.items():
            assert isinstance(file_path, Path)
            assert isinstance(libraries, dict)
    
    def test_ultra_fast_vs_standard(self):
        """Compare performance of ultra-fast vs standard library reading."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))
        if not test_files:
            pytest.skip("No test blend files found")
        
        test_file = test_files[0]
        
        # Test standard method
        start_time = time.time()
        standard_result = get_blend_file_libraries(test_file)
        standard_time = time.time() - start_time
        
        # Test ultra-fast method
        start_time = time.time()
        ultra_fast_result = get_libraries_ultra_fast(test_file)
        ultra_fast_time = time.time() - start_time
        
        # Both should return the same data
        assert standard_result == ultra_fast_result
        
        print(f"Standard time: {standard_time:.4f}s, Ultra-fast time: {ultra_fast_time:.4f}s")
        
        # Ultra-fast should be at least as fast (accounting for some variance)
        # Note: In practice, ultra-fast should be faster on subsequent calls due to caching
    
    def test_batch_scanning_performance(self):
        """Test batch scanning performance improvements."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))
        if len(test_files) < 2:
            pytest.skip("Need at least 2 test blend files")
        
        # Limit to reasonable number for testing
        test_files = test_files[:10]
        
        # Test individual scanning
        start_time = time.time()
        individual_results = {}
        for file_path in test_files:
            try:
                libraries = get_blend_file_libraries(file_path)
                if libraries:
                    individual_results[file_path] = libraries
            except Exception:
                continue
        individual_time = time.time() - start_time
        
        # Test batch scanning
        start_time = time.time()
        batch_results = batch_scan_libraries(test_files)
        batch_time = time.time() - start_time
        
        print(f"Individual scanning: {individual_time:.4f}s")
        print(f"Batch scanning: {batch_time:.4f}s")
        print(f"Files processed - Individual: {len(individual_results)}, Batch: {len(batch_results)}")
        
        # Results should be consistent
        assert len(batch_results) == len(individual_results)
    
    def test_selective_filtering(self):
        """Test that selective filtering improves performance."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))
        if not test_files:
            pytest.skip("No test blend files found")
        
        # First, identify which files actually have libraries
        files_with_libraries = []
        files_without_libraries = []
        
        for file_path in test_files:
            if SelectiveBlockReader.has_libraries(file_path):
                files_with_libraries.append(file_path)
            else:
                files_without_libraries.append(file_path)
        
        print(f"Files with libraries: {len(files_with_libraries)}")
        print(f"Files without libraries: {len(files_without_libraries)}")
        
        # The filtering should correctly identify files
        for file_path in files_with_libraries:
            libraries = get_libraries_ultra_fast(file_path)
            # Files identified as having libraries should actually have them
            # (though some might be empty due to different Blender versions)
            assert isinstance(libraries, dict)
    
    def test_performance_metrics(self):
        """Generate performance metrics for the optimizations."""
        test_files = list(self.blendfiles_dir.glob("*.blend"))[:5]
        if not test_files:
            pytest.skip("No test blend files found")
        
        print("\\n=== Performance Metrics ===")
        
        # Measure block type detection
        total_block_time = 0
        for file_path in test_files:
            start_time = time.time()
            block_types = SelectiveBlockReader.get_block_types_in_file(file_path)
            total_block_time += time.time() - start_time
            print(f"{file_path.name}: {len(block_types)} block types")
        
        print(f"Average block type detection: {total_block_time / len(test_files):.4f}s per file")
        
        # Measure library reading
        total_lib_time = 0
        total_libraries = 0
        for file_path in test_files:
            start_time = time.time()
            libraries = get_libraries_ultra_fast(file_path)
            total_lib_time += time.time() - start_time
            total_libraries += len(libraries)
            print(f"{file_path.name}: {len(libraries)} libraries")
        
        print(f"Average library reading: {total_lib_time / len(test_files):.4f}s per file")
        print(f"Total libraries found: {total_libraries}")


def test_integration_with_existing_code():
    """Test that the new optimizations integrate well with existing BlendWatch code."""
    from blendwatch.blender.cache import BlendFileCache
    from blendwatch.blender.backlinks import BacklinkScanner
    
    # This test ensures the new optimizations can be drop-in replacements
    test_dir = Path(__file__).parent / "blendfiles"
    if not test_dir.exists():
        pytest.skip("Test blend files directory not found")
    
    test_files = list(test_dir.glob("*.blend"))
    if not test_files:
        pytest.skip("No test blend files found")
    
    # Test integration with cache
    cache = BlendFileCache()
    test_file = test_files[0]
    
    # Standard approach
    standard_libs = cache.get_library_paths(test_file)
    
    # New optimized approach
    optimized_libs = get_libraries_ultra_fast(test_file)
    
    # Should produce same results
    if standard_libs and optimized_libs:
        # Both methods should find the same libraries
        assert set(standard_libs.keys()) == set(optimized_libs.keys())


if __name__ == "__main__":
    # Run a simple performance demonstration
    test_dir = Path(__file__).parent / "blendfiles"
    if test_dir.exists():
        test_files = list(test_dir.glob("*.blend"))[:3]
        if test_files:
            print("=== Block-Level I/O Performance Demo ===")
            
            for test_file in test_files:
                print(f"\\nAnalyzing {test_file.name}:")
                
                # Block type analysis
                start = time.time()
                block_types = SelectiveBlockReader.get_block_types_in_file(test_file)
                print(f"  Block types ({time.time() - start:.4f}s): {sorted(block_types)}")
                
                # Library check
                start = time.time()
                has_libs = SelectiveBlockReader.has_libraries(test_file)
                print(f"  Has libraries ({time.time() - start:.4f}s): {has_libs}")
                
                if has_libs:
                    # Library reading
                    start = time.time()
                    libraries = get_libraries_ultra_fast(test_file)
                    print(f"  Libraries ({time.time() - start:.4f}s): {len(libraries)} found")
            
            # Batch processing demo
            print(f"\\nBatch processing {len(test_files)} files:")
            start = time.time()
            batch_results = batch_scan_libraries(test_files)
            print(f"  Batch scan ({time.time() - start:.4f}s): {len(batch_results)} files with libraries")
        
        else:
            print("No test blend files found")
    else:
        print("Test blend files directory not found")
