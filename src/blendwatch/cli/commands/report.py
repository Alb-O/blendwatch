"""
Report command for BlendWatch CLI
"""

import sys
import json
from pathlib import Path
from typing import Optional
from datetime import datetime

import click
from colorama import Fore, Style
from blender_asset_tracer.cli.common import shorten

from blendwatch.cli.utils import check_file_exists, suggest_alternatives


@click.command()
@click.argument('log_file', type=click.Path(), default='blendwatch.log', required=False)
@click.option('--format', 'output_format', type=click.Choice(['json', 'table', 'csv']), 
              default='table', help='Output format')
@click.option('--filter-type', type=click.Choice(['moved', 'renamed', 'all']), 
              default='all', help='Filter by operation type')
@click.option('--since', help='Show changes since date (YYYY-MM-DD)')
def report_command(log_file: str, output_format: str, filter_type: str, since: Optional[str]):
    """Generate a report from the log file.
    
    LOG_FILE: Path to the log file to analyze (default: blendwatch.log)
    """
    
    # Resolve path and check existence
    log_path = Path(log_file).resolve()
    
    if not check_file_exists(log_path, "log file"):
        # Look for alternative log files in current directory
        suggest_alternatives('*.log', Path('.'))
        sys.exit(1)
    
    try:
        events = []
        with open(log_path, 'r') as f:
            # Try to parse each line as JSON first (BlendWatch format)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    # Fall back to simple text parsing for legacy logs
                    if ' -> ' in line:
                        parts = line.split(' -> ')
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
            # Handle both "moved"/"renamed" and "file_moved"/"file_renamed" formats
            if filter_type == 'moved':
                events = [e for e in events if e.get('type') in ('moved', 'file_moved')]
            elif filter_type == 'renamed':
                events = [e for e in events if e.get('type') in ('renamed', 'file_renamed')]
            else:
                events = [e for e in events if e.get('type') == filter_type]
        
        # Output report
        if output_format == 'json':
            click.echo(json.dumps(events, indent=2))
        elif output_format == 'csv':
            click.echo('timestamp,type,old_path,new_path')
            for event in events:
                click.echo(f"{event.get('timestamp', '')},{event.get('type', '')},{event.get('old_path', '')},{event.get('new_path', '')}")
        else:  # table
            cwd = Path.cwd()
            click.echo(f"\n{Fore.GREEN}File Operations Report{Style.RESET_ALL}")
            click.echo(f"{Fore.CYAN}Total events: {len(events)}{Style.RESET_ALL}\n")
            
            for event in events:
                timestamp = event.get('timestamp', 'Unknown')
                op_type = event.get('type', 'unknown')
                old_path = event.get('old_path', '')
                new_path = event.get('new_path', '')
                
                # Use shorten for better path display
                if old_path:
                    old_path = str(shorten(cwd, Path(old_path)))
                if new_path:
                    new_path = str(shorten(cwd, Path(new_path)))
                
                click.echo(f"{Fore.YELLOW}[{timestamp}]{Style.RESET_ALL} {Fore.MAGENTA}{op_type.upper()}{Style.RESET_ALL}")
                click.echo(f"  {Fore.RED}From:{Style.RESET_ALL} {old_path}")
                click.echo(f"  {Fore.GREEN}To:{Style.RESET_ALL} {new_path}")
                click.echo()
    
    except Exception as e:
        click.echo(f"{Fore.RED}Error reading log file: {e}{Style.RESET_ALL}")
        sys.exit(1)
