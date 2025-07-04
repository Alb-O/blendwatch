"""
Tests for the watcher module
"""

import json
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from watchdog.events import (
    FileMovedEvent, 
    DirMovedEvent, 
    FileDeletedEvent, 
    FileCreatedEvent,
    DirDeletedEvent,
    DirCreatedEvent
)

from blendwatch.core.watcher import FileWatcher, MoveTrackingHandler


class TestMoveTrackingHandler:
    """Test the MoveTrackingHandler class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.extensions = ['.py', '.txt']
        self.ignore_patterns = [r'__pycache__', r'\.git']
        self.output_file = None
        self.verbose = False
        
        self.handler = MoveTrackingHandler(
            extensions=self.extensions,
            ignore_patterns=self.ignore_patterns,
            output_file=self.output_file,
            verbose=self.verbose
        )
    
    def test_should_track_file_with_matching_extension(self):
        """Test that files with matching extensions are tracked"""
        assert self.handler.should_track_file('/path/to/file.py')
        assert self.handler.should_track_file('/path/to/file.txt')
        assert not self.handler.should_track_file('/path/to/file.jpg')
        assert not self.handler.should_track_file('/path/to/file')
    
    def test_should_track_file_with_no_extensions_filter(self):
        """Test tracking all files when no extensions specified"""
        handler = MoveTrackingHandler(
            extensions=[],
            ignore_patterns=[],
            output_file=None,
            verbose=False
        )
        
        assert handler.should_track_file('/path/to/file.py')
        assert handler.should_track_file('/path/to/file.jpg')
        assert handler.should_track_file('/path/to/file')
    
    def test_should_ignore_matching_patterns(self):
        """Test that paths matching ignore patterns are ignored"""
        assert self.handler.should_ignore_path('/project/__pycache__/file.pyc')
        assert self.handler.should_ignore_path('/project/.git/config')
        assert not self.handler.should_ignore_path('/project/src/main.py')
    
    def test_should_ignore_with_no_patterns(self):
        """Test behavior when no ignore patterns are specified"""
        handler = MoveTrackingHandler(
            extensions=[],
            ignore_patterns=[],
            output_file=None,
            verbose=False
        )
        
        assert not handler.should_ignore_path('/project/__pycache__/file.pyc')
        assert not handler.should_ignore_path('/project/.git/config')
    
    @patch('builtins.print')
    def test_on_moved_file_event(self, mock_print):
        """Test handling file moved events"""
        event = FileMovedEvent('/old/path/file.py', '/new/path/file.py')
        
        self.handler.on_moved(event)
        
        # Should print the move event
        mock_print.assert_called()
        call_args = mock_print.call_args[0][0]
        assert 'MOVED' in call_args or 'RENAMED' in call_args
    
    @patch('builtins.print')
    def test_on_moved_directory_event(self, mock_print):
        """Test handling directory moved events"""
        event = DirMovedEvent('/old/path/dir', '/new/path/dir')
        
        self.handler.on_moved(event)
        
        # Should print the move event
        mock_print.assert_called()
        call_args = mock_print.call_args[0][0]
        assert 'MOVED' in call_args or 'RENAMED' in call_args
    
    @patch('builtins.print')
    def test_on_moved_ignored_file(self, mock_print):
        """Test that ignored files don't generate events"""
        event = FileMovedEvent('/old/__pycache__/file.pyc', '/new/__pycache__/file.pyc')
        
        self.handler.on_moved(event)
        
        # Should not print anything for ignored files
        mock_print.assert_not_called()
    
    @patch('builtins.print')
    def test_on_moved_wrong_extension(self, mock_print):
        """Test that files with wrong extensions don't generate events"""
        event = FileMovedEvent('/old/path/file.jpg', '/new/path/file.jpg')
        
        self.handler.on_moved(event)
        
        # Should not print anything for non-watched extensions
        mock_print.assert_not_called()
    
    def test_on_moved_with_output_file(self):
        """Test logging to output file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            handler = MoveTrackingHandler(
                extensions=['.py'],
                ignore_patterns=[],
                output_file=f.name,
                verbose=False
            )
            
            event = FileMovedEvent('/old/path/file.py', '/new/path/file.py')
            handler.on_moved(event)
            
            # Check that the event was logged to file
            with open(f.name, 'r') as log_file:
                content = log_file.read()
                assert '"type":' in content
                assert '"/old/path/file.py"' in content
                assert '"/new/path/file.py"' in content
    
    def test_rename_vs_move_detection(self):
        """Test distinguishing between renames and moves"""
        # Test rename (same directory)
        rename_event = FileMovedEvent('/path/old_name.py', '/path/new_name.py')
        self.handler.on_moved(rename_event)
        
        # Test move (different directory)
        move_event = FileMovedEvent('/old_path/file.py', '/new_path/file.py')
        self.handler.on_moved(move_event)
        
        events = self.handler.move_events
        assert len(events) == 2
        assert 'renamed' in events[0]['type']
        assert 'moved' in events[1]['type']
    
    def test_windows_style_move_correlation(self):
        """Test correlation of delete + create events into move events (same filename, different folders)"""
        handler = MoveTrackingHandler(['.txt'], [], event_correlation_timeout=1.0)
        
        # Create mock delete event
        delete_event = FileDeletedEvent('/old/folder/file.txt')
        
        # Create mock create event with same filename in different folder
        create_event = FileCreatedEvent('/new/folder/file.txt')
        
        # Simulate the delete event first
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_deleted(delete_event)
        
        # Should have no move events yet
        assert len(handler.move_events) == 0
        
        # Now simulate the create event
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_created(create_event)
        
        # Should now have a correlated move event
        assert len(handler.move_events) == 1
        event = handler.move_events[0]
        assert event['type'] == 'file_moved'
        assert event['old_path'] == '/old/folder/file.txt'
        assert event['new_path'] == '/new/folder/file.txt'
        assert event['correlated'] == True

    def test_windows_style_different_filenames_correlation(self):
        """Test that files with different names ARE correlated when timing and extension match (improved logic)"""
        handler = MoveTrackingHandler(['.txt'], [], event_correlation_timeout=1.0)
        
        # Create mock delete event
        delete_event = FileDeletedEvent('/same/path/oldname.txt')
        
        # Create mock create event with different filename in same directory
        create_event = FileCreatedEvent('/same/path/newname.txt')
        
        # Simulate the events
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_deleted(delete_event)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_created(create_event)
        
        # Should correlate because extension matches, timing is close, and it's likely a rename
        # (Improved logic handles renames with different filenames)
        assert len(handler.move_events) == 1
        move_event = handler.move_events[0]
        assert move_event['type'] == 'file_renamed'  # Same directory = rename
        assert move_event['old_path'] == '/same/path/oldname.txt'
        assert move_event['new_path'] == '/same/path/newname.txt'

    def test_event_correlation_timeout(self):
        """Test that events outside timeout window are not correlated"""
        handler = MoveTrackingHandler(['.txt'], [], event_correlation_timeout=0.1)
        
        delete_event = FileDeletedEvent('/old/path/file.txt')
        create_event = FileCreatedEvent('/new/path/file.txt')
        
        # Simulate delete event
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_deleted(delete_event)
        
        # Wait longer than timeout
        time.sleep(0.2)
        
        # Simulate create event
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_created(create_event)
        
        # Should not correlate due to timeout
        assert len(handler.move_events) == 0

    def test_directory_correlation(self):
        """Test correlation of directory delete + create events"""
        handler = MoveTrackingHandler([], [], event_correlation_timeout=1.0)
        
        # Create mock directory events with same directory name
        delete_event = DirDeletedEvent('/old/location/mydir')
        create_event = DirCreatedEvent('/new/location/mydir')
        
        # Simulate directory events
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 0  # directories typically have size 0 or 4096
            handler.on_deleted(delete_event)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 0
            handler.on_created(create_event)
        
        # Should have a correlated directory move
        assert len(handler.move_events) == 1
        event = handler.move_events[0]
        assert event['type'] == 'directory_moved'
        assert event['is_directory'] == True
        assert event['correlated'] == True

    def test_flush_pending_events(self):
        """Test flushing of unmatched pending events"""
        handler = MoveTrackingHandler(['.txt', '.py'], [], event_correlation_timeout=1.0)
        
        # Create unmatched delete event (.txt file)
        delete_event = FileDeletedEvent('/deleted/file1.txt')
        
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024
            handler.on_deleted(delete_event)
        
        # Create unmatched create event with different extension (.py file)
        # This will NOT correlate because extensions are different
        create_event = FileCreatedEvent('/created/file2.py')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 1024  # Same size but different extension, won't correlate
            handler.on_created(create_event)
        
        # Flush pending events
        unmatched = handler.flush_pending_events()
        
        # Should have 2 unmatched events (different extensions prevent correlation)
        assert len(unmatched) == 2
        
        # Check delete event
        delete_unmatched = next(e for e in unmatched if e['type'] == 'file_deleted')
        assert delete_unmatched['path'] == '/deleted/file1.txt'
        assert delete_unmatched['unmatched'] == True
        
        # Check create event
        create_unmatched = next(e for e in unmatched if e['type'] == 'file_created')
        assert create_unmatched['path'] == '/created/file2.py'
        assert create_unmatched['unmatched'] == True

    def test_directory_move_with_blend_files(self):
        """Test directory move with blend files inside"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            # Mock finding blend files in the moved directory
            mock_blend_files = [
                Path('/new/project/scene.blend'),
                Path('/new/project/assets/character.blend')
            ]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [], verbose=True)
            
            # Simulate directory move event
            dir_event = DirMovedEvent('/old/project', '/new/project')
            handler.on_moved(dir_event)
            
            # Should create file move events for each blend file
            assert len(handler.move_events) == 2
            
            # Check first blend file move (normalize paths for platform compatibility)
            scene_move = handler.move_events[0]
            assert scene_move['type'] == 'file_moved'
            assert Path(scene_move['old_path']) == Path('/old/project/scene.blend')
            assert Path(scene_move['new_path']) == Path('/new/project/scene.blend')
            
            # Check second blend file move
            character_move = handler.move_events[1]
            assert character_move['type'] == 'file_moved'
            assert Path(character_move['old_path']) == Path('/old/project/assets/character.blend')
            assert Path(character_move['new_path']) == Path('/new/project/assets/character.blend')

    def test_directory_move_deduplication(self):
        """Test that individual file moves are deduplicated when part of directory move"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            # Mock finding blend files in the moved directory
            mock_blend_files = [Path('/new/project/scene.blend')]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [], verbose=True)
            
            # First: directory move event (which creates file move events)
            dir_event = DirMovedEvent('/old/project', '/new/project')
            handler.on_moved(dir_event)
            
            # Second: individual file move event (should be skipped as duplicate)
            file_event = FileMovedEvent('/old/project/scene.blend', '/new/project/scene.blend')
            handler.on_moved(file_event)
            
            # Should only have one file move event (from directory move, not from individual file move)
            assert len(handler.move_events) == 1
            move_event = handler.move_events[0]
            assert Path(move_event['old_path']) == Path('/old/project/scene.blend')
            assert Path(move_event['new_path']) == Path('/new/project/scene.blend')

    def test_complex_nested_directory_move(self):
        """Test complex directory structure moves with multiple nested blend files"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            # Mock finding multiple blend files in nested directories
            mock_blend_files = [
                Path('/new/complex_project/main.blend'),
                Path('/new/complex_project/scenes/scene1.blend'),
                Path('/new/complex_project/scenes/scene2.blend'),
                Path('/new/complex_project/assets/models/character.blend'),
                Path('/new/complex_project/assets/models/environment.blend')
            ]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [], verbose=True)
            
            # Simulate directory move event
            dir_event = DirMovedEvent('/old/complex_project', '/new/complex_project')
            handler.on_moved(dir_event)
            
            # Should create file move events for all blend files
            assert len(handler.move_events) == 5
            
            # Verify each expected move (normalize paths for cross-platform compatibility)
            expected_moves = [
                (Path('/old/complex_project/main.blend'), Path('/new/complex_project/main.blend')),
                (Path('/old/complex_project/scenes/scene1.blend'), Path('/new/complex_project/scenes/scene1.blend')),
                (Path('/old/complex_project/scenes/scene2.blend'), Path('/new/complex_project/scenes/scene2.blend')),
                (Path('/old/complex_project/assets/models/character.blend'), Path('/new/complex_project/assets/models/character.blend')),
                (Path('/old/complex_project/assets/models/environment.blend'), Path('/new/complex_project/assets/models/environment.blend')),
            ]
            
            actual_moves = [(Path(event['old_path']), Path(event['new_path'])) for event in handler.move_events]
            assert sorted(actual_moves) == sorted(expected_moves)

    def test_directory_processed_files_tracking(self):
        """Test that files processed as part of directory moves are tracked to prevent duplication"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            mock_blend_files = [Path('/new/project/scene.blend')]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [], event_correlation_timeout=2.0)
            
            # Process directory move
            dir_event = DirMovedEvent('/old/project', '/new/project')
            handler.on_moved(dir_event)
            
            # Check that files are tracked in directory_processed_files (normalize paths)
            old_path_str = str(Path('/old/project/scene.blend'))
            new_path_str = str(Path('/new/project/scene.blend'))
            assert old_path_str in handler.directory_processed_files
            assert new_path_str in handler.directory_processed_files

    def test_correlation_skips_directory_processed_files(self):
        """Test that correlation logic skips files already processed by directory moves"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            mock_blend_files = [Path('/new/project/scene.blend')]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [], verbose=True, event_correlation_timeout=2.0)
            
            # Process directory move first
            dir_event = DirMovedEvent('/old/project', '/new/project')
            handler.on_moved(dir_event)
            
            # Now simulate individual delete/create events that might come from OS
            delete_event = FileDeletedEvent('/old/project/scene.blend')
            create_event = FileCreatedEvent('/new/project/scene.blend')
            
            with patch('pathlib.Path.exists', return_value=False):
                handler.on_deleted(delete_event)
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.stat') as mock_stat:
                mock_stat.return_value.st_size = 1024
                handler.on_created(create_event)
            
            # Should still only have one move event (from directory move)
            # The individual delete/create should be ignored since the file was already processed
            assert len(handler.move_events) == 1

    def test_user_reported_scenario(self):
        """Test the exact scenario reported by the user: moving folder with blend file inside"""
        handler = MoveTrackingHandler(['.blend'], [], verbose=True, event_correlation_timeout=2.0)
        
        # Step 1: Move "New folder" to "nested" (directory move)
        dir_event = DirMovedEvent(
            '/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/New folder',
            '/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/nested'
        )
        handler.on_moved(dir_event)  # Should not create any move events (no tracked files in directory)
        
        # Step 2: Create subfolder (create event)
        create_dir_event = DirCreatedEvent('/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/nested/subfolder')
        handler.on_created(create_dir_event)  # Should be ignored (directory event)
        
        # Step 3: Move blend file into subfolder (individual file move via delete/create correlation)
        delete_event = FileDeletedEvent('/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/PIVOT_SNB_Track Mouse.blend')
        create_event = FileCreatedEvent('/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/nested/subfolder/PIVOT_SNB_Track Mouse.blend')
        
        # Simulate the events
        with patch('pathlib.Path.exists', return_value=False):
            handler.on_deleted(delete_event)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 112
            handler.on_created(create_event)
        
        # Should have exactly one file move event for the blend file
        assert len(handler.move_events) == 1
        
        move_event = handler.move_events[0]
        assert move_event['type'] == 'file_moved'
        assert move_event['old_path'] == '/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/PIVOT_SNB_Track Mouse.blend'
        assert move_event['new_path'] == '/SNB_Instructional Animation/PIVOT_SNB_Track Mouse.blend/nested/subfolder/PIVOT_SNB_Track Mouse.blend'
        assert move_event['correlated'] == True

    def test_directory_cleanup_limits(self):
        """Test that directory tracking data structures are cleaned up properly"""
        handler = MoveTrackingHandler(['.blend'], [], event_correlation_timeout=0.1)
        
        # Add many directory moves to trigger cleanup
        with handler.correlation_lock:
            for i in range(25):  # More than the 20 limit
                handler.recent_directory_moves[f'/old/dir{i}'] = f'/new/dir{i}'
        
        # Trigger cleanup by processing another event
        handler._clean_expired_events()
        
        # Should have cleaned up to reasonable size (roughly half, so around 12-13)
        assert len(handler.recent_directory_moves) <= 13  # Allow some variance in cleanup

    def test_directory_processed_files_cleanup(self):
        """Test that directory processed files are cleaned up after timeout"""
        handler = MoveTrackingHandler(['.blend'], [], event_correlation_timeout=0.1)
        
        # Add some processed files
        import time
        current_time = time.time()
        with handler.correlation_lock:
            # Add recent file (should not be cleaned)
            handler.directory_processed_files['/recent/file.blend'] = current_time
            # Add old file (should be cleaned)
            handler.directory_processed_files['/old/file.blend'] = current_time - 1.0
        
        # Trigger cleanup
        handler._clean_expired_events()
        
        # Recent file should remain, old file should be cleaned
        assert '/recent/file.blend' in handler.directory_processed_files
        assert '/old/file.blend' not in handler.directory_processed_files

    def test_move_chain_detection(self):
        """Test that chain moves are detected when only CREATE events are seen"""
        handler = MoveTrackingHandler(['.blend'], [], verbose=True, event_correlation_timeout=2.0)
        
        # Simulate the first normal move (DELETE + CREATE correlation)
        delete_event1 = FileDeletedEvent('/project/scene.blend')
        create_event1 = FileCreatedEvent('/project/subdir1/scene.blend')
        
        with patch('pathlib.Path.exists', return_value=False), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 100
            handler.on_deleted(delete_event1)
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 100
            handler.on_created(create_event1)
        
        # Should have one normal move
        assert len(handler.move_events) == 1
        assert handler.move_events[0]['type'] == 'file_moved'
        assert handler.move_events[0]['old_path'] == '/project/scene.blend'
        assert handler.move_events[0]['new_path'] == '/project/subdir1/scene.blend'
        assert handler.move_events[0].get('correlated') == True
        assert not handler.move_events[0].get('chain_move')
        
        # Now simulate rapid moves where only CREATE events are seen
        # This simulates the user's scenario where filesystem events come too fast
        
        # Second move: only CREATE event (no DELETE because move was too fast)
        create_event2 = FileCreatedEvent('/project/subdir2/scene.blend')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 100
            handler.on_created(create_event2)
        
        # Should now have two moves, second one is a chain move
        assert len(handler.move_events) == 2
        chain_move1 = handler.move_events[1]
        assert chain_move1['type'] == 'file_moved'
        assert chain_move1['old_path'] == '/project/subdir1/scene.blend'
        assert chain_move1['new_path'] == '/project/subdir2/scene.blend'
        assert chain_move1.get('chain_move') == True
        assert chain_move1.get('correlated') == True
        
        # Third move: another CREATE-only event
        create_event3 = FileCreatedEvent('/project/subdir3/scene.blend')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value.st_size = 100
            handler.on_created(create_event3)
        
        # Should now have three moves, third one is also a chain move
        assert len(handler.move_events) == 3
        chain_move2 = handler.move_events[2]
        assert chain_move2['type'] == 'file_moved'
        assert chain_move2['old_path'] == '/project/subdir2/scene.blend'
        assert chain_move2['new_path'] == '/project/subdir3/scene.blend'
        assert chain_move2.get('chain_move') == True
        assert chain_move2.get('correlated') == True

    def test_filesystem_based_chain_move_detection(self):
        """Test chain move detection using filesystem search when no recent events exist"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            # Mock filesystem search to find a file with the same name in a different location
            mock_find_files.return_value = [
                Path('/project/old_location/scene.blend'),  # Source file
                Path('/project/new_location/scene.blend')   # Target file (the one being created)
            ]
            
            handler = MoveTrackingHandler(['.blend'], [], verbose=True, event_correlation_timeout=2.0)
            
            # First, create some recent move activity to satisfy the conditions for filesystem search
            # This simulates an active editing session where files are being moved around
            initial_move_event = {
                'timestamp': datetime.now().isoformat(),
                'type': 'file_moved',
                'old_path': '/project/temp/other.blend',
                'new_path': '/project/somewhere/other.blend',
                'old_name': 'other.blend',
                'new_name': 'other.blend',
                'is_directory': False
            }
            handler.move_events.append(initial_move_event)
            
            # Simulate a CREATE event with no prior context for this specific file (no recent moves, no pending deletes)
            create_event = FileCreatedEvent('/project/new_location/scene.blend')
            
            with patch('pathlib.Path.exists', return_value=True), \
                 patch('pathlib.Path.stat') as mock_stat:
                mock_stat.return_value.st_size = 1024
                handler.on_created(create_event)
            
            # Should have created a chain move event using filesystem search
            assert len(handler.move_events) == 2  # Initial move + new chain move
            move_event = handler.move_events[1]  # The new chain move
            assert move_event['type'] == 'file_moved'
            assert Path(move_event['old_path']) == Path('/project/old_location/scene.blend')
            assert Path(move_event['new_path']) == Path('/project/new_location/scene.blend')
            assert move_event.get('chain_move') == True
            assert move_event.get('correlated') == True
            
            # Verify that filesystem search was called
            mock_find_files.assert_called_once()
    
    # ...existing code...

class TestFileWatcher:
    """Test the FileWatcher class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.watch_path = '/test/path'
        self.extensions = ['.py', '.txt']
        self.ignore_dirs = [r'__pycache__']
        self.recursive = True
        self.output_file = None
        self.verbose = False
        
        self.watcher = FileWatcher(
            watch_path=self.watch_path,
            extensions=self.extensions,
            ignore_dirs=self.ignore_dirs,
            recursive=self.recursive,
            output_file=self.output_file,
            verbose=self.verbose
        )
    
    def test_watcher_initialization(self):
        """Test FileWatcher initialization"""
        assert self.watcher.watch_path == Path(self.watch_path)
        assert self.watcher.extensions == self.extensions
        assert self.watcher.ignore_dirs == self.ignore_dirs
        assert self.watcher.recursive == self.recursive
        assert self.watcher.output_file == self.output_file
        assert self.watcher.verbose == self.verbose
        assert self.watcher.observer is not None
        assert self.watcher.event_handler is not None
    
    @patch('blendwatch.core.watcher.Observer')
    def test_start_watching(self, mock_observer_class):
        """Test starting the file watcher"""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=[],
            recursive=True,
            output_file=None,
            verbose=False
        )
        
        watcher.start()
        
        mock_observer.schedule.assert_called_once()
        mock_observer.start.assert_called_once()
    
    @patch('blendwatch.core.watcher.Observer')
    def test_stop_watching(self, mock_observer_class):
        """Test stopping the file watcher"""
        mock_observer = Mock()
        mock_observer_class.return_value = mock_observer
        
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=[],
            recursive=True,
            output_file=None,
            verbose=False
        )
        
        watcher.start()
        watcher.stop()
        
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
    
    def test_watcher_with_custom_parameters(self, tmp_path):
        """Test FileWatcher with custom parameters"""
        log_file = tmp_path / 'log.json'
        watcher = FileWatcher(
            watch_path='/custom/path',
            extensions=['.blend', '.fbx'],
            ignore_dirs=[r'\.git', r'backup'],
            recursive=False,
            output_file=str(log_file),
            verbose=True
        )
        
        assert watcher.watch_path == Path('/custom/path')
        assert watcher.extensions == ['.blend', '.fbx']
        assert watcher.ignore_dirs == [r'\.git', r'backup']
        assert watcher.recursive == False
        assert watcher.output_file == str(log_file)
        assert watcher.verbose == True
    
    def test_get_events(self):
        """Test getting recorded events"""
        events = self.watcher.get_events()
        assert isinstance(events, list)
        # Initially should be empty
        assert len(events) == 0
    
    @patch('blendwatch.core.watcher.Observer')
    def test_is_alive(self, mock_observer_class):
        """Test checking if watcher is alive"""
        mock_observer = Mock()
        mock_observer.is_alive.return_value = True
        mock_observer_class.return_value = mock_observer
        
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=[],
            recursive=True,
            output_file=None,
            verbose=False
        )
        
        assert watcher.is_alive() == True
        mock_observer.is_alive.assert_called_once()
