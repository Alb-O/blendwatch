"""
Sync command for BlendWatch CLI
"""

import sys
import time
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style

from blendwatch.core.watcher import FileWatcher
from blendwatch.blender.link_updater import apply_move_log_incremental
from blendwatch.cli.utils import load_config_with_fallback, handle_cli_exception


@click.command()
@click.argument('watch_path', type=click.Path(exists=True), default='.', required=False)
@click.option('--update-dir', type=click.Path(), 
              help='Directory to update links in (default: same as watch path)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--dry-run', is_flag=True, help='Show what would be updated without making changes')
@click.option('--relative', is_flag=True, help='Write library paths in relative format (e.g., //path/to/file.blend)')
def sync_command(watch_path: str, update_dir: Optional[str], config: Optional[str], 
                 verbose: bool, dry_run: bool, relative: bool):
    """Watch for file changes and automatically update blend file links.
    
    WATCH_PATH: Directory to watch (default: current directory)
    
    This command combines watching and auto-updating functionality.
    It will watch for file moves/renames and immediately update any
    blend files that reference the moved assets.
    """
    
    # Set up paths
    watch_dir = Path(watch_path).resolve()
    update_directory = Path(update_dir).resolve() if update_dir else watch_dir
    log_file = watch_dir / "blendwatch.log"
    
    click.echo(f"{Fore.GREEN}Starting BlendWatch auto-sync mode...{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Watching: {watch_dir}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Updating links in: {update_directory}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Log file: {log_file}{Style.RESET_ALL}")
    
    if dry_run:
        click.echo(f"{Fore.YELLOW}DRY RUN MODE: No files will be modified{Style.RESET_ALL}")
    
    # Load configuration with fallback
    config_obj = load_config_with_fallback(config, watch_dir, verbose)
    
    try:
        # Start the file watcher
        watcher = FileWatcher(
            watch_path=str(watch_dir),
            extensions=config_obj.extensions,
            ignore_dirs=config_obj.ignore_dirs,
            output_file=str(log_file),
            verbose=verbose,
            recursive=True
        )
        
        watcher.start()
        click.echo(f"{Fore.YELLOW}Press Ctrl+C to stop auto-sync...{Style.RESET_ALL}")
        
        # Keep track of when we last processed the log to avoid reprocessing
        # Initialize to current size if log file exists to avoid processing old entries
        last_processed_position = log_file.stat().st_size if log_file.exists() else 0
        
        # Keep the program running and periodically check for updates
        while True:
            time.sleep(2)  # Check every 2 seconds
            
            # Check if log file has grown (new events)
            if log_file.exists():
                current_size = log_file.stat().st_size
                if current_size > last_processed_position:
                    if verbose:
                        click.echo(f"{Fore.CYAN}Processing new file changes... (position: {last_processed_position} -> {current_size}){Style.RESET_ALL}")
                    
                    try:
                        # Process only new entries from the last position
                        updated, new_position = apply_move_log_incremental(
                            str(log_file), str(update_directory), 
                            start_position=last_processed_position,
                            dry_run=dry_run, verbose=verbose, relative=relative
                        )
                        if updated > 0:
                            if dry_run:
                                click.echo(f"{Fore.CYAN}Would update {updated} library paths{Style.RESET_ALL}")
                            else:
                                click.echo(f"{Fore.GREEN}Auto-updated {updated} library paths{Style.RESET_ALL}")
                        else:
                            if verbose:
                                click.echo(f"{Fore.YELLOW}No library path updates needed{Style.RESET_ALL}")
                    except Exception as e:
                        click.echo(f"{Fore.RED}Error during auto-update: {e}{Style.RESET_ALL}")
                        if verbose:
                            import traceback
                            traceback.print_exc()
                    
                    last_processed_position = new_position
            
    except KeyboardInterrupt:
        click.echo(f"\n{Fore.YELLOW}Stopping BlendWatch auto-sync...{Style.RESET_ALL}")
        watcher.stop()
        click.echo(f"{Fore.GREEN}Auto-sync stopped.{Style.RESET_ALL}")
    except Exception as e:
        handle_cli_exception(e, verbose)


# Alias command
@click.command()
@click.argument('watch_path', type=click.Path(exists=True), default='.', required=False)
@click.option('--update-dir', type=click.Path(), 
              help='Directory to update links in (default: same as watch path)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--dry-run', is_flag=True, help='Show what would be updated without making changes')
@click.option('--relative', is_flag=True, help='Write library paths in relative format (e.g., //path/to/file.blend)')
@click.pass_context
def auto_alias(ctx, **kwargs):
    """Alias for 'sync' command."""
    ctx.invoke(sync_command, **kwargs)
