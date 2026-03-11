# coding: utf-8
"""
Main AR Sandbox application: integrates Kinect capture, terrain generation,
Cell2Fire simulation, and Pygame projection rendering.

Usage:
    python -m cell2fire.sandbox.app
"""
import os
import sys
import math
import time
import numpy as np

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

from . import config
from .kinect_capture import KinectCapture
from .terrain_generator import TerrainGenerator
from .simulation_bridge import SimulationBridge
from .renderer import SandboxRenderer


class SandboxApp:
    """Main application class for the AR Sandbox fire simulation.

    Controls:
        SPACE       — Capture terrain from Kinect (or fallback image)
        Left Click  — Set ignition point at mouse position
        Arrow Keys  — Change wind direction
        + / =       — Increase wind speed by 5 km/h
        - / _       — Decrease wind speed by 5 km/h
        R           — Reset simulation (clear fire, keep terrain)
        T           — Re-capture terrain (reset everything)
        ESC         — Quit
    """

    def __init__(self):
        if not HAS_PYGAME:
            print("ERROR: pygame is required. Install with: pip install pygame")
            sys.exit(1)

        # Set Pygame window position before init
        os.environ["SDL_VIDEO_WINDOW_POS"] = config.SDL_WINDOW_POS

        # Initialize components
        print("=" * 60)
        print("  Cell2Fire AR Sandbox — Real-Time Fire Simulation")
        print("=" * 60)

        self.kinect = KinectCapture()
        self.terrain_gen = TerrainGenerator()
        self.sim_bridge = SimulationBridge()
        self.renderer = SandboxRenderer()

        # State
        self.running = True
        self.frame = 0
        self.time_step = 0

        # Terrain state
        self.terrain_captured = False
        self.elevation = None
        self.fuel_grid = None

        # Ignition state
        self.ignition_point = None      # (row, col) in grid coords
        self.ignition_cell_id = None    # 1-indexed cell number

        # Simulation state
        self.sim_running = False
        self.fire_grids = []            # List of grid arrays from simulation
        self.current_fire_grid = None
        self.sim_status = "Press SPACE to capture terrain"

        # Weather (modifiable at runtime)
        self.weather_params = config.DEFAULT_WEATHER.copy()

        # Wind direction cycling
        self._wind_dir_keys = list(config.WIND_DIRECTIONS.keys())
        self._wind_dir_idx = self._wind_dir_keys.index("W")  # default W (270°)

        print("\nControls:")
        print("  SPACE       — Capture terrain")
        print("  Left Click  — Set ignition point")
        print("  Arrow Keys  — Change wind direction")
        print("  +/-         — Adjust wind speed")
        print("  R           — Reset fire")
        print("  ESC         — Quit\n")

    def handle_events(self):
        """Process Pygame events and update state accordingly."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    self._handle_click(event.pos)

    def _handle_keydown(self, key):
        """Handle keyboard input."""
        if key == pygame.K_ESCAPE:
            self.running = False

        elif key == pygame.K_SPACE:
            self._capture_terrain()

        elif key == pygame.K_r:
            self._reset_simulation()

        elif key == pygame.K_t:
            self._capture_terrain()

        # Wind direction
        elif key == pygame.K_UP:
            self._set_wind_direction("N")
        elif key == pygame.K_DOWN:
            self._set_wind_direction("S")
        elif key == pygame.K_LEFT:
            self._set_wind_direction("W")
        elif key == pygame.K_RIGHT:
            self._set_wind_direction("E")

        # Wind speed
        elif key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self._adjust_wind_speed(5)
        elif key in (pygame.K_MINUS, pygame.K_UNDERSCORE, pygame.K_KP_MINUS):
            self._adjust_wind_speed(-5)

    def _handle_click(self, pos):
        """Handle mouse click — set ignition point."""
        if not self.terrain_captured:
            self.sim_status = "Capture terrain first (SPACE)"
            return

        x, y = pos
        col = int(x / self.renderer.cell_w)
        row = int(y / self.renderer.cell_h)

        # Clamp to grid bounds
        row = max(0, min(row, config.SIM_ROWS - 1))
        col = max(0, min(col, config.SIM_COLS - 1))

        # Check if cell is burnable
        fuel_val = int(self.fuel_grid[row, col])
        non_burnable = {101, 102, 100, 103, 104, 105}
        if fuel_val in non_burnable:
            self.sim_status = "Cannot ignite non-fuel cell"
            return

        # Set ignition point (1-indexed, row-major)
        self.ignition_point = (row, col)
        self.ignition_cell_id = row * config.SIM_COLS + col + 1

        self.sim_status = f"Ignition set at ({row}, {col}). Running simulation..."
        print(f"[App] Ignition at grid ({row}, {col}), cell ID = {self.ignition_cell_id}")

        # Run the simulation
        self._run_simulation()

    def _capture_terrain(self):
        """Capture depth from Kinect and generate terrain."""
        self.sim_status = "Capturing terrain..."
        print("[App] Capturing terrain from Kinect...")

        depth_frame = self.kinect.get_depth_frame()
        if depth_frame is None:
            self.sim_status = "Failed to capture depth frame"
            return

        # Generate terrain files
        result = self.sim_bridge.prepare_terrain(depth_frame)

        self.elevation = result["elevation"]
        self.fuel_grid = result["fuel"]
        self.terrain_captured = True

        # Reset simulation state
        self._reset_simulation()

        self.sim_status = "Terrain captured. Click to set ignition point."
        print("[App] Terrain captured and processed.")

    def _run_simulation(self):
        """Execute Cell2Fire simulation with current terrain and ignition."""
        if self.ignition_cell_id is None:
            return

        self.sim_status = "Running Cell2Fire simulation..."
        self.sim_running = False
        self.fire_grids = []
        self.time_step = 0
        self.current_fire_grid = None

        # Force display update to show status
        self._render_frame()

        # Run simulation
        grids = self.sim_bridge.run_simulation(
            ignition_cells=[self.ignition_cell_id],
            weather_params=self.weather_params,
        )

        if grids:
            self.fire_grids = grids
            self.sim_running = True
            self.time_step = 0
            self.sim_status = f"Simulating — {len(grids)} time steps"
            print(f"[App] Simulation complete: {len(grids)} time steps")
        else:
            self.sim_status = "Simulation produced no output. Check C++ build."
            print("[App] WARNING: No grid outputs from simulation.")

    def _reset_simulation(self):
        """Reset fire state, keep terrain."""
        self.sim_running = False
        self.fire_grids = []
        self.current_fire_grid = None
        self.ignition_point = None
        self.ignition_cell_id = None
        self.time_step = 0

        if self.terrain_captured:
            self.sim_status = "Fire reset. Click to set new ignition."
        else:
            self.sim_status = "Press SPACE to capture terrain"

    def _set_wind_direction(self, direction: str):
        """Update wind direction."""
        if direction in config.WIND_DIRECTIONS:
            self.weather_params["WD"] = config.WIND_DIRECTIONS[direction]
            self.sim_status = f"Wind direction: {direction} ({self.weather_params['WD']}°)"
            print(f"[App] Wind direction set to {direction}")

            # Re-run simulation if fire was active
            if self.ignition_cell_id is not None and self.terrain_captured:
                self._run_simulation()

    def _adjust_wind_speed(self, delta: float):
        """Adjust wind speed by delta km/h."""
        current = self.weather_params.get("WS", 20)
        new_speed = max(0, min(100, current + delta))
        self.weather_params["WS"] = new_speed
        self.sim_status = f"Wind speed: {new_speed} km/h"
        print(f"[App] Wind speed set to {new_speed} km/h")

        # Re-run simulation if fire was active
        if self.ignition_cell_id is not None and self.terrain_captured:
            self._run_simulation()

    def _update_fire_animation(self):
        """Advance the fire animation to the next time step."""
        if not self.sim_running or not self.fire_grids:
            return

        # Cycle through time steps (loop the animation)
        if self.time_step < len(self.fire_grids):
            self.current_fire_grid = self.fire_grids[self.time_step]

            # Advance every few frames for smooth visualization
            if self.frame % 5 == 0:  # advance sim step every 5 render frames
                self.time_step += 1
        else:
            # Hold on the last frame
            self.current_fire_grid = self.fire_grids[-1]
            self.sim_status = f"Simulation complete — {len(self.fire_grids)} steps"

    def _render_frame(self):
        """Render the current state to the display."""
        if self.terrain_captured and self.fuel_grid is not None:
            self.renderer.update(
                fuel_grid=self.fuel_grid,
                elevation=self.elevation,
                fire_grid=self.current_fire_grid,
                weather_params=self.weather_params,
                frame=self.frame,
                time_step=self.time_step,
                sim_status=self.sim_status,
                ignition_point=self.ignition_point if not self.sim_running else None,
            )
        else:
            # No terrain yet — show welcome screen
            self.renderer.screen.fill(config.COLOR_BACKGROUND)
            self.renderer.render_hud(self.weather_params, 0, self.sim_status)
            self.renderer.render_controls_help()
            pygame.display.flip()

    def run(self):
        """Main application loop."""
        print("[App] Starting main loop...")

        try:
            while self.running:
                self.handle_events()
                self._update_fire_animation()
                self._render_frame()
                self.renderer.tick()
                self.frame += 1

        except KeyboardInterrupt:
            print("\n[App] Interrupted by user.")
        finally:
            self.cleanup()

    def cleanup(self):
        """Release all resources."""
        print("[App] Shutting down...")
        self.kinect.cleanup()
        self.sim_bridge.cleanup_all()
        self.renderer.cleanup()
        print("[App] Goodbye.")


def main():
    """Entry point for the AR Sandbox application."""
    app = SandboxApp()
    app.run()


if __name__ == "__main__":
    main()
