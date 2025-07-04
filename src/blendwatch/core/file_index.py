#!/usr/bin/env python3
"""
File Index System for BlendWatch

This module provides a file indexing system that tracks all files with specific extensions
in the watched directory. This is used to detect file moves on Windows where watchdog
has limitations with directory move events.

Key functionality:
- Scans directory tree for files with tracked extensions
- Maintains a database of file paths, sizes, and modification times
- Detects when files disappear from one location and appear in another
- Provides correlation between file deletions and creations to detect moves
"""

import os
import time
import threading
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from collections import defaultdict

from ..utils.logging_utils import setup_logger

logger = setup_logger(__name__)


@dataclass
class FileInfo:
    """Information about a tracked file"""
    path: str
    size: int
    mtime: float
    checksum: Optional[str] = None  # For future use if needed
    
    def __hash__(self):
        return hash((self.path, self.size, self.mtime))
    
    def __eq__(self, other):
        if not isinstance(other, FileInfo):
            return False
        return (self.path == other.path and 
                self.size == other.size and 
                abs(self.mtime - other.mtime) < 1.0)  # Allow 1 second tolerance


class FileIndex:
    """
    File index that tracks all files with specific extensions in a directory tree.
    
    This is used to work around Windows watchdog limitations where directory moves
    via shutil.move() generate FileDeletedEvent for the source directory and 
    FileCreatedEvent for files in the destination, but no proper move events.
    """
    
    def __init__(self, watch_path: str, extensions: List[str], rescan_interval: int = 300):
        """
        Initialize the file index.
        
        Args:
            watch_path: Root directory to watch
            extensions: List of file extensions to track (e.g., ['.blend', '.py'])
            rescan_interval: How often to rescan the directory tree (seconds)
        """
        self.watch_path = Path(watch_path)
        self.extensions = set(ext.lower() for ext in extensions)
        self.rescan_interval = rescan_interval
        
        # Current file index: path -> FileInfo
        self.current_files: Dict[str, FileInfo] = {}
        
        # Files that have been deleted recently (for correlation)
        # path -> (FileInfo, deletion_time)
        self.recent_deletions: Dict[str, Tuple[FileInfo, float]] = {}
        
        # Files that have been created recently (for correlation)
        # path -> (FileInfo, creation_time)
        self.recent_creations: Dict[str, Tuple[FileInfo, float]] = {}
        
        # How long to keep recent events for correlation (seconds)
        self.correlation_window = 10.0
        
        # Lock for thread-safe access
        self._lock = threading.RLock()
        
        # Background thread for periodic rescanning
        self._rescan_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        logger.info(f"Initialized FileIndex for {watch_path} with extensions {extensions}")
    
    def start(self):
        """Start the file index system"""
        logger.info("Starting file index system...")
        
        # Initial scan
        self.rescan()
        
        # Start background rescan thread if interval is positive
        if self.rescan_interval > 0:
            self._stop_event.clear()
            self._rescan_thread = threading.Thread(target=self._rescan_loop, daemon=True)
            self._rescan_thread.start()
            logger.info(f"Started background rescan thread (interval: {self.rescan_interval}s)")
    
    def stop(self):
        """Stop the file index system"""
        logger.info("Stopping file index system...")
        
        if self._rescan_thread:
            self._stop_event.set()
            self._rescan_thread.join(timeout=5.0)
            self._rescan_thread = None
        
        logger.info("File index system stopped")
    
    def rescan(self):
        """Perform a full rescan of the directory tree"""
        logger.debug(f"Rescanning directory tree: {self.watch_path}")
        start_time = time.time()
        
        new_files = {}
        file_count = 0
        
        try:
            for root, dirs, files in os.walk(self.watch_path):
                for file in files:
                    file_path = Path(root) / file
                    
                    # Check if this file has a tracked extension
                    if file_path.suffix.lower() in self.extensions:
                        try:
                            stat = file_path.stat()
                            file_info = FileInfo(
                                path=str(file_path),
                                size=stat.st_size,
                                mtime=stat.st_mtime
                            )
                            new_files[str(file_path)] = file_info
                            file_count += 1
                        except (OSError, IOError) as e:
                            logger.warning(f"Could not stat file {file_path}: {e}")
            
            # Update the index atomically
            with self._lock:
                old_files = set(self.current_files.keys())
                new_file_set = set(new_files.keys())
                
                # Find deleted and created files
                deleted_files = old_files - new_file_set
                created_files = new_file_set - old_files
                
                # Log changes
                if deleted_files:
                    logger.debug(f"Files deleted since last scan: {len(deleted_files)}")
                    for path in deleted_files:
                        logger.debug(f"  Deleted: {path}")
                
                if created_files:
                    logger.debug(f"Files created since last scan: {len(created_files)}")
                    for path in created_files:
                        logger.debug(f"  Created: {path}")
                
                self.current_files = new_files
            
            elapsed = time.time() - start_time
            logger.info(f"Rescan completed: {file_count} files indexed in {elapsed:.2f}s")
            
        except Exception as e:
            logger.error(f"Error during directory rescan: {e}")
    
    def _rescan_loop(self):
        """Background thread loop for periodic rescanning"""
        while not self._stop_event.wait(self.rescan_interval):
            try:
                self.rescan()
                self._cleanup_old_events()
            except Exception as e:
                logger.error(f"Error in rescan loop: {e}")
    
    def _cleanup_old_events(self):
        """Clean up old events that are outside the correlation window"""
        current_time = time.time()
        cutoff_time = current_time - self.correlation_window
        
        with self._lock:
            # Clean up old deletions
            old_deletions = [
                path for path, (_, timestamp) in self.recent_deletions.items()
                if timestamp < cutoff_time
            ]
            for path in old_deletions:
                del self.recent_deletions[path]
            
            # Clean up old creations
            old_creations = [
                path for path, (_, timestamp) in self.recent_creations.items()
                if timestamp < cutoff_time
            ]
            for path in old_creations:
                del self.recent_creations[path]
    
    def record_deletion(self, file_path: str):
        """
        Record that a file has been deleted.
        
        This is called by the event handler when a file deletion is detected.
        """
        with self._lock:
            # Check if we have this file in our index
            if file_path in self.current_files:
                file_info = self.current_files[file_path]
                self.recent_deletions[file_path] = (file_info, time.time())
                del self.current_files[file_path]
                logger.debug(f"Recorded deletion: {file_path}")
            else:
                logger.debug(f"Deletion recorded for unknown file: {file_path}")
    
    def record_creation(self, file_path: str) -> Optional[Tuple[str, str]]:
        """
        Record that a file has been created and check for potential moves.
        
        Args:
            file_path: Path of the created file
            
        Returns:
            Tuple of (old_path, new_path) if a move is detected, None otherwise
        """
        try:
            # Get file info for the new file
            stat = Path(file_path).stat()
            new_file_info = FileInfo(
                path=file_path,
                size=stat.st_size,
                mtime=stat.st_mtime
            )
        except (OSError, IOError) as e:
            logger.warning(f"Could not stat created file {file_path}: {e}")
            return None
        
        with self._lock:
            # Add to current files
            self.current_files[file_path] = new_file_info
            
            # Record the creation
            self.recent_creations[file_path] = (new_file_info, time.time())
            
            # Look for a matching deletion
            move_detected = self._find_matching_deletion(new_file_info)
            
            if move_detected:
                old_path, old_file_info = move_detected
                logger.info(f"Move detected: {old_path} -> {file_path}")
                
                # Remove from recent deletions since we matched it
                if old_path in self.recent_deletions:
                    del self.recent_deletions[old_path]
                
                return (old_path, file_path)
            else:
                logger.debug(f"Recorded creation (no move detected): {file_path}")
                return None
    
    def _find_matching_deletion(self, new_file_info: FileInfo) -> Optional[Tuple[str, FileInfo]]:
        """
        Find a recent deletion that matches the given file info.
        
        Args:
            new_file_info: FileInfo for the newly created file
            
        Returns:
            Tuple of (deleted_path, deleted_file_info) if match found, None otherwise
        """
        # Look for files with same size and similar modification time
        for deleted_path, (deleted_file_info, _) in self.recent_deletions.items():
            if (deleted_file_info.size == new_file_info.size and
                abs(deleted_file_info.mtime - new_file_info.mtime) < 2.0):  # 2 second tolerance
                
                # Additional check: same filename
                deleted_name = Path(deleted_path).name
                new_name = Path(new_file_info.path).name
                
                if deleted_name == new_name:
                    return (deleted_path, deleted_file_info)
        
        return None
    
    def get_files_in_directory(self, directory: str) -> List[str]:
        """
        Get all tracked files in a specific directory and its subdirectories.
        
        Args:
            directory: Directory path
            
        Returns:
            List of file paths in that directory tree
        """
        directory_path = Path(directory)
        
        with self._lock:
            files_in_dir = []
            for file_path in self.current_files.keys():
                file_path_obj = Path(file_path)
                # Check if the file is in this directory or any subdirectory
                try:
                    file_path_obj.relative_to(directory_path)
                    files_in_dir.append(file_path)
                except ValueError:
                    # Not in this directory tree
                    continue
            
            return files_in_dir
    
    def is_file_tracked(self, file_path: str) -> bool:
        """
        Check if a file is currently being tracked.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if the file is tracked, False otherwise
        """
        with self._lock:
            return file_path in self.current_files
    
    def get_file_count(self) -> int:
        """Get the total number of tracked files"""
        with self._lock:
            return len(self.current_files)
    
    def get_recent_events_summary(self) -> Dict[str, int]:
        """Get a summary of recent events for debugging"""
        with self._lock:
            return {
                'tracked_files': len(self.current_files),
                'recent_deletions': len(self.recent_deletions),
                'recent_creations': len(self.recent_creations)
            }
