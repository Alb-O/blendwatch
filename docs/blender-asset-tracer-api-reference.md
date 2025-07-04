# blender-asset-tracer API Reference for BlendWatch

## Quick Reference for Integration

### Path Handling (bpathlib.py)

```python
from blender_asset_tracer.bpathlib import BlendPath

# Create a BlendPath object
path = BlendPath("/absolute/path/to/file.blend")

# Convert to relative (replaces our _convert_to_relative_path)
relative = path.mkrelative(base_directory)
# Returns: "//relative/path/to/file.blend"

# Convert to absolute  
absolute = path.absolute(base_directory)
# Returns: "/absolute/path/to/file.blend"

# Check if path is relative
is_relative = path.is_relative()
# Returns: True/False
```

### CLI Utilities (cli/common.py)

```python
from blender_asset_tracer.cli.common import shorten, humanize_bytes

# Shorten paths for display (replaces our custom path shortening)
short_path = shorten("/very/long/path/to/some/file.blend")
# Returns: "~/some/file.blend" or similar

# Human readable file sizes (new capability)
size_str = humanize_bytes(1024*1024*5.5)
# Returns: "5.5 MB"
```

### Asset Tracing (trace/)

```python
from blender_asset_tracer.trace import dependencies

# Find all dependencies of a blend file (new capability)
deps = dependencies("/path/to/file.blend")
# Returns: Generator of Path objects for all dependencies

# Filter dependencies by type
blend_deps = [dep for dep in deps if dep.suffix == '.blend']
image_deps = [dep for dep in deps if dep.suffix in {'.png', '.jpg', '.exr'}]
```

### Progress Reporting (trace/progress.py)

```python
from blender_asset_tracer.trace.progress import Spinner, Progress

# Spinner for unknown duration tasks
with Spinner("Scanning directory..."):
    # Long running operation

# Progress bar for known duration tasks  
with Progress("Processing files", total=100) as progress:
    for i in range(100):
        # Do work
        progress.update(1)
```

## Implementation Examples

### Replace Current Path Conversion

**Before (50+ lines in library_writer.py):**
```python
def _convert_to_relative_path(self, absolute_path: str) -> str:
    try:
        new_path_obj = resolve_path(absolute_path)
        blend_dir = self.blend_file_path.parent
        
        # Try direct relative path first
        relative_path = get_relative_path(new_path_obj, blend_dir)
        if relative_path is not None:
            return '//' + str(relative_path).replace('\\', '/')
        
        # Complex fallback logic...
        # [30+ more lines of edge case handling]
    except (ValueError, OSError):
        return absolute_path
```

**After (6 lines):**
```python
def _convert_to_relative_path(self, absolute_path: str) -> str:
    try:
        blend_path = BlendPath(absolute_path)
        return blend_path.mkrelative(self.blend_file_path.parent)
    except Exception:
        return absolute_path
```

### Enhanced CLI Output

**Before:**
```python
print(f"Updated {result.blend_file} -> {new_path}")
```

**After:**
```python
from blender_asset_tracer.cli.common import shorten
print(f"Updated {shorten(str(result.blend_file))} -> {shorten(new_path)}")
```

### New Dependency Analysis Command

```python
@click.command()
@click.argument('blend_file', type=click.Path(exists=True))
def deps_command(blend_file: str):
    """Show all dependencies of a blend file"""
    from blender_asset_tracer.trace import dependencies
    from blender_asset_tracer.cli.common import shorten
    
    deps = list(dependencies(blend_file))
    
    # Group by type
    libraries = [d for d in deps if d.suffix == '.blend']
    images = [d for d in deps if d.suffix in {'.png', '.jpg', '.exr', '.tiff'}]
    other = [d for d in deps if d not in libraries + images]
    
    print(f"Dependencies for {shorten(blend_file)}:")
    
    if libraries:
        print(f"  Libraries ({len(libraries)}):")
        for lib in libraries:
            print(f"    {shorten(str(lib))}")
    
    if images:
        print(f"  Images ({len(images)}):")
        for img in images:
            print(f"    {shorten(str(img))}")
    
    if other:
        print(f"  Other ({len(other)}):")
        for item in other:
            print(f"    {shorten(str(item))}")
```

### Enhanced Status Command

```python
@click.command()
@click.argument('directory', type=click.Path(exists=True), default='.')
def status_command(directory: str):
    """Show enhanced status with file sizes"""
    from blender_asset_tracer.cli.common import shorten, humanize_bytes
    
    for blend_file in Path(directory).rglob("*.blend"):
        size = blend_file.stat().st_size
        libs = get_blend_file_libraries(blend_file)
        
        print(f"{shorten(str(blend_file))} ({humanize_bytes(size)})")
        if libs:
            print(f"  Libraries: {len(libs)}")
            for name, path in libs.items():
                print(f"    {name} -> {shorten(path)}")
```

## Migration Testing Strategy

### Compatibility Tests
```python
def test_path_conversion_compatibility():
    """Ensure new BlendPath.mkrelative matches our old logic"""
    test_cases = [
        ("/abs/path/file.blend", "/abs", "//path/file.blend"),
        ("/different/tree/file.blend", "/abs", "/different/tree/file.blend"),
        # Add edge cases that our old code handled
    ]
    
    for abs_path, base, expected in test_cases:
        # Test old implementation
        old_result = old_convert_to_relative_path(abs_path, base)
        
        # Test new implementation  
        blend_path = BlendPath(abs_path)
        new_result = blend_path.mkrelative(Path(base))
        
        assert old_result == new_result, f"Mismatch for {abs_path} -> {base}"
```

### Performance Tests
```python
def test_performance_regression():
    """Ensure new implementation is not slower"""
    import time
    
    test_paths = [generate_test_paths()]  # 1000 test cases
    
    # Benchmark old implementation
    start = time.time()
    for path in test_paths:
        old_convert_to_relative_path(path, "/base")
    old_time = time.time() - start
    
    # Benchmark new implementation
    start = time.time() 
    for path in test_paths:
        BlendPath(path).mkrelative("/base")
    new_time = time.time() - start
    
    # New implementation should be same speed or faster
    assert new_time <= old_time * 1.1, "Performance regression detected"
```

## Integration Checklist

### Phase 1: Path Handling ✅
- [ ] Add `from blender_asset_tracer.bpathlib import BlendPath`
- [ ] Replace `_convert_to_relative_path` method
- [ ] Update tests to verify compatibility
- [ ] Test cross-platform behavior
- [ ] Benchmark performance

### Phase 2: CLI Utilities 🔄
- [ ] Import `shorten` and `humanize_bytes`
- [ ] Update all CLI verbose output
- [ ] Add file sizes to status commands
- [ ] Test output formatting on different terminal sizes

### Phase 3: Asset Tracking 🔄
- [ ] Study `trace.dependencies()` API
- [ ] Implement new `find_all_dependencies` method
- [ ] Add `blendwatch deps` command
- [ ] Test with various blend file types

### Phase 4: Progress Reporting 🔄
- [ ] Add progress indicators to long operations
- [ ] Test progress bars in different terminals
- [ ] Ensure graceful fallback for non-interactive use

### Phase 5: Code Cleanup 🔄
- [ ] Remove redundant path utilities
- [ ] Simplify complex matching logic
- [ ] Update documentation
- [ ] Final performance validation

## Expected Benefits Summary

| Area | Before | After | Improvement |
|------|--------|-------|-------------|
| Path conversion | 50+ lines, custom logic | 6 lines, battle-tested | 85% less code, more robust |
| CLI output | Basic paths | Shortened paths + file sizes | Better UX |
| Asset discovery | Basic backlinks | Full dependency tree | New capabilities |
| Progress feedback | Print statements | Progress bars | Professional UX |
| Maintenance | Many edge cases | Leveraged library | Less bugs |

This integration will significantly improve BlendWatch's robustness while reducing our maintenance burden!
