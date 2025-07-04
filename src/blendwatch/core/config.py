"""
Configuration management for BlendWatch
"""

from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

# PyInstaller-compatible TOML loading
try:
    import tomli
except (ImportError, ModuleNotFoundError):
    # Fallback for PyInstaller builds - use tomllib from Python 3.11+
    try:
        import tomllib as tomli
    except ImportError:
        # Final fallback for older Python versions
        tomli = None


@dataclass
class Config:
    """Configuration class for BlendWatch"""
    extensions: List[str]
    ignore_dirs: List[str]
    output_format: str = 'toml'
    log_level: str = 'info'
    buffer_size: int = 100
    debounce_delay: float = 0.1
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Create Config instance from dictionary"""
        return cls(
            extensions=data.get('extensions', []),
            ignore_dirs=data.get('ignore_dirs', []),
            output_format=data.get('output_format', 'toml'),
            log_level=data.get('log_level', 'info'),
            buffer_size=data.get('buffer_size', 100),
            debounce_delay=data.get('debounce_delay', 0.1)
        )


def load_config(config_path: str) -> Optional[Config]:
    """Load configuration from TOML file"""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            return None
        
        if tomli is None:
            print(f"TOML support not available in this build. Cannot load config file.")
            return None
            
        with open(config_file, 'rb') as f:
            data = tomli.load(f)
        
        # Handle both flat and nested config formats
        if 'blendwatch' in data:
            config_data = data['blendwatch']
        else:
            config_data = data
            
        return Config.from_dict(config_data)
    
    except Exception as e:
        print(f"Error loading config: {e}")
        return None


def load_default_config() -> Config:
    """Load the default configuration from the package"""
    try:
        default_config_path = Path(__file__).parent / 'default.config.toml'
        if tomli is None:
            # TOML support not available, use hardcoded defaults
            raise ImportError("TOML support not available")
        
        with open(default_config_path, 'rb') as f:
            data = tomli.load(f)
        return Config.from_dict(data)
    except Exception as e:
        # Return sensible defaults if default config can't be loaded
        return Config(
            extensions=['.blend', '.py', '.txt', '.json', '.toml'],
            ignore_dirs=[r'\.git', r'__pycache__', r'\.venv', r'.*\.blend[0-9]+$', r'.*\.blend@$'],
            output_format='toml',
            log_level='info',
            buffer_size=100,
            debounce_delay=0.1
        )
