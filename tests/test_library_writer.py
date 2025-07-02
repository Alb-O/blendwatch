"""
Tests for the library_writer module.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from blendwatch.library_writer import (
    LibraryPathWriter, 
    update_blend_file_paths, 
    get_blend_file_libraries
)


class TestLibraryPathWriter:
    """Test the LibraryPathWriter class"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Create a temporary directory for test files
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_blend_file = self.temp_dir / "test.blend"
        
        # Create a mock blend file
        self.test_blend_file.write_bytes(b"BLENDER")  # Basic file to test existence
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_init_valid_file(self):
        """Test LibraryPathWriter initialization with valid file"""
        writer = LibraryPathWriter(self.test_blend_file)
        assert writer.blend_file_path == self.test_blend_file
    
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
        writer = LibraryPathWriter(str(self.test_blend_file))
        assert writer.blend_file_path == self.test_blend_file
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
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
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
    def test_get_library_paths_with_libraries(self, mock_blendfile):
        """Test getting library paths from file with libraries"""
        # Mock library blocks
        mock_lib1 = MagicMock()
        mock_lib1.__getitem__.side_effect = lambda key: {
            b"name": b"//lib1.blend\x00",
            b"filepath": b"//lib1.blend\x00"
        }[key]
        
        mock_lib2 = MagicMock()
        mock_lib2.__getitem__.side_effect = lambda key: {
            b"name": b"/absolute/path/lib2.blend\x00",
            b"filepath": b"/absolute/path/lib2.blend\x00"
        }[key]
        
        # Mock blend file with LI blocks
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib1, mock_lib2]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        paths = writer.get_library_paths()
        
        expected = {
            "//lib1.blend": "//lib1.blend",
            "/absolute/path/lib2.blend": "/absolute/path/lib2.blend"
        }
        assert paths == expected
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
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
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
    def test_update_library_path_success(self, mock_blendfile):
        """Test successful library path update"""
        # Mock library block
        mock_lib = MagicMock()
        mock_lib.__getitem__.side_effect = lambda key: {
            b"filepath": b"//old_path.blend\x00",
            b"name": b"//old_path.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        result = writer.update_library_path("//old_path.blend", "//new_path.blend")
        
        assert result is True
        # Check that the library block was updated
        mock_lib.__setitem__.assert_any_call(b"filepath", b"//new_path.blend\x00")
        mock_lib.__setitem__.assert_any_call(b"name", b"//new_path.blend\x00")
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
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
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
    def test_update_library_paths_multiple(self, mock_blendfile):
        """Test updating multiple library paths"""
        # Mock library blocks
        mock_lib1 = MagicMock()
        mock_lib1.__getitem__.side_effect = lambda key: {
            b"filepath": b"//lib1.blend\x00",
            b"name": b"//lib1.blend\x00"
        }[key]
        
        mock_lib2 = MagicMock()
        mock_lib2.__getitem__.side_effect = lambda key: {
            b"filepath": b"//lib2.blend\x00",
            b"name": b"//lib2.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib1, mock_lib2]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        path_mapping = {
            "//lib1.blend": "//new_lib1.blend",
            "//lib2.blend": "//new_lib2.blend"
        }
        result = writer.update_library_paths(path_mapping)
        
        assert result == 2
        # Check that both library blocks were updated
        mock_lib1.__setitem__.assert_any_call(b"filepath", b"//new_lib1.blend\x00")
        mock_lib1.__setitem__.assert_any_call(b"name", b"//new_lib1.blend\x00")
        mock_lib2.__setitem__.assert_any_call(b"filepath", b"//new_lib2.blend\x00")
        mock_lib2.__setitem__.assert_any_call(b"name", b"//new_lib2.blend\x00")
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
    def test_update_library_path_by_name_success(self, mock_blendfile):
        """Test successful library path update by name"""
        # Mock library block
        mock_lib = MagicMock()
        mock_lib.__getitem__.side_effect = lambda key: {
            b"filepath": b"//old_path.blend\x00",
            b"name": b"//old_path.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        result = writer.update_library_path_by_name("//old_path.blend", "//new_path.blend")
        
        assert result is True
        # Check that the library block was updated
        mock_lib.__setitem__.assert_any_call(b"filepath", b"//new_path.blend\x00")
        mock_lib.__setitem__.assert_any_call(b"name", b"//new_path.blend\x00")
    
    @patch('blendwatch.library_writer.blendfile.BlendFile')
    def test_update_library_path_by_name_not_found(self, mock_blendfile):
        """Test library path update by name when name not found"""
        # Mock library block with different name
        mock_lib = MagicMock()
        mock_lib.__getitem__.side_effect = lambda key: {
            b"filepath": b"//different.blend\x00",
            b"name": b"//different.blend\x00"
        }[key]
        
        # Mock blend file
        mock_bf = MagicMock()
        mock_bf.code_index = {b"LI": [mock_lib]}
        mock_blendfile.return_value.__enter__.return_value = mock_bf
        
        writer = LibraryPathWriter(self.test_blend_file)
        result = writer.update_library_path_by_name("//old_path.blend", "//new_path.blend")
        
        assert result is False
        # Check that the library block was not updated
        mock_lib.__setitem__.assert_not_called()
    
    @patch('blendwatch.library_writer.LibraryPathWriter.get_library_paths')
    @patch('blendwatch.library_writer.LibraryPathWriter.update_library_paths')
    def test_make_paths_relative(self, mock_update, mock_get_paths):
        """Test converting absolute paths to relative"""
        # Mock current library paths (mix of absolute and relative)
        # Use paths that can actually be made relative to the base
        mock_get_paths.return_value = {
            "lib1": "/base/project/assets/lib1.blend",
            "lib2": "//already/relative.blend",
            "lib3": "/base/shared/lib3.blend"
        }
        mock_update.return_value = 2
        
        writer = LibraryPathWriter(self.test_blend_file)
        writer.blend_file_path = Path("/base/project/main.blend")
        
        result = writer.make_paths_relative(Path("/base"))
        
        assert result == 2
        # Check that update_library_paths was called with correct mapping
        mock_update.assert_called_once()
        path_mapping = mock_update.call_args[0][0]
        
        # Should only include absolute paths that can be made relative
        assert len(path_mapping) == 2
        assert "/base/project/assets/lib1.blend" in path_mapping
        assert "/base/shared/lib3.blend" in path_mapping
        assert path_mapping["/base/project/assets/lib1.blend"] == "//project/assets/lib1.blend"
        assert path_mapping["/base/shared/lib3.blend"] == "//shared/lib3.blend"
    
    @patch('blendwatch.library_writer.LibraryPathWriter.get_library_paths')
    @patch('blendwatch.library_writer.LibraryPathWriter.update_library_paths')
    def test_make_paths_absolute(self, mock_update, mock_get_paths):
        """Test converting relative paths to absolute"""
        # Mock current library paths (mix of relative and absolute)
        mock_get_paths.return_value = {
            "lib1": "//relative/lib1.blend",
            "lib2": "/already/absolute.blend",
            "lib3": "//relative/lib3.blend"
        }
        mock_update.return_value = 2
        
        writer = LibraryPathWriter(self.test_blend_file)
        base_path = Path("/base/project")
        
        result = writer.make_paths_absolute(base_path)
        
        assert result == 2
        # Check that update_library_paths was called with correct mapping
        mock_update.assert_called_once()
        path_mapping = mock_update.call_args[0][0]
        
        # Should only include relative paths
        assert len(path_mapping) == 2
        assert "//relative/lib1.blend" in path_mapping
        assert "//relative/lib3.blend" in path_mapping
    
    @patch('blendwatch.library_writer.LibraryPathWriter.get_library_paths')
    @patch('blendwatch.library_writer.LibraryPathWriter.update_library_paths')
    def test_make_paths_relative_unreachable_paths(self, mock_update, mock_get_paths):
        """Test converting absolute paths to relative when paths cannot be made relative"""
        # Mock current library paths with paths outside the base directory
        mock_get_paths.return_value = {
            "lib1": "/completely/different/path/lib1.blend",
            "lib2": "//already/relative.blend",
            "lib3": "/another/unrelated/path/lib3.blend"
        }
        mock_update.return_value = 0
        
        writer = LibraryPathWriter(self.test_blend_file)
        writer.blend_file_path = Path("/base/project/main.blend")
        
        result = writer.make_paths_relative(Path("/base"))
        
        # Should return 0 since no paths could be made relative
        assert result == 0
        # update_library_paths should not be called if no paths can be converted
        mock_update.assert_not_called()


class TestConvenienceFunctions:
    """Test the convenience functions"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_blend_file = self.temp_dir / "test.blend"
        self.test_blend_file.write_bytes(b"BLENDER")
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    @patch('blendwatch.library_writer.LibraryPathWriter')
    def test_update_blend_file_paths(self, mock_writer_class):
        """Test update_blend_file_paths convenience function"""
        mock_writer = MagicMock()
        mock_writer.update_library_paths.return_value = 3
        mock_writer_class.return_value = mock_writer
        
        path_mapping = {"old": "new", "old2": "new2"}
        result = update_blend_file_paths(self.test_blend_file, path_mapping)
        
        assert result == 3
        mock_writer_class.assert_called_once_with(self.test_blend_file)
        mock_writer.update_library_paths.assert_called_once_with(path_mapping)
    
    @patch('blendwatch.library_writer.LibraryPathWriter')
    def test_get_blend_file_libraries(self, mock_writer_class):
        """Test get_blend_file_libraries convenience function"""
        mock_writer = MagicMock()
        expected_paths = {"lib1": "//lib1.blend", "lib2": "//lib2.blend"}
        mock_writer.get_library_paths.return_value = expected_paths
        mock_writer_class.return_value = mock_writer
        
        result = get_blend_file_libraries(self.test_blend_file)
        
        assert result == expected_paths
        mock_writer_class.assert_called_once_with(self.test_blend_file)
        mock_writer.get_library_paths.assert_called_once()


class TestIntegration:
    """Integration tests that would work with real blend files"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_blend_file = self.temp_dir / "test.blend"
        self.test_blend_file.write_bytes(b"BLENDER")
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    @pytest.mark.skip(reason="Requires real blend file for integration testing")
    def test_real_blend_file_operations(self):
        """Integration test with a real blend file (skipped by default)"""
        # This test would require a real .blend file with libraries
        # and would test the actual blender-asset-tracer integration
        pass


if __name__ == "__main__":
    pytest.main([__file__])
