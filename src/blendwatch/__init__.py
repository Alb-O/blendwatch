"""
BlendWatch - File watcher for tracking renames and moves
"""

__version__ = "0.1.0"
__description__ = "Track and updated linked assets in Blender on a large filesystem."

from .watcher import FileWatcher
from .config import Config, load_config

__all__ = ['FileWatcher', 'Config', 'load_config']