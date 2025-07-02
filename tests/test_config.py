"""
Tests for the config module
"""

import json
import tempfile
import pytest
from pathlib import Path

from blendwatch.config import Config, load_config, load_default_config, load_default_config


class TestConfig:
    """Test the Config class"""
    
    def test_config_creation(self):
        """Test creating a Config instance"""
        config = Config(
            extensions=['.py', '.txt'],
            ignore_dirs=['__pycache__', '.git'],
            output_format='json',
            log_level='info'
        )
        
        assert config.extensions == ['.py', '.txt']
        assert config.ignore_dirs == ['__pycache__', '.git']
        assert config.output_format == 'json'
        assert config.log_level == 'info'
    
    def test_config_from_dict(self):
        """Test creating Config from dictionary"""
        data = {
            'extensions': ['.blend', '.py'],
            'ignore_dirs': [r'\.git', '__pycache__'],
            'output_format': 'text',
            'log_level': 'debug'
        }
        
        config = Config.from_dict(data)
        
        assert config.extensions == ['.blend', '.py']
        assert config.ignore_dirs == [r'\.git', '__pycache__']
        assert config.output_format == 'text'
        assert config.log_level == 'debug'
    
    def test_config_from_dict_defaults(self):
        """Test Config defaults when not all keys are provided"""
        data = {
            'extensions': ['.txt'],
            'ignore_dirs': ['temp']
        }
        
        config = Config.from_dict(data)
        
        assert config.extensions == ['.txt']
        assert config.ignore_dirs == ['temp']
        assert config.output_format == 'json'  # default
        assert config.log_level == 'info'  # default
    
    def test_config_from_dict_empty(self):
        """Test Config with empty dictionary"""
        config = Config.from_dict({})
        
        assert config.extensions == []
        assert config.ignore_dirs == []
        assert config.output_format == 'json'
        assert config.log_level == 'info'


class TestLoadConfig:
    """Test the load_config function"""
    
    def test_load_toml_config(self):
        """Test loading TOML configuration"""
        toml_content = '''
extensions = [".py", ".txt"]
ignore_dirs = ["__pycache__", "\\\\.git"]
output_format = "json"
log_level = "debug"
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write(toml_content)
            f.flush()
            
            config = load_config(f.name)
            
            assert config is not None
            assert config.extensions == ['.py', '.txt']
            assert config.ignore_dirs == ['__pycache__', r'\.git']
            assert config.output_format == 'json'
            assert config.log_level == 'debug'
    
    def test_load_json_config(self):
        """Test loading JSON configuration"""
        json_data = {
            'extensions': ['.blend', '.py'],
            'ignore_dirs': ['node_modules', r'\.venv'],
            'output_format': 'text',
            'log_level': 'warning'
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(json_data, f)
            f.flush()
            
            config = load_config(f.name)
            
            assert config is not None
            assert config.extensions == ['.blend', '.py']
            assert config.ignore_dirs == ['node_modules', r'\.venv']
            assert config.output_format == 'text'
            assert config.log_level == 'warning'
    
    def test_load_nonexistent_config(self):
        """Test loading config from non-existent file"""
        config = load_config('/nonexistent/config.toml')
        assert config is None
    
    def test_load_invalid_config(self):
        """Test loading invalid configuration file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('invalid toml content ][')
            f.flush()
            
            config = load_config(f.name)
            assert config is None
    
    def test_load_config_defaults_to_toml(self):
        """Test that files without extension default to TOML parsing"""
        toml_content = '''
extensions = [".test"]
ignore_dirs = ["test_dir"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(toml_content)
            f.flush()
            
            config = load_config(f.name)
            
            assert config is not None
            assert config.extensions == ['.test']
            assert config.ignore_dirs == ['test_dir']


class TestLoadDefaultConfig:
    """Test loading the default configuration"""
    
    def test_load_default_config(self):
        """Test loading the default configuration from package"""
        config = load_default_config()
        
        assert isinstance(config, Config)
        assert len(config.extensions) > 0
        assert len(config.ignore_dirs) > 0
        assert config.output_format in ['json', 'text']
        assert config.log_level in ['debug', 'info', 'warning', 'error']
        assert config.buffer_size > 0
        assert config.debounce_delay >= 0
        
        # Verify specific expected values from default config
        assert '.blend' in config.extensions
        assert '.py' in config.extensions
        assert r'\.git' in config.ignore_dirs or '\\.git' in config.ignore_dirs
        assert '__pycache__' in config.ignore_dirs
