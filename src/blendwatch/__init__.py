"""
BlendWatch - File watcher for tracking renames and moves
"""

__version__ = "0.1.0"
__description__ = "Track and updated linked assets in Blender on a large filesystem."

from .watcher import FileWatcher
from .config import Config, load_config
from .library_writer import LibraryPathWriter, update_blend_file_paths, get_blend_file_libraries
from .link_updater import apply_move_log

__all__ = [
    'FileWatcher', 
    'Config', 
    'load_config',
    'LibraryPathWriter',
    'update_blend_file_paths',
    'get_blend_file_libraries',
    'apply_move_log'
]
