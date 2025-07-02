# BlendWatch

A CLI file watcher for tracking file and directory renames and moves with configurable filtering.

## Features

- File and directory move/rename detection
- Extension-based filtering
- Directory ignore patterns with regex support
- Cross-platform Windows event correlation
- TOML configuration
- JSON and text output formats

## Installation

```bash
poetry install
```

## Quick Start

Create a configuration file:

```bash
poetry run blendwatch init-config
```

Start watching:

```bash
poetry run blendwatch watch /path/to/directory
```

## Configuration

The default configuration file `blendwatch.config.toml` is automatically used if present:

```toml
extensions = [".blend", ".py", ".txt", ".json"]
ignore_dirs = ["\\.git", "__pycache__", "\\.venv"]
output_format = "json"
log_level = "info"
debounce_delay = 2.0
```

## Usage

### Commands

- `blendwatch watch PATH` - Monitor directory for file operations
- `blendwatch backlinks TARGET_ASSET SEARCH_DIR` - Find blend files linking to target
- `blendwatch init-config [FILE]` - Generate configuration file
- `blendwatch report LOG_FILE` - Analyze recorded events

### Options

- `--config`, `-c` - Configuration file path
- `--extensions`, `-e` - File extensions to monitor
- `--ignore-dirs`, `-i` - Directory patterns to ignore
- `--output`, `-o` - Log file path
- `--verbose`, `-v` - Detailed output
- `--recursive/--no-recursive` - Subdirectory monitoring

### Examples

Monitor with specific extensions:

```bash
poetry run blendwatch watch ~/projects --extensions .py --extensions .js
```

Use custom configuration:

```bash
poetry run blendwatch watch ~/data --config custom.toml --output events.log
```

Find backlinks to a blend file:

```bash
poetry run blendwatch backlinks assets/character.blend ~/projects
```

## Output Format

JSON events:

```json
{
	"timestamp": "2025-07-02T10:30:45.123456",
	"type": "file_moved",
	"old_path": "/src/file.txt",
	"new_path": "/dst/file.txt",
	"is_directory": false
}
```

## Windows Compatibility

Automatically correlates delete+create event pairs into move operations when files are moved between drives or folders on Windows systems. Correlation timeout is configurable via `debounce_delay`.

## Requirements

- Python 3.9+
- watchdog, click, colorama, tomli, blender-asset-tracer
