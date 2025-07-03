"""
Update links command for BlendWatch CLI
"""

import sys
from pathlib import Path

import click
from colorama import Fore, Style

from blendwatch.blender.link_updater import apply_move_log
from blendwatch.cli.utils import check_file_exists, check_directory_exists, suggest_alternatives, handle_cli_exception


@click.command()
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.argument('search_directory', type=click.Path(), default='.', required=False)
@click.option('--dry-run', is_flag=True, help='Show changes without modifying files')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def update_links_command(log_file: str, search_directory: str, dry_run: bool, verbose: bool):
    """Update linked library paths based on a move log.
    
    LOG_FILE: Path to the move log file (default: blendwatch.log)
    SEARCH_DIRECTORY: Directory to search for blend files (default: current directory)
    """
    
    # Resolve paths and check existence
    log_path = Path(log_file).resolve()
    search_path = Path(search_directory).resolve()
    
    # Check if log file exists
    if not check_file_exists(log_path, "log file"):
        # Look for alternative log files in current directory
        suggest_alternatives('*.log', Path('.'))
        sys.exit(1)
    
    # Check if search directory exists and is valid
    if not check_directory_exists(search_path, "search directory"):
        sys.exit(1)

    try:
        if verbose:
            click.echo(f"{Fore.CYAN}Updating links from log: {log_path}{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Searching in directory: {search_path}{Style.RESET_ALL}")
        
        updated = apply_move_log(str(log_path), str(search_path), dry_run=dry_run, verbose=verbose)
        if dry_run:
            click.echo(f"{Fore.CYAN}Would update {updated} library paths{Style.RESET_ALL}")
        else:
            click.echo(f"{Fore.GREEN}Updated {updated} library paths{Style.RESET_ALL}")
    except Exception as e:
        handle_cli_exception(e, verbose)


# Alias command
@click.command()
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.argument('search_directory', type=click.Path(), default='.', required=False)
@click.option('--dry-run', is_flag=True, help='Show changes without modifying files')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def update_alias(ctx, **kwargs):
    """Alias for 'update-links' command."""
    ctx.invoke(update_links_command, **kwargs)
