# coding: utf-8
"""
Terrain generator: converts Kinect depth frames into Cell2Fire-compatible
ESRI ASCII Grid (.asc) raster files for elevation, slope, aspect, and fuel type.
"""
import os
import numpy as np
import cv2

from . import config


class TerrainGenerator:
    """Converts raw depth data into Cell2Fire topographic input files.

    Pipeline:
        depth_frame → crop/clamp/normalize → elevation
        elevation → slope, aspect (via gradients)
        elevation → fuel type classification
        All → written as .asc ESRI ASCII Grid files
    """

    def __init__(
        self,
        rows: int = None,
        cols: int = None,
        cell_size: float = None,
        depth_min: int = None,
        depth_max: int = None,
        roi: dict = None,
    ):
        self.rows = rows or config.SIM_ROWS
        self.cols = cols or config.SIM_COLS
        self.cell_size = cell_size or config.CELL_SIZE_METERS
        self.depth_min = depth_min or config.DEPTH_MIN_MM
        self.depth_max = depth_max or config.DEPTH_MAX_MM
        self.roi = roi or config.KINECT_ROI

    def depth_to_elevation(self, depth_frame: np.ndarray) -> np.ndarray:
        """Convert a raw Kinect depth frame to an elevation grid.

        Steps:
            1. Crop to the Region of Interest
            2. Clamp to [depth_min, depth_max]
            3. Normalize to 0..1
            4. Flip vertically (Kinect depth: closer = smaller value = higher elevation)
            5. Resize to simulation grid (rows × cols)
            6. Scale to realistic elevation range

        Args:
            depth_frame: 2D uint16 array (424×512) from the Kinect.

        Returns:
            2D float32 array (rows × cols) with elevation values in meters.
        """
        roi = self.roi
        crop = depth_frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]].astype(np.float32)

        # Clamp and normalize
        crop = np.clip(crop, self.depth_min, self.depth_max)
        crop_norm = (crop - self.depth_min) / (self.depth_max - self.depth_min)

        # Invert: lower depth value = closer to sensor = higher elevation
        crop_norm = 1.0 - crop_norm

        # Flip vertically so the sandbox orientation matches the simulation
        crop_norm = np.flipud(crop_norm)

        # Resize to simulation grid
        heightmap = cv2.resize(
            crop_norm, (self.cols, self.rows), interpolation=cv2.INTER_LINEAR
        )

        # Scale to realistic elevation range
        elevation = (
            config.ELEVATION_MIN_M
            + heightmap * (config.ELEVATION_MAX_M - config.ELEVATION_MIN_M)
        )

        return elevation.astype(np.float32)

    def compute_slope(self, elevation: np.ndarray) -> np.ndarray:
        """Compute slope in degrees from an elevation grid.

        Uses numpy gradient to compute dz/dx and dz/dy, then calculates
        the slope angle.

        Args:
            elevation: 2D float32 array (rows × cols) in meters.

        Returns:
            2D float32 array (rows × cols) with slope in degrees (0-90).
        """
        dy, dx = np.gradient(elevation, self.cell_size)
        slope_rad = np.arctan(np.sqrt(dx ** 2 + dy ** 2))
        slope_deg = np.degrees(slope_rad)
        return slope_deg.astype(np.float32)

    def compute_aspect(self, elevation: np.ndarray) -> np.ndarray:
        """Compute aspect (slope azimuth) in degrees from an elevation grid.

        Aspect is the compass direction the slope faces:
            0° / 360° = North, 90° = East, 180° = South, 270° = West.

        Args:
            elevation: 2D float32 array (rows × cols) in meters.

        Returns:
            2D float32 array (rows × cols) with aspect in degrees (0-360).
        """
        dy, dx = np.gradient(elevation, self.cell_size)

        # Geographic aspect: compass direction of the downhill direction
        # arctan2(-dx, dy) gives: 0°=N, 90°=E, 180°=S, 270°=W
        # dy positive = elevation increases with row (uphill toward south) → north facing
        # dy negative = elevation decreases with row (downhill toward south) → south facing
        aspect_rad = np.arctan2(-dx, dy)
        aspect_deg = np.degrees(aspect_rad)

        # Convert from -180..180 to 0..360
        aspect_deg = np.where(aspect_deg < 0, aspect_deg + 360, aspect_deg)

        # Flat areas (no slope) get aspect = 0
        flat_mask = (np.abs(dx) < 1e-6) & (np.abs(dy) < 1e-6)
        aspect_deg[flat_mask] = 0

        return aspect_deg.astype(np.float32)

    def classify_fuel(self, elevation: np.ndarray) -> np.ndarray:
        """Classify elevation values into FBP fuel type codes.

        Uses percentile-based bands defined in config.FUEL_BANDS.

        Args:
            elevation: 2D float32 array (rows × cols) in meters.

        Returns:
            2D int array (rows × cols) with FBP fuel type grid_value codes.
        """
        fuel_grid = np.full(
            (self.rows, self.cols), config.DEFAULT_FUEL_TYPE, dtype=int
        )

        # Compute percentile thresholds from the elevation data
        flat_elev = elevation.flatten()
        prev_pct = 0.0

        for upper_pct, grid_value, _desc in config.FUEL_BANDS:
            lower_val = np.percentile(flat_elev, prev_pct * 100)
            upper_val = np.percentile(flat_elev, upper_pct * 100)

            if prev_pct == 0.0:
                mask = elevation <= upper_val
            elif upper_pct >= 1.0:
                mask = elevation > lower_val
            else:
                mask = (elevation > lower_val) & (elevation <= upper_val)

            fuel_grid[mask] = grid_value
            prev_pct = upper_pct

        return fuel_grid

    @staticmethod
    def write_asc(
        data: np.ndarray,
        filepath: str,
        cell_size: float = None,
        xllcorner: float = None,
        yllcorner: float = None,
        nodata_value: int = -9999,
    ):
        """Write a 2D array as an ESRI ASCII Grid (.asc) file.

        Args:
            data: 2D numpy array to write.
            filepath: Output file path.
            cell_size: Cell size in the .asc header.
            xllcorner: X coordinate of lower-left corner.
            yllcorner: Y coordinate of lower-left corner.
            nodata_value: Value representing no data.
        """
        rows, cols = data.shape
        cs = cell_size or config.CELL_SIZE_METERS
        xll = xllcorner if xllcorner is not None else config.XLLCORNER
        yll = yllcorner if yllcorner is not None else config.YLLCORNER

        with open(filepath, "w") as f:
            f.write(f"ncols        {cols}\n")
            f.write(f"nrows        {rows}\n")
            f.write(f"xllcorner    {xll}\n")
            f.write(f"yllcorner    {yll}\n")
            f.write(f"cellsize     {cs}\n")
            f.write(f"NODATA_value {nodata_value}\n")

            for row in range(rows):
                values = data[row]
                # Use integer format for fuel grids, float for elevation/slope/aspect
                if data.dtype in (np.int32, np.int64, int):
                    line = " ".join(str(int(v)) for v in values)
                else:
                    line = " ".join(f"{v:.1f}" for v in values)
                f.write(line + "\n")

    def generate_all(self, depth_frame: np.ndarray, output_dir: str) -> dict:
        """Full pipeline: depth frame → all Cell2Fire .asc raster files.

        Args:
            depth_frame: 2D uint16 array from the Kinect.
            output_dir: Directory to write the output files.

        Returns:
            Dict with keys 'elevation', 'slope', 'aspect', 'fuel' containing
            the numpy arrays, and 'files' with the written file paths.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Compute terrain
        elevation = self.depth_to_elevation(depth_frame)
        slope = self.compute_slope(elevation)
        aspect = self.compute_aspect(elevation)
        fuel_grid = self.classify_fuel(elevation)

        # Round slope and aspect to integers (Cell2Fire convention from sample data)
        slope_int = np.round(slope).astype(int)
        aspect_int = np.round(aspect).astype(int)

        # Write files
        files = {}
        files["elevation"] = os.path.join(output_dir, "elevation.asc")
        files["slope"] = os.path.join(output_dir, "slope.asc")
        files["saz"] = os.path.join(output_dir, "saz.asc")
        files["forest"] = os.path.join(output_dir, "Forest.asc")

        # Cell2Fire uses cell_size in the .asc header (in meters matching CELL_SIZE_METERS)
        self.write_asc(elevation, files["elevation"], self.cell_size)
        self.write_asc(slope_int, files["slope"], self.cell_size)
        self.write_asc(aspect_int, files["saz"], self.cell_size)
        self.write_asc(fuel_grid, files["forest"], self.cell_size)

        print(f"[TerrainGenerator] Written {len(files)} raster files to {output_dir}")

        return {
            "elevation": elevation,
            "slope": slope,
            "aspect": aspect,
            "fuel": fuel_grid,
            "files": files,
        }
