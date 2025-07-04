# Technical Implementation Guide: blender-asset-tracer Integration

## Module-by-Module Analysis

### Current BlendWatch Architecture
```
blendwatch/
├── blender/
│   ├── library_writer.py      # 500+ lines - Path conversion, blend I/O
│   ├── backlinks.py          # 400+ lines - Asset discovery
│   ├── link_updater.py       # 200+ lines - Update coordination
│   └── block_level_optimizations.py  # 400+ lines - I/O optimizations
├── utils/
│   └── path_utils.py         # 100+ lines - Path utilities
└── cli/
    └── commands/             # Various CLI implementations
```

### blender-asset-tracer Modules We Can Leverage
```
blender_asset_tracer/
├── bpathlib.py              # Robust path handling
├── blendfile/               # Advanced blend file operations
├── trace/                   # Asset dependency tracking
├── cli/common.py           # CLI utilities
└── compressor.py           # File compression support
```

---

## Detailed Implementation Plans

### Phase 1: Path Handling Replacement

#### Current Implementation (library_writer.py:386-420)
```python
def _convert_to_relative_path(self, absolute_path: str) -> str:
    """Convert an absolute path to Blender relative format if possible."""
    try:
        new_path_obj = resolve_path(absolute_path)
        blend_dir = self.blend_file_path.parent
        
        # Try direct relative path first
        relative_path = get_relative_path(new_path_obj, blend_dir)
        if relative_path is not None:
            return '//' + str(relative_path).replace('\\', '/')
        
        # Complex fallback logic with common ancestor finding
        # ... 30+ lines of custom edge case handling
        
    except (ValueError, OSError):
        return absolute_path
```

#### New Implementation Using blender-asset-tracer
```python
from blender_asset_tracer.bpathlib import BlendPath

def _convert_to_relative_path(self, absolute_path: str) -> str:
    """Convert an absolute path to Blender relative format if possible."""
    try:
        blend_path = BlendPath(absolute_path)
        relative = blend_path.mkrelative(self.blend_file_path.parent)
        return relative if relative.startswith('//') else absolute_path
    except Exception:
        return absolute_path
```

**Code reduction:** ~40 lines → ~6 lines (85% reduction)

#### Migration Steps
1. Add import: `from blender_asset_tracer.bpathlib import BlendPath`
2. Replace method implementation
3. Update unit tests in `test_library_writer.py`
4. Verify cross-platform compatibility

---

### Phase 2: CLI Utilities Enhancement

#### Current Implementation (scattered across CLI commands)
```python
# Custom path shortening
def shorten_path(path):
    if len(path) > 50:
        return f"...{path[-47:]}"
    return path

# No file size reporting
# Basic progress output
```

#### New Implementation
```python
from blender_asset_tracer.cli.common import shorten, humanize_bytes

# In CLI commands
print(f"Updated {shorten(blend_file)} -> {shorten(new_path)}")
print(f"File size: {humanize_bytes(file_size)}")

# Enhanced status command
def show_file_info(blend_file):
    size = blend_file.stat().st_size
    libs = get_blend_file_libraries(blend_file)
    print(f"{shorten(str(blend_file))} ({humanize_bytes(size)})")
    print(f"  Libraries: {len(libs)}")
    for name, path in libs.items():
        print(f"    {name} -> {shorten(path)}")
```

#### Files to Modify
- `src/blendwatch/cli/commands/status.py` - Add file size reporting
- `src/blendwatch/cli/commands/update_links.py` - Better path display
- `src/blendwatch/cli/commands/sync.py` - Enhanced verbose output
- `src/blendwatch/blender/link_updater.py` - Update verbose messages

---

### Phase 3: Asset Tracking Enhancement

#### Current Implementation (backlinks.py)
```python
class BacklinkScanner:
    def find_backlinks_to_file(self, target_file: str) -> List[BacklinkResult]:
        # Scans directory tree
        # Manually parses blend files
        # Basic path matching
        # ~200 lines of custom logic
```

#### Enhanced Implementation
```python
from blender_asset_tracer.trace import dependencies

class BacklinkScanner:
    def find_backlinks_to_file(self, target_file: str) -> List[BacklinkResult]:
        # Use existing implementation for backward compatibility
        return self._legacy_find_backlinks(target_file)
    
    def find_all_dependencies(self, blend_file: str) -> Dict[str, List[str]]:
        """New capability: find ALL dependencies of a blend file"""
        deps = dependencies(blend_file)
        return {
            'libraries': [str(dep) for dep in deps if dep.suffix == '.blend'],
            'images': [str(dep) for dep in deps if dep.suffix in {'.png', '.jpg', '.exr'}],
            'sequences': [str(dep) for dep in deps if self._is_sequence(dep)],
        }
    
    def _is_sequence(self, path):
        # Use blender-asset-tracer's sequence detection
        from blender_asset_tracer.trace.file_sequence import FileSequence
        return FileSequence.is_sequence_file(path)
```

#### New CLI Commands
```python
# blendwatch deps command
@click.command()
@click.argument('blend_file', type=click.Path(exists=True))
def deps_command(blend_file: str):
    """Show all dependencies of a blend file"""
    scanner = BacklinkScanner('.')
    deps = scanner.find_all_dependencies(blend_file)
    
    print(f"Dependencies for {shorten(blend_file)}:")
    for dep_type, files in deps.items():
        if files:
            print(f"  {dep_type.title()}:")
            for file in files:
                print(f"    {shorten(file)}")
```

---

### Phase 4: Progress Reporting

#### Current Implementation
```python
# Basic print statements
print(f"Processing {file}...")
print(f"Updated {count} files")
```

#### Enhanced Implementation
```python
from blender_asset_tracer.trace.progress import Spinner, Progress

# For long operations
with Spinner("Scanning directory tree..."):
    files = self._scan_directory()

# For operations with known progress
with Progress("Processing files", total=len(files)) as progress:
    for file in files:
        # Process file
        progress.update(1)
```

#### Files to Enhance
- `src/blendwatch/core/watcher.py` - Directory scanning progress
- `src/blendwatch/blender/backlinks.py` - Backlink scanning progress
- `src/blendwatch/cli/commands/sync.py` - Sync operation progress

---

### Phase 5: Code Consolidation

#### Files to Simplify/Remove

**path_utils.py reductions:**
```python
# REMOVE: Custom relative path logic (replaced by BlendPath)
def get_relative_path(path: Path, base: Path) -> Optional[Path]:
    # 20+ lines → DELETE

# KEEP: Basic utilities
def resolve_path(path: str) -> Path:
    # Still needed for consistency

def bytes_to_string(data: bytes) -> str:
    # Still needed for blend file parsing
```

**library_writer.py reductions:**
```python
# SIMPLIFY: Path matching logic (use blender-asset-tracer normalization)
def _find_matching_libraries(self, current_paths, path_mapping):
    # 80+ lines → 30-40 lines
    # Use BlendPath for normalization instead of custom logic

# SIMPLIFY: Debug output (use shorten() for paths)
def _debug_path_matching(self, current_paths, path_mapping):
    # Better formatted output with shorten()
```

---

## Implementation Priority Matrix

| Phase | Impact | Effort | Risk | Priority |
|-------|--------|--------|------|----------|
| 1. Path handling | High | Low | Low | 🟢 Start Here |
| 2. CLI utilities | Medium | Low | Low | 🟡 Next |
| 5. Consolidation | High | Medium | Low | 🟡 Parallel |
| 4. Progress | Low | Low | Low | 🟡 Nice to have |
| 3. Asset tracking | High | High | Medium | 🔴 Later |

---

## Testing Strategy

### Integration Tests
```python
# test_blender_asset_tracer_integration.py
def test_path_conversion_compatibility():
    """Ensure new path conversion matches old behavior for common cases"""
    
def test_cli_output_improvements():
    """Verify enhanced CLI output is better formatted"""
    
def test_performance_regression():
    """Ensure no performance degradation"""
```

### Backward Compatibility
- All existing APIs remain unchanged
- Internal implementation improvements only
- Same command-line interface

---

## Migration Checklist

### Pre-Implementation
- [ ] Create feature branch: `feature/blender-asset-tracer-integration`
- [ ] Document current behavior with tests
- [ ] Benchmark current performance

### Phase 1: Path Handling
- [ ] Update imports in library_writer.py
- [ ] Replace _convert_to_relative_path method
- [ ] Update tests
- [ ] Verify cross-platform compatibility
- [ ] Performance test

### Phase 2: CLI Utilities  
- [ ] Add shorten() to all verbose output
- [ ] Add file size reporting to status commands
- [ ] Update CLI help text
- [ ] Test CLI output formatting

### Phase 3: Asset Tracking
- [ ] Study blender-asset-tracer trace APIs
- [ ] Implement enhanced BacklinkScanner methods
- [ ] Add new CLI commands
- [ ] Comprehensive testing

### Phase 4: Progress Reporting
- [ ] Add progress bars to long operations
- [ ] Test progress reporting UX
- [ ] Ensure graceful fallback

### Phase 5: Consolidation
- [ ] Remove redundant code
- [ ] Simplify complex methods
- [ ] Update documentation
- [ ] Final performance validation

### Post-Implementation
- [ ] Update README with new capabilities
- [ ] Document API changes
- [ ] Create migration guide
- [ ] Performance comparison report

---

## Expected File Changes Summary

| File | Current Lines | Expected Lines | Change |
|------|---------------|----------------|---------|
| library_writer.py | ~500 | ~400 | -20% |
| path_utils.py | ~100 | ~60 | -40% |
| backlinks.py | ~400 | ~450 | +12% (new features) |
| CLI commands | ~300 | ~350 | +15% (better output) |
| **Total** | ~1300 | ~1260 | **-3% + better features** |

The slight overall reduction combined with significant feature improvements and robustness gains makes this a very worthwhile refactor.
