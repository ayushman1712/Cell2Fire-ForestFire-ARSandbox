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

## Wizard of Oz (WoZ) Prototyping

For user testing and rapid prototyping, the system supports a dual-window "Wizard of Oz" mode. This allows an operator to control the simulation (start fires, change wind, reset) from a separate monitor without the participant seeing the controls on the projected sand.

### 1. Start the Projector Display
This window should be moved to the projector screen. It only displays the simulation and has no interactive controls (except ESC to quit).
```bash
python -m cell2fire.sandbox
```

### 2. Start the Operator Console
Run this in a separate terminal on your primary monitor. It shows a live, 2.5x scaled Kinect depth view to help you spot physical tokens placed by the user.
```bash
python -m cell2fire.sandbox.woz_operator
```

### Operator Controls
| Action | Key/Mouse |
| :--- | :--- |
| **Ignite Fire** | Left Click (on operator window) |
| **Capture Terrain** | `SPACE` |
| **Precompute Sim** | `F` |
| **Play Cache** | `P` |
| **Wind Direction** | `W`, `A`, `S`, `D` (N, W, S, E) |
| **Wind Speed** | `+` / `-` |
| **Fire Spread Speed** | `<` / `>` (Comma / Period) |
| **Reset Simulation** | `R` |
| **Toggle Grid** | `G` |
| **Quit** | `ESC` / `Q` |

## Biomes & Colors
All visual rendering (Rivers, Biome elevations, Fire gradients) is fully decoupled and configurable within `config.py` under the `FUEL_BANDS` and `COLOR_XYZ` variables.
