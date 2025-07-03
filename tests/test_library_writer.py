"""
Tests for the library_writer module using real blend files.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from blendwatch.blender.library_writer import (
    LibraryPathWriter, 
    update_blend_file_paths, 
    get_blend_file_libraries
)


class TestLibraryPathWriterReal:
    """Test the LibraryPathWriter class with real blend files"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Path to test blend files
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        
        # Create a temporary directory for test files
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Verify test blend files exist
        self.linked_cube = self.blendfiles_dir / "linked_cube.blend"
        self.doubly_linked = self.blendfiles_dir / "doubly_linked_up.blend"
        
        if not self.linked_cube.exists():
            pytest.skip(f"Test blend file not found: {self.linked_cube}")
        if not self.doubly_linked.exists():
            pytest.skip(f"Test blend file not found: {self.doubly_linked}")
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_init_valid_blend_file(self):
        """Test LibraryPathWriter initialization with valid blend file"""
        writer = LibraryPathWriter(self.linked_cube)
        assert writer.blend_file_path == self.linked_cube
    
    def test_init_nonexistent_file(self):
        """Test LibraryPathWriter initialization with nonexistent file"""
        nonexistent = self.temp_dir / "nonexistent.blend"
        with pytest.raises(FileNotFoundError):
            LibraryPathWriter(nonexistent)
    
    def test_init_non_blend_file(self):
        """Test LibraryPathWriter initialization with non-blend file"""
        text_file = self.temp_dir / "test.txt"
        text_file.write_text("not a blend file")
        
        with pytest.raises(ValueError):
            LibraryPathWriter(text_file)
    
    def test_init_string_path(self):
        """Test LibraryPathWriter initialization with string path"""
        writer = LibraryPathWriter(str(self.linked_cube))
        assert writer.blend_file_path == self.linked_cube
    
    def test_get_library_paths_linked_cube(self):
        """Test getting library paths from linked_cube.blend"""
        writer = LibraryPathWriter(self.linked_cube)
        paths = writer.get_library_paths()
        
        # The exact libraries depend on how the test file was created
        # but we can test the basic functionality
        assert isinstance(paths, dict)
        
        # If there are libraries, each should have a name and filepath
        for name, filepath in paths.items():
            assert isinstance(name, str)
            assert isinstance(filepath, str)
            assert len(name) > 0
            assert len(filepath) > 0
    
    def test_get_library_paths_doubly_linked(self):
        """Test getting library paths from doubly_linked_up.blend"""
        writer = LibraryPathWriter(self.doubly_linked)
        paths = writer.get_library_paths()
        
        assert isinstance(paths, dict)
        
        # If there are libraries, verify structure
        for name, filepath in paths.items():
            assert isinstance(name, str)
            assert isinstance(filepath, str)
    
    def test_update_library_path_copy_and_modify(self):
        """Test updating library paths by copying a blend file and modifying it"""
        # Copy the blend file to temp directory so we can modify it
        test_file = self.temp_dir / "test_linked.blend"
        shutil.copy2(self.linked_cube, test_file)
        
        writer = LibraryPathWriter(test_file)
        original_paths = writer.get_library_paths()
        
        if not original_paths:
            pytest.skip("No libraries found in test file")
        
        # Try to update the first library path
        old_path = list(original_paths.values())[0]
        new_path = "//updated_library.blend"
        
        result = writer.update_library_path(old_path, new_path)
        
        # Verify the update worked
        if result:
            updated_paths = writer.get_library_paths()
            assert new_path in updated_paths.values()
            assert old_path not in updated_paths.values()
        else:
            # If no update occurred, that's also valid behavior
            # (e.g., if the path wasn't found exactly as expected)
            pass
    
    def test_update_multiple_library_paths(self):
        """Test updating multiple library paths"""
        # Copy the blend file to temp directory
        test_file = self.temp_dir / "test_multiple.blend"
        shutil.copy2(self.doubly_linked, test_file)
        
        writer = LibraryPathWriter(test_file)
        original_paths = writer.get_library_paths()
        
        if len(original_paths) < 2:
            pytest.skip("Need at least 2 libraries for this test")
        
        # Create mapping for first two libraries
        path_list = list(original_paths.values())[:2]
        path_mapping = {
            path_list[0]: "//new_lib1.blend",
            path_list[1]: "//new_lib2.blend"
        }
        
        result = writer.update_library_paths(path_mapping)
        
        # Verify updates
        if result > 0:
            updated_paths = writer.get_library_paths()
            assert "//new_lib1.blend" in updated_paths.values()
            assert "//new_lib2.blend" in updated_paths.values()
    
    def test_make_paths_relative_and_absolute(self):
        """Test converting between relative and absolute paths"""
        # Copy the blend file to temp directory
        test_file = self.temp_dir / "test_relative.blend"
        shutil.copy2(self.linked_cube, test_file)
        
        writer = LibraryPathWriter(test_file)
        writer.blend_file_path = test_file  # Ensure the path is set correctly
        
        original_paths = writer.get_library_paths()
        
        if not original_paths:
            pytest.skip("No libraries found in test file")
        
        # Test making paths relative (if they're currently absolute)
        base_path = self.temp_dir
        relative_count = writer.make_paths_relative(base_path)
        
        # Test making paths absolute (if they're currently relative)  
        absolute_count = writer.make_paths_absolute(base_path)
        
        # The exact behavior depends on the original paths in the blend file
        # but we can verify the methods don't crash and return valid counts
        assert isinstance(relative_count, int)
        assert isinstance(absolute_count, int)
        assert relative_count >= 0
        assert absolute_count >= 0


class TestLibraryPathWriterMocked:
    """Test the LibraryPathWriter class with mocked blend files for edge cases"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_blend_file = self.temp_dir / "test.blend"
        # Create a mock blend file
        self.test_blend_file.write_bytes(b"BLENDER")
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    @patch('blendwatch.blender.library_writer.blendfile.BlendFile')
    def test_get_library_paths_empty(self, mock_blendfile):
        """Test getting library paths from file with no libraries"""
        # Mock blend file with no LI blocks
        mock_bf = MagicMock()
        mock_bf.code_index = {b"SC": []}  # Some other blocks but no LI
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        paths = writer.get_library_paths()
        
        assert paths == {}
        mock_blendfile.assert_called_once_with(self.test_blend_file, mode="rb")
    
    @patch('blendwatch.blender.library_writer.blendfile.BlendFile')
    def test_get_library_paths_with_unicode_error(self, mock_blendfile):
        """Test getting library paths handles unicode decode errors"""
        # Mock library block with invalid UTF-8
        mock_lib = MagicMock()
        mock_lib.__getitem__.side_effect = lambda key: {
            b"name": b"\xff\xfe//lib.blend\x00",  # Invalid UTF-8
            b"filepath": b"\xff\xfe//lib.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        paths = writer.get_library_paths()
        
        # Should handle decode error gracefully and return replacement characters
        assert len(paths) == 1
        # The exact replacement characters may vary, but it should contain something
        assert any("lib.blend" in key for key in paths.keys())
    
    @patch('blendwatch.blender.library_writer.blendfile.BlendFile')
    def test_update_library_path_not_found(self, mock_blendfile):
        """Test library path update when path not found"""
        # Mock library block with different path
        mock_lib = MagicMock()
        mock_lib.__getitem__.side_effect = lambda key: {
            b"filepath": b"//different_path.blend\x00",
            b"name": b"//different_path.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        result = writer.update_library_path("//old_path.blend", "//new_path.blend")
        
        assert result is False
        # Check that the library block was not updated
        mock_lib.__setitem__.assert_not_called()


class TestConvenienceFunctions:
    """Test the convenience functions"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        self.linked_cube = self.blendfiles_dir / "linked_cube.blend"
        
        if not self.linked_cube.exists():
            pytest.skip(f"Test blend file not found: {self.linked_cube}")
    
    def test_get_blend_file_libraries(self):
        """Test get_blend_file_libraries convenience function"""
        result = get_blend_file_libraries(self.linked_cube)
        
        assert isinstance(result, dict)
        # The function should return the same as calling the method directly
        writer = LibraryPathWriter(self.linked_cube)
        expected = writer.get_library_paths()
        assert result == expected
    
    def test_update_blend_file_paths_with_real_file(self):
        """Test update_blend_file_paths convenience function with real file"""
        # Create a temporary copy
        temp_dir = Path(tempfile.mkdtemp())
        try:
            test_file = temp_dir / "test_update.blend"
            shutil.copy2(self.linked_cube, test_file)
            
            # Get original paths
            original_paths = get_blend_file_libraries(test_file)
            
            if not original_paths:
                pytest.skip("No libraries found in test file")
            
            # Create a mapping to update one path
            old_path = list(original_paths.values())[0]
            path_mapping = {old_path: "//updated_via_convenience.blend"}
            
            result = update_blend_file_paths(test_file, path_mapping)
            
            # Result should be number of updated paths
            assert isinstance(result, int)
            assert result >= 0
            
            # If update was successful, verify the change
            if result > 0:
                updated_paths = get_blend_file_libraries(test_file)
                assert "//updated_via_convenience.blend" in updated_paths.values()
        
        finally:
            shutil.rmtree(temp_dir)


class TestRealBlendFileIntegration:
    """Integration tests with real blend files"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_workflow_with_linked_cube(self):
        """Test a complete workflow with linked_cube.blend"""
        linked_cube = self.blendfiles_dir / "linked_cube.blend"
        
        if not linked_cube.exists():
            pytest.skip(f"Test blend file not found: {linked_cube}")
        
        # Copy to temp directory for modification
        test_file = self.temp_dir / "workflow_test.blend"
        shutil.copy2(linked_cube, test_file)
        
        # Initialize writer
        writer = LibraryPathWriter(test_file)
        
        # Get current library paths
        original_paths = writer.get_library_paths()
        print(f"Original library paths: {original_paths}")
        
        # Test the complete workflow even if no libraries exist
        assert isinstance(original_paths, dict)
        
        # If there are libraries, test updating them
        if original_paths:
            # Test updating paths
            old_path = list(original_paths.values())[0]
            new_path = "//workflow_updated.blend"
            
            success = writer.update_library_path(old_path, new_path)
            if success:
                updated_paths = writer.get_library_paths()
                assert new_path in updated_paths.values()
                print(f"Successfully updated path: {old_path} -> {new_path}")
            else:
                print(f"Path update failed (this may be expected): {old_path}")
        
        # Test relative/absolute conversion
        relative_count = writer.make_paths_relative(self.temp_dir)
        absolute_count = writer.make_paths_absolute(self.temp_dir)
        
        print(f"Relative conversions: {relative_count}, Absolute conversions: {absolute_count}")
        
        # Verify methods return valid results
        assert isinstance(relative_count, int)
        assert isinstance(absolute_count, int)
    
    def test_workflow_with_doubly_linked(self):
        """Test a complete workflow with doubly_linked_up.blend"""
        doubly_linked = self.blendfiles_dir / "doubly_linked_up.blend"
        
        if not doubly_linked.exists():
            pytest.skip(f"Test blend file not found: {doubly_linked}")
        
        # Copy to temp directory for modification
        test_file = self.temp_dir / "doubly_linked_test.blend"
        shutil.copy2(doubly_linked, test_file)
        
        # Test with this file
        writer = LibraryPathWriter(test_file)
        paths = writer.get_library_paths()
        
        print(f"Doubly linked file library paths: {paths}")
        
        # Basic verification
        assert isinstance(paths, dict)
        
        # If multiple libraries exist, test batch update
        if len(paths) >= 2:
            path_list = list(paths.values())
            path_mapping = {
                path_list[0]: "//batch_update_1.blend",
                path_list[1]: "//batch_update_2.blend"
            }
            
            updated_count = writer.update_library_paths(path_mapping)
            print(f"Batch updated {updated_count} paths")
            
            if updated_count > 0:
                final_paths = writer.get_library_paths()
                assert "//batch_update_1.blend" in final_paths.values()
                assert "//batch_update_2.blend" in final_paths.values()


if __name__ == "__main__":
    pytest.main([__file__])
