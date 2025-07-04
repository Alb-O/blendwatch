"""
Watch command for BlendWatch CLI
"""

import time
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style
from blender_asset_tracer.cli.common import shorten

from blendwatch.core.watcher import FileWatcher
from blendwatch.core.config import load_default_config
from blendwatch.cli.utils import load_config_with_fallback

@click.command()
@click.argument('path', type=click.Path(exists=True), default='.', required=False)
@click.option('--extensions', '-e', multiple=True, 
              help='File extensions to watch (e.g. .blend, .py, .txt)')
@click.option('--ignore-dirs', '-i', multiple=True,
              help='Directory patterns to ignore (regex supported)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file to log changes (default: blendwatch.log)')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
@click.option('--recursive/--no-recursive', default=True,
              help='Watch subdirectories recursively')
def watch_command(path: str, extensions: tuple, ignore_dirs: tuple, config: Optional[str], 
                  output: Optional[str], verbose: bool, recursive: bool):
    """Start watching a directory for file/directory renames and moves.
    
    PATH: Directory to watch (defaults to current directory)
    """
    
    # Default output file if not specified
    if not output:
        output = "blendwatch.log"
    
    # Convert relative path to absolute
    watch_path = Path(path).resolve()
    
    # Load configuration with fallback
    config_obj = load_config_with_fallback(config, watch_path, verbose)
    
    # Merge CLI options with config
    watch_extensions = list(extensions) if extensions else []
    ignore_patterns = list(ignore_dirs) if ignore_dirs else []
    
    # Load default config for fallback values
    default_config = load_default_config()
    
    if config_obj:
        if not watch_extensions:
            watch_extensions = config_obj.extensions
        if not ignore_patterns:
            ignore_patterns = config_obj.ignore_dirs
    
    # Use default config as fallback if no config file and no CLI options
    if not watch_extensions:
        watch_extensions = default_config.extensions
    
    if not ignore_patterns:
        ignore_patterns = default_config.ignore_dirs
    
    cwd = Path.cwd()
    click.echo(f"{Fore.GREEN}Starting BlendWatch...{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Watching: {shorten(cwd, watch_path)}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Extensions: {', '.join(watch_extensions)}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Ignore patterns: {', '.join(ignore_patterns)}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Recursive: {recursive}{Style.RESET_ALL}")
    
    if output:
        output_path = Path(output).resolve()
        click.echo(f"{Fore.CYAN}Output file: {shorten(cwd, output_path)}{Style.RESET_ALL}")
    
    # Create and start the file watcher
    watcher = FileWatcher(
        watch_path=str(watch_path),
        extensions=watch_extensions,
        ignore_dirs=ignore_patterns,
        output_file=output,
        verbose=verbose,
        recursive=recursive
    )
    
    try:
        watcher.start()
        click.echo(f"{Fore.YELLOW}Press Ctrl+C to stop watching...{Style.RESET_ALL}")
        
        # Keep the program running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        click.echo(f"\n{Fore.YELLOW}Stopping BlendWatch...{Style.RESET_ALL}")
        watcher.stop()
        click.echo(f"{Fore.GREEN}BlendWatch stopped.{Style.RESET_ALL}")


# Alias command
@click.command()
@click.argument('path', type=click.Path(exists=True), default='.', required=False)
@click.option('--extensions', '-e', multiple=True, 
              help='File extensions to watch (e.g. .blend, .py, .txt)')
@click.option('--ignore-dirs', '-i', multiple=True,
              help='Directory patterns to ignore (regex supported)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file to log changes (default: blendwatch.log)')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
@click.option('--recursive/--no-recursive', default=True,
              help='Watch subdirectories recursively')
@click.pass_context
def watch_alias(ctx, **kwargs):
    """Alias for 'watch' command."""
    ctx.invoke(watch_command, **kwargs)
