"""
Init-config command for BlendWatch CLI
"""

import sys
from pathlib import Path

import click
from colorama import Fore, Style


@click.command()
@click.argument('config_path', type=click.Path(), default='blendwatch.config.toml')
def init_config_command(config_path: str):
    """Create a TOML configuration file. Defaults to 'blendwatch.config.toml' if no path specified."""
    
    try:
        # Ensure the config file has a .toml extension
        if not config_path.endswith('.toml'):
            click.echo(f"{Fore.YELLOW}Warning: Config file should have .toml extension. Adding .toml{Style.RESET_ALL}")
            config_path = config_path + '.toml'
        
        # Get the path to the default config file in the package
        default_config_path = Path(__file__).parent.parent.parent / 'default.config.toml'
        
        if default_config_path.exists():
            # Copy the existing default TOML file
            with open(default_config_path, 'r') as source:
                toml_content = source.read()
            
            with open(config_path, 'w') as dest:
                dest.write(toml_content)
        else:
            # Create default TOML content if the default file doesn't exist
            default_toml_content = '''# BlendWatch Configuration File

[blendwatch]
extensions = [".blend", ".py", ".txt", ".json", ".toml"]
ignore_dirs = [
    "\\.git",
    "__pycache__", 
    "\\.venv",
    ".*\\.blend[0-9]+$",
    ".*\\.blend@$"
]
output_format = "toml"
log_level = "info"
buffer_size = 100
debounce_delay = 0.1
'''
            with open(config_path, 'w') as dest:
                dest.write(default_toml_content)
        
        click.echo(f"{Fore.GREEN}TOML configuration file created: {config_path}{Style.RESET_ALL}")
        click.echo(f"{Fore.CYAN}Edit this file to customize your watching preferences.{Style.RESET_ALL}")
        
    except Exception as e:
        click.echo(f"{Fore.RED}Error creating config file: {e}{Style.RESET_ALL}")
        sys.exit(1)
