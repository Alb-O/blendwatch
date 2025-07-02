"""
File watcher implementation for tracking renames and moves
"""

import os
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileMovedEvent, DirMovedEvent


class MoveTrackingHandler(FileSystemEventHandler):
    """Event handler for tracking file and directory moves/renames"""
    
    def __init__(self, extensions: List[str], ignore_patterns: List[str], 
                 output_file: Optional[str] = None, verbose: bool = False):
        super().__init__()
        self.extensions = [ext.lower() for ext in extensions]
        self.ignore_patterns = [re.compile(pattern) for pattern in ignore_patterns]
        self.output_file = output_file
        self.verbose = verbose
        self.move_events: List[Dict] = []
        
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
        path_obj = Path(path)
        
        # Check each part of the path against ignore patterns
        for part in path_obj.parts:
            for pattern in self.ignore_patterns:
                if pattern.search(part):
                    return True
        return False
    
    def should_track_file(self, file_path: str) -> bool:
        """Check if file should be tracked based on extensions"""
        if not self.extensions:
            return True  # Track all files if no extensions specified
        
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.extensions
    
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
            event_type = 'directory_moved'
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


class FileWatcher:
    """Main file watcher class"""
    
    def __init__(self, watch_path: str, extensions: List[str], ignore_dirs: List[str],
                 output_file: Optional[str] = None, verbose: bool = False, 
                 recursive: bool = True):
        self.watch_path = Path(watch_path)
        self.extensions = extensions
        self.ignore_dirs = ignore_dirs
        self.output_file = output_file
        self.verbose = verbose
        self.recursive = recursive
        
        # Create event handler
        self.event_handler = MoveTrackingHandler(
            extensions=extensions,
            ignore_patterns=ignore_dirs,
            output_file=output_file,
            verbose=verbose
        )
        
        # Create observer
        self.observer = Observer()
    
    def start(self):
        """Start watching for file system events"""
        self.observer.schedule(
            self.event_handler,
            str(self.watch_path),
            recursive=self.recursive
        )
        self.observer.start()
        
        if self.verbose:
            print(f"Started watching: {self.watch_path}")
    
    def stop(self):
        """Stop watching for file system events"""
        self.observer.stop()
        self.observer.join()
        
        if self.verbose:
            print(f"Stopped watching: {self.watch_path}")
    
    def get_events(self) -> List[Dict]:
        """Get list of recorded events"""
        return self.event_handler.move_events.copy()
    
    def is_alive(self) -> bool:
        """Check if watcher is still running"""
        return self.observer.is_alive()
