"""
Tests for the backlinks module.
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from blendwatch.backlinks import (
    BacklinkScanner,
    BacklinkResult,
    find_backlinks
)


class TestBacklinkScanner:
    """Test the BacklinkScanner class with real blend files"""
    
    def setup_method(self):
        """Set up test fixtures"""
        # Path to test blend files
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        
        # Create a temporary directory for test files
        self.temp_dir = Path(tempfile.mkdtemp())
        
        # Verify test blend files exist
        if not self.blendfiles_dir.exists():
            pytest.skip(f"Test blend files directory not found: {self.blendfiles_dir}")
    
    def teardown_method(self):
        """Clean up test fixtures"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_init_valid_directory(self):
        """Test BacklinkScanner initialization with valid directory"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        assert scanner.search_directory == self.blendfiles_dir
    
    def test_init_nonexistent_directory(self):
        """Test BacklinkScanner initialization with nonexistent directory"""
        nonexistent = self.temp_dir / "nonexistent"
        with pytest.raises(FileNotFoundError):
            BacklinkScanner(nonexistent)
    
    def test_init_file_instead_of_directory(self):
        """Test BacklinkScanner initialization with file instead of directory"""
        test_file = self.temp_dir / "test.txt"
        test_file.write_text("not a directory")
        
        with pytest.raises(ValueError):
            BacklinkScanner(test_file)
    
    def test_find_blend_files(self):
        """Test finding blend files with Python scanning"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        blend_files = scanner.find_blend_files()
        
        assert isinstance(blend_files, list)
        assert len(blend_files) > 0
        
        # All results should be .blend files
        for blend_file in blend_files:
            assert blend_file.suffix.lower() == ".blend"
            assert blend_file.exists()
    
    def test_find_backlinks_to_basic_file(self):
        """Test finding backlinks to basic_file.blend"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        basic_file = self.blendfiles_dir / "basic_file.blend"
        
        if not basic_file.exists():
            pytest.skip(f"Test file not found: {basic_file}")
        
        backlinks = scanner.find_backlinks_to_file(basic_file)
        
        assert isinstance(backlinks, list)
        
        # We know linked_cube.blend should link to basic_file.blend
        linking_files = [result.blend_file.name for result in backlinks]
        if "linked_cube.blend" in [f.name for f in scanner.find_blend_files()]:
            assert "linked_cube.blend" in linking_files
    
    def test_find_backlinks_to_nonexistent_file(self):
        """Test finding backlinks to a nonexistent file"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        nonexistent = self.temp_dir / "nonexistent.blend"
        
        # Should not crash, just warn and return empty results
        backlinks = scanner.find_backlinks_to_file(nonexistent)
        assert isinstance(backlinks, list)
    
    def test_find_backlinks_excludes_self(self):
        """Test that a blend file doesn't link to itself"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        linked_cube = self.blendfiles_dir / "linked_cube.blend"
        
        if not linked_cube.exists():
            pytest.skip(f"Test file not found: {linked_cube}")
        
        backlinks = scanner.find_backlinks_to_file(linked_cube)
        
        # The file should not link to itself
        linking_files = [result.blend_file for result in backlinks]
        assert linked_cube not in linking_files
    
    def test_find_backlinks_to_multiple_files(self):
        """Test finding backlinks to multiple files"""
        scanner = BacklinkScanner(self.blendfiles_dir)
        
        basic_file = self.blendfiles_dir / "basic_file.blend"
        material_textures = self.blendfiles_dir / "material_textures.blend"
        
        test_files = []
        if basic_file.exists():
            test_files.append(basic_file)
        if material_textures.exists():
            test_files.append(material_textures)
        
        if not test_files:
            pytest.skip("No test files found")
        
        results = scanner.find_backlinks_to_multiple_files(test_files)
        
        assert isinstance(results, dict)
        assert len(results) == len(test_files)
        
        for target_file in test_files:
            assert target_file in results
            assert isinstance(results[target_file], list)


class TestConvenienceFunctions:
    """Test the convenience functions"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
        
        if not self.blendfiles_dir.exists():
            pytest.skip(f"Test blend files directory not found: {self.blendfiles_dir}")
    
    def test_find_backlinks_convenience_function(self):
        """Test find_backlinks convenience function"""
        basic_file = self.blendfiles_dir / "basic_file.blend"
        
        if not basic_file.exists():
            pytest.skip(f"Test file not found: {basic_file}")
        
        backlinks = find_backlinks(basic_file, self.blendfiles_dir)
        
        assert isinstance(backlinks, list)
        # Should return the same as calling the method directly
        scanner = BacklinkScanner(self.blendfiles_dir)
        expected = scanner.find_backlinks_to_file(basic_file)
        assert len(backlinks) == len(expected)


class TestBacklinkResult:
    """Test the BacklinkResult NamedTuple"""
    
    def test_backlink_result_creation(self):
        """Test creating a BacklinkResult"""
        blend_file = Path("test.blend")
        library_paths = {"lib1": "//lib1.blend"}
        matching_libraries = ["lib1"]
        
        result = BacklinkResult(
            blend_file=blend_file,
            library_paths=library_paths,
            matching_libraries=matching_libraries
        )
        
        assert result.blend_file == blend_file
        assert result.library_paths == library_paths
        assert result.matching_libraries == matching_libraries
    
    def test_backlink_result_immutable(self):
        """Test that BacklinkResult is immutable"""
        result = BacklinkResult(
            blend_file=Path("test.blend"),
            library_paths={"lib1": "//lib1.blend"},
            matching_libraries=["lib1"]
        )
        
        # Should not be able to modify fields (NamedTuple is immutable)
        with pytest.raises(AttributeError):
            result.blend_file = Path("other.blend")


class TestRealBlendFileIntegration:
    """Integration tests with real blend files"""
    
    def setup_method(self):
        """Set up test fixtures"""
        self.blendfiles_dir = Path(__file__).parent / "blendfiles"
    
    def test_complete_backlink_workflow(self):
        """Test a complete backlink workflow with real files"""
        if not self.blendfiles_dir.exists():
            pytest.skip(f"Test blend files directory not found: {self.blendfiles_dir}")
        
        scanner = BacklinkScanner(self.blendfiles_dir)
        
        # Find all blend files
        blend_files = scanner.find_blend_files()
        print(f"Found {len(blend_files)} blend files")
        
        # Test with basic_file.blend if it exists
        basic_file = self.blendfiles_dir / "basic_file.blend"
        if basic_file.exists():
            backlinks = scanner.find_backlinks_to_file(basic_file)
            print(f"Found {len(backlinks)} backlinks to {basic_file.name}")
            
            for result in backlinks:
                print(f"  {result.blend_file.name} -> {result.matching_libraries}")
                
                # Verify result structure
                assert isinstance(result.blend_file, Path)
                assert isinstance(result.library_paths, dict)
                assert isinstance(result.matching_libraries, list)
                assert len(result.matching_libraries) > 0


if __name__ == "__main__":
    pytest.main([__file__])
