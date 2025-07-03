"""
CLI commands package for BlendWatch
"""

# Import all command modules to make them available
from .watch import watch_command, watch_alias
from .init_config import init_config_command
from .report import report_command
from .update_links import update_links_command, update_alias
from .backlinks import backlinks_command, links_alias
from .sync import sync_command, auto_alias
from .status import status_command

__all__ = [
    'watch_command', 'watch_alias',
    'init_config_command',
    'report_command',
    'update_links_command', 'update_alias',
    'backlinks_command', 'links_alias',
    'sync_command', 'auto_alias',
    'status_command',
]
