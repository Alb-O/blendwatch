#!/usr/bin/env python3
"""
BlendWatch CLI - Main entry point
"""

import click
from colorama import init

# Import command modules
from blendwatch.cli.commands.watch import watch_command, watch_alias
from blendwatch.cli.commands.init_config import init_config_command
from blendwatch.cli.commands.report import report_command
from blendwatch.cli.commands.update_links import update_links_command, update_alias
from blendwatch.cli.commands.backlinks import backlinks_command, links_alias
from blendwatch.cli.commands.sync import sync_command, auto_alias
from blendwatch.cli.commands.status import status_command
from blendwatch.cli.commands.deps import deps

# Initialize colorama for cross-platform colored output
init()


@click.group()
@click.version_option()
def main():
    """BlendWatch - Intelligent file tracking and link management for Blender projects.
    
    Common workflows:
    
      # Quick start - watch current directory and auto-update links
      blendwatch sync
      
      # Manual workflow - watch, then update
      blendwatch watch
      blendwatch update
      
      # Check current status
      blendwatch status
      
      # Find which files link to an asset
      blendwatch links my_asset.blend
      
      # Analyze dependencies of a blend file
      blendwatch deps my_file.blend
    
    Use 'blendwatch COMMAND --help' for detailed help on any command.
    """
    pass


# Register main commands
main.add_command(watch_command, name='watch')
main.add_command(init_config_command, name='init-config')
main.add_command(report_command, name='report')
main.add_command(update_links_command, name='update-links')
main.add_command(backlinks_command, name='backlinks')
main.add_command(sync_command, name='sync')
main.add_command(status_command, name='status')
main.add_command(deps, name='deps')

# Register aliases
main.add_command(watch_alias, name='w')
main.add_command(update_alias, name='update')
main.add_command(links_alias, name='links')
main.add_command(auto_alias, name='auto')


if __name__ == '__main__':
    main()
