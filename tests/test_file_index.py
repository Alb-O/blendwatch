"""
Tests for the file index module
"""

import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from blendwatch.core.file_index import FileIndex, FileInfo


class TestFileInfo:
    """Test the FileInfo dataclass"""
    
    def test_file_info_creation(self):
        """Test FileInfo creation and properties"""
        info = FileInfo(
            path="/test/path/file.blend",
            size=1024,
            mtime=1234567890.0
        )
        
        assert info.path == "/test/path/file.blend"
        assert info.size == 1024
        assert info.mtime == 1234567890.0
        assert info.checksum is None
    
    def test_file_info_equality(self):
        """Test FileInfo equality comparison"""
        info1 = FileInfo("/test/file.blend", 1024, 1234567890.0)
        info2 = FileInfo("/test/file.blend", 1024, 1234567890.0)
        info3 = FileInfo("/test/file.blend", 1024, 1234567891.0)  # Different time
        info4 = FileInfo("/test/file.blend", 2048, 1234567890.0)  # Different size
        
        assert info1 == info2
        assert info1 != info3  # Different time beyond tolerance
        assert info1 != info4  # Different size
    
    def test_file_info_time_tolerance(self):
        """Test FileInfo time tolerance in equality"""
        info1 = FileInfo("/test/file.blend", 1024, 1234567890.0)
        info2 = FileInfo("/test/file.blend", 1024, 1234567890.5)  # 0.5s difference
        info3 = FileInfo("/test/file.blend", 1024, 1234567892.0)  # 2s difference
        
        assert info1 == info2  # Within tolerance
        assert info1 != info3  # Beyond tolerance
    
    def test_file_info_hash(self):
        """Test FileInfo hash functionality"""
        info1 = FileInfo("/test/file.blend", 1024, 1234567890.0)
        info2 = FileInfo("/test/file.blend", 1024, 1234567890.0)
        
        assert hash(info1) == hash(info2)
        
        # Should be usable in sets
        info_set = {info1, info2}
        assert len(info_set) == 1  # Should be deduplicated


class TestFileIndex:
    """Test the FileIndex class"""
    
    def test_file_index_initialization(self, tmp_path):
        """Test FileIndex initialization"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend', '.py'],
            rescan_interval=300
        )
        
        assert index.watch_path == tmp_path
        assert index.extensions == {'.blend', '.py'}
        assert index.rescan_interval == 300
        assert index.correlation_window == 10.0
        assert len(index.current_files) == 0
        assert len(index.recent_deletions) == 0
        assert len(index.recent_creations) == 0
    
    def test_file_index_initial_scan(self, tmp_path):
        """Test that initial scan finds existing files"""
        # Create test files
        (tmp_path / "test1.blend").write_text("content1")
        (tmp_path / "test2.py").write_text("content2")
        (tmp_path / "test3.txt").write_text("content3")  # Should be ignored
        
        # Create subdirectory with files
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.blend").write_text("nested content")
        
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend', '.py'],
            rescan_interval=0
        )
        
        index.rescan()
        
        # Should find .blend and .py files but not .txt
        assert index.get_file_count() == 3
        assert index.is_file_tracked(str(tmp_path / "test1.blend"))
        assert index.is_file_tracked(str(tmp_path / "test2.py"))
        assert index.is_file_tracked(str(subdir / "nested.blend"))
        assert not index.is_file_tracked(str(tmp_path / "test3.txt"))
    
    def test_record_deletion_and_creation(self, tmp_path):
        """Test recording file deletions and creations"""
        test_file = tmp_path / "test.blend"
        test_file.write_text("content")
        
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        index.rescan()
        assert index.get_file_count() == 1
        
        # Record deletion
        index.record_deletion(str(test_file))
        
        # File should be removed from current files and added to recent deletions
        assert index.get_file_count() == 0
        assert len(index.recent_deletions) == 1
        assert str(test_file) in index.recent_deletions
    
    def test_move_detection(self, tmp_path):
        """Test move detection through deletion/creation correlation"""
        source_file = tmp_path / "source.blend"
        source_file.write_text("content")
        
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        index.rescan()
        
        # Record deletion of source file
        index.record_deletion(str(source_file))
        
        # Create target file with same content
        target_dir = tmp_path / "target"
        target_dir.mkdir()
        target_file = target_dir / "source.blend"
        target_file.write_text("content")
        
        # Record creation should detect the move
        move_result = index.record_creation(str(target_file))
        
        assert move_result is not None
        old_path, new_path = move_result
        assert old_path == str(source_file)
        assert new_path == str(target_file)
    
    def test_no_false_positive_moves(self, tmp_path):
        """Test that new file creation doesn't trigger false move detection"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Create a completely new file
        new_file = tmp_path / "new.blend"
        new_file.write_text("content")
        
        # Should not detect any move
        move_result = index.record_creation(str(new_file))
        assert move_result is None
    
    def test_get_files_in_directory_recursive(self, tmp_path):
        """Test getting files in directory recursively"""
        # Create nested structure
        subdir1 = tmp_path / "sub1"
        subdir2 = tmp_path / "sub1" / "sub2"
        subdir1.mkdir()
        subdir2.mkdir()
        
        (tmp_path / "root.blend").write_text("root")
        (subdir1 / "sub1.blend").write_text("sub1")
        (subdir2 / "sub2.blend").write_text("sub2")
        
        # Create other directory and file
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        (other_dir / "other.blend").write_text("other")
        
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        index.rescan()
        
        # Get files in sub1 directory (should include subdirectories)
        files_in_sub1 = index.get_files_in_directory(str(subdir1))
        
        assert len(files_in_sub1) == 2  # sub1.blend and sub2.blend
        assert str(subdir1 / "sub1.blend") in files_in_sub1
        assert str(subdir2 / "sub2.blend") in files_in_sub1
        assert str(tmp_path / "root.blend") not in files_in_sub1
    
    def test_correlation_window_cleanup(self, tmp_path):
        """Test that old events are cleaned up"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Record some events
        index.recent_deletions["/old/file1.blend"] = (
            FileInfo("/old/file1.blend", 1024, 123456789.0),
            1000.0
        )
        index.recent_creations["/new/file1.blend"] = (
            FileInfo("/new/file1.blend", 1024, 123456789.0),
            1000.0
        )
        
        # Mock time to trigger cleanup
        with patch('time.time', return_value=1020.0):  # 20 seconds later
            index._cleanup_old_events()
        
        # Events should be cleaned up (beyond 10s correlation window)
        assert len(index.recent_deletions) == 0
        assert len(index.recent_creations) == 0
    
    def test_matching_deletion_logic(self, tmp_path):
        """Test the logic for finding matching deletions"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Create file info for testing
        old_file_info = FileInfo("/old/test.blend", 1024, 1234567890.0)
        new_file_info = FileInfo("/new/test.blend", 1024, 1234567890.5)  # Slightly different time
        
        # Add to recent deletions
        index.recent_deletions["/old/test.blend"] = (old_file_info, time.time())
        
        # Test matching
        match = index._find_matching_deletion(new_file_info)
        
        assert match is not None
        matched_path, matched_info = match
        assert matched_path == "/old/test.blend"
        assert matched_info == old_file_info
    
    def test_different_sizes_no_match(self, tmp_path):
        """Test that files with different sizes don't match"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Create file info with different sizes
        old_file_info = FileInfo("/old/test.blend", 1024, 1234567890.0)
        new_file_info = FileInfo("/new/test.blend", 2048, 1234567890.0)  # Different size
        
        # Add to recent deletions
        index.recent_deletions["/old/test.blend"] = (old_file_info, time.time())
        
        # Test matching
        match = index._find_matching_deletion(new_file_info)
        
        assert match is None  # Should not match due to different size
    
    def test_different_names_no_match(self, tmp_path):
        """Test that files with different names don't match"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Create file info with different names
        old_file_info = FileInfo("/old/test1.blend", 1024, 1234567890.0)
        new_file_info = FileInfo("/new/test2.blend", 1024, 1234567890.0)  # Different name
        
        # Add to recent deletions
        index.recent_deletions["/old/test1.blend"] = (old_file_info, time.time())
        
        # Test matching
        match = index._find_matching_deletion(new_file_info)
        
        assert match is None  # Should not match due to different filename
    
    def test_start_stop_lifecycle(self, tmp_path):
        """Test the start/stop lifecycle of FileIndex"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=1  # Short interval for testing
        )
        
        # Start should initialize and begin background thread
        index.start()
        assert index._rescan_thread is not None
        assert index._rescan_thread.is_alive()
        
        # Store reference to thread for checking after stop
        thread = index._rescan_thread
        
        # Stop should terminate background thread
        index.stop()
        time.sleep(0.1)  # Give thread time to stop
        assert not thread.is_alive()
    
    def test_rescan_interval_zero_no_thread(self, tmp_path):
        """Test that rescan_interval=0 doesn't start background thread"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        index.start()
        assert index._rescan_thread is None
        
        index.stop()  # Should not error
    
    def test_get_recent_events_summary(self, tmp_path):
        """Test getting a summary of recent events"""
        index = FileIndex(
            watch_path=str(tmp_path),
            extensions=['.blend'],
            rescan_interval=0
        )
        
        # Add some test data
        index.current_files["/test1.blend"] = FileInfo("/test1.blend", 1024, 123456789.0)
        index.current_files["/test2.blend"] = FileInfo("/test2.blend", 2048, 123456790.0)
        
        index.recent_deletions["/old.blend"] = (
            FileInfo("/old.blend", 512, 123456788.0),
            time.time()
        )
        
        index.recent_creations["/new.blend"] = (
            FileInfo("/new.blend", 1024, 123456791.0),
            time.time()
        )
        
        summary = index.get_recent_events_summary()
        
        assert summary['tracked_files'] == 2
        assert summary['recent_deletions'] == 1
        assert summary['recent_creations'] == 1
