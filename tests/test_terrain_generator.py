# coding: utf-8
"""
Unit tests for the terrain generator module.
Tests depth→elevation→slope/aspect→fuel classification→.asc file pipeline.
"""
import os
import sys
import tempfile
import unittest
import numpy as np

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cell2fire.sandbox.terrain_generator import TerrainGenerator
from cell2fire.sandbox import config


class TestTerrainGenerator(unittest.TestCase):
    """Tests for TerrainGenerator class."""

    def setUp(self):
        """Create a terrain generator instance and synthetic depth frame."""
        self.gen = TerrainGenerator(
            rows=20, cols=20, cell_size=20.0,
            depth_min=960, depth_max=1030,
            roi={"x1": 72, "y1": 125, "x2": 462, "y2": 345},
        )
        # Create a synthetic depth frame (424×512)
        rng = np.random.RandomState(42)
        self.depth_frame = (960 + rng.rand(424, 512) * 70).astype(np.uint16)

    def test_depth_to_elevation_shape(self):
        """Elevation output should match configured grid dimensions."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        self.assertEqual(elev.shape, (20, 20))

    def test_depth_to_elevation_range(self):
        """Elevation values should be within the configured range."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        self.assertGreaterEqual(elev.min(), config.ELEVATION_MIN_M - 1)
        self.assertLessEqual(elev.max(), config.ELEVATION_MAX_M + 1)

    def test_depth_to_elevation_dtype(self):
        """Elevation should be float32."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        self.assertEqual(elev.dtype, np.float32)

    def test_compute_slope_shape(self):
        """Slope output should match elevation dimensions."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        slope = self.gen.compute_slope(elev)
        self.assertEqual(slope.shape, elev.shape)

    def test_compute_slope_range(self):
        """Slope should be in [0, 90] degrees."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        slope = self.gen.compute_slope(elev)
        self.assertGreaterEqual(slope.min(), 0)
        self.assertLessEqual(slope.max(), 90)

    def test_compute_slope_flat_surface(self):
        """A perfectly flat surface should have near-zero slope."""
        flat = np.full((20, 20), 2000.0, dtype=np.float32)
        slope = self.gen.compute_slope(flat)
        np.testing.assert_allclose(slope, 0, atol=0.01)

    def test_compute_slope_tilted_plane(self):
        """A tilted plane should have uniform non-zero slope."""
        # 45° slope: rise = cell_size for every cell
        elev = np.zeros((20, 20), dtype=np.float32)
        for r in range(20):
            elev[r, :] = r * self.gen.cell_size  # rise = cell_size per row
        slope = self.gen.compute_slope(elev)
        # Interior cells should have ~45° slope
        interior = slope[1:-1, 1:-1]
        expected = np.degrees(np.arctan(1.0))  # 45°
        np.testing.assert_allclose(interior, expected, atol=1.0)

    def test_compute_aspect_shape(self):
        """Aspect output should match elevation dimensions."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        aspect = self.gen.compute_aspect(elev)
        self.assertEqual(aspect.shape, elev.shape)

    def test_compute_aspect_range(self):
        """Aspect should be in [0, 360) degrees."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        aspect = self.gen.compute_aspect(elev)
        self.assertGreaterEqual(aspect.min(), 0)
        self.assertLess(aspect.max(), 360.1)

    def test_compute_aspect_south_facing(self):
        """A slope that descends to the south should have ~180° aspect."""
        elev = np.zeros((20, 20), dtype=np.float32)
        for r in range(20):
            elev[r, :] = (19 - r) * 100  # highest at top, lowest at bottom
        aspect = self.gen.compute_aspect(elev)
        # Check only deep interior cells to avoid edge gradient artifacts
        interior = aspect[2:-2, 2:-2]
        # All interior cells should face south (~180°)
        for val in interior.flatten():
            self.assertAlmostEqual(val, 180, delta=10,
                                  msg=f"Expected ~180° aspect, got {val}°")


    def test_classify_fuel_shape(self):
        """Fuel grid should match configured dimensions."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        fuel = self.gen.classify_fuel(elev)
        self.assertEqual(fuel.shape, (20, 20))

    def test_classify_fuel_valid_codes(self):
        """Fuel grid should only contain valid FBP codes."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        fuel = self.gen.classify_fuel(elev)
        valid_codes = {band[1] for band in config.FUEL_BANDS}
        unique_codes = set(np.unique(fuel))
        self.assertTrue(
            unique_codes.issubset(valid_codes),
            f"Unexpected fuel codes: {unique_codes - valid_codes}"
        )

    def test_classify_fuel_distribution(self):
        """Fuel classification should produce at least 2 different types."""
        elev = self.gen.depth_to_elevation(self.depth_frame)
        fuel = self.gen.classify_fuel(elev)
        self.assertGreater(len(np.unique(fuel)), 1)

    def test_write_asc_format(self):
        """Written .asc file should have correct header and data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = np.array([[1, 2, 3], [4, 5, 6]], dtype=int)
            filepath = os.path.join(tmpdir, "test.asc")
            TerrainGenerator.write_asc(data, filepath, cell_size=100.0)

            # Read back and verify
            with open(filepath, "r") as f:
                lines = f.readlines()

            self.assertIn("ncols", lines[0])
            self.assertIn("3", lines[0])
            self.assertIn("nrows", lines[1])
            self.assertIn("2", lines[1])
            self.assertIn("cellsize", lines[4])
            self.assertIn("100", lines[4])

            # Data starts at line 6
            data_line = lines[6].strip().split()
            self.assertEqual(len(data_line), 3)
            self.assertEqual(data_line[0], "1")

    def test_write_asc_float(self):
        """Float data should be written with one decimal place."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = np.array([[1.5, 2.7], [3.2, 4.9]], dtype=np.float32)
            filepath = os.path.join(tmpdir, "test_float.asc")
            TerrainGenerator.write_asc(data, filepath, cell_size=20.0)

            with open(filepath, "r") as f:
                lines = f.readlines()

            data_line = lines[6].strip().split()
            self.assertEqual(data_line[0], "1.5")

    def test_generate_all(self):
        """Full pipeline should produce all 4 .asc files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.gen.generate_all(self.depth_frame, tmpdir)

            # Check all keys exist
            self.assertIn("elevation", result)
            self.assertIn("slope", result)
            self.assertIn("aspect", result)
            self.assertIn("fuel", result)
            self.assertIn("files", result)

            # Check all files exist
            for key in ["elevation", "slope", "saz", "forest"]:
                filepath = result["files"][key]
                self.assertTrue(
                    os.path.isfile(filepath),
                    f"File not found: {filepath}"
                )

            # Check file sizes are non-zero
            for key in result["files"]:
                filepath = result["files"][key]
                size = os.path.getsize(filepath)
                self.assertGreater(size, 0, f"Empty file: {filepath}")


if __name__ == "__main__":
    unittest.main()
