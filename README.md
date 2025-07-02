# BlendWatch

A CLI file watcher program specifically designed for tracking and determining file/directory rename/move operations with configurable extension filtering and directory ignore patterns.

## Features

- 🔍 **Intelligent File Tracking**: Detects file and directory renames/moves using filesystem events
- 🎯 **Extension Filtering**: Monitor only the file types you care about (e.g., .blend, .py, .jpg)
- 🚫 **Directory Exclusion**: Ignore directories using regex patterns (.git, **pycache**, node_modules, etc.)
- ⚙️ **TOML Configuration**: Easy-to-read configuration files
- 📊 **Multiple Output Formats**: JSON and human-readable text output
- 🎨 **Colored Output**: Beautiful terminal output with colors
- 📝 **Detailed Logging**: Track all file operations with timestamps

## Installation

Using Poetry (recommended):

```bash
poetry install
```

## Quick Start

1. **Initialize a configuration file:**

   ```bash
   poetry run blendwatch init-config config.toml
   ```

2. **Start watching a directory:**

   ```bash
   poetry run blendwatch watch /path/to/watch --config config.toml
   ```

3. **Watch with custom extensions and ignore patterns:**
   ```bash
   poetry run blendwatch watch /path/to/watch \
     --extensions .blend --extensions .py \
     --ignore-dirs "\.git" --ignore-dirs "__pycache__"
   ```

## Configuration

BlendWatch uses TOML configuration files. Create one using:

```bash
poetry run blendwatch init-config my-config.toml
```

### Sample Configuration

```toml
# File extensions to watch (include the dot)
extensions = [
    ".blend",
    ".py",
    ".txt",
    ".json",
    ".toml",
    ".fbx",
    ".obj",
    ".png",
    ".jpg",
    ".jpeg"
]

# Directory patterns to ignore (regex patterns)
ignore_dirs = [
    "\\.git",          # Git directories
    "__pycache__",     # Python cache
    "\\.venv",         # Virtual environments
    "node_modules",    # Node.js modules
    "\\.DS_Store",     # macOS system files
    "\\.tmp",          # Temporary directories
    "\\.cache"         # Cache directories
]

# Output format: 'json' or 'text'
output_format = "json"

# Log level: 'debug', 'info', 'warning', 'error'
log_level = "info"
```

## Usage

### Commands

- `blendwatch watch PATH` - Start watching a directory
- `blendwatch init-config CONFIG_FILE` - Create a sample configuration
- `blendwatch report LOG_FILE` - Generate reports from log files

### Options

- `--extensions`, `-e` - File extensions to watch (can be used multiple times)
- `--ignore-dirs`, `-i` - Directory patterns to ignore (regex, can be used multiple times)
- `--config`, `-c` - Path to TOML configuration file
- `--output`, `-o` - Output file to save events
- `--verbose`, `-v` - Enable verbose output
- `--recursive/--no-recursive` - Watch subdirectories (default: recursive)

### Examples

**Watch Blender project files:**

```bash
poetry run blendwatch watch ~/BlenderProjects \
  --extensions .blend --extensions .py --extensions .fbx \
  --ignore-dirs "\.git" --ignore-dirs "backup"
```

**Watch with configuration file:**

```bash
poetry run blendwatch watch ~/Projects --config project.toml --output changes.log
```

**Generate reports:**

```bash
poetry run blendwatch report changes.log --format table --filter-type moved
```

## Output Format

### JSON Output

```json
{
	"timestamp": "2025-07-02T10:30:45.123456",
	"event_type": "moved",
	"src_path": "/old/path/file.blend",
	"dest_path": "/new/path/file.blend",
	"is_directory": false
}
```

### Text Output

```
[2025-07-02 10:30:45] MOVED: /old/path/file.blend -> /new/path/file.blend
```

## Use Cases

- **Blender Asset Management**: Track when .blend files and assets are moved or renamed
- **Project Organization**: Monitor file reorganization in large codebases
- **Backup Verification**: Ensure important files haven't been accidentally moved
- **Build System Integration**: Track source file movements for build tools
- **Version Control**: Monitor file operations outside of git tracking

## Requirements

- Python 3.13+
- Poetry (for dependency management)

## Dependencies

- `watchdog>=4.0.0` - Cross-platform file system event monitoring
- `click>=8.1.0` - Command-line interface creation
- `colorama>=0.4.6` - Cross-platform colored terminal output
- `tomli>=2.0.0` - TOML parsing

## License

This project is open source. See the LICENSE file for details.
