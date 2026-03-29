# Cell2Fire AR Sandbox

An Augmented Reality (AR) Sandbox implementation for the Cell2Fire wildfire simulation engine.

## Hardware Requirements
- Microsoft Kinect v2 Depth Sensor
- Short-throw or standard projector (Native 16:10 aspect ratio recommended, e.g. 1280x800)
- Windows OS (Required for `pykinect2` library usage)

## Dependencies
Ensure your environment has the following installed:
- `pyglet` (UI and rendering)
- `opencv-python` (Image processing)
- `numpy`
- `matplotlib` (Colormap generation)
- `pykinect2` (Kinect v2 hardware interfacing)

## How to Run
Run the projector visualizer directly as a module from the root directory:
```bash
python -m cell2fire.sandbox
```

## Hardware Calibration Guide

Before running the simulation properly, you must configure the projection bounds to match your physical sand.

### 1. Depth Calibration
Run `python measure_depth.py` from the root folder to point your mouse and find raw depth values in mm.
- **DEPTH_MAX_MM**: The distance to the flat bottom/table holding the sand.
- **DEPTH_MIN_MM**: The distance to the tallest sand peak you intend to build.
Enter these values into `config.py`.

### 2. Aspect Ratio / Framing
Run `python calibrate_kinect.py` from the root folder to visually draw a 16:10 rectangle over your sand view. 
Copy the generated `KINECT_ROI` dictionary from the terminal into `config.py`.

### 3. Projector & Sensor Mirroring
If your projector is mounted backwards or upside down via a mirror:
Set your projector hardware's "Projection" setting so the HUD Text is perfectly readable.
Then adjust `MIRROR_KINECT_X` and `MIRROR_KINECT_Y` in `config.py` to ensure physical sand touches match the simulated terrain locations.

## Biomes & Colors
All visual rendering (Rivers, Biome elevations, Fire gradients) is fully decoupled and configurable within `config.py` under the `FUEL_BANDS` and `COLOR_XYZ` variables.
