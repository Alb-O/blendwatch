"""
Configuration management for BlendWatch
"""

import json
import tomli
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration class for BlendWatch"""
    extensions: List[str]
    ignore_dirs: List[str]
    output_format: str = 'json'
    log_level: str = 'info'
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create Config instance from dictionary"""
        return cls(
            extensions=data.get('extensions', []),
            ignore_dirs=data.get('ignore_dirs', []),
            output_format=data.get('output_format', 'json'),
            log_level=data.get('log_level', 'info')
        )


def load_config(config_path: str) -> Optional[Config]:
    """Load configuration from file"""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            return None
        
        with open(config_file, 'rb') as f:
            if config_path.endswith('.json'):
                # For JSON files, read as text
                with open(config_file, 'r') as text_f:
                    data = json.load(text_f)
            elif config_path.endswith('.toml'):
                data = tomli.load(f)
            else:
                # Default to TOML
                data = tomli.load(f)
        
        return Config.from_dict(data)
    
    except Exception as e:
        print(f"Error loading config: {e}")
        return None
