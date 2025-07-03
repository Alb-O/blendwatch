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
    
    Use 'blendwatch COMMAND --help' for detailed help on any command.
    """
    pass


@main.command('watch')
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
def watch(path: str, extensions: tuple, ignore_dirs: tuple, config: Optional[str], 
          output: Optional[str], verbose: bool, recursive: bool):
    """Start watching a directory for file/directory renames and moves.
    
    PATH: Directory to watch (defaults to current directory)
    """
    
    # Default output file if not specified
    if not output:
        output = "blendwatch.log"
    
    # Convert relative path to absolute
    watch_path = Path(path).resolve()
    
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
    click.echo(f"{Fore.CYAN}Watching: {watch_path}{Style.RESET_ALL}")
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
        watch_path=str(watch_path),
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


@main.command('init-config')
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


@main.command('report')
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.option('--format', 'output_format', type=click.Choice(['json', 'table', 'csv']), 
              default='table', help='Output format')
@click.option('--filter-type', type=click.Choice(['moved', 'renamed', 'all']), 
              default='all', help='Filter by operation type')
@click.option('--since', help='Show changes since date (YYYY-MM-DD)')
def report(log_file: str, output_format: str, filter_type: str, since: Optional[str]):
    """Generate a report from the log file.
    
    LOG_FILE: Path to the log file to analyze (default: blendwatch.log)
    """
    
    # Resolve path and check existence
    log_path = Path(log_file).resolve()
    
    if not log_path.exists():
        click.echo(f"{Fore.RED}Error: Log file not found: {log_path}{Style.RESET_ALL}")
        
        # Look for alternative log files in current directory
        alternatives = list(Path('.').glob('*.log'))
        if alternatives:
            click.echo(f"{Fore.YELLOW}Available log files in current directory:{Style.RESET_ALL}")
            for alt in alternatives:
                click.echo(f"  {alt}")
        sys.exit(1)
    
    try:
        with open(log_path, 'r') as f:
            if log_path.suffix == '.json':
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


@main.command('update-links')
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.argument('search_directory', type=click.Path(), default='.', required=False)
@click.option('--dry-run', is_flag=True, help='Show changes without modifying files')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def update_links_cmd(log_file: str, search_directory: str, dry_run: bool, verbose: bool):
    """Update linked library paths based on a move log.
    
    LOG_FILE: Path to the move log file (default: blendwatch.log)
    SEARCH_DIRECTORY: Directory to search for blend files (default: current directory)
    """
    
    # Resolve paths and check existence
    log_path = Path(log_file).resolve()
    search_path = Path(search_directory).resolve()
    
    # Check if log file exists
    if not log_path.exists():
        click.echo(f"{Fore.RED}Error: Log file not found: {log_path}{Style.RESET_ALL}")
        
        # Look for alternative log files in current directory
        alternatives = list(Path('.').glob('*.log'))
        if alternatives:
            click.echo(f"{Fore.YELLOW}Available log files in current directory:{Style.RESET_ALL}")
            for alt in alternatives:
                click.echo(f"  {alt}")
        sys.exit(1)
    
    # Check if search directory exists
    if not search_path.exists():
        click.echo(f"{Fore.RED}Error: Search directory not found: {search_path}{Style.RESET_ALL}")
        sys.exit(1)
    
    if not search_path.is_dir():
        click.echo(f"{Fore.RED}Error: Search path must be a directory: {search_path}{Style.RESET_ALL}")
        sys.exit(1)

    from .link_updater import apply_move_log

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
        click.echo(f"{Fore.RED}Error updating links: {e}{Style.RESET_ALL}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command('backlinks')
@click.argument('target_asset', type=click.Path())
@click.argument('search_directory', type=click.Path(), default='.', required=False)
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
    SEARCH_DIRECTORY: Directory to search for blend files (default: current directory)
    """
    
    # Resolve paths
    target_path = Path(target_asset).resolve()
    search_path = Path(search_directory).resolve()
    
    # Check if target exists
    if not target_path.exists():
        click.echo(f"{Fore.RED}Error: Target asset not found: {target_path}{Style.RESET_ALL}")
        sys.exit(1)
    
    # Check if search directory exists
    if not search_path.exists():
        click.echo(f"{Fore.RED}Error: Search directory not found: {search_path}{Style.RESET_ALL}")
        sys.exit(1)
    
    if not search_path.is_dir():
        click.echo(f"{Fore.RED}Error: Search path must be a directory: {search_path}{Style.RESET_ALL}")
        sys.exit(1)
    
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


@main.command('sync')
@click.argument('watch_path', type=click.Path(exists=True), default='.', required=False)
@click.option('--update-dir', type=click.Path(), 
              help='Directory to update links in (default: same as watch path)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--dry-run', is_flag=True, help='Show what would be updated without making changes')
def sync(watch_path: str, update_dir: Optional[str], config: Optional[str], 
         verbose: bool, dry_run: bool):
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
    
    # Load configuration
    config_obj = None
    config_file = config
    
    if not config_file:
        # Look for default config file in current directory
        default_config = watch_dir / "blendwatch.config.toml"
        if default_config.exists():
            config_file = str(default_config)
            if verbose:
                click.echo(f"{Fore.CYAN}Using config: {config_file}{Style.RESET_ALL}")
    
    if config_file:
        config_obj = load_config(config_file)
        if not config_obj:
            click.echo(f"{Fore.RED}Error: Could not load config file: {config_file}{Style.RESET_ALL}")
            sys.exit(1)
    
    # Use default config if no config file provided
    if not config_obj:
        config_obj = load_default_config()
    
    try:
        from .link_updater import apply_move_log
        
        # Start the file watcher
        watcher = FileWatcher(
            watch_path=str(watch_dir),
            extensions=config_obj.extensions,
            ignore_dirs=config_obj.ignore_dirs,
            output_file=str(log_file),
            verbose=verbose,
            recursive=True,
            event_correlation_timeout=float(getattr(config_obj, 'debounce_delay', 2.0))
        )
        
        watcher.start()
        click.echo(f"{Fore.YELLOW}Press Ctrl+C to stop auto-sync...{Style.RESET_ALL}")
        
        # Keep track of when we last processed the log to avoid reprocessing
        last_processed_size = 0
        
        # Keep the program running and periodically check for updates
        while True:
            time.sleep(2)  # Check every 2 seconds
            
            # Check if log file has grown (new events)
            if log_file.exists():
                current_size = log_file.stat().st_size
                if current_size > last_processed_size:
                    if verbose:
                        click.echo(f"{Fore.CYAN}Processing new file changes...{Style.RESET_ALL}")
                    
                    try:
                        updated = apply_move_log(str(log_file), str(update_directory), 
                                               dry_run=dry_run, verbose=verbose)
                        if updated > 0:
                            if dry_run:
                                click.echo(f"{Fore.CYAN}Would update {updated} library paths{Style.RESET_ALL}")
                            else:
                                click.echo(f"{Fore.GREEN}Auto-updated {updated} library paths{Style.RESET_ALL}")
                    except Exception as e:
                        click.echo(f"{Fore.RED}Error during auto-update: {e}{Style.RESET_ALL}")
                        if verbose:
                            import traceback
                            traceback.print_exc()
                    
                    last_processed_size = current_size
            
    except KeyboardInterrupt:
        click.echo(f"\n{Fore.YELLOW}Stopping BlendWatch auto-sync...{Style.RESET_ALL}")
        watcher.stop()
        click.echo(f"{Fore.GREEN}Auto-sync stopped.{Style.RESET_ALL}")
    except Exception as e:
        click.echo(f"{Fore.RED}Error in auto-sync mode: {e}{Style.RESET_ALL}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@main.command('status')
@click.argument('directory', type=click.Path(), default='.', required=False)
@click.option('--verbose', '-v', is_flag=True, help='Show detailed information')
def status(directory: str, verbose: bool):
    """Show the current status of BlendWatch in a directory.
    
    DIRECTORY: Directory to check (default: current directory)
    """
    
    dir_path = Path(directory).resolve()
    
    click.echo(f"{Fore.GREEN}BlendWatch Status for: {dir_path}{Style.RESET_ALL}\n")
    
    # Check for config file
    config_files = [
        dir_path / "blendwatch.config.toml",
        dir_path / "blendwatch.config.json"
    ]
    
    config_found = None
    for config_file in config_files:
        if config_file.exists():
            config_found = config_file
            break
    
    if config_found:
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Configuration: {config_found.name}")
        if verbose:
            try:
                config_obj = load_config(str(config_found))
                if config_obj:
                    click.echo(f"    Extensions: {', '.join(config_obj.extensions)}")
                    click.echo(f"    Ignore patterns: {', '.join(config_obj.ignore_dirs)}")
            except Exception:
                pass
    else:
        click.echo(f"{Fore.YELLOW}○{Style.RESET_ALL} Configuration: Using defaults (no config file found)")
    
    # Check for log files
    log_files = list(dir_path.glob('*.log'))
    if log_files:
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Log files found:")
        for log_file in log_files:
            size = log_file.stat().st_size
            modified = datetime.fromtimestamp(log_file.stat().st_mtime)
            click.echo(f"    {log_file.name} ({size} bytes, modified {modified.strftime('%Y-%m-%d %H:%M:%S')})")
            
            if verbose and log_file.name == 'blendwatch.log':
                # Count recent events
                try:
                    with open(log_file, 'r') as f:
                        recent_events = 0
                        for line in f:
                            try:
                                event = json.loads(line.strip())
                                event_time = datetime.fromisoformat(event.get('timestamp', ''))
                                if (datetime.now() - event_time).days < 7:  # Last 7 days
                                    recent_events += 1
                            except (json.JSONDecodeError, ValueError):
                                continue
                        if recent_events > 0:
                            click.echo(f"      {recent_events} events in the last 7 days")
                except Exception:
                    pass
    else:
        click.echo(f"{Fore.YELLOW}○{Style.RESET_ALL} Log files: None found")
    
    # Check for blend files
    blend_files = list(dir_path.rglob('*.blend'))
    if blend_files:
        click.echo(f"{Fore.GREEN}✓{Style.RESET_ALL} Blend files: {len(blend_files)} found")
        if verbose and len(blend_files) <= 10:
            for blend_file in blend_files:
                rel_path = blend_file.relative_to(dir_path)
                click.echo(f"    {rel_path}")
        elif verbose:
            click.echo(f"    (showing first 10 of {len(blend_files)})")
            for blend_file in blend_files[:10]:
                rel_path = blend_file.relative_to(dir_path)
                click.echo(f"    {rel_path}")
    else:
        click.echo(f"{Fore.YELLOW}○{Style.RESET_ALL} Blend files: None found")
    
    # Suggest next steps
    click.echo(f"\n{Fore.CYAN}Suggested commands:{Style.RESET_ALL}")
    
    if not config_found:
        click.echo(f"  blendwatch init-config    # Create a configuration file")
    
    if not log_files:
        click.echo(f"  blendwatch watch          # Start watching for file changes")
    else:
        click.echo(f"  blendwatch update         # Update links based on recent changes")
        click.echo(f"  blendwatch report         # View report of recent changes")
    
    if blend_files:
        click.echo(f"  blendwatch sync           # Watch and auto-update links")


# Command aliases for convenience
@main.command('w')
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
def w_alias(ctx, **kwargs):
    """Alias for 'watch' command."""
    ctx.invoke(watch, **kwargs)


@main.command('update')
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.argument('search_directory', type=click.Path(), default='.', required=False)
@click.option('--dry-run', is_flag=True, help='Show changes without modifying files')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def update_alias(ctx, **kwargs):
    """Alias for 'update-links' command."""
    ctx.invoke(update_links_cmd, **kwargs)


@main.command('links')
@click.argument('target_asset', type=click.Path())
@click.argument('search_directory', type=click.Path(), default='.', required=False)
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
@click.pass_context
def links_alias(ctx, **kwargs):
    """Alias for 'backlinks' command."""
    ctx.invoke(backlinks, **kwargs)


@main.command('auto')
@click.argument('watch_path', type=click.Path(exists=True), default='.', required=False)
@click.option('--update-dir', type=click.Path(), 
              help='Directory to update links in (default: same as watch path)')
@click.option('--config', '-c', type=click.Path(),
              help='Path to configuration file (TOML or JSON)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--dry-run', is_flag=True, help='Show what would be updated without making changes')
@click.pass_context
def auto_alias(ctx, **kwargs):
    """Alias for 'sync' command."""
    ctx.invoke(sync, **kwargs)


if __name__ == '__main__':
    main()
