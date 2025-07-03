"""
Utility functions for CLI commands
"""

import sys
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style

from blendwatch.core.config import Config, load_config, load_default_config


def load_config_with_fallback(config_file: Optional[str], search_dir: Path, verbose: bool = False) -> Config:
    """Load configuration with automatic fallback to default config file and default config."""
    config_obj = None
    
    if not config_file:
        # Look for default config file in search directory
        default_config = search_dir / "blendwatch.config.toml"
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
    
    return config_obj


def check_file_exists(file_path: Path, file_type: str = "file") -> bool:
    """Check if a file exists and show error if not."""
    if not file_path.exists():
        click.echo(f"{Fore.RED}Error: {file_type.title()} not found: {file_path}{Style.RESET_ALL}")
        return False
    return True


def check_directory_exists(dir_path: Path, dir_type: str = "directory") -> bool:
    """Check if a directory exists and is actually a directory."""
    if not dir_path.exists():
        click.echo(f"{Fore.RED}Error: {dir_type.title()} not found: {dir_path}{Style.RESET_ALL}")
        return False
    
    if not dir_path.is_dir():
        click.echo(f"{Fore.RED}Error: {dir_type.title()} path must be a directory: {dir_path}{Style.RESET_ALL}")
        return False
    
    return True


def suggest_alternatives(search_pattern: str, search_dir: Path) -> None:
    """Suggest alternative files based on a glob pattern."""
    alternatives = list(search_dir.glob(search_pattern))
    if alternatives:
        click.echo(f"{Fore.YELLOW}Available files in {search_dir}:{Style.RESET_ALL}")
        for alt in alternatives:
            click.echo(f"  {alt}")


def handle_cli_exception(e: Exception, verbose: bool = False) -> None:
    """Handle exceptions in CLI commands consistently."""
    click.echo(f"{Fore.RED}Error: {e}{Style.RESET_ALL}")
    if verbose:
        import traceback
        traceback.print_exc()
    sys.exit(1)
