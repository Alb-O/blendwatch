"""
Tests for the CLI module
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from blendwatch.cli import main, watch, init_config


class TestCLI:
    """Test the CLI commands"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_main_help(self):
        """Test main command help"""
        result = self.runner.invoke(main, ['--help'])
        assert result.exit_code == 0
        assert 'BlendWatch' in result.output
        assert 'Track file and directory renames/moves' in result.output
    
    def test_watch_help(self):
        """Test watch command help"""
        result = self.runner.invoke(main, ['watch', '--help'])
        assert result.exit_code == 0
        assert 'Start watching a directory' in result.output
        assert '--extensions' in result.output
        assert '--ignore-dirs' in result.output
        assert '--config' in result.output
    
    def test_init_config_help(self):
        """Test init-config command help"""
        result = self.runner.invoke(main, ['init-config', '--help'])
        assert result.exit_code == 0
        assert 'Create a sample configuration file' in result.output
    
    def test_init_config_toml(self):
        """Test creating TOML configuration file"""
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False) as f:
            result = self.runner.invoke(main, ['init-config', f.name])
            
            assert result.exit_code == 0
            assert 'Sample configuration created' in result.output
            
            # Check file contents
            with open(f.name, 'r') as config_file:
                content = config_file.read()
                assert 'extensions =' in content
                assert 'ignore_dirs =' in content
                assert '".blend"' in content
                assert '".py"' in content
    
    def test_init_config_json(self):
        """Test creating JSON configuration file"""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            result = self.runner.invoke(main, ['init-config', f.name])
            
            assert result.exit_code == 0
            assert 'Sample configuration created' in result.output
            
            # Check file contents
            with open(f.name, 'r') as config_file:
                config_data = json.load(config_file)
                assert 'extensions' in config_data
                assert 'ignore_dirs' in config_data
                assert '.blend' in config_data['extensions']
                assert '.py' in config_data['extensions']
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    def test_watch_with_extensions(self, mock_sleep, mock_watcher_class):
        """Test watch command with extension filters"""
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()  # Simulate Ctrl+C
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(main, [
                'watch', temp_dir,
                '--extensions', '.py',
                '--extensions', '.txt'
            ])
            
            assert result.exit_code == 0
            mock_watcher_class.assert_called_once()
            call_args = mock_watcher_class.call_args
            assert '.py' in call_args.kwargs['extensions']
            assert '.txt' in call_args.kwargs['extensions']
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    def test_watch_with_ignore_dirs(self, mock_sleep, mock_watcher_class):
        """Test watch command with ignore directory patterns"""
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(main, [
                'watch', temp_dir,
                '--ignore-dirs', '__pycache__',
                '--ignore-dirs', r'\.git'
            ])
            
            assert result.exit_code == 0
            mock_watcher_class.assert_called_once()
            call_args = mock_watcher_class.call_args
            assert '__pycache__' in call_args.kwargs['ignore_dirs']
            assert r'\.git' in call_args.kwargs['ignore_dirs']
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    @patch('blendwatch.cli.load_config')
    def test_watch_with_config(self, mock_load_config, mock_sleep, mock_watcher_class):
        """Test watch command with configuration file"""
        from blendwatch.config import Config
        
        # Mock config loading
        mock_config = Config(
            extensions=['.blend', '.py'],
            ignore_dirs=[r'\.git', '__pycache__'],
            output_format='json',
            log_level='info'
        )
        mock_load_config.return_value = mock_config
        
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with tempfile.NamedTemporaryFile(suffix='.toml') as config_file:
                result = self.runner.invoke(main, [
                    'watch', temp_dir,
                    '--config', config_file.name
                ])
                
                assert result.exit_code == 0
                mock_load_config.assert_called_once_with(config_file.name)
                mock_watcher_class.assert_called_once()
                
                call_args = mock_watcher_class.call_args
                assert '.blend' in call_args.kwargs['extensions']
                assert '.py' in call_args.kwargs['extensions']
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    def test_watch_with_output_file(self, mock_sleep, mock_watcher_class):
        """Test watch command with output file"""
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with tempfile.NamedTemporaryFile(delete=False) as output_file:
                result = self.runner.invoke(main, [
                    'watch', temp_dir,
                    '--output', output_file.name
                ])
                
                assert result.exit_code == 0
                mock_watcher_class.assert_called_once()
                call_args = mock_watcher_class.call_args
                assert call_args.kwargs['output_file'] == output_file.name
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    def test_watch_verbose_mode(self, mock_sleep, mock_watcher_class):
        """Test watch command in verbose mode"""
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(main, [
                'watch', temp_dir,
                '--verbose'
            ])
            
            assert result.exit_code == 0
            mock_watcher_class.assert_called_once()
            call_args = mock_watcher_class.call_args
            assert call_args.kwargs['verbose'] == True
    
    @patch('blendwatch.cli.FileWatcher')
    @patch('blendwatch.cli.time.sleep')
    def test_watch_non_recursive(self, mock_sleep, mock_watcher_class):
        """Test watch command in non-recursive mode"""
        mock_watcher = Mock()
        mock_watcher_class.return_value = mock_watcher
        mock_sleep.side_effect = KeyboardInterrupt()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self.runner.invoke(main, [
                'watch', temp_dir,
                '--no-recursive'
            ])
            
            assert result.exit_code == 0
            mock_watcher_class.assert_called_once()
            call_args = mock_watcher_class.call_args
            assert call_args.kwargs['recursive'] == False
    
    def test_watch_nonexistent_path(self):
        """Test watch command with non-existent path"""
        result = self.runner.invoke(main, [
            'watch', '/nonexistent/path'
        ])
        
        assert result.exit_code != 0
        assert 'does not exist' in result.output or 'Path' in result.output
    
    @patch('blendwatch.cli.load_config')
    def test_watch_invalid_config(self, mock_load_config):
        """Test watch command with invalid config file"""
        mock_load_config.return_value = None
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with tempfile.NamedTemporaryFile(suffix='.toml') as config_file:
                result = self.runner.invoke(main, [
                    'watch', temp_dir,
                    '--config', config_file.name
                ])
                
                assert result.exit_code != 0
                assert 'Could not load config file' in result.output
    
    def test_watch_default_extensions(self):
        """Test that default extensions are used when none specified"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('blendwatch.cli.FileWatcher') as mock_watcher_class:
                with patch('blendwatch.cli.time.sleep', side_effect=KeyboardInterrupt()):
                    result = self.runner.invoke(main, ['watch', temp_dir])
                    
                    assert result.exit_code == 0
                    mock_watcher_class.assert_called_once()
                    call_args = mock_watcher_class.call_args
                    extensions = call_args.kwargs['extensions']
                    assert '.blend' in extensions
                    assert '.py' in extensions
                    assert '.txt' in extensions


class TestConfigIntegration:
    """Integration tests for config loading in CLI"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.runner = CliRunner()
    
    def test_config_overrides_defaults(self):
        """Test that config file values override defaults"""
        toml_content = '''
extensions = [".custom"]
ignore_dirs = ["custom_ignore"]
output_format = "text"
log_level = "debug"
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as config_file:
            config_file.write(toml_content)
            config_file.flush()
            
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch('blendwatch.cli.FileWatcher') as mock_watcher_class:
                    with patch('blendwatch.cli.time.sleep', side_effect=KeyboardInterrupt()):
                        result = self.runner.invoke(main, [
                            'watch', temp_dir,
                            '--config', config_file.name
                        ])
                        
                        assert result.exit_code == 0
                        mock_watcher_class.assert_called_once()
                        call_args = mock_watcher_class.call_args
                        assert call_args.kwargs['extensions'] == ['.custom']
                        assert call_args.kwargs['ignore_dirs'] == ['custom_ignore']
    
    def test_cli_args_override_config(self):
        """Test that CLI arguments override config file values"""
        toml_content = '''
extensions = [".config"]
ignore_dirs = ["config_ignore"]
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as config_file:
            config_file.write(toml_content)
            config_file.flush()
            
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch('blendwatch.cli.FileWatcher') as mock_watcher_class:
                    with patch('blendwatch.cli.time.sleep', side_effect=KeyboardInterrupt()):
                        result = self.runner.invoke(main, [
                            'watch', temp_dir,
                            '--config', config_file.name,
                            '--extensions', '.cli',
                            '--ignore-dirs', 'cli_ignore'
                        ])
                        
                        assert result.exit_code == 0
                        mock_watcher_class.assert_called_once()
                        call_args = mock_watcher_class.call_args
                        # CLI args should override config
                        assert '.cli' in call_args.kwargs['extensions']
                        assert 'cli_ignore' in call_args.kwargs['ignore_dirs']
