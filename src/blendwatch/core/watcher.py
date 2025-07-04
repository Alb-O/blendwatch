"""
File watcher implementation for tracking renames and moves
"""

import os
import json
import time
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from datetime import datetime

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
from .file_index import FileIndex


class FileWatcher:
    """Main file watcher class for tracking file/directory moves and renames"""
    
    def __init__(self, watch_path: str, extensions: List[str], ignore_dirs: List[str],
                 recursive: bool = True, output_file: Optional[str] = None, 
                 verbose: bool = False, enable_file_index: bool = True, 
                 index_rescan_interval: int = 300):
        """Initialize the file watcher
        
        Args:
            watch_path: Path to watch for changes
            extensions: List of file extensions to track
            ignore_dirs: List of directory patterns to ignore
            recursive: Whether to watch subdirectories recursively
            output_file: Optional output file to log changes
            verbose: Whether to enable verbose output
            enable_file_index: Whether to enable the file index system for better move detection
            index_rescan_interval: How often to rescan the directory tree (seconds)
        """
        self.watch_path = Path(watch_path)
        self.extensions = extensions
        self.ignore_dirs = ignore_dirs
        self.recursive = recursive
        self.output_file = output_file
        self.verbose = verbose
        
        # Initialize file index if enabled
        self.file_index = None
        if enable_file_index:
            self.file_index = FileIndex(
                watch_path=str(watch_path),
                extensions=extensions,
                rescan_interval=index_rescan_interval,
                ignore_patterns=ignore_dirs
            )
        
        # Create observer and event handler
        self.observer = Observer()
        self.event_handler = MoveTrackingHandler(
            extensions=extensions,
            ignore_patterns=ignore_dirs,
            output_file=output_file,
            verbose=verbose,
            file_index=self.file_index
        )
    
    def start(self):
        """Start watching for file changes"""
        # Start file index first if enabled
        if self.file_index:
            self.file_index.start()
        
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
        
        # Stop file index
        if self.file_index:
            self.file_index.stop()
    
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
                 file_index: Optional['FileIndex'] = None):
        super().__init__()
        self.extensions = [ext.lower() for ext in extensions]
        self.ignore_patterns = ignore_patterns
        self.output_file = output_file
        self.verbose = verbose
        self.move_events: List[Dict] = []
        self.file_index = file_index
        
        # Track files processed by file index to avoid duplicates
        self.file_index_processed_files: Dict[str, float] = {}  # file_path -> timestamp
        
        # Simplified correlation for Windows directory moves
        self.correlation_lock = threading.Lock()
        self.pending_deletes: Dict[str, Dict] = {}  # path -> event_data
        self.correlation_timeout = 3.0  # Fixed timeout for correlation
        
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
        
        # Check if this is a move event with old_path and new_path
        if 'old_path' in event_data and 'new_path' in event_data:
            old_path = event_data['old_path']
            new_path = event_data['new_path']
            
            if self.verbose:
                print(f"[{timestamp}] {event_type.upper()}: {old_path} -> {new_path}")
            else:
                print(f"{event_type.upper()}: {Path(old_path).name} -> {Path(new_path).name}")
        else:
            # Handle non-move events (standalone creates/deletes)
            path = event_data.get('path', 'unknown')
            if self.verbose:
                print(f"[{timestamp}] {event_type.upper()}: {path}")
            else:
                print(f"{event_type.upper()}: {Path(path).name}")
        
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
            # Log the directory move itself
            if self.verbose:
                print(f"[{datetime.now().isoformat()}] DIRECTORY_MOVED: {src_path} -> {dest_path}")
            else:
                print(f"DIRECTORY_MOVED: {Path(src_path).name} -> {Path(dest_path).name}")
            
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
        """Handle file/directory delete events"""
        path = str(event.src_path)
        
        # Skip if path should be ignored
        if self.should_ignore_path(path):
            return
        
        is_directory = isinstance(event, DirDeletedEvent)
        
        # For files, check if we should track them
        if not is_directory and not self.should_track_file(path):
            return
        
        if self.verbose:
            print(f"[DELETE EVENT] {path} (directory: {is_directory})")
        
        # Notify file index about deletion if it's a file we track
        if self.file_index and not is_directory and self.should_track_file(path):
            self.file_index.record_deletion(path)
        
        # Handle directory deletion - check if it contained tracked files
        if self.file_index and is_directory:
            # Get files that were in this directory
            files_in_dir = self.file_index.get_files_in_directory(path)
            for file_path in files_in_dir:
                if self.verbose:
                    print(f"[DELETE EVENT] Recording deletion of file in deleted directory: {file_path}")
                self.file_index.record_deletion(file_path)
        
        # For correlation: store delete events temporarily
        if not is_directory and self.should_track_file(path):
            self._clean_expired_pending_deletes()
            
            with self.correlation_lock:
                self.pending_deletes[path] = {
                    'timestamp': datetime.now().isoformat(),
                    'timestamp_unix': time.time(),
                    'path': path,
                    'is_directory': is_directory
                }
    
    def on_created(self, event):
        """Handle file/directory create events"""
        path = str(event.src_path)
        
        # Skip if path should be ignored
        if self.should_ignore_path(path):
            return
        
        # We are not interested in directory events
        is_directory = isinstance(event, DirCreatedEvent)
        if not is_directory and not self.should_track_file(path):
            return
        
        if self.verbose:
            print(f"[CREATE EVENT] {path} (directory: {is_directory})")
        
        # For file creation in a directory context, check if this might be part of a folder move
        if not is_directory and self.should_track_file(path):
            # Check if this file creation might be from a folder move by looking for
            # recently created parent directories
            parent_path = str(Path(path).parent)
            
            # Look for recent directory creation events that might indicate a folder move
            recent_dir_creation = False
            current_time = time.time()
            
            # Check if the parent directory was recently created (within correlation timeout)
            # This might indicate a folder move scenario
            if hasattr(self, '_recent_dir_creates'):
                for dir_path, create_time in list(self._recent_dir_creates.items()):
                    if (current_time - create_time <= self.correlation_timeout and
                        parent_path.startswith(dir_path)):
                        recent_dir_creation = True
                        if self.verbose:
                            print(f"[CREATE EVENT] File {path} appears to be in recently created directory {dir_path}")
                        break
            
            # If this file appears to be part of a directory move, try to find the old location
            if recent_dir_creation and self.file_index:
                # Use file index to try to find where this file came from
                move_detected = self.file_index.record_creation(path)
                if move_detected:
                    old_path, new_path = move_detected
                    if self.verbose:
                        print(f"[FILE INDEX MOVE] Detected move from directory operation: {old_path} -> {new_path}")
                    
                    # Mark both paths as processed to avoid duplicates
                    current_time = time.time()
                    self.file_index_processed_files[old_path] = current_time
                    self.file_index_processed_files[new_path] = current_time
                    
                    # Record the move event
                    move_event = {
                        'timestamp': datetime.now().isoformat(),
                        'old_path': old_path,
                        'new_path': new_path,
                        'type': 'file_moved',
                        'detection_method': 'file_index_directory_move'
                    }
                    
                    self.log_event(move_event)
                    return  # Don't continue with normal correlation logic
        
        # Track recent directory creations for folder move detection
        if is_directory:
            if not hasattr(self, '_recent_dir_creates'):
                self._recent_dir_creates = {}
            self._recent_dir_creates[path] = time.time()
            
            # Clean up old directory creation records
            current_time = time.time()
            expired_dirs = [
                dir_path for dir_path, create_time in self._recent_dir_creates.items()
                if current_time - create_time > self.correlation_timeout * 2
            ]
            for dir_path in expired_dirs:
                del self._recent_dir_creates[dir_path]
        
        # Check file index for potential move detection
        if (self.file_index and not is_directory and self.should_track_file(path) and
            path not in self.file_index_processed_files):
            
            move_detected = self.file_index.record_creation(path)
            
            if move_detected:
                old_path, new_path = move_detected
                if self.verbose:
                    print(f"[FILE INDEX MOVE] Detected move: {old_path} -> {new_path}")
                
                # Mark both paths as processed to avoid duplicates
                current_time = time.time()
                self.file_index_processed_files[old_path] = current_time
                self.file_index_processed_files[new_path] = current_time
                
                # Check if we already recorded this move to avoid duplicates
                already_recorded = False
                for event in self.move_events:
                    if (event.get('old_path') == old_path and 
                        event.get('new_path') == new_path and
                        event.get('detection_method') == 'file_index'):
                        already_recorded = True
                        break
                
                if not already_recorded:
                    # Record the move event
                    move_event = {
                        'timestamp': datetime.now().isoformat(),
                        'old_path': old_path,
                        'new_path': new_path,
                        'type': 'file_moved',
                        'detection_method': 'file_index'
                    }
                    
                    self.log_event(move_event)
        
        # Try to correlate with pending deletes for Windows-style moves
        if not is_directory and self.should_track_file(path):
            self._try_correlate_create_with_delete(path)
        
        # Clean up expired file index processed files
        current_time = time.time()
        expired_files = [
            file_path for file_path, timestamp in self.file_index_processed_files.items()
            if current_time - timestamp > 600  # Clean up after 10 minutes
        ]
        for file_path in expired_files:
            del self.file_index_processed_files[file_path]
    
    def _clean_expired_pending_deletes(self):
        """Clean up expired pending delete events"""
        current_time = time.time()
        with self.correlation_lock:
            expired_deletes = [
                path for path, data in self.pending_deletes.items()
                if current_time - data['timestamp_unix'] > self.correlation_timeout
            ]
            for path in expired_deletes:
                del self.pending_deletes[path]
    
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
    
    def _try_correlate_create_with_delete(self, create_path: str):
        """Try to correlate a create event with a pending delete event"""
        if not self.pending_deletes:
            return
        
        self._clean_expired_pending_deletes()
        
        create_name, create_ext, create_size = self._get_file_info(create_path)
        current_time = time.time()
        
        if self.verbose:
            print(f"[CORRELATION] Looking for delete match for create event {create_path}")
            print(f"[CORRELATION] Current pending deletes: {list(self.pending_deletes.keys())}")
        
        with self.correlation_lock:
            for delete_path, delete_data in list(self.pending_deletes.items()):
                delete_name, delete_ext, delete_size = self._get_file_info(delete_path)
                
                if self.verbose:
                    print(f"[CORRELATION] Checking delete {delete_path}: name={delete_name}, ext={delete_ext}, size={delete_size}")
                    print(f"[CORRELATION] Against create {create_path}: name={create_name}, ext={create_ext}, size={create_size}")
                
                # Check for correlation match
                time_diff = abs(current_time - delete_data['timestamp_unix'])
                
                if (delete_ext == create_ext and
                    time_diff <= self.correlation_timeout):
                    
                    # Additional checks to increase confidence this is a move:
                    # - Same filename (exact rename/move)
                    # - OR similar file size (different name but likely same file)
                    # - OR if we can't get delete size (common), use timing + extension match
                    same_name = delete_name == create_name
                    similar_size = abs(delete_size - create_size) < 1024 if delete_size > 0 else False
                    no_delete_size = delete_size == 0  # Can't get size of deleted file
                    
                    # Be more permissive if we can't get the deleted file size
                    match_confidence = same_name or similar_size or no_delete_size
                    
                    if match_confidence:
                        if self.verbose:
                            if same_name:
                                match_reason = "same_name"
                            elif similar_size:
                                match_reason = f"similar_size ({delete_size} ≈ {create_size})"
                            else:
                                match_reason = f"timing_and_extension (no_delete_size)"
                            print(f"[CORRELATION] MATCH FOUND ({match_reason})! {delete_path} -> {create_path}")
                        
                        # Check if this file was already processed by the file index to avoid duplicates
                        already_processed_by_index = (
                            create_path in self.file_index_processed_files or
                            delete_path in self.file_index_processed_files
                        )
                        
                        if not already_processed_by_index:
                            # Create move event
                            move_event = {
                                'timestamp': datetime.now().isoformat(),
                                'type': 'file_moved',
                                'old_path': delete_path,
                                'new_path': create_path,
                                'old_name': delete_name,
                                'new_name': create_name,
                                'is_directory': False,
                                'detection_method': 'correlation'
                            }
                            
                            # Check if it's a rename (same parent) or move
                            if Path(delete_path).parent == Path(create_path).parent:
                                move_event['type'] = 'file_renamed'
                            
                            # Mark as processed to avoid future duplicates
                            current_time = time.time()
                            self.file_index_processed_files[delete_path] = current_time
                            self.file_index_processed_files[create_path] = current_time
                            
                            self.log_event(move_event)
                        elif self.verbose:
                            print(f"[CORRELATION] Skipping correlated move - already processed by file index")
                        
                        # Remove the matched delete event
                        del self.pending_deletes[delete_path]
                        return
    
    def flush_pending_events(self) -> List[Dict]:
        """Flush any pending move events (for testing or manual triggering)"""
        with self.correlation_lock:
            # Collect events from pending_deletes
            events_to_flush = list(self.pending_deletes.values())
            self.pending_deletes.clear()

        # Log unmatched delete events if verbose
        for event_data in events_to_flush:
            if self.verbose:
                timestamp = event_data.get('timestamp', 'unknown')
                event_type = 'UNMATCHED_DELETE'
                path = event_data.get('path', 'unknown')
                print(f"[{timestamp}] {event_type}: {path}")

        return events_to_flush
