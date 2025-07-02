"""
Integration tests for BlendWatch
"""

import json
import tempfile
import time
from pathlib import Path
from threading import Thread

import pytest

from blendwatch.watcher import FileWatcher
from blendwatch.config import Config, load_config


class TestIntegration:
    """Integration tests for the complete BlendWatch system"""
    
    def test_complete_workflow(self):
        """Test complete workflow: config -> watcher -> events"""
        # Create a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test subdirectories
            src_dir = temp_path / "src"
            dst_dir = temp_path / "dst"
            src_dir.mkdir()
            dst_dir.mkdir()
            
            # Create test files
            test_file = src_dir / "test.py"
            test_file.write_text("# Test file")
            
            # Create output file for logging
            log_file = temp_path / "events.log"
            
            # Set up watcher
            watcher = FileWatcher(
                watch_path=str(temp_path),
                extensions=['.py'],
                ignore_dirs=[],
                output_file=str(log_file),
                verbose=False,
                recursive=True
            )
            
            # Start watching
            watcher.start()
            
            try:
                # Give watcher time to start
                time.sleep(0.1)
                
                # Perform file operations
                new_file = dst_dir / "moved_test.py"
                test_file.rename(new_file)
                
                # Give watcher time to detect changes
                time.sleep(0.2)
                
                # Check events were recorded
                events = watcher.get_events()
                assert len(events) > 0
                
                # Check the event details
                event = events[0]
                assert event['type'] in ['file_moved', 'file_renamed']
                assert str(src_dir / "test.py") in event['old_path']
                assert str(dst_dir / "moved_test.py") in event['new_path']
                
                # Check log file was created and contains data
                if log_file.exists():
                    with open(log_file, 'r') as f:
                        log_content = f.read()
                        assert len(log_content) > 0
                        # Should contain JSON data
                        lines = log_content.strip().split('\n')
                        for line in lines:
                            if line.strip():
                                event_data = json.loads(line)
                                assert 'timestamp' in event_data
                                assert 'type' in event_data
                                assert 'old_path' in event_data
                                assert 'new_path' in event_data
                
            finally:
                watcher.stop()
    
    def test_extension_filtering(self):
        """Test that extension filtering works correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test files with different extensions
            py_file = temp_path / "test.py"
            txt_file = temp_path / "test.txt"
            jpg_file = temp_path / "test.jpg"
            
            py_file.write_text("# Python file")
            txt_file.write_text("Text file")
            jpg_file.write_bytes(b"fake jpg data")
            
            # Set up watcher to only watch .py files
            watcher = FileWatcher(
                watch_path=str(temp_path),
                extensions=['.py'],
                ignore_dirs=[],
                output_file=None,
                verbose=False,
                recursive=True
            )
            
            watcher.start()
            
            try:
                time.sleep(0.1)
                
                # Move all files
                py_file.rename(temp_path / "moved.py")
                txt_file.rename(temp_path / "moved.txt")
                jpg_file.rename(temp_path / "moved.jpg")
                
                time.sleep(0.2)
                
                # Should only have one event (for .py file)
                events = watcher.get_events()
                assert len(events) == 1
                assert events[0]['old_path'].endswith('.py')
                assert events[0]['new_path'].endswith('.py')
                
            finally:
                watcher.stop()
    
    def test_ignore_patterns(self):
        """Test that ignore patterns work correctly"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create directories to test ignore patterns
            normal_dir = temp_path / "normal"
            git_dir = temp_path / ".git"
            cache_dir = temp_path / "__pycache__"
            
            normal_dir.mkdir()
            git_dir.mkdir()
            cache_dir.mkdir()
            
            # Create test files
            normal_file = normal_dir / "test.py"
            git_file = git_dir / "config"
            cache_file = cache_dir / "test.pyc"
            
            normal_file.write_text("# Normal file")
            git_file.write_text("git config")
            cache_file.write_bytes(b"compiled python")
            
            # Set up watcher with ignore patterns
            watcher = FileWatcher(
                watch_path=str(temp_path),
                extensions=['.py', '.pyc'],  # Include both to test filtering
                ignore_dirs=[r'\.git', r'__pycache__'],
                output_file=None,
                verbose=False,
                recursive=True
            )
            
            watcher.start()
            
            try:
                time.sleep(0.1)
                
                # Move all files
                normal_file.rename(normal_dir / "moved.py")
                git_file.rename(git_dir / "moved_config")
                cache_file.rename(cache_dir / "moved.pyc")
                
                time.sleep(0.2)
                
                # Should only have one event (for normal file)
                events = watcher.get_events()
                assert len(events) == 1
                assert 'normal' in events[0]['old_path']
                
            finally:
                watcher.stop()
    
    def test_config_integration(self):
        """Test loading config and using it with watcher"""
        # Create config file
        toml_content = '''
extensions = [".py", ".txt"]
ignore_dirs = ["test_ignore", "\\\\.git"]
output_format = "json"
log_level = "info"
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as config_file:
            config_file.write(toml_content)
            config_file.flush()
            
            # Load config
            config = load_config(config_file.name)
            assert config is not None
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Use config with watcher
                watcher = FileWatcher(
                    watch_path=temp_dir,
                    extensions=config.extensions,
                    ignore_dirs=config.ignore_dirs,
                    output_file=None,
                    verbose=False,
                    recursive=True
                )
                
                assert watcher.extensions == [".py", ".txt"]
                assert "test_ignore" in watcher.ignore_dirs
                assert r"\.git" in watcher.ignore_dirs
    
    def test_rename_vs_move_detection(self):
        """Test that the system correctly distinguishes renames from moves"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create subdirectories
            dir1 = temp_path / "dir1"
            dir2 = temp_path / "dir2"
            dir1.mkdir()
            dir2.mkdir()
            
            # Create test files
            file1 = dir1 / "test.py"
            file2 = dir1 / "rename_me.py"
            
            file1.write_text("# File for moving")
            file2.write_text("# File for renaming")
            
            watcher = FileWatcher(
                watch_path=str(temp_path),
                extensions=['.py'],
                ignore_dirs=[],
                output_file=None,
                verbose=False,
                recursive=True
            )
            
            watcher.start()
            
            try:
                time.sleep(0.1)
                
                # Perform rename (same directory)
                file2.rename(dir1 / "renamed.py")
                time.sleep(0.1)
                
                # Perform move (different directory)
                file1.rename(dir2 / "test.py")
                time.sleep(0.1)
                
                events = watcher.get_events()
                assert len(events) == 2
                
                # Check event types
                event_types = [event['type'] for event in events]
                assert 'renamed' in str(event_types)
                assert 'moved' in str(event_types)
                
            finally:
                watcher.stop()
    
    def test_directory_operations(self):
        """Test tracking directory moves and renames"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create test directory
            test_dir = temp_path / "test_directory"
            test_dir.mkdir()
            
            # Create a file inside to make sure it's not empty
            (test_dir / "file.py").write_text("# Test file")
            
            watcher = FileWatcher(
                watch_path=str(temp_path),
                extensions=['.py'],
                ignore_dirs=[],
                output_file=None,
                verbose=False,
                recursive=True
            )
            
            watcher.start()
            
            try:
                time.sleep(0.1)
                
                # Rename directory
                test_dir.rename(temp_path / "renamed_directory")
                time.sleep(0.2)
                
                events = watcher.get_events()
                
                # Should have at least one event for the directory
                dir_events = [e for e in events if e.get('is_directory', False)]
                assert len(dir_events) >= 1
                
                dir_event = dir_events[0]
                assert 'directory' in dir_event['type']
                assert 'test_directory' in dir_event['old_path']
                assert 'renamed_directory' in dir_event['new_path']
                
            finally:
                watcher.stop()
