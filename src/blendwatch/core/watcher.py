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
        
        # Track recent directory moves to avoid double-reporting file moves
        self.recent_directory_moves: Dict[str, str] = {}  # old_dir -> new_dir
        
        # Track files that have already been processed as part of directory moves
        self.directory_processed_files: Dict[str, float] = {}  # file_path -> timestamp
        
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
            # Track this directory move FIRST to avoid double-reporting file moves
            with self.correlation_lock:
                self.recent_directory_moves[src_path] = dest_path
                
                # Clean up old directory moves (keep only recent ones)
                if len(self.recent_directory_moves) > 10:
                    # Remove oldest entries
                    keys_to_remove = list(self.recent_directory_moves.keys())[:len(self.recent_directory_moves)//2]
                    for old_dir in keys_to_remove:
                        del self.recent_directory_moves[old_dir]
            
            # Log the directory move itself
            if self.verbose:
                print(f"[{datetime.now().isoformat()}] DIRECTORY_MOVED: {src_path} -> {dest_path}")
            else:
                print(f"DIRECTORY_MOVED: {Path(src_path).name} -> {Path(dest_path).name}")
            
            # Directory move: find all relevant files and create individual move events
            moved_files = path_utils.find_files_by_extension(Path(dest_path), self.extensions, recursive=True)
            current_time = time.time()
            
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
                
                # Track that we've processed these file paths as part of a directory move
                with self.correlation_lock:
                    self.directory_processed_files[str(old_file_path)] = current_time
                    self.directory_processed_files[str(new_file_path)] = current_time
            
            return
        elif isinstance(event, FileMovedEvent):
            # Check if file should be tracked
            if not self.should_track_file(src_path) and not self.should_track_file(dest_path):
                return
            
            # Check if this file move is part of a recent directory move
            # If so, don't log it separately since it was already logged by the directory move handler
            with self.correlation_lock:
                for old_dir, new_dir in self.recent_directory_moves.items():
                    # Check if this file was moved as part of the directory move
                    if (src_path.startswith(old_dir) and dest_path.startswith(new_dir)):
                        # Calculate relative paths to verify it's the same logical move
                        try:
                            src_relative = str(Path(src_path))[len(str(Path(old_dir))):].lstrip(os.sep)
                            dest_relative = str(Path(dest_path))[len(str(Path(new_dir))):].lstrip(os.sep)
                            
                            if src_relative == dest_relative:
                                if self.verbose:
                                    print(f"[FILE_MOVE] Skipping individual file move - already processed as part of directory move {old_dir} -> {new_dir}")
                                return
                        except (ValueError, IndexError):
                            # If path manipulation fails, continue with normal processing
                            pass
            
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
        
        if self.verbose:
            print(f"[DELETE EVENT] {path} (directory: {is_directory})")
        
        # Clean expired events first
        self._clean_expired_events()
        
        # Create event data for correlation
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'path': path,
            'is_directory': is_directory,
            'type': 'file_deleted' if not is_directory else 'directory_deleted'
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
        
        if self.verbose:
            print(f"[CREATE EVENT] {path} (directory: {is_directory})")
        
        # Clean expired events first
        self._clean_expired_events()
        
        # Create event data for correlation
        event_data = {
            'timestamp': datetime.now().isoformat(),
            'path': path,
            'is_directory': is_directory,
            'type': 'file_created' if not is_directory else 'directory_created'
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
            
            # Clean expired directory processed files  
            expired_processed = [
                path for path, timestamp in self.directory_processed_files.items()
                if current_time - timestamp > self.event_correlation_timeout * 3  # Keep longer than correlation timeout
            ]
            for path in expired_processed:
                del self.directory_processed_files[path]
            
            # Clean up recent directory moves if we have too many
            if len(self.recent_directory_moves) > 20:
                # Remove oldest entries (we don't have timestamps, so just remove half)
                keys_to_remove = list(self.recent_directory_moves.keys())[:len(self.recent_directory_moves)//2]
                for old_dir in keys_to_remove:
                    del self.recent_directory_moves[old_dir]
    
    def _try_correlate_events(self, event_data: Dict, is_delete: bool) -> bool:
        """Try to correlate delete/create events into a move operation"""
        with self.correlation_lock:
            file_name, file_ext, file_size = self._get_file_info(event_data['path'])
            current_time = time.time()
            
            # Check if this file has already been processed as part of a directory move
            if event_data['path'] in self.directory_processed_files:
                file_processed_time = self.directory_processed_files[event_data['path']]
                if current_time - file_processed_time < self.event_correlation_timeout * 2:
                    if self.verbose:
                        print(f"[CORRELATION] Skipping {event_data['path']} - already processed as part of directory move")
                    return True  # Indicate we "handled" this event by ignoring it
            
            if is_delete:
                # Store delete event for later correlation with create events
                if self.verbose:
                    print(f"[CORRELATION] Storing delete event for {event_data['path']}")
                self.pending_deletes[event_data['path']] = {
                    **event_data,
                    'timestamp_unix': current_time
                }
                return False
            else:
                # This is a create event - first check for move chains before correlation
                if not event_data['is_directory']:
                    # Check if this file was already processed as part of a directory move
                    # Normalize paths for comparison (handle Windows/Unix path differences)
                    normalized_path = str(Path(event_data['path']))
                    
                    processed_match = False
                    for processed_path in self.directory_processed_files:
                        if str(Path(processed_path)) == normalized_path:
                            file_processed_time = self.directory_processed_files[processed_path]
                            if current_time - file_processed_time < self.event_correlation_timeout * 2:
                                processed_match = True
                                if self.verbose:
                                    print(f"[CORRELATION] Skipping chain move detection for {event_data['path']} - already processed as part of directory move")
                                break
                    
                    if not processed_match:
                        # Check if this might be a move from a recent location (move chain detection)
                        recent_locations = []
                        
                        # Look through recently processed files for the same filename
                        for processed_path, processed_time in list(self.directory_processed_files.items()):
                            if (current_time - processed_time < self.event_correlation_timeout * 2 and
                                Path(processed_path).name == file_name and
                                str(Path(processed_path)) != normalized_path):
                                recent_locations.append(processed_path)
                        
                        # Also check recent move events for the same filename
                        for move_event in reversed(self.move_events[-10:]):  # Check last 10 events
                            if (move_event.get('new_name') == file_name and 
                                str(Path(move_event.get('new_path', ''))) != normalized_path):
                                try:
                                    # Parse timestamp and check if recent
                                    event_time = datetime.fromisoformat(move_event['timestamp'].replace('Z', '+00:00'))
                                    if (current_time - event_time.timestamp()) < self.event_correlation_timeout * 2:
                                        recent_locations.append(move_event['new_path'])
                                except (ValueError, KeyError):
                                    continue
                        
                        # If we found recent locations for this file, create a move event from the most recent one
                        if recent_locations:
                            most_recent_location = recent_locations[0]  # Take the first (most recent due to iteration order)
                            
                            if self.verbose:
                                print(f"[CORRELATION] Creating move event from recent location: {most_recent_location} -> {event_data['path']}")
                            
                            # Create a move event from the recent location
                            move_event = {
                                'timestamp': event_data['timestamp'],
                                'type': 'file_moved',
                                'old_path': most_recent_location,
                                'new_path': event_data['path'],
                                'old_name': Path(most_recent_location).name,
                                'new_name': file_name,
                                'is_directory': False,
                                'correlated': True,
                                'chain_move': True  # Mark as a chained move
                            }
                            
                            # Check if it's a rename (same parent) or move
                            if Path(most_recent_location).parent == Path(event_data['path']).parent:
                                move_event['type'] = 'file_renamed'
                            
                            self.log_event(move_event)
                            return True

                # No chain move found - look for matching delete events
                if self.verbose:
                    print(f"[CORRELATION] Looking for delete match for create event {event_data['path']}")
                    print(f"[CORRELATION] Current pending deletes: {list(self.pending_deletes.keys())}")
                
                for delete_path, delete_data in list(self.pending_deletes.items()):
                    # Check if the delete path was already processed as part of a directory move
                    if delete_path in self.directory_processed_files:
                        delete_processed_time = self.directory_processed_files[delete_path]
                        if current_time - delete_processed_time < self.event_correlation_timeout * 2:
                            if self.verbose:
                                print(f"[CORRELATION] Skipping correlation with {delete_path} - already processed as part of directory move")
                            continue
                    
                    delete_name, delete_ext, delete_size = self._get_file_info(delete_path)
                    
                    if self.verbose:
                        print(f"[CORRELATION] Checking delete {delete_path}: name={delete_name}, ext={delete_ext}, size={delete_size}")
                        print(f"[CORRELATION] Against create {event_data['path']}: name={file_name}, ext={file_ext}, size={file_size}")
                    
                    # For correlation, we check:
                    # 1. Same file extension (must match)
                    # 2. Within timing window (must be close in time)
                    # 3. Same filename OR similar file size (to handle both renames and moves)
                    time_diff = abs(current_time - delete_data['timestamp_unix'])
                    
                    if (delete_ext == file_ext and 
                        time_diff <= self.event_correlation_timeout):
                        
                        # Additional checks to increase confidence this is a move:
                        # - Same filename (exact rename/move)
                        # - OR similar file size (different name but likely same file)
                        # - OR if we can't get delete size (common), use timing + extension match
                        same_name = delete_name == file_name
                        similar_size = abs(delete_size - file_size) < 1024 if delete_size > 0 else False
                        no_delete_size = delete_size == 0  # Can't get size of deleted file
                        
                        # Be more permissive if we can't get the deleted file size
                        match_confidence = same_name or similar_size or no_delete_size
                        
                        if match_confidence:
                            if self.verbose:
                                if same_name:
                                    match_reason = "same_name"
                                elif similar_size:
                                    match_reason = f"similar_size ({delete_size} ≈ {file_size})"
                                else:
                                    match_reason = f"timing_and_extension (no_delete_size)"
                                print(f"[CORRELATION] MATCH FOUND ({match_reason})! {delete_path} -> {event_data['path']}")
                            
                            # Check if this file move is actually just a file being moved into a recently renamed directory
                            # In this case, we don't want to report it as a separate file move
                            file_move_is_directory_related = False
                            # Note: We're already inside the correlation_lock, so no need to acquire it again
                            for old_dir, new_dir in self.recent_directory_moves.items():
                                # Check if the file was moved FROM the directory's old location TO the directory's new location
                                if (delete_path.startswith(old_dir) and 
                                    event_data['path'].startswith(new_dir)):
                                    # This is likely a file move that's part of moving files into a renamed directory
                                    # Don't report it as a separate move
                                    file_move_is_directory_related = True
                                    if self.verbose:
                                        print(f"[CORRELATION] File move is related to directory move {old_dir} -> {new_dir}, skipping separate report")
                                    break
                                
                                # Also check if files are being moved as part of a directory restructure
                                # This handles cases where individual file events are generated during directory moves
                                try:
                                    old_dir_path = Path(old_dir)
                                    new_dir_path = Path(new_dir)
                                    delete_path_obj = Path(delete_path)
                                    create_path_obj = Path(event_data['path'])
                                    
                                    # Check if the delete was in the old directory and create is in the new directory
                                    # with the same relative path (using string-based check for compatibility)
                                    if (str(delete_path_obj).startswith(str(old_dir_path)) and 
                                        str(create_path_obj).startswith(str(new_dir_path))):
                                        
                                        # Calculate relative paths manually to avoid version issues
                                        delete_relative = str(delete_path_obj)[len(str(old_dir_path)):].lstrip(os.sep)
                                        create_relative = str(create_path_obj)[len(str(new_dir_path)):].lstrip(os.sep)
                                        
                                        if delete_relative == create_relative:
                                            file_move_is_directory_related = True
                                            if self.verbose:
                                                print(f"[CORRELATION] File move with same relative path is related to directory move {old_dir} -> {new_dir}, skipping separate report")
                                            break
                                except (ValueError, OSError):
                                    # Handle any path manipulation errors
                                    continue
                            
                            if file_move_is_directory_related:
                                # Remove the matched delete event but don't log a separate file move
                                del self.pending_deletes[delete_path]
                                return True
                            
                            # Found a match! Create move event
                            move_event = {
                                'timestamp': event_data['timestamp'],
                                'type': 'file_moved' if not event_data['is_directory'] else 'directory_moved',
                                'old_path': delete_path,
                                'new_path': event_data['path'],
                                'old_name': delete_name,
                                'new_name': file_name,
                                'is_directory': event_data['is_directory'],
                                'correlated': True
                            }
                            
                            # Check if it's a rename (same parent) or move
                            if Path(delete_path).parent == Path(event_data['path']).parent:
                                move_event['type'] = move_event['type'].replace('moved', 'renamed')
                            
                            # Remove the matched delete event and log the move
                            del self.pending_deletes[delete_path]
                            self.log_event(move_event)
                            return True
                
                # No match found - store create event for later correlation
                if self.verbose:
                    print(f"[CORRELATION] No delete match found, storing create event for {event_data['path']}")
                self.pending_creates[event_data['path']] = {
                    **event_data,
                    'timestamp_unix': current_time
                }
                return False

    def flush_pending_events(self) -> List[Dict]:
        """Flush any pending move events (for testing or manual triggering)"""
        with self.correlation_lock:
            # Collect events from both pending_creates and pending_deletes
            events_to_flush = list(self.pending_creates.values()) + list(self.pending_deletes.values())
            self.pending_creates.clear()
            self.pending_deletes.clear()
        
        # Mark all flushed events as unmatched and log them
        for event_data in events_to_flush:
            # Mark as unmatched since they're being flushed
            event_data['unmatched'] = True
            
            # Only log if this is a proper move event (has both old_path and new_path)
            if 'old_path' in event_data and 'new_path' in event_data:
                self.log_event(event_data)
            elif self.verbose:
                # For non-move events, just print them without adding to move_events
                timestamp = event_data.get('timestamp', 'unknown')
                event_type = event_data.get('type', 'unknown')
                path = event_data.get('path', 'unknown')
                print(f"[{timestamp}] FLUSHED_{event_type.upper()}: {path}")
        
        return events_to_flush
