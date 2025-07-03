"""
File watcher implementation for tracking renames and moves
"""

import os
import re
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler, 
    FileMovedEvent, 
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    DirCreatedEvent,
    DirDeletedEvent
)

from ..utils import path_utils


class FileWatcher:
    """Main file watcher class for tracking file/directory moves and renames"""
    
    def __init__(self, watch_path: str, extensions: List[str], ignore_dirs: List[str],
                 recursive: bool = True, output_file: Optional[str] = None, 
                 verbose: bool = False, event_correlation_timeout: float = 2.0):
        """Initialize the file watcher
        
        Args:
            watch_path: Path to watch for changes
            extensions: List of file extensions to track
            ignore_dirs: List of directory patterns to ignore
            recursive: Whether to watch subdirectories recursively
            output_file: Optional output file to log changes
            verbose: Whether to enable verbose output
            event_correlation_timeout: Timeout for correlating move events
        """
        self.watch_path = Path(watch_path)
        self.extensions = extensions
        self.ignore_dirs = ignore_dirs
        self.recursive = recursive
        self.output_file = output_file
        self.verbose = verbose
        self.event_correlation_timeout = event_correlation_timeout
        
        # Create observer and event handler
        self.observer = Observer()
        self.event_handler = MoveTrackingHandler(
            extensions=extensions,
            ignore_patterns=ignore_dirs,
            output_file=output_file,
            verbose=verbose,
            event_correlation_timeout=event_correlation_timeout
        )
    
    def start(self):
        """Start watching for file changes"""
        self.observer.schedule(
            self.event_handler,
            path=str(self.watch_path),
            recursive=self.recursive
        )
        self.observer.start()
    
    def stop(self):
        """Stop watching for file changes"""
        self.observer.stop()
        self.observer.join()
    
    def is_alive(self) -> bool:
        """Check if the watcher is currently running"""
        return self.observer.is_alive()
    
    def get_events(self) -> List[Dict]:
        """Get list of recorded move events"""
        return self.event_handler.move_events.copy()


class MoveTrackingHandler(FileSystemEventHandler):
    """Event handler for tracking file and directory moves/renames"""
    
    def __init__(self, extensions: List[str], ignore_patterns: List[str], 
                 output_file: Optional[str] = None, verbose: bool = False,
                 event_correlation_timeout: float = 2.0):
        super().__init__()
        self.extensions = [ext.lower() for ext in extensions]
        self.ignore_patterns = ignore_patterns
        self.output_file = output_file
        self.verbose = verbose
        self.move_events: List[Dict] = []
        self.event_correlation_timeout = event_correlation_timeout
        
        # Event correlation for Windows-style moves (delete + create)
        self.pending_deletes: Dict[str, Dict] = {}  # path -> event_data
        self.pending_creates: Dict[str, Dict] = {}  # path -> event_data
        self.correlation_lock = threading.Lock()
        
        # Open output file if specified
        self.output_fp = None
        if self.output_file:
            self.output_fp = open(self.output_file, 'a', encoding='utf-8')
    
    def __del__(self):
        """Clean up file handle"""
        if self.output_fp:
            self.output_fp.close()
    
    def should_ignore_path(self, path: str) -> bool:
        """Check if path should be ignored based on ignore patterns"""
        return path_utils.is_path_ignored(Path(path), self.ignore_patterns)
    
    def should_track_file(self, file_path: str) -> bool:
        """Check if file should be tracked based on extensions"""
        if not self.extensions:
            return True  # Track all files if no extensions specified
        
        file_path_obj = Path(file_path)
        file_ext = file_path_obj.suffix.lower()
        
        # Check if it matches our tracked extensions
        if file_ext not in self.extensions:
            return False
        
        # Special handling for .blend files - ignore backup and temporary files
        if file_ext == '.blend':
            filename = file_path_obj.name
            # Ignore Blender backup files (.blend1, .blend2, etc.)
            if filename.endswith(('.blend1', '.blend2', '.blend3', '.blend4', '.blend5',
                                 '.blend6', '.blend7', '.blend8', '.blend9')):
                return False
            # Ignore Blender temporary files (.blend@)
            if filename.endswith('.blend@'):
                return False
        
        return True
    
    def log_event(self, event_data: Dict):
        """Log event to output file and/or console"""
        self.move_events.append(event_data)
        
        # Console output
        timestamp = event_data['timestamp']
        event_type = event_data['type']
        old_path = event_data['old_path']
        new_path = event_data['new_path']
        
        if self.verbose:
            print(f"[{timestamp}] {event_type.upper()}: {old_path} -> {new_path}")
        else:
            print(f"{event_type.upper()}: {Path(old_path).name} -> {Path(new_path).name}")
        
        # File output
        if self.output_fp:
            json_line = json.dumps(event_data)
            self.output_fp.write(json_line + '\n')
            self.output_fp.flush()
    
    def on_moved(self, event):
        """Handle file/directory move events"""
        # Convert paths to strings to handle bytes/str type issues
        src_path = str(event.src_path)
        dest_path = str(event.dest_path)
        
        # Skip if path should be ignored
        if self.should_ignore_path(src_path) or self.should_ignore_path(dest_path):
            return
        
        # Determine event type
        if isinstance(event, DirMovedEvent):
            # Directory move: find all relevant files and create individual move events
            moved_files = path_utils.find_files_by_extension(Path(dest_path), self.extensions, recursive=True)
            for new_file_path in moved_files:
                try:
                    relative_path = new_file_path.relative_to(dest_path)
                    old_file_path = Path(src_path) / relative_path
                except ValueError:
                    continue

                file_event_data = {
                    'timestamp': datetime.now().isoformat(),
                    'type': 'file_moved',
                    'old_path': str(old_file_path),
                    'new_path': str(new_file_path),
                    'old_name': new_file_path.name,
                    'new_name': new_file_path.name,
                    'is_directory': False
                }
                self.log_event(file_event_data)
            return
        elif isinstance(event, FileMovedEvent):
            # Check if file should be tracked
            if not self.should_track_file(src_path) and not self.should_track_file(dest_path):
                return
            event_type = 'file_moved'
        else:
            return
        
        # Check if it's a rename (same parent directory) or move
        src_parent = Path(src_path).parent
        dest_parent = Path(dest_path).parent
        
        if src_parent == dest_parent:
            event_type = event_type.replace('moved', 'renamed')
        
        # Create event data
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'type': event_type,
            'old_path': src_path,
            'new_path': dest_path,
            'old_name': Path(src_path).name,
            'new_name': Path(dest_path).name,
            'is_directory': isinstance(event, DirMovedEvent)
        }
        
        self.log_event(event_data)
    
    def on_deleted(self, event):
        """Handle file/directory delete events (for Windows move correlation)"""
        path = str(event.src_path)
        
        # Skip if path should be ignored
        if self.should_ignore_path(path):
            return
        
        # We are not interested in directory events
        is_directory = isinstance(event, DirDeletedEvent)
        if not is_directory and not self.should_track_file(path):
            return
        
        # Clean expired events first
        self._clean_expired_events()
        
        # Create event data for correlation
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'path': path,
            'is_directory': is_directory,
            'type': 'delete'
        }
        
        # Try to correlate with pending create events
        self._try_correlate_events(event_data, is_delete=True)
    
    def on_created(self, event):
        """Handle file/directory create events (for Windows move correlation)"""
        path = str(event.src_path)
        
        # Skip if path should be ignored
        if self.should_ignore_path(path):
            return
        
        # We are not interested in directory events
        is_directory = isinstance(event, DirCreatedEvent)
        if not is_directory and not self.should_track_file(path):
            return
        
        # Clean expired events first
        self._clean_expired_events()
        
        # Create event data for correlation
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'path': path,
            'is_directory': is_directory,
            'type': 'create'
        }
        
        # Try to correlate with pending delete events
        self._try_correlate_events(event_data, is_delete=False)
    
    def _get_file_info(self, path: str) -> Tuple[str, str, int]:
        """Get file information for correlation (name, extension, and size)"""
        try:
            path_obj = Path(path)
            name = path_obj.name
            extension = path_obj.suffix.lower()
            
            if path_obj.exists():
                stat = path_obj.stat()
                size = stat.st_size
            else:
                size = 0
            
            return name, extension, size
        except (OSError, FileNotFoundError):
            path_obj = Path(path)
            return path_obj.name, path_obj.suffix.lower(), 0
    
    def _clean_expired_events(self):
        """Clean up expired pending events"""
        current_time = time.time()
        with self.correlation_lock:
            # Clean expired deletes
            expired_deletes = [
                path for path, data in self.pending_deletes.items()
                if current_time - data['timestamp_unix'] > self.event_correlation_timeout
            ]
            for path in expired_deletes:
                del self.pending_deletes[path]
            
            # Clean expired creates
            expired_creates = [
                path for path, data in self.pending_creates.items()
                if current_time - data['timestamp_unix'] > self.event_correlation_timeout
            ]
            for path in expired_creates:
                del self.pending_creates[path]
    
    def _try_correlate_events(self, event_data: Dict, is_delete: bool) -> bool:
        """Try to correlate delete/create events into a move operation"""
        with self.correlation_lock:
            file_name, file_ext, file_size = self._get_file_info(event_data['path'])
            current_time = time.time()
            
            if is_delete:
                # Look for matching create events
                for create_path, create_data in list(self.pending_creates.items()):
                    create_name, create_ext, create_size = self._get_file_info(create_path)
                    
                    # For correlation, we check:
                    # 1. Same file extension (must match)
                    # 2. Same filename (for moves between folders)
                    # 3. Within timing window
                    if (create_ext == file_ext and 
                        create_name == file_name and  # Same filename = move between folders
                        abs(current_time - create_data['timestamp_unix']) <= self.event_correlation_timeout):
                        
                        # Found a match! Create move event
                        move_event = {
                            'timestamp': event_data['timestamp'],
                            'type': 'file_moved' if not event_data['is_directory'] else 'directory_moved',
                            'old_path': event_data['path'],
                            'new_path': create_path,
                            'old_name': file_name,
                            'new_name': create_name,
                            'is_directory': event_data['is_directory'],
                            'correlated': True
                        }
                        
                        # Check if it's a rename (same parent) or move
                        if Path(event_data['path']).parent == Path(create_path).parent:
                            move_event['type'] = move_event['type'].replace('moved', 'renamed')
                        
                        # Remove the matched create event and log the move
                        del self.pending_creates[create_path]
                        self.log_event(move_event)
                        return True
            else:
                # For delete events, we just store the event data with the current timestamp
                self.pending_deletes[event_data['path']] = {
                    **event_data,
                    'timestamp_unix': current_time
                }
        
        return False

    def flush_pending_events(self) -> List[Dict]:
        """Flush any pending move events (for testing or manual triggering)"""
        with self.correlation_lock:
            # Move events are stored in pending_creates for correlation
            events_to_flush = list(self.pending_creates.values())
            self.pending_creates.clear()
        
        # Log the flushed events
        for event_data in events_to_flush:
            self.log_event(event_data)
        
        return events_to_flush
