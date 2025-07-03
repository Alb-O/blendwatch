import pytest
import shutil
import tempfile
from pathlib import Path

# Ensure the test environment is set up to find the blendwatch src
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from blendwatch.blender.library_writer import (
    get_blend_file_libraries,
    LibraryPathWriter,
    update_blend_file_paths,
)


class TestLibraryWriter:
    """
    Tests for reading and writing library paths in .blend files,
    aligned with the new simplified and optimized API.
    """

    def setup_method(self):
        """Set up test fixtures, including a temporary directory for modifications."""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        if not self.blendfiles_dir.exists():
            pytest.skip(f"Test blend files directory not found: {self.blendfiles_dir}")

        self.linked_cube_path = self.blendfiles_dir / "linked_cube.blend"
        if not self.linked_cube_path.exists():
            pytest.skip("Core test file 'linked_cube.blend' not found.")

        self.temp_dir = Path(tempfile.mkdtemp(prefix="blendwatch_test_"))

    def teardown_method(self):
        """Clean up the temporary directory."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_get_blend_file_libraries(self):
        """
        Tests the main public function for reading library paths.
        """
        # Test with a file that has a linked library
        libs = get_blend_file_libraries(self.linked_cube_path)
        assert isinstance(libs, dict)
        assert len(libs) > 0

        # The function should return resolved, absolute paths
        lib_path_str = list(libs.values())[0]
        assert Path(lib_path_str).is_absolute()
        assert "basic_file.blend" in lib_path_str

        # Test with a file that has no libraries
        basic_file_path = self.blendfiles_dir / "basic_file.blend"
        assert get_blend_file_libraries(basic_file_path) == {}

        # Test with a non-existent file
        non_existent_file = self.blendfiles_dir / "no_such_file.blend"
        assert get_blend_file_libraries(non_existent_file) == {}

    def test_library_path_writer_init(self):
        """
        Tests the initialization and error handling of the LibraryPathWriter class.
        """
        # Should initialize correctly with a valid file
        writer = LibraryPathWriter(self.linked_cube_path)
        assert writer.blend_file_path == self.linked_cube_path

        # Should raise FileNotFoundError for a non-existent file
        with pytest.raises(FileNotFoundError):
            LibraryPathWriter(self.temp_dir / "non_existent.blend")

        # Should raise ValueError for a directory
        with pytest.raises(ValueError):
            LibraryPathWriter(self.temp_dir)

        # Should raise ValueError for a non-blend file
        text_file = self.temp_dir / "test.txt"
        text_file.touch()
        with pytest.raises(ValueError):
            LibraryPathWriter(text_file)

    def test_update_library_paths_basic(self):
        """
        Tests the core functionality of updating a library path in a copied file.
        """
        # Copy the test file to the temp directory to avoid modifying the original
        test_file = self.temp_dir / "test_update.blend"
        shutil.copy2(self.linked_cube_path, test_file)

        writer = LibraryPathWriter(test_file)
        original_paths = writer.get_library_paths()
        assert len(original_paths) > 0

        old_path = list(original_paths.keys())[0]
        new_path = "/tmp/new_library_location.blend"
        path_mapping = {old_path: new_path}

        # Perform the update
        updated_count = writer.update_library_paths(path_mapping)
        assert updated_count == 1

        # Verify the change
        new_libs = writer.get_library_paths()
        assert list(new_libs.values())[0] == new_path

    def test_update_library_paths_relative(self):
        """
        Tests the `relative=True` option to ensure paths are converted correctly.
        """
        test_file = self.temp_dir / "test_relative_update.blend"
        shutil.copy2(self.linked_cube_path, test_file)

        writer = LibraryPathWriter(test_file)
        original_paths = writer.get_library_paths()
        old_path = list(original_paths.keys())[0]

        # Define a new path that can be made relative to the test file
        new_lib_file = self.temp_dir / "new_lib.blend"
        new_lib_file.touch()
        path_mapping = {old_path: str(new_lib_file)}

        # Perform the update with the relative flag
        updated_count = writer.update_library_paths(path_mapping, relative=True)
        assert updated_count == 1

        # To verify, we need to use the raw reader, as the public one resolves paths
        from blendwatch.blender.block_level_optimizations import get_libraries_ultra_fast
        raw_libs = get_libraries_ultra_fast(test_file, resolve_paths=False)
        new_raw_path = list(raw_libs.values())[0]

        # The new path should be in Blender's relative format
        assert new_raw_path == "//new_lib.blend"

    def test_update_idempotency_and_no_ops(self):
        """
        Tests that no updates are performed when paths don't match or are the same.
        """
        test_file = self.temp_dir / "test_idempotent.blend"
        shutil.copy2(self.linked_cube_path, test_file)
        writer = LibraryPathWriter(test_file)
        original_paths_dict = writer.get_library_paths()
        original_path = list(original_paths_dict.keys())[0]

        # Case 1: Mapping a path that doesn't exist in the file
        path_mapping_no_match = {"/path/does/not/exist.blend": "/new/path.blend"}
        updated_count = writer.update_library_paths(path_mapping_no_match)
        assert updated_count == 0

        # Case 2: Mapping a path to itself
        path_mapping_same = {original_path: original_path}
        updated_count = writer.update_library_paths(path_mapping_same)
        assert updated_count == 0

        # Case 3: Empty mapping
        updated_count = writer.update_library_paths({})
        assert updated_count == 0

        # Verify the file's libraries remain unchanged
        final_paths = writer.get_library_paths()
        assert final_paths == original_paths_dict

    def test_update_blend_file_paths_convenience_function(self):
        """
        Tests the top-level convenience function `update_blend_file_paths`.
        """
        test_file = self.temp_dir / "test_convenience.blend"
        shutil.copy2(self.linked_cube_path, test_file)

        original_path = list(get_blend_file_libraries(test_file).keys())[0]
        new_path = "/some/other/path.blend"
        path_mapping = {original_path: new_path}

        # Use the convenience function to perform the update
        updated_count = update_blend_file_paths(test_file, path_mapping)
        assert updated_count == 1

        # Verify the change
        new_libs = get_blend_file_libraries(test_file)
        updated_path = list(new_libs.values())[0]
        # On Windows, paths get normalized, so check that the path ends with the expected filename
        assert "path.blend" in updated_path
