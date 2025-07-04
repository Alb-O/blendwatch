"""
Tests for the file watcher module with file index integration
"""

import pytest
import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from watchdog.events import (
    FileMovedEvent, 
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    DirCreatedEvent,
    DirDeletedEvent
)

from blendwatch.core.watcher import FileWatcher, MoveTrackingHandler
from blendwatch.core.file_index import FileIndex


class TestMoveTrackingHandler:
    """Test the MoveTrackingHandler class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.handler = MoveTrackingHandler(['.py', '.txt'], [], verbose=False)
    
    def test_should_track_file(self):
        """Test file tracking logic"""
        # Should track .py files
        assert self.handler.should_track_file('/path/to/file.py')
        assert self.handler.should_track_file('/path/to/file.txt')
        
        # Should not track other extensions
        assert not self.handler.should_track_file('/path/to/file.jpg')
        assert not self.handler.should_track_file('/path/to/file.doc')
    
    def test_should_track_blend_files(self):
        """Test special Blender file tracking logic"""
        handler = MoveTrackingHandler(['.blend'], [])
        
        # Should track .blend files
        assert handler.should_track_file('/path/to/scene.blend')
        
        # Should not track Blender backup files
        assert not handler.should_track_file('/path/to/scene.blend1')
        assert not handler.should_track_file('/path/to/scene.blend2')
        assert not handler.should_track_file('/path/to/scene.blend@')
    
    def test_should_ignore_path(self):
        """Test path ignoring logic"""
        handler = MoveTrackingHandler(['.py'], ['__pycache__', r'.*\.tmp'])
        
        # Should ignore patterns
        assert handler.should_ignore_path('/path/__pycache__/file.py')
        assert handler.should_ignore_path('/path/temp.tmp')
        
        # Should not ignore normal paths
        assert not handler.should_ignore_path('/path/to/file.py')
    
    def test_should_ignore_blend_backup_files(self):
        """Test that Blender backup and temporary files are ignored via ignore patterns"""
        from blendwatch.core.config import load_default_config
        
        # Load default config with Blender ignore patterns
        config = load_default_config()
        handler = MoveTrackingHandler(['.blend'], config.ignore_dirs)
        
        # Should ignore Blender backup and temporary files via ignore patterns
        assert handler.should_ignore_path('/path/to/scene.blend1')
        assert handler.should_ignore_path('/path/to/scene.blend2')
        assert handler.should_ignore_path('/path/to/scene.blend9')
        assert handler.should_ignore_path('/path/to/project.blend@')
        assert handler.should_ignore_path('C:\\Projects\\scene.blend1')
        assert handler.should_ignore_path('C:\\Projects\\scene.blend@')
        
        # Should not ignore normal .blend files
        assert not handler.should_ignore_path('/path/to/scene.blend')
        assert not handler.should_ignore_path('/path/to/project.blend')
        assert not handler.should_ignore_path('C:\\Projects\\scene.blend')
    
    def test_direct_file_move_events(self):
        """Test direct file move events (not correlation-based)"""
        # Test rename (same directory)
        rename_event = FileMovedEvent('/same_path/oldname.py', '/same_path/newname.py')
        self.handler.on_moved(rename_event)
        
        # Test move (different directory)
        move_event = FileMovedEvent('/old_path/file.py', '/new_path/file.py')
        self.handler.on_moved(move_event)
        
        events = self.handler.move_events
        assert len(events) == 2
        assert 'renamed' in events[0]['type']
        assert 'moved' in events[1]['type']
    
    def test_directory_move_with_files(self):
        """Test directory move events generate file move events"""
        with patch('blendwatch.utils.path_utils.find_files_by_extension') as mock_find_files:
            mock_blend_files = [Path('/new/project/scene.blend')]
            mock_find_files.return_value = mock_blend_files
            
            handler = MoveTrackingHandler(['.blend'], [])
            
            # Process directory move
            dir_event = DirMovedEvent('/old/project', '/new/project')
            handler.on_moved(dir_event)
            
            # Should have one file move event for the found .blend file
            assert len(handler.move_events) == 1
            move_event = handler.move_events[0]
            assert move_event['type'] == 'file_moved'
            assert move_event['old_path'] == str(Path('/old/project/scene.blend'))
            assert move_event['new_path'] == str(Path('/new/project/scene.blend'))
    
    def test_file_index_integration(self):
        """Test integration with file index for move detection"""
        # Create mock file index
        mock_file_index = Mock(spec=FileIndex)
        mock_file_index.record_creation.return_value = ('/old/path/file.txt', '/new/path/file.txt')
        
        handler = MoveTrackingHandler(['.txt'], [], file_index=mock_file_index)
        
        # Simulate create event
        create_event = FileCreatedEvent('/new/path/file.txt')
        
        with patch('pathlib.Path.exists', return_value=True):
            handler.on_created(create_event)
        
        # Should have detected move via file index
        assert len(handler.move_events) == 1
        move_event = handler.move_events[0]
        assert move_event['type'] == 'file_moved'
        assert move_event['old_path'] == '/old/path/file.txt'
        assert move_event['new_path'] == '/new/path/file.txt'
        assert move_event['detection_method'] == 'file_index'
        
        # File index should have been called
        mock_file_index.record_creation.assert_called_once_with('/new/path/file.txt')
    
    def test_file_index_deletion_tracking(self):
        """Test that deletions are recorded in file index"""
        mock_file_index = Mock(spec=FileIndex)
        handler = MoveTrackingHandler(['.txt'], [], file_index=mock_file_index)
        
        # Simulate delete event
        delete_event = FileDeletedEvent('/path/to/file.txt')
        
        with patch('pathlib.Path.exists', return_value=False):
            handler.on_deleted(delete_event)
        
        # File index should have been notified of deletion
        mock_file_index.record_deletion.assert_called_once_with('/path/to/file.txt')
    
    def test_directory_deletion_with_files(self):
        """Test directory deletion records all contained files as deleted"""
        mock_file_index = Mock(spec=FileIndex)
        mock_file_index.get_files_in_directory.return_value = [
            '/dir/file1.txt',
            '/dir/file2.txt'
        ]
        
        handler = MoveTrackingHandler(['.txt'], [], file_index=mock_file_index)
        
        # Simulate directory delete event
        delete_event = DirDeletedEvent('/dir')
        
        with patch('pathlib.Path.exists', return_value=False):
            handler.on_deleted(delete_event)
        
        # All files in directory should be recorded as deleted
        assert mock_file_index.record_deletion.call_count == 2
        mock_file_index.record_deletion.assert_any_call('/dir/file1.txt')
        mock_file_index.record_deletion.assert_any_call('/dir/file2.txt')
    
    def test_duplicate_move_prevention(self):
        """Test that duplicate moves are not recorded"""
        mock_file_index = Mock(spec=FileIndex)
        mock_file_index.record_creation.return_value = ('/old/path/file.txt', '/new/path/file.txt')
        
        handler = MoveTrackingHandler(['.txt'], [], file_index=mock_file_index)
        
        # Add existing move event to simulate already recorded move
        handler.move_events.append({
            'old_path': '/old/path/file.txt',
            'new_path': '/new/path/file.txt',
            'detection_method': 'file_index'
        })
        
        # Simulate create event that would normally trigger move detection
        create_event = FileCreatedEvent('/new/path/file.txt')
        
        with patch('pathlib.Path.exists', return_value=True):
            handler.on_created(create_event)
        
        # Should still only have one move event (no duplicate)
        assert len(handler.move_events) == 1
    
    def test_file_index_processed_files_cleanup(self):
        """Test that processed files list is cleaned up over time"""
        handler = MoveTrackingHandler(['.txt'], [])
        
        # Add some old processed files
        current_time = time.time()
        handler.file_index_processed_files['/old/file.txt'] = current_time - 700  # Old (> 600 seconds)
        handler.file_index_processed_files['/recent/file.txt'] = current_time - 100  # Recent
        
        # Trigger cleanup by processing a create event
        create_event = FileCreatedEvent('/new/file.txt')
        
        with patch('pathlib.Path.exists', return_value=True):
            handler.on_created(create_event)
        
        # Old file should be cleaned up, recent should remain
        assert '/old/file.txt' not in handler.file_index_processed_files
        assert '/recent/file.txt' in handler.file_index_processed_files


class TestFileWatcher:
    """Test the FileWatcher class"""
    
    def test_init_with_file_index(self):
        """Test FileWatcher initialization with file index enabled"""
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=['__pycache__'],
            enable_file_index=True
        )
        
        assert watcher.file_index is not None
        # Use Path for cross-platform compatibility
        assert Path(str(watcher.file_index.watch_path)) == Path('/test/path')
        assert '.py' in watcher.file_index.extensions
    
    def test_init_without_file_index(self):
        """Test FileWatcher initialization with file index disabled"""
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=['__pycache__'],
            enable_file_index=False
        )
        
        assert watcher.file_index is None
    
    def test_start_stop_with_file_index(self):
        """Test starting and stopping watcher with file index"""
        with patch('blendwatch.core.watcher.Observer') as mock_observer_class:
            mock_observer = Mock()
            mock_observer_class.return_value = mock_observer
            
            watcher = FileWatcher(
                watch_path='/test/path',
                extensions=['.py'],
                ignore_dirs=[],
                enable_file_index=True
            )
            
            # Verify file index was created
            assert watcher.file_index is not None
            
            # Mock file index methods after creation
            original_start = watcher.file_index.start
            original_stop = watcher.file_index.stop
            watcher.file_index.start = Mock(side_effect=original_start)
            watcher.file_index.stop = Mock(side_effect=original_stop)
            
            # Start watcher
            watcher.start()
            
            # File index should be started
            watcher.file_index.start.assert_called_once()
            mock_observer.schedule.assert_called_once()
            mock_observer.start.assert_called_once()
            
            # Stop watcher
            watcher.stop()
            
            # File index should be stopped
            watcher.file_index.stop.assert_called_once()
            mock_observer.stop.assert_called_once()
            mock_observer.join.assert_called_once()
    
    def test_get_events(self):
        """Test getting move events from watcher"""
        watcher = FileWatcher(
            watch_path='/test/path',
            extensions=['.py'],
            ignore_dirs=[],
            enable_file_index=False
        )
        
        # Add some test events
        test_events = [
            {'type': 'file_moved', 'old_path': '/a.py', 'new_path': '/b.py'},
            {'type': 'file_renamed', 'old_path': '/c.py', 'new_path': '/d.py'}
        ]
        watcher.event_handler.move_events = test_events
        
        events = watcher.get_events()
        assert len(events) == 2
        assert events == test_events
        
        # Should return a copy, not the original list
        assert events is not watcher.event_handler.move_events


class TestFileIndexIntegration:
    """Integration tests with real file index"""
    
    def test_real_file_index_integration(self):
        """Test with a real file index instance"""
        with patch('blendwatch.core.file_index.FileIndex') as mock_file_index_class:
            mock_file_index = Mock()
            mock_file_index_class.return_value = mock_file_index
            mock_file_index.record_creation.return_value = None  # No move detected
            
            handler = MoveTrackingHandler(['.txt'], [], file_index=mock_file_index)
            
            # Test creation event
            create_event = FileCreatedEvent('/test/file.txt')
            
            with patch('pathlib.Path.exists', return_value=True):
                handler.on_created(create_event)
            
            # File index should be called
            mock_file_index.record_creation.assert_called_once_with('/test/file.txt')
            
            # No move event should be created since file index returned None
            assert len(handler.move_events) == 0


class TestCreateDeleteCorrelation:
    """Test create/delete event correlation for Windows-style moves"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.handler = MoveTrackingHandler(['.blend'], [], verbose=False)
        # Use shorter timeout for faster tests
        self.handler.correlation_timeout = 1.0
    
    def test_simple_file_correlation(self):
        """Test basic delete->create correlation"""
        # Simulate delete event
        delete_event = FileDeletedEvent('/old/path/file.blend')
        
        with patch('pathlib.Path.exists', return_value=False):
            self.handler.on_deleted(delete_event)
        
        # Check delete was recorded
        assert '/old/path/file.blend' in self.handler.pending_deletes
        
        # Simulate create event for the same file in a new location
        create_event = FileCreatedEvent('/new/path/file.blend')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch.object(self.handler, '_get_file_info') as mock_get_info:
            
            # Mock file info to simulate same file (name + extension match)
            mock_get_info.side_effect = [
                ('file.blend', '.blend', 1024),  # create file info
                ('file.blend', '.blend', 0)      # delete file info (no size available)
            ]
            
            self.handler.on_created(create_event)
        
        # Should have created a move event and removed the pending delete
        assert len(self.handler.move_events) == 1
        assert '/old/path/file.blend' not in self.handler.pending_deletes
        
        move_event = self.handler.move_events[0]
        assert move_event['old_path'] == '/old/path/file.blend'
        assert move_event['new_path'] == '/new/path/file.blend'
        assert move_event['type'] == 'file_moved'
        assert move_event['detection_method'] == 'correlation'
    
    def test_correlation_with_rename(self):
        """Test correlation detects renames (same parent directory)"""
        # Simulate delete event
        delete_event = FileDeletedEvent('/same/path/oldname.blend')
        
        with patch('pathlib.Path.exists', return_value=False):
            self.handler.on_deleted(delete_event)
        
        # Simulate create event in same directory (rename)
        create_event = FileCreatedEvent('/same/path/newname.blend')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch.object(self.handler, '_get_file_info') as mock_get_info:
            
            # Mock file info - same extension, different names
            mock_get_info.side_effect = [
                ('newname.blend', '.blend', 1024),    # create file info
                ('oldname.blend', '.blend', 0)        # delete file info (no size available)
            ]
            
            self.handler.on_created(create_event)
        
        # Should have created a rename event
        assert len(self.handler.move_events) == 1
        move_event = self.handler.move_events[0]
        assert move_event['type'] == 'file_renamed'
        assert move_event['detection_method'] == 'correlation'
    
    def test_correlation_timeout(self):
        """Test that correlation times out correctly"""
        # Use very short timeout for this test
        self.handler.correlation_timeout = 0.1
        
        # Simulate delete event
        delete_event = FileDeletedEvent('/old/path/file.blend')
        
        with patch('pathlib.Path.exists', return_value=False):
            self.handler.on_deleted(delete_event)
        
        # Check delete was recorded
        assert '/old/path/file.blend' in self.handler.pending_deletes
        
        # Wait for timeout
        time.sleep(0.2)
        
        # Simulate create event after timeout
        create_event = FileCreatedEvent('/new/path/file.blend')
        
        with patch('pathlib.Path.exists', return_value=True), \
             patch.object(self.handler, '_get_file_info') as mock_get_info:
            
            mock_get_info.return_value = ('file.blend', '.blend', 1024)
            self.handler.on_created(create_event)
        
        # Should not have created a move event due to timeout
        assert len(self.handler.move_events) == 0
        # Delete should have been cleaned up
        assert '/old/path/file.blend' not in self.handler.pending_deletes
