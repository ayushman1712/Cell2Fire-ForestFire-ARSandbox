# coding: utf-8
"""
Unit tests for the data builder module.
Tests Weather.csv, IgnitionPoints.csv generation, and Data.csv pipeline.
"""
import os
import sys
import tempfile
import unittest
import shutil
import numpy as np
import pandas as pd

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cell2fire.sandbox import data_builder, config
from cell2fire.sandbox.terrain_generator import TerrainGenerator


class TestWeatherCSV(unittest.TestCase):
    """Tests for Weather.csv generation."""

    def test_generate_default_weather(self):
        """Default weather should produce a valid CSV with correct columns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.generate_weather_csv(tmpdir)
            self.assertTrue(os.path.isfile(filepath))

            df = pd.read_csv(filepath)
            expected_cols = ["Scenario", "datetime", "APCP", "TMP", "RH",
                           "WS", "WD", "FFMC", "DMC", "DC", "ISI", "BUI", "FWI"]
            for col in expected_cols:
                self.assertIn(col, df.columns)

    def test_weather_multiple_rows(self):
        """Weather CSV should have multiple rows for multi-period sims."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.generate_weather_csv(tmpdir)
            df = pd.read_csv(filepath)
            self.assertEqual(len(df), 8)  # 8 hours of weather

    def test_custom_weather_params(self):
        """Custom weather parameters should override defaults."""
        custom = config.DEFAULT_WEATHER.copy()
        custom["WS"] = 42
        custom["WD"] = 90

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.generate_weather_csv(tmpdir, custom)
            df = pd.read_csv(filepath)
            self.assertEqual(df["WS"].iloc[0], 42)
            self.assertEqual(df["WD"].iloc[0], 90)


class TestIgnitionCSV(unittest.TestCase):
    """Tests for IgnitionPoints.csv generation."""

    def test_single_ignition(self):
        """Single ignition point should produce correct CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.generate_ignition_csv(tmpdir, [100])
            self.assertTrue(os.path.isfile(filepath))

            df = pd.read_csv(filepath)
            self.assertEqual(len(df), 1)
            self.assertEqual(df["Ncell"].iloc[0], 100)
            self.assertEqual(df["Year"].iloc[0], 1)

    def test_multiple_ignitions(self):
        """Multiple ignition points should all appear in CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.generate_ignition_csv(tmpdir, [10, 20, 30])
            df = pd.read_csv(filepath)
            self.assertEqual(len(df), 3)
            self.assertListEqual(list(df["Ncell"]), [10, 20, 30])


class TestFBPLookup(unittest.TestCase):
    """Tests for fbp_lookup_table.csv copy."""

    def test_copy_fbp_lookup(self):
        """FBP lookup table should be copied to output directory."""
        if not os.path.isfile(os.path.join(config.REFERENCE_DATA_DIR, "fbp_lookup_table.csv")):
            self.skipTest("Reference data directory not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = data_builder.copy_fbp_lookup(tmpdir)
            self.assertTrue(os.path.isfile(filepath))
            # Should have at least the header + several fuel types
            df = pd.read_csv(filepath)
            self.assertGreater(len(df), 10)


class TestDataCSV(unittest.TestCase):
    """Tests for Data.csv generation from .asc rasters."""

    def test_generate_data_csv(self):
        """Data.csv should have one row per cell."""
        if not os.path.isfile(os.path.join(config.REFERENCE_DATA_DIR, "fbp_lookup_table.csv")):
            self.skipTest("Reference data directory not found")

        rows, cols = 10, 10
        gen = TerrainGenerator(rows=rows, cols=cols, cell_size=20.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Generate raster files first
            rng = np.random.RandomState(42)
            depth = (960 + rng.rand(424, 512) * 70).astype(np.uint16)
            gen.generate_all(depth, tmpdir)

            # Copy fbp_lookup_table
            data_builder.copy_fbp_lookup(tmpdir)

            # Generate Data.csv
            filepath = data_builder.generate_data_csv(tmpdir)
            self.assertTrue(os.path.isfile(filepath))

            df = pd.read_csv(filepath)
            self.assertEqual(len(df), rows * cols)
            self.assertIn("fueltype", df.columns)
            self.assertIn("elev", df.columns)
            self.assertIn("ps", df.columns)
            self.assertIn("saz", df.columns)


if __name__ == "__main__":
    unittest.main()
