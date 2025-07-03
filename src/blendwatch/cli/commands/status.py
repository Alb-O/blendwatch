"""
Status command for BlendWatch CLI
"""

import json
from pathlib import Path
from datetime import datetime

import click
from colorama import Fore, Style

from blendwatch.core.config import load_config


@click.command()
@click.argument('directory', type=click.Path(), default='.', required=False)
@click.option('--verbose', '-v', is_flag=True, help='Show detailed information')
def status_command(directory: str, verbose: bool):
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
