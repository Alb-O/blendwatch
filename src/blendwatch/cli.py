#!/usr/bin/env python3
"""
BlendWatch CLI - File watcher for tracking renames and moves
"""

import os
import sys
import re
import json
import time
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime

import click
import tomli
from colorama import init, Fore, Style

from .watcher import FileWatcher
from .config import Config, load_config, load_default_config
from .backlinks import find_backlinks, BacklinkScanner

# Initialize colorama for cross-platform colored output
init()


@click.group()
@click.version_option()
def main():
    """BlendWatch - Track file and directory renames/moves with filtering."""
    pass


@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--extensions', '-e', multiple=True, 
              help='File extensions to watch (e.g. .blend, .py, .txt)')
@click.option('--ignore-dirs', '-i', multiple=True,
              help='Directory patterns to ignore (regex supported)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--output', '-o', type=click.Path(),
              help='Output file to log changes (optional)')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
@click.option('--recursive/--no-recursive', default=True,
              help='Watch subdirectories recursively')
def watch(path: str, extensions: tuple, ignore_dirs: tuple, config: Optional[str], 
          output: Optional[str], verbose: bool, recursive: bool):
    """Start watching a directory for file/directory renames and moves."""
    
    # Load configuration - check for default config if none provided
    config_obj = None
    config_file = config
    
    if not config_file:
        # Look for default config file in current directory
        default_config = Path("blendwatch.config.toml")
        if default_config.exists():
            config_file = str(default_config)
            if verbose:
                click.echo(f"{Fore.CYAN}Using default config: {config_file}{Style.RESET_ALL}")
    
    if config_file:
        config_obj = load_config(config_file)
        if not config_obj:
            click.echo(f"{Fore.RED}Error: Could not load config file: {config_file}{Style.RESET_ALL}")
            sys.exit(1)
    
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
    
    click.echo(f"{Fore.GREEN}Starting BlendWatch...{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Watching: {path}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Extensions: {', '.join(watch_extensions)}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Ignore patterns: {', '.join(ignore_patterns)}{Style.RESET_ALL}")
    click.echo(f"{Fore.CYAN}Recursive: {recursive}{Style.RESET_ALL}")
    
    if output:
        click.echo(f"{Fore.CYAN}Output file: {output}{Style.RESET_ALL}")
    
    # Get event correlation timeout from config
    correlation_timeout = 2.0  # default
    if config_obj and hasattr(config_obj, 'debounce_delay'):
        correlation_timeout = float(config_obj.debounce_delay)
    elif default_config and hasattr(default_config, 'debounce_delay'):
        correlation_timeout = float(default_config.debounce_delay)
    
    click.echo(f"{Fore.CYAN}Event correlation timeout: {correlation_timeout}s{Style.RESET_ALL}")
    
    # Create and start the file watcher
    watcher = FileWatcher(
        watch_path=path,
        extensions=watch_extensions,
        ignore_dirs=ignore_patterns,
        output_file=output,
        verbose=verbose,
        recursive=recursive,
        event_correlation_timeout=correlation_timeout
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


@main.command()
@click.argument('config_path', type=click.Path(), default='blendwatch.config.toml')
def init_config(config_path: str):
    """Create a configuration file. Defaults to 'blendwatch.config.toml' if no path specified."""
    
    try:
        # Get the path to the default config file in the package
        default_config_path = Path(__file__).parent / 'default.config.toml'
        
        if config_path.endswith('.json'):
            # Convert TOML to JSON for JSON output
            with open(default_config_path, 'rb') as f:
                config_data = tomli.load(f)
            
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
        else:
            # Copy the TOML file directly
            with open(default_config_path, 'r') as source:
                toml_content = source.read()
            
            with open(config_path, 'w') as dest:
                dest.write(toml_content)
        
        click.echo(f"{Fore.GREEN}Configuration file created: {config_path}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}Edit this file to customize your watching preferences.{Style.RESET_ALL}")
        
    except Exception as e:
        click.echo(f"{Fore.RED}Error creating config file: {e}{Style.RESET_ALL}")
        sys.exit(1)


@main.command()
@click.argument('log_file', type=click.Path(exists=True))
@click.option('--format', 'output_format', type=click.Choice(['json', 'table', 'csv']), 
              default='table', help='Output format')
@click.option('--filter-type', type=click.Choice(['moved', 'renamed', 'all']), 
              default='all', help='Filter by operation type')
@click.option('--since', help='Show changes since date (YYYY-MM-DD)')
def report(log_file: str, output_format: str, filter_type: str, since: Optional[str]):
    """Generate a report from the log file."""
    
    try:
        with open(log_file, 'r') as f:
            if log_file.endswith('.json'):
                events = []
                for line in f:
                    try:
                        events.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            else:
                # Parse text format logs
                events = []
                for line in f:
                    # Simple text parsing - you might want to improve this
                    if ' -> ' in line:
                        parts = line.strip().split(' -> ')
                        if len(parts) == 2:
                            events.append({
                                'timestamp': datetime.now().isoformat(),
                                'type': 'moved',
                                'old_path': parts[0],
                                'new_path': parts[1]
                            })
        
        # Filter events
        if since:
            since_date = datetime.fromisoformat(since)
            events = [e for e in events if datetime.fromisoformat(e.get('timestamp', '')) >= since_date]
        
        if filter_type != 'all':
            events = [e for e in events if e.get('type') == filter_type]
        
        # Output report
        if output_format == 'json':
            click.echo(json.dumps(events, indent=2))
        elif output_format == 'csv':
            click.echo('timestamp,type,old_path,new_path')
            for event in events:
                click.echo(f"{event.get('timestamp', '')},{event.get('type', '')},{event.get('old_path', '')},{event.get('new_path', '')}")
        else:  # table
            click.echo(f"\n{Fore.GREEN}File Operations Report{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Total events: {len(events)}{Style.RESET_ALL}\n")
            
            for event in events:
                timestamp = event.get('timestamp', 'Unknown')
                op_type = event.get('type', 'unknown')
                old_path = event.get('old_path', '')
                new_path = event.get('new_path', '')
                
                click.echo(f"{Fore.YELLOW}[{timestamp}]{Style.RESET_ALL} {Fore.MAGENTA}{op_type.upper()}{Style.RESET_ALL}")
                click.echo(f"  {Fore.RED}From:{Style.RESET_ALL} {old_path}")
                click.echo(f"  {Fore.GREEN}To:{Style.RESET_ALL} {new_path}")
                click.echo()
    
    except Exception as e:
        click.echo(f"{Fore.RED}Error reading log file: {e}{Style.RESET_ALL}")
        sys.exit(1)


@main.command()
@click.argument('target_asset', type=click.Path(exists=True))
@click.argument('search_directory', type=click.Path(exists=True, file_okay=False))
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--max-workers', '-w', default=4, type=int,
              help='Number of parallel threads for scanning (default: 4)')
@click.option('--output-format', '-f', 
              type=click.Choice(['json', 'table'], case_sensitive=False),
              default='table',
              help='Output format (default: table)')
@click.option('--verbose', '-v', is_flag=True,
              help='Enable verbose output')
def backlinks(target_asset: str, search_directory: str, config: Optional[str], 
              max_workers: int, output_format: str, verbose: bool):
    """Find all blend files that link to the target asset.
    
    TARGET_ASSET: Path to the asset file to find backlinks for
    SEARCH_DIRECTORY: Directory to search for blend files
    """
    
    # Load configuration
    config_obj = None
    config_file = config
    
    if not config_file:
        # Look for default config file in current directory
        default_config = Path("blendwatch.config.toml")
        if default_config.exists():
            config_file = str(default_config)
            if verbose:
                click.echo(f"{Fore.CYAN}Using default config: {config_file}{Style.RESET_ALL}")
    
    if config_file:
        config_obj = load_config(config_file)
        if not config_obj:
            click.echo(f"{Fore.RED}Error: Could not load config file: {config_file}{Style.RESET_ALL}")
            sys.exit(1)
    
    # Use default config if no config file provided
    if not config_obj:
        config_obj = load_default_config()
    
    try:
        target_path = Path(target_asset)
        search_path = Path(search_directory)
        
        if verbose:
            click.echo(f"{Fore.GREEN}Searching for backlinks...{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Target: {target_path.name}{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Search directory: {search_path}{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Max workers: {max_workers}{Style.RESET_ALL}")
            if config_obj.ignore_dirs:
                click.echo(f"{Fore.CYAN}Ignoring directories: {', '.join(config_obj.ignore_dirs)}{Style.RESET_ALL}")
        
        # Find backlinks using the scanner with config
        scanner = BacklinkScanner(search_path, config=config_obj)
        results = scanner.find_backlinks_to_file(target_path, max_workers=max_workers)
        
        # Output results
        if output_format == 'json':
            # Convert results to JSON-serializable format
            json_results = []
            for result in results:
                json_results.append({
                    'blend_file': str(result.blend_file),
                    'library_paths': result.library_paths,
                    'matching_libraries': result.matching_libraries
                })
            click.echo(json.dumps(json_results, indent=2))
        else:  # table format
            if results:
                click.echo(f"\n{Fore.GREEN}Found {len(results)} backlinks to {target_path.name}:{Style.RESET_ALL}\n")
                
                for i, result in enumerate(results, 1):
                    click.echo(f"{Fore.YELLOW}{i:2d}.{Style.RESET_ALL} {Fore.CYAN}{result.blend_file.name}{Style.RESET_ALL}")
                    click.echo(f"     Path: {result.blend_file}")
                    click.echo(f"     Libraries: {Fore.MAGENTA}{', '.join(result.matching_libraries)}{Style.RESET_ALL}")
                    
                    if verbose:
                        click.echo(f"     All library paths:")
                        for lib_name, lib_path in result.library_paths.items():
                            marker = Fore.GREEN + "→ " + Style.RESET_ALL if lib_name in result.matching_libraries else "  "
                            click.echo(f"       {marker}{lib_name}: {lib_path}")
                    click.echo()
            else:
                click.echo(f"{Fore.YELLOW}No backlinks found for {target_path.name}{Style.RESET_ALL}")
    
    except Exception as e:
        click.echo(f"{Fore.RED}Error finding backlinks: {e}{Style.RESET_ALL}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
