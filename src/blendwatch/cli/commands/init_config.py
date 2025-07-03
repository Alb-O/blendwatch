"""
Init-config command for BlendWatch CLI
"""

import sys
import json
from pathlib import Path

import click
import tomli
from colorama import Fore, Style


@click.command()
@click.argument('config_path', type=click.Path(), default='blendwatch.config.toml')
def init_config_command(config_path: str):
    """Create a configuration file. Defaults to 'blendwatch.config.toml' if no path specified."""
    
    try:
        # Get the path to the default config file in the package
        default_config_path = Path(__file__).parent.parent.parent / 'default.config.toml'
        
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
