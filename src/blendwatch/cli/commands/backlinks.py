"""
Backlinks command for BlendWatch CLI
"""

import sys
import json
from pathlib import Path
from typing import Optional

import click
from colorama import Fore, Style
from blender_asset_tracer.cli.common import shorten

from blendwatch.blender.backlinks import BacklinkScanner
from blendwatch.core.config import load_default_config
from blendwatch.cli.utils import load_config_with_fallback, check_file_exists, check_directory_exists, handle_cli_exception


@click.command()
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
def backlinks_command(target_asset: str, search_directory: str, config: Optional[str], 
                      max_workers: int, output_format: str, verbose: bool):
    """Find all blend files that link to the target asset.
    
    TARGET_ASSET: Path to the asset file to find backlinks for
    SEARCH_DIRECTORY: Directory to search for blend files (default: current directory)
    """
    
    # Resolve paths
    target_path = Path(target_asset).resolve()
    search_path = Path(search_directory).resolve()
    
    # Check if target exists
    if not check_file_exists(target_path, "target asset"):
        sys.exit(1)
    
    # Check if search directory exists and is valid
    if not check_directory_exists(search_path, "search directory"):
        sys.exit(1)
    
    # Load configuration with fallback
    config_obj = load_config_with_fallback(config, search_path, verbose)
    
    try:
        cwd = Path.cwd()
        if verbose:
            click.echo(f"{Fore.GREEN}Searching for backlinks...{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Target: {shorten(cwd, target_path)}{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Search directory: {shorten(cwd, search_path)}{Style.RESET_ALL}")
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
                    rel_path = shorten(cwd, result.blend_file)
                    click.echo(f"{Fore.YELLOW}{i:2d}.{Style.RESET_ALL} {Fore.CYAN}{result.blend_file.name}{Style.RESET_ALL}")
                    click.echo(f"     Path: {rel_path}")
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
        handle_cli_exception(e, verbose)


# Alias command
@click.command()
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
    ctx.invoke(backlinks_command, **kwargs)
