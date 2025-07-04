"""
Dependencies command for BlendWatch CLI.

This command provides comprehensive dependency analysis using blender-asset-tracer.
"""

import logging
from pathlib import Path
from typing import Optional

import click

from blender_asset_tracer.cli.common import humanize_bytes

from blendwatch.blender.backlinks import BacklinkScanner, DependencyInfo
from blendwatch.core.config import load_default_config
from blendwatch.cli.utils import load_config_with_fallback
from blendwatch.utils.path_utils import resolve_path

log = logging.getLogger(__name__)


def shorten_path(base_path: Path, target_path: Path) -> str:
    """Shorten a path relative to a base path for display."""
    try:
        return str(target_path.relative_to(base_path))
    except ValueError:
        # If not relative, show abbreviated absolute path
        path_str = str(target_path)
        if len(path_str) > 60:
            return f"...{path_str[-57:]}"
        return path_str


@click.command()
@click.argument('blend_file', type=click.Path(exists=True, path_type=Path))
@click.option('--search-dir', '-d', 
              type=click.Path(exists=True, file_okay=False, path_type=Path),
              help='Directory to search for blend files (defaults to current directory)')
@click.option('--show-missing', '-m', is_flag=True,
              help='Only show missing dependencies')
@click.option('--by-type', '-t', is_flag=True,
              help='Group dependencies by type')
@click.option('--summary', '-s', is_flag=True,
              help='Show summary of dependency types')
@click.option('--verbose', '-v', is_flag=True,
              help='Show detailed information about each dependency')
@click.option('--config-file', '-c',
              type=click.Path(exists=True, path_type=Path),
              help='Path to configuration file')
def deps(blend_file: Path, search_dir: Optional[Path], show_missing: bool, 
         by_type: bool, summary: bool, verbose: bool, config_file: Optional[Path]):
    """Analyze dependencies of a blend file using blender-asset-tracer.
    
    This command provides comprehensive dependency analysis including:
    - Library files (.blend)
    - Image sequences and UDIMs  
    - Individual texture files
    - Sound files
    - Other asset types
    
    BLEND_FILE: Path to the blend file to analyze
    """
    
    try:
        # Load configuration using the utility function
        config = load_config_with_fallback(
            str(config_file) if config_file else None, 
            search_dir if search_dir else Path.cwd()
        )
        
        # Use provided search directory or default to current directory
        if search_dir is None:
            search_dir = Path.cwd()
        
        # Initialize scanner
        scanner = BacklinkScanner(search_dir, config)
        
        # Show summary only
        if summary:
            click.echo(f"Analyzing dependencies for {shorten_path(Path.cwd(), blend_file)}...")
            dep_summary = scanner.get_dependency_summary(blend_file)
            
            click.echo(f"\nDependency Summary for {blend_file.name}:")
            click.echo("=" * 50)
            
            total_deps = sum(dep_summary.values())
            if total_deps == 0:
                click.echo("No dependencies found.")
                return
            
            for dep_type, count in sorted(dep_summary.items()):
                click.echo(f"  {dep_type:20} {count:4d}")
            
            click.echo(f"  {'Total':20} {total_deps:4d}")
            return
        
        # Progress callback for long operations
        progress_cb = None
        # Note: blender-asset-tracer progress.Spinner doesn't exist, so we'll skip this for now
        
        # Get dependencies
        if show_missing:
            dependencies = scanner.find_missing_dependencies(blend_file)
            if not dependencies:
                click.echo(f"✓ All dependencies found for {blend_file.name}")
                return
            
            click.echo(f"Missing dependencies for {blend_file.name}:")
            click.echo("=" * 50)
        else:
            dependencies = scanner.find_all_dependencies(blend_file, progress_cb)
            click.echo(f"Dependencies for {blend_file.name}:")
            click.echo("=" * 50)
        
        if not dependencies:
            click.echo("No dependencies found.")
            return
        
        # Group by type if requested
        if by_type:
            by_type_dict = {}
            for dep in dependencies:
                dep_type = dep.usage_type
                if dep.is_sequence:
                    dep_type += "_sequence"
                
                if dep_type not in by_type_dict:
                    by_type_dict[dep_type] = []
                by_type_dict[dep_type].append(dep)
            
            for dep_type, deps in sorted(by_type_dict.items()):
                click.echo(f"\n{dep_type.upper()} ({len(deps)} files):")
                click.echo("-" * 30)
                
                for dep in deps:
                    _display_dependency(dep, verbose)
        else:
            # Show all dependencies in order
            for dep in dependencies:
                _display_dependency(dep, verbose)
        
        click.echo(f"\nTotal: {len(dependencies)} dependencies")
        
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()
    except Exception as e:
        log.error(f"Error analyzing dependencies: {e}")
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


def _display_dependency(dep: DependencyInfo, verbose: bool):
    """Display a single dependency with appropriate formatting."""
    
    # Color coding for different states
    if not dep.asset_path.exists():
        status = click.style("✗ MISSING", fg="red", bold=True)
    else:
        status = click.style("✓", fg="green")
    
    # Sequence indicator
    seq_indicator = " [SEQ]" if dep.is_sequence else ""
    
    # Basic display
    path_display = shorten_path(Path.cwd(), dep.asset_path)
    click.echo(f"  {status} {path_display}{seq_indicator}")
    
    # Verbose details
    if verbose:
        click.echo(f"      Type: {dep.usage_type}")
        click.echo(f"      Block: {dep.block_name}")
        if dep.asset_path.exists():
            try:
                size = dep.asset_path.stat().st_size
                size_str = _humanize_bytes(size)
                click.echo(f"      Size: {size_str}")
            except (OSError, IOError):
                pass
        click.echo()


def _humanize_bytes(size: int) -> str:
    """Convert bytes to human readable format."""
    size_float = float(size)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_float < 1024.0:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024.0
    return f"{size_float:.1f} PB"
