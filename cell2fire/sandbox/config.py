# coding: utf-8
"""
Centralized configuration for the AR Sandbox fire simulation.
Edit these values to match your hardware setup and preferences.
"""
import os
import tempfile

# ═══════════════════════════════════════════════════════════
# Simulation Grid
# ═══════════════════════════════════════════════════════════
SIM_ROWS = 40                    # Number of rows in the simulation grid
SIM_COLS = 40                    # Number of columns in the simulation grid
CELL_SIZE_METERS = 50.0          # Physical size of each cell in meters (for FBP model)

# ═══════════════════════════════════════════════════════════
# Kinect v2 Depth Sensor
# ═══════════════════════════════════════════════════════════
KINECT_FRAME_WIDTH = 512         # Kinect v2 depth frame width
KINECT_FRAME_HEIGHT = 424        # Kinect v2 depth frame height

# Region of Interest (crop rectangle) within the Kinect depth frame
# Adjust these to match your sandbox's physical footprint in the Kinect's view
KINECT_ROI = {
    "x1": 72,
    "y1": 125,
    "x2": 462,
    "y2": 345,
}

# Depth clamp range in millimeters
# Objects closer than DEPTH_MIN_MM or farther than DEPTH_MAX_MM are clipped
DEPTH_MIN_MM = 960
DEPTH_MAX_MM = 1030

# ═══════════════════════════════════════════════════════════
# Elevation Mapping
# ═══════════════════════════════════════════════════════════
# The normalized depth (0..1) is scaled to this elevation range (meters)
# This simulates realistic wildland terrain for the FBP model
ELEVATION_MIN_M = 1800.0
ELEVATION_MAX_M = 2400.0

# ═══════════════════════════════════════════════════════════
# Fuel Type Classification (FBP lookup grid_value codes)
# ═══════════════════════════════════════════════════════════
# Elevation bands (percentile-based) mapped to FBP fuel type grid codes
# See fbp_lookup_table.csv for the full list
FUEL_BANDS = [
    # (percentile_upper, grid_value, description)
    (0.10, 102, "Water / Non-fuel"),          # Lowest 10% = water
    (0.35, 31,  "O1a - Matted Grass"),        # 10-35% = grassland
    (0.70, 2,   "C2 - Boreal Spruce"),        # 35-70% = conifer forest
    (0.90, 3,   "C3 - Mature Jack Pine"),     # 70-90% = dense conifer
    (1.00, 101, "Non-fuel (alpine rock)"),     # Top 10% = non-burnable alpine
]

DEFAULT_FUEL_TYPE = 2  # C2 Boreal Spruce (fallback)

# ═══════════════════════════════════════════════════════════
# Cell2Fire Simulation Parameters
# ═══════════════════════════════════════════════════════════
FIRE_PERIOD_LENGTH = 0.2         # Fire period length in minutes (smaller = more output grids)
SIM_YEARS = 1                    # Number of years per simulation
N_SIMS = 1                       # Number of replications
ROS_CV = 0.0                     # Rate of Spread coefficient of variation (0 = deterministic)
ROS_THRESHOLD = 0.1              # Minimum ROS (m/min) for fire to spread
HFI_THRESHOLD = 0.1              # Minimum HFI (kW/m) for fire to spread
WEATHER_OPT = "rows"             # Weather option for Cell2Fire
SEED = 123                       # Random seed

# ═══════════════════════════════════════════════════════════
# Default Weather Parameters
# ═══════════════════════════════════════════════════════════
DEFAULT_WEATHER = {
    "scenario": "SBX",
    "datetime": "2024-07-15 13:00",
    "APCP": 0.0,        # Precipitation (mm)
    "TMP": 25.0,         # Temperature (°C)
    "RH": 30,            # Relative Humidity (%)
    "WS": 20,            # Wind Speed (km/h)
    "WD": 270,           # Wind Direction (degrees, 0=N, 90=E, 180=S, 270=W)
    "FFMC": 90,          # Fine Fuel Moisture Code
    "DMC": 50,           # Duff Moisture Code
    "DC": 300,           # Drought Code
    "ISI": 12.0,         # Initial Spread Index
    "BUI": 65,           # Build Up Index
    "FWI": 30,           # Fire Weather Index
}

# Wind direction names mapped to compass degrees
WIND_DIRECTIONS = {
    "N": 0,
    "NE": 45,
    "E": 90,
    "SE": 135,
    "S": 180,
    "SW": 225,
    "W": 270,
    "NW": 315,
}

# ═══════════════════════════════════════════════════════════
# Projector / Display
# ═══════════════════════════════════════════════════════════
PROJECTOR_WIDTH = 1280           # Epson EB-1781W native width
PROJECTOR_HEIGHT = 800           # Epson EB-1781W native height

# Pygame window position: set to projector's display coordinates
# Use '0,0' for primary display, or e.g. '1920,0' for a second monitor to the right
SDL_WINDOW_POS = "0,0"

# Frame rate cap for the render loop
TARGET_FPS = 30

# ═══════════════════════════════════════════════════════════
# Colors (RGB tuples)
# ═══════════════════════════════════════════════════════════
COLOR_WATER = (30, 100, 180)
COLOR_GRASS = (120, 180, 60)
COLOR_CONIFER = (34, 100, 34)
COLOR_DENSE_CONIFER = (20, 70, 20)
COLOR_ALPINE = (160, 160, 160)
COLOR_BURNING = [(255, 80, 0), (255, 140, 0), (255, 200, 40), (255, 60, 0)]
COLOR_BURNED = (40, 40, 40)
COLOR_BACKGROUND = (0, 0, 0)
COLOR_UI_TEXT = (255, 255, 255)
COLOR_WIND_ARROW = (200, 200, 255)

# Map fuel grid_values to display colors
FUEL_COLORS = {
    102: COLOR_WATER,
    31:  COLOR_GRASS,
    2:   COLOR_CONIFER,
    3:   COLOR_DENSE_CONIFER,
    101: COLOR_ALPINE,
}

# ═══════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════
# Temporary directory for generated Cell2Fire input files
SANDBOX_DATA_DIR = os.path.join(tempfile.gettempdir(), "cell2fire_sandbox_data")
SANDBOX_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "cell2fire_sandbox_output")

# Reference data directory (for fbp_lookup_table.csv)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
CELL2FIRE_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
REFERENCE_DATA_DIR = os.path.join(CELL2FIRE_ROOT, "data", "Sub20x20")
CELL2FIRE_EXE = os.path.join(_THIS_DIR, "..", "Cell2FireC", "Cell2Fire")

# Fallback depth image for development without Kinect
FALLBACK_DEPTH_IMAGE = os.path.join(_THIS_DIR, "depth.png")

# ═══════════════════════════════════════════════════════════
# Precomputed Simulation Cache
# ═══════════════════════════════════════════════════════════
PRECOMPUTED_CACHE_DIR = os.path.join(tempfile.gettempdir(), "cell2fire_sandbox_cache")
PRECOMPUTED_CACHE_FILE = os.path.join(PRECOMPUTED_CACHE_DIR, "fire_sim_cache.npz")

# Default ignition point for precomputed simulation (row, col in grid coords)
# Center of grid by default — adjust to match your scenario
DEFAULT_IGNITION_ROW = SIM_ROWS // 2
DEFAULT_IGNITION_COL = SIM_COLS // 2

# ═══════════════════════════════════════════════════════════
# Hillshade Rendering (AR Sandbox style)
# ═══════════════════════════════════════════════════════════
HILLSHADE_AZIMUTH = 315          # Light source azimuth (degrees)
HILLSHADE_ALTITUDE = 45          # Light source altitude (degrees)
HILLSHADE_VERT_EXAG = 4          # Vertical exaggeration for hillshade
HILLSHADE_BLEND_MODE = "soft"    # Blend mode: 'soft', 'overlay', 'hsv'
CONTOUR_LEVELS = 10              # Number of contour lines to draw
CONTOUR_COLOR = (220, 220, 220, 80)  # Semi-transparent white contour lines

# Geo-reference constants (arbitrary, needed for .asc header)
XLLCORNER = 457900
YLLCORNER = 5716800
LATITUDE = 51.621244
LONGITUDE = -115.608378
