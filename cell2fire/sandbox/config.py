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
MIRROR_KINECT_X = True           # Set to True to flip the Kinect input left-to-right (Horizontal)
MIRROR_KINECT_Y = False           # Set to True to flip the Kinect input top-to-bottom (Vertical)

# Region of Interest (crop rectangle) within the Kinect depth frame
# Adjust these to match your sandbox's physical footprint in the Kinect's view
KINECT_ROI = {
    "x1": 95,
    "y1": 112,
    "x2": 419,
    "y2": 314,
}

# Depth clamp range in millimeters
# Objects closer than DEPTH_MIN_MM or farther than DEPTH_MAX_MM are clipped
DEPTH_MIN_MM = 940
DEPTH_MAX_MM = 1030

# ═══════════════════════════════════════════════════════════
# Elevation Mapping
# ═══════════════════════════════════════════════════════════
# The normalized depth (0..1) is scaled to this elevation range (meters)
# This simulates realistic wildland terrain for the FBP model
ELEVATION_MIN_M = 860.0
ELEVATION_MAX_M = 1025.0

# ═══════════════════════════════════════════════════════════
# Fuel Type Classification (FBP lookup grid_value codes)
# ═══════════════════════════════════════════════════════════
# Elevation bands (percentile-based) mapped to FBP fuel type grid codes
# See fbp_lookup_table.csv for the full list

# --- ORIGINAL CANADIAN/BOREAL BIOMES (COMMENTED OUT) ---
# FUEL_BANDS = [
#     # (percentile_upper, grid_value, description)
#     (0.20, 102, "Water / Non-fuel"),          # Lowest 10% = water
#     (0.35, 31,  "O1a - Matted Grass"),        # 10-35% = grassland
#     (0.70, 2,   "C2 - Boreal Spruce"),        # 35-70% = conifer forest
#     (0.90, 3,   "C3 - Mature Jack Pine"),     # 70-90% = dense conifer
#     (1.00, 101, "Non-fuel (alpine rock)"),    # Top 10% = non-burnable alpine
# ]

# --- INDIAN FOREST BIOMES ---
# Note: The cell2fire engine requires valid FBP grid_values (like 2, 3, 31) for fire physics.
# We are repurposing those physics values to visually and thematically represent an Indian landscape.
# FUEL_BANDS = [
#     (0.15, 102, "River Water"),                           # Lowest 15% = Rivers
#     (0.35, 31,  "Tropical Scrub / Savannah (Dry Grass)"), # 15-35% = Scrubland
#     (0.70, 2,   "Tropical Dry Deciduous Forest"),         # 35-70% = Dry Deciduous
#     (0.90, 3,   "Tropical Moist Deciduous (Teak/Sal)"),   # 70-90% = Dense Jungle
#     (1.00, 101, "Deccan Laterite Rock Outcrops"),         # Top 10% = Red rocky hills
# ]
FUEL_BANDS = [
    (0.15, 102, "River Water"),                           # Lowest 15% = Rivers
    (0.35, 31,  "Tropical Scrub / Savannah (Dry Grass)"), # 15-35% = Scrubland
    (0.70, 2,   "Tropical Dry Deciduous Forest"),         # 35-70% = Dry Deciduous
    (1.00, 3,   "Tropical Moist Deciduous (Teak/Sal)"),   # 70-90% = Dense Jungle
]

DEFAULT_FUEL_TYPE = 2  # Tropical Dry Deciduous (fallback)

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
# --- ORIGINAL VIBRANT COLORS (COMMENTED OUT) ---
# COLOR_WATER = (15, 120, 255)         # Vibrant deep blue
# COLOR_GRASS = (100, 210, 50)         # Bright lush green
# COLOR_CONIFER = (15, 130, 30)        # Rich emerald green
# COLOR_DENSE_CONIFER = (0, 75, 15)    # Very dark pure moss green
# COLOR_ALPINE = (105, 75, 50)         # Rocky mountain earth brown

# --- INDIAN FOREST COLORS ---
COLOR_WATER = (0, 140, 220)          # Tropical teal river water
COLOR_GRASS = (180, 200, 60)         # Golden/Yellow-green Savannah scrub
COLOR_CONIFER = (90, 150, 40)        # Warm olive green for Dry Deciduous
COLOR_DENSE_CONIFER = (20, 90, 30)   # Deep dark jungle green for Moist Deciduous (Teak/Sal)
COLOR_ALPINE = (220, 150, 80)        # Bright baked sandy Laterite (Deccan rocks)
COLOR_BURNING = [(255, 30, 0), (255, 120, 0), (255, 230, 0), (255, 0, 0)] # More intense fire
COLOR_BURNED = (20, 20, 20)          # Darker charcoal for higher contrast
COLOR_BACKGROUND = (0, 0, 0)
COLOR_UI_TEXT = (255, 255, 0)       # High-visibility Yellow
COLOR_WIND_ARROW = (50, 255, 255)   # Vivid Cyan
COLOR_FIREBREAK = (60, 45, 35)      # Natural dark earth/soil color

# Map fuel grid_values to display colors
FUEL_COLORS = {
    102: COLOR_WATER,
    31:  COLOR_GRASS,
    2:   COLOR_CONIFER,
    3:   COLOR_DENSE_CONIFER,
    101: COLOR_ALPINE,
    103: COLOR_FIREBREAK,
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
