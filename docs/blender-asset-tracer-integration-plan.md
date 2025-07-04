# BlendWatch Integration Plan: Leveraging blender-asset-tracer

## Overview

This document outlines a comprehensive plan to integrate functionality from the `blender-asset-tracer` repository to simplify BlendWatch's codebase, improve robustness, and leverage battle-tested library code.

## Current State Analysis

### What We're Currently Implementing Ourselves
1. **Path handling** - Custom relative/absolute path conversion
2. **Blend file I/O** - Basic blendfile reading/writing through blender-asset-tracer
3. **Library path resolution** - Custom path matching and normalization
4. **Progress reporting** - Basic console output
5. **CLI utilities** - Custom path shortening and display
6. **Asset dependency tracking** - Minimal backlink scanning

### What blender-asset-tracer Already Provides
1. **Robust path handling** (`bpathlib.py`)
2. **Advanced blend file operations** (`blendfile/` modules)
3. **Asset tracing and dependency resolution** (`trace/` modules)
4. **File sequence support** (image sequences, UDIMs)
5. **Progress reporting** (`trace/progress.py`)
6. **CLI utilities** (`cli/common.py`)
7. **Compression handling** (`compressor.py`)

## Integration Plan

### Phase 1: Core Path Handling (High Priority) 🎯

**Replace:** Our custom `_convert_to_relative_path()` method  
**With:** `BlendPath.mkrelative()` from `bpathlib.py`

**Benefits:**
- ✅ More robust cross-platform path handling
- ✅ Better support for cross-drive scenarios (Windows)
- ✅ Proper handling of edge cases (symlinks, network paths)
- ✅ Battle-tested code used in production tools

**Changes Required:**
```python
# Current (blendwatch/blender/library_writer.py)
def _convert_to_relative_path(self, absolute_path: str) -> str:
    # ~50 lines of custom logic with edge cases

# New (using blender-asset-tracer)
from blender_asset_tracer.bpathlib import BlendPath

def _convert_to_relative_path(self, absolute_path: str) -> str:
    blend_path = BlendPath(absolute_path)
    return blend_path.mkrelative(self.blend_file_path.parent)
```

**Files to modify:**
- `src/blendwatch/blender/library_writer.py`
- Update imports and method implementation

**Estimated effort:** 2-3 hours  
**Risk:** Low (drop-in replacement)

---

### Phase 2: Enhanced CLI Utilities (Medium Priority) 🔧

**Replace:** Custom path display and utility functions  
**With:** `cli/common.py` utilities

**Benefits:**
- ✅ Better path display (relative to CWD when possible)
- ✅ Human-readable file sizes
- ✅ Consistent CLI styling
- ✅ Progress indicators

**Changes Required:**
```python
# Add to blendwatch/cli/utils.py or commands
from blender_asset_tracer.cli.common import shorten, humanize_bytes

# Replace custom path display with shorten()
# Add file size reporting to status commands
# Improve progress feedback
```

**New capabilities:**
- Show file sizes in `blendwatch status`
- Better path display in verbose output
- Relative paths in CLI output when appropriate

**Files to modify:**
- `src/blendwatch/cli/utils.py`
- `src/blendwatch/cli/commands/*.py`
- Update all verbose output to use `shorten()`

**Estimated effort:** 4-6 hours  
**Risk:** Low (additive changes)

---

### Phase 3: Advanced Asset Tracking (Medium Priority) 🚀

**Replace:** Our basic backlink scanning  
**With:** `trace/` modules for comprehensive dependency analysis

**Benefits:**
- ✅ Find all dependencies of a blend file
- ✅ Support for image sequences and UDIMs
- ✅ Better asset discovery
- ✅ Foundation for advanced features

**Changes Required:**
```python
# Current (blendwatch/blender/backlinks.py)
class BacklinkScanner:
    # ~200 lines of custom scanning logic

# Enhanced (using blender-asset-tracer)
from blender_asset_tracer.trace import BlendFileTrace

class BacklinkScanner:
    def find_all_dependencies(self, blend_file):
        trace = BlendFileTrace(blend_file)
        return trace.list_all_dependencies()
```

**New capabilities:**
- `blendwatch deps <file.blend>` - List all dependencies
- Support for image sequences in moves
- Better asset packaging capabilities

**Files to modify:**
- `src/blendwatch/blender/backlinks.py`
- Add new CLI commands for dependency analysis

**Estimated effort:** 8-12 hours  
**Risk:** Medium (requires API understanding)

---

### Phase 4: Progress Reporting (Low Priority) 📊

**Replace:** Basic console output  
**With:** `trace/progress.py` for better feedback

**Benefits:**
- ✅ Progress bars for long operations
- ✅ ETA calculations
- ✅ Better user experience

**Changes Required:**
- Add progress reporting to directory scans
- Progress bars for large backlink operations
- Better feedback during sync operations

**Files to modify:**
- `src/blendwatch/core/watcher.py`
- `src/blendwatch/blender/backlinks.py`
- CLI commands with long-running operations

**Estimated effort:** 4-6 hours  
**Risk:** Low (UI improvements)

---

### Phase 5: Code Consolidation (High Priority) 🧹

**Remove:** Redundant and duplicate functionality  
**Consolidate:** Similar code patterns

**Code to Remove/Simplify:**

1. **Custom path utilities** (30-40% reduction)
   - `src/blendwatch/utils/path_utils.py` - Remove custom relative path logic
   - Consolidate into blender-asset-tracer calls

2. **Complex matching logic** (50+ lines)
   - Simplify `_find_matching_libraries()` 
   - Use blender-asset-tracer's path normalization

3. **Custom blend file operations** (20-30% reduction)
   - Remove duplicate functionality
   - Leverage blender-asset-tracer's optimized operations

**Estimated code reduction:** 200-300 lines  
**Maintenance reduction:** Significant (fewer custom edge cases)

---

## Implementation Strategy

### Dependencies
```toml
# pyproject.toml - already have this
[tool.poetry.dependencies]
blender-asset-tracer = "^1.18.0"  # ✅ Already included
```

### Migration Approach
1. **Incremental replacement** - Replace one module at a time
2. **Maintain backward compatibility** - Keep existing APIs
3. **Comprehensive testing** - Test each phase thoroughly
4. **Performance validation** - Ensure no regressions

### Testing Strategy
```python
# Add integration tests
def test_blender_asset_tracer_integration():
    # Test path conversion compatibility
    # Test dependency discovery
    # Test performance benchmarks
```

---

## Expected Benefits

### Code Quality
- ✅ **-200-300 lines** of custom code
- ✅ **Fewer edge cases** to maintain
- ✅ **Battle-tested logic** from production tools
- ✅ **Better cross-platform support**

### Features
- ✅ **More robust path handling** (cross-drive, symlinks)
- ✅ **Image sequence support** (for future features)
- ✅ **Better dependency analysis**
- ✅ **Enhanced CLI experience**

### Maintenance
- ✅ **Reduced bug surface** (leverage maintained code)
- ✅ **Easier updates** (upstream improvements)
- ✅ **Better documentation** (established APIs)

---

## Risk Assessment

### Low Risk (Phases 1, 2, 4)
- Drop-in replacements
- Additive improvements
- Well-documented APIs

### Medium Risk (Phase 3)
- Requires understanding trace APIs
- May need adaptation for our use cases
- Performance implications

### Mitigation
- Implement incrementally
- Maintain fallback options
- Comprehensive testing at each phase

---

## Timeline Estimate

- **Phase 1 (Path handling):** 2-3 hours
- **Phase 2 (CLI utilities):** 4-6 hours  
- **Phase 3 (Asset tracking):** 8-12 hours
- **Phase 4 (Progress reporting):** 4-6 hours
- **Phase 5 (Consolidation):** 6-8 hours

**Total estimated effort:** 24-35 hours over 2-3 weeks

---

## Next Steps

1. ✅ **Document the plan** (this document)
2. 🎯 **Start with Phase 1** - Replace path handling (highest impact, lowest risk)
3. 🧪 **Create integration tests** - Ensure compatibility
4. 📊 **Benchmark performance** - Validate no regressions
5. 🔄 **Iterative implementation** - One phase at a time

---

## Success Metrics

- **Code reduction:** 15-20% fewer lines in core modules
- **Robustness:** Better handling of edge cases (cross-drive, symlinks)
- **Features:** New capabilities (dependency analysis, progress reporting)
- **Maintenance:** Fewer custom edge cases to maintain
- **User experience:** Better CLI feedback and path display
