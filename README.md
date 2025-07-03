# BlendWatch

A CLI file watcher for tracking file and directory renames and moves with intelligent link management for Blender projects.

## Features

- File and directory move/rename detection with cross-platform compatibility
- Automatic Blender library path updates after file moves
- Extension-based filtering and directory ignore patterns with regex support
- Smart defaults and working directory context
- TOML configuration with sensible defaults
- JSON and text output formats
- One-command auto-sync workflow

## Installation

```bash
poetry install
```

> **Note:** Examples below assume `blendwatch` is in your PATH. If using Poetry, prefix commands with `poetry run` (e.g., `poetry run blendwatch sync`).

## Quick Start

**Auto-sync mode (recommended):**

```bash
blendwatch sync
```

**Manual workflow:**

```bash
blendwatch watch          # Start watching (uses current directory)
# ... move/rename files ...
blendwatch update         # Update blend file links
```

**Check project status:**

```bash
blendwatch status
```

## Configuration

The default configuration file `blendwatch.config.toml` is automatically detected:

```toml
extensions = [".blend", ".py", ".txt", ".json"]
ignore_dirs = ["\\.git", "__pycache__", "\\.venv"]
output_format = "json"
log_level = "info"
debounce_delay = 2.0
```

## Usage

### Core Commands

- `blendwatch sync` - Watch and auto-update links (one-command solution)
- `blendwatch watch [PATH]` - Monitor directory for file operations (defaults to current directory)
- `blendwatch update [LOG] [DIR]` - Update library paths from move log (smart defaults)
- `blendwatch backlinks TARGET [DIR]` - Find blend files linking to target asset
- `blendwatch status [DIR]` - Show current project status and suggestions

### Aliases

- `blendwatch w` - Short for `watch`
- `blendwatch links` - Short for `backlinks`
- `blendwatch auto` - Short for `sync`

### Common Workflows

**Start tracking in current project:**

```bash
blendwatch sync                    # Auto-sync mode
# or
blendwatch watch                   # Manual mode
```

**Update links after reorganizing files:**

```bash
blendwatch update                  # Uses blendwatch.log and current directory
```

**Find which files link to an asset:**

```bash
blendwatch links my_asset.blend    # Search current directory
```

**Check what's happening:**

```bash
blendwatch status                  # Shows config, logs, blend files, and suggestions
```

### Advanced Options

All commands support these options where applicable:

- `--config`, `-c` - Configuration file path
- `--verbose`, `-v` - Detailed output
- `--dry-run` - Preview changes without modifying files
- `--output`, `-o` - Custom log file path

### Examples

**Custom configuration:**

```bash
blendwatch init-config my-config.toml
blendwatch watch --config my-config.toml
```

**Monitor specific extensions:**

```bash
blendwatch watch --extensions .blend --extensions .fbx
```

**Verbose output with custom log:**

```bash
blendwatch watch --verbose --output my-changes.log
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

## Working with Large Asset Libraries

BlendWatch excels at managing directory trees full of linked Blender libraries. A typical asset library structure:

```
/assets
├── characters
│   ├── hero.blend
│   └── materials
├── environments
│   ├── forest.blend
│   └── textures
└── props
    └── tools.blend
```

**Simple setup:**

```bash
cd /assets
blendwatch init-config                # Create configuration
blendwatch sync                       # Start auto-sync mode
```

**Alternative manual workflow:**

```bash
cd /assets
blendwatch watch --verbose           # Start watching
# ... reorganize files ...
blendwatch update                     # Fix all broken links
```

As you reorganize or rename files, BlendWatch automatically logs moves and updates any blend files that reference the moved assets. This keeps large libraries consistent without opening each file in Blender.

### Key Benefits

- **Zero-configuration**: Works out of the box with sensible defaults
- **Automatic link updates**: No more broken references after reorganizing
- **Safe operations**: Use `--dry-run` to preview changes
- **Cross-platform**: Handles different path formats seamlessly
- **Scalable**: Efficiently processes large asset libraries
