# coding: utf-8
"""
Main AR Sandbox application using Pyglet (matching mcsandtable architecture).

Integrates Kinect capture, terrain generation, Cell2Fire simulation,
and Pyglet projection rendering with AR Sandbox-style hillshade terrain.

Usage:
    python -m cell2fire.sandbox
"""
import os
import sys
import math
import numpy as np
import pyglet
import pyglet.event
from pyglet.window import key, mouse
import cv2

# Wizard-of-Oz IPC
from .woz_operator import read_commands, write_state

from . import config
from .kinect_capture import KinectCapture
from .terrain_generator import TerrainGenerator
from .simulation_bridge import SimulationBridge
from .renderer import SandboxRenderer


class Cell2FireSandbox(pyglet.window.Window):
    """Pyglet window for the Cell2Fire AR Sandbox projection system.

    Mirrors the AR Sandbox (MCSandTable) architecture:
    - Subclasses pyglet.window.Window
    - on_draw renders the scene
    - on_key_press handles input
    - flip_canvas rotates for overhead projector

    Controls:
        SPACE       — Capture depth from Kinect (single snapshot)
        F           — Precompute simulation → save to disk
        P           — Play precomputed simulation from cache
        Left Click  — Set ignition point (runs sim in real time)
        Arrow Keys  — Change wind direction
        EQUAL/MINUS — Adjust wind speed ±5 km/h
        R           — Reset fire (keep terrain)
        ESC         — Quit
    """

    def __init__(self, force_windowed=True, fps=30, screen_id=0):
        # Detect screens (handle pyglet API differences)
        screens = []
        try:
            _canvas = __import__("pyglet.canvas", fromlist=["canvas"])
            display = _canvas.get_display()
            screens = display.get_screens()
        except Exception:
            pass

        if force_windowed or len(screens) <= 1:
            super().__init__(
                resizable=True,
                width=config.PROJECTOR_WIDTH,
                height=config.PROJECTOR_HEIGHT,
                caption="Cell2Fire AR Sandbox",
            )
        else:
            target = screens[min(screen_id, len(screens) - 1)]
            super().__init__(screen=target, fullscreen=True)

        self.fps = fps

        # ── Components ──
        self.kinect = KinectCapture()
        self.terrain_gen = TerrainGenerator()
        self.sim_bridge = SimulationBridge()
        self.renderer = SandboxRenderer(self.width, self.height)

        # ── State ──
        self.frame = 0
        self.anim_frame = 0
        self.time_step = 0
        self.frames_per_step = 15  # Default visual speed

        self.terrain_captured = False
        self.elevation = None
        self.fuel_grid = None
        self._depth_frame = None

        self.ignition_point = None
        self.ignition_cell_id = None

        self.sim_running = False
        self.fire_grids = []
        self.current_fire_grid = None
        self.sim_status = "Press SPACE to capture terrain"

        self.weather_params = config.DEFAULT_WEATHER.copy()
        self.show_projection_grid = False
        
        self.paused = False
        self.show_hud_text = True
        self.burn_pct = 0.0
        self.sim_time_str = "00:00"
        self._total_fuel_cells = 0

        # ── HUD Labels ──
        self.fps_display = pyglet.window.FPSDisplay(window=self, color=(255, 0, 0, 255))
        self.status_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=12,
            x=10, y=self.height - 20, color=(255, 255, 255, 220),
        )
        self.step_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=12,
            x=10, y=self.height - 40, color=(255, 255, 255, 220),
        )
        self.weather_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=12,
            x=10, y=self.height - 60, color=(255, 255, 255, 220),
        )
        self.controls_label = pyglet.text.Label(
            "Controls moved to WoZ Operator Console | ESC:Quit",
            font_name="Consolas", font_size=10,
            x=self.width // 2, y=10, anchor_x="center",
            color=(180, 180, 180, 200),
        )
        self.wind_label = pyglet.text.Label(
            "WIND", font_name="Consolas", font_size=10,
            x=self.width - 60, y=self.height - 10,
            anchor_x="center", color=(200, 200, 255, 220),
        )
        self.wind_speed_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=10,
            x=self.width - 60, y=self.height - 110,
            anchor_x="center", color=(200, 200, 255, 220),
        )
        self.time_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=18,
            x=self.width // 2, y=self.height - 35, anchor_x="center",
            color=(255, 255, 255, 255),
        )
        self.burn_label = pyglet.text.Label(
            "", font_name="Consolas", font_size=14,
            x=self.width // 2, y=self.height - 65, anchor_x="center",
            color=(255, 200, 150, 220),
        )

        # ── Projector flip ──
        if self.fullscreen:
            pyglet.clock.schedule_once(self.flip_canvas, delay=2)

        # ── Wizard-of-Oz command polling ──
        pyglet.clock.schedule_interval(self._poll_woz_commands, 0.05)

        # Check for cached simulation
        cached = SimulationBridge.load_precomputed()
        if cached:
            self.sim_status = "Cached simulation available — press P to play"

        print("=" * 60)
        print("  Cell2Fire AR Sandbox — Pyglet Projection System")
        print("=" * 60)
        print("\n  [All controls moved to WoZ Operator Console]")
        print("  ESC=Quit Pyglet window\n")

    # ── Canvas Flip (same as AR Sandbox) ────────────────────

    def flip_canvas(self, _=None):
        """Rotate 180° for overhead projector (identical to MCSandTable)."""
        from pyglet.math import Mat4, Vec3
        ortho = Mat4.orthogonal_projection(0, self.width, 0, self.height, -255, 255)
        translate = Mat4.from_translation(Vec3(self.width, self.height, 0))
        rotate = Mat4.from_rotation(3.14, Vec3(0, 0, 1))
        self.projection = ortho @ translate @ rotate

    # ── Numpy → Pyglet (same pattern as MCSandTable.create_pyglet_img) ──

    @staticmethod
    def numpy_to_pyglet(img):
        """Convert numpy HxWx3 RGB array to pyglet ImageData."""
        img = np.ascontiguousarray(np.flipud(img))
        h, w, nc = img.shape
        fmt = "RGBA" if nc == 4 else "RGB"
        raw = np.ctypeslib.as_ctypes(img.ravel().astype(np.uint8))
        return pyglet.image.ImageData(w, h, fmt, raw, pitch=w * nc)

    # ── Input Events ────────────────────────────────────────

    def on_key_press(self, symbol, modifiers):
        if symbol == key.ESCAPE:
            self._cleanup()
            self.close()

    def on_mouse_press(self, x, y, button, modifiers):
        # Ignore mouse clicks inside the sandbox window
        if not self.terrain_captured:
            self.sim_status = "WoZ: Capture terrain first"
            return

    # ── Wizard-of-Oz Command Polling ────────────────────────

    def _poll_woz_commands(self, dt=None):
        """Check for pending Wizard-of-Oz operator commands."""
        cmds = read_commands()
        if not cmds:
            return

        for cmd in cmds:
            cmd_type = cmd.get("type", "")

            if cmd_type == "ignite":
                row = cmd["row"]
                col = cmd["col"]
                print(f"[WoZ] Received ignition command: ({row}, {col})")

                if not self.terrain_captured:
                    self.sim_status = "WoZ: Capture terrain first"
                    continue # Use continue instead of return since we are in a loop

                fuel_val = int(self.fuel_grid[row, col])
                if fuel_val in {100, 101, 102, 103, 104, 105}:
                    self.sim_status = f"Non-fuel at ({row}, {col})"
                    self._sync_woz_state()
                    continue

                self.ignition_point = (row, col)
                self.ignition_cell_id = row * config.SIM_COLS + col + 1
                self.sim_status = f"Ignition at ({row}, {col})"
                print(f"[WoZ] Ignition at ({row}, {col}), cell ID={self.ignition_cell_id}")
                self._sync_woz_state() # Clear previous "Non-fuel" status

                if self._depth_frame is not None:
                    # Sync and prepare terrain/fuel files for the C++ engine
                    self.sim_bridge.prepare_terrain(self._depth_frame)
                    # Overwrite Forest.asc with the latest fuel_grid (including any new firebreaks/water)
                    forest_asc = os.path.join(self.sim_bridge.sim_data_dir, "Forest.asc")
                    self.terrain_gen.write_asc(self.fuel_grid, forest_asc, config.CELL_SIZE_METERS)
                    
                self._run_simulation()

            elif cmd_type == "reset":
                print("[WoZ] Received reset command.")
                self._reset_simulation()
                
            elif cmd_type == "firebreak_line":
                r1, c1 = cmd.get("r1"), cmd.get("c1")
                r2, c2 = cmd.get("r2"), cmd.get("c2")
                # print(f"[WoZ] Received firebreak line: ({r1}, {c1}) to ({r2}, {c2})")
                if not self.terrain_captured or self.fuel_grid is None:
                    self.sim_status = "WoZ: Capture terrain first"
                    continue
                self._draw_firebreak_line(r1, c1, r2, c2)
                # self.sim_status = f"Firebreak ({r1},{c1}) to ({r2},{c2})"
                self._sync_woz_state()
            
            elif cmd_type == "capture":
                print("[WoZ] Received capture command.")
                self._capture_terrain()
                
            elif cmd_type == "precompute":
                print("[WoZ] Received precompute command.")
                self._precompute_simulation()
                
            elif cmd_type == "play":
                print("[WoZ] Received play command.")
                self._play_precomputed()
                
            elif cmd_type == "wind_dir":
                print(f"[WoZ] Received wind_dir command: {cmd.get('dir')}")
                self._set_wind_direction(cmd.get("dir", "N"))
                
            elif cmd_type == "wind_speed":
                print(f"[WoZ] Received wind_speed command: delta {cmd.get('delta')}")
                self._adjust_wind_speed(cmd.get("delta", 0))
                
            elif cmd_type == "anim_speed":
                delta = cmd.get("delta", 0)
                self.frames_per_step = max(5, min(100, self.frames_per_step + delta))
                print(f"[WoZ] Received anim_speed command. New speed: {self.frames_per_step} frames/step")
                self.sim_status = f"Visual speed: {self.frames_per_step} frames/step"
                
            elif cmd_type == "projection_grid":
                self.show_projection_grid = cmd.get("value", False)
                print(f"[WoZ] 3x3 Grid projection: {'ON' if self.show_projection_grid else 'OFF'}")
                self.sim_status = f"3x3 Grid projection: {'ON' if self.show_projection_grid else 'OFF'}"
                self._sync_woz_state() # Ensure WoZ console is in sync
            
            elif cmd_type == "toggle_pause":
                self.paused = not self.paused
                print(f"[WoZ] Simulation paused: {self.paused}")
                self.sim_status = f"{'PAUSED' if self.paused else 'RESUMED'}"
                self._sync_woz_state()
                
            elif cmd_type == "toggle_hud":
                self.show_hud_text = not self.show_hud_text
                print(f"[WoZ] HUD visibility: {self.show_hud_text}")
                self._sync_woz_state()

    # ── Rendering (on_draw, same pattern as MCSandTable) ────

    def on_draw(self):
        self.clear()

        if self.terrain_captured and self.elevation is not None:
            # Advance fire animation
            self._advance_fire()

            # Generate images
            terrain = self.renderer.generate_terrain_image(self.elevation, self.fuel_grid)
            fire = None
            if self.current_fire_grid is not None:
                fire = self.renderer.generate_fire_overlay(
                    self.current_fire_grid, 
                    getattr(self, "next_fire_grid", None), 
                    getattr(self, "fire_blend", 0.0), 
                    self.frame
                )

            show_marker = self.ignition_point is not None and not self.sim_running
            final = self.renderer.composite(terrain, fire, self.ignition_point, show_marker)

            # Draw 3x3 grid if enabled
            if self.show_projection_grid:
                self.renderer.draw_3x3_grid(final)

            # Convert to pyglet and blit (same as MCSandTable)
            pimg = self.numpy_to_pyglet(final)
            pimg.blit(0, 0, width=self.width, height=self.height)

        self._draw_hud()
        self._draw_wind_indicator()
        self.fps_display.draw()
        
        # Periodic state sync to operator console
        if self.frame % 10 == 0:
            self._sync_woz_state()
            
        self.frame += 1

    def _draw_hud(self):
        """Draw HUD labels."""
        if not self.show_hud_text:
            return
            
        wp = self.weather_params
        self.status_label.text = self.sim_status
        self.step_label.text = f"Step: {self.time_step}"
        self.weather_label.text = f"T:{wp['TMP']}°C  RH:{wp['RH']}%"
        self.time_label.text = self.sim_time_str
        self.burn_label.text = f"BURNED: {self.burn_pct:.1f}%"
        
        self.status_label.draw()
        self.step_label.draw()
        self.weather_label.draw()
        self.controls_label.draw()
        self.time_label.draw()
        self.burn_label.draw()

    def _draw_wind_indicator(self):
        """Draw a prominent wind dial in the top-right corner."""
        # Positioning
        radius = 50
        cx = self.width - radius - 20
        cy = self.height - radius - 60
        
        wp = self.weather_params
        direction_deg = wp.get("WD", 270)
        speed = wp.get("WS", 20)

        # 1. Background plate for contrast
        bg = pyglet.shapes.Circle(cx, cy, radius + 15, color=(0, 0, 0, 160))
        bg.draw()

        # 2. Outer ring
        circle = pyglet.shapes.Arc(cx, cy, radius, color=(100, 100, 150, 200))
        circle.draw()

        # 3. Direction Markers (N/S/E/W)
        markers = [
            ("N", 0, 1), ("E", 1, 0), ("S", 0, -1), ("W", -1, 0)
        ]
        mlabels = []
        for text, dx, dy in markers:
            mlabels.append(pyglet.text.Label(
                text, font_name="Consolas", font_size=8,
                x=cx + dx*(radius-12), y=cy + dy*(radius-12),
                anchor_x="center", anchor_y="center",
                color=(150, 150, 200, 200)
            ))
            mlabels[-1].draw()

        # 4. Arrow
        angle_rad = math.radians(direction_deg)
        arrow_len = radius - 5
        dx = arrow_len * math.sin(angle_rad)
        dy = arrow_len * math.cos(angle_rad)

        # Main shaft
        line = pyglet.shapes.Line(
            cx - dx * 0.2, cy - dy * 0.2, cx + dx, cy + dy,
            thickness=6, color=(150, 200, 255, 255),
        )
        line.draw()

        # Arrowhead
        head_len = 15
        la = angle_rad + math.radians(150)
        ra = angle_rad - math.radians(150)
        tri = pyglet.shapes.Triangle(
            cx + dx, cy + dy,
            cx + dx + head_len * math.sin(la), cy + dy + head_len * math.cos(la),
            cx + dx + head_len * math.sin(ra), cy + dy + head_len * math.cos(ra),
            color=(150, 200, 255, 255),
        )
        tri.draw()

        # 5. Text data
        self.wind_label.x = cx
        self.wind_label.y = cy + radius + 25
        self.wind_label.draw()
        
        self.wind_speed_label.x = cx
        self.wind_speed_label.y = cy - radius - 25
        self.wind_speed_label.text = f"{speed:.0f} km/h"
        self.wind_speed_label.draw()

    # ── Simulation Logic ────────────────────────────────────

    def _capture_terrain(self):
        self.sim_status = "Capturing terrain..."
        print("[App] Capturing terrain...")
        depth = self.kinect.get_depth_frame()
        if depth is None:
            self.sim_status = "Failed to capture depth frame"
            return
        self._depth_frame = depth.copy()
        result = self.sim_bridge.prepare_terrain(depth)
        self.elevation = result["elevation"]
        self.fuel_grid = result["fuel"]
        # Exclude non-fuel cells (water=102, non-burnable=101) from burn percentage
        self._total_fuel_cells = np.count_nonzero((self.fuel_grid != 101) & (self.fuel_grid != 102))
        self.terrain_captured = True
        self._reset_simulation()
        self._sync_woz_state()  # Reset operator view
        self.sim_status = "Terrain captured. Click to ignite or F to precompute."
        print("[App] Terrain captured.")

    def _precompute_simulation(self):
        if not self.terrain_captured or self._depth_frame is None:
            self.sim_status = "Capture terrain first (SPACE)"
            return
        r, c = config.DEFAULT_IGNITION_ROW, config.DEFAULT_IGNITION_COL
        self.sim_status = f"Precomputing from ({r}, {c})..."
        print(f"[App] Precomputing from ({r}, {c})...")
        # Ensure latest fuel/firebreaks are saved for the engine
        forest_asc = os.path.join(self.sim_bridge.sim_data_dir, "Forest.asc")
        self.terrain_gen.write_asc(self.fuel_grid, forest_asc, config.CELL_SIZE_METERS)
        
        grids = self.sim_bridge.precompute_and_save(
            self._depth_frame, r, c, self.weather_params,
        )
        if grids:
            self.sim_status = f"Precomputed! {len(grids)} steps. Press P to play."
        else:
            self.sim_status = "Precomputation failed."

    def _play_precomputed(self):
        cached = SimulationBridge.load_precomputed()
        if cached is None:
            self.sim_status = "No cache. SPACE then F first."
            return
        self.fire_grids = cached["grids"]
        self.ignition_point = (cached["ignition_row"], cached["ignition_col"])
        self.ignition_cell_id = cached["ignition_row"] * config.SIM_COLS + cached["ignition_col"] + 1
        self.elevation = cached["elevation"]
        self.fuel_grid = cached["fuel"]
        self.terrain_captured = True
        self.time_step = 0
        self.anim_frame = 0
        self.sim_running = True
        self.current_fire_grid = None
        self.sim_status = f"Playing — {len(self.fire_grids)} steps"
        print(f"[App] Playing cached simulation ({len(self.fire_grids)} steps)")

    def _run_simulation(self):
        if self.ignition_cell_id is None:
            return
        self.sim_running = False
        self.fire_grids = []
        self.time_step = 0
        self.anim_frame = 0
        self.current_fire_grid = None
        grids = self.sim_bridge.run_simulation(
            ignition_cells=[self.ignition_cell_id],
            weather_params=self.weather_params,
        )
        if grids:
            self.fire_grids = grids
            self.sim_running = True
            self.sim_status = f"Simulating — {len(grids)} steps"
            print(f"[App] Simulation complete: {len(grids)} steps")
        else:
            self.sim_status = "Simulation failed. Check C++ build."

    def _reset_simulation(self):
        self.sim_running = False
        self.fire_grids = []
        self.current_fire_grid = None
        self.ignition_point = None
        self.ignition_cell_id = None
        self.time_step = 0
        self.anim_frame = 0
        if self.terrain_captured:
            self.sim_status = "Click to ignite, F to precompute, P to play."
        else:
            self.sim_status = "Press SPACE to capture terrain"

    def _set_wind_direction(self, direction):
        if direction in config.WIND_DIRECTIONS:
            self.weather_params["WD"] = config.WIND_DIRECTIONS[direction]
            self.sim_status = f"Wind: {direction} ({self.weather_params['WD']}°)"
            if self.ignition_cell_id and self.terrain_captured:
                self._run_simulation()

    def _adjust_wind_speed(self, delta):
        ws = max(0, min(100, self.weather_params.get("WS", 20) + delta))
        self.weather_params["WS"] = ws
        self.sim_status = f"Wind speed: {ws} km/h"
        if self.ignition_cell_id and self.terrain_captured:
            self._run_simulation()

    def _advance_fire(self):
        if not self.sim_running or not self.fire_grids:
            return

        # Calculate logical step
        self.time_step = self.anim_frame // self.frames_per_step
        
        # Update HUD stats (Time and Burn %)
        # Each grid frame corresponds to one Weather Period in Cell2Fire,
        # which is 60 minutes by default.
        total_hours = self.time_step  # Step index = number of elapsed hours
        days = total_hours // 24
        hrs = total_hours % 24
        if days > 0:
            self.sim_time_str = f"{days} Day{'s' if days > 1 else ''} {hrs:02d} hrs elapsed"
        else:
            self.sim_time_str = f"{hrs:02d} hrs elapsed"
        
        # Burn percentage
        if self.current_fire_grid is not None and self._total_fuel_cells > 0:
            burned_cells = np.count_nonzero(self.current_fire_grid >= 1)
            self.burn_pct = (burned_cells / self._total_fuel_cells) * 100
        
        if self.paused:
            return # Skip animation frame advancing if paused

        if self.time_step < len(self.fire_grids) - 1:
            self.current_fire_grid = self.fire_grids[self.time_step]
            self.next_fire_grid = self.fire_grids[self.time_step + 1]
            self.fire_blend = (self.anim_frame % self.frames_per_step) / float(self.frames_per_step)
            self.anim_frame += 1
            
        elif self.time_step < len(self.fire_grids):
            self.current_fire_grid = self.fire_grids[self.time_step]
            self.next_fire_grid = None
            self.fire_blend = 0.0
            self.anim_frame += 1
            
        else:
            self.time_step = len(self.fire_grids) - 1
            self.current_fire_grid = self.fire_grids[-1]
            self.next_fire_grid = None
            self.fire_blend = 0.0
            self.sim_status = f"Complete — {len(self.fire_grids)} steps"

    def _draw_firebreak_line(self, r1, c1, r2, c2):
        """Draws a 1-cell wide, 4-connected firebreak line (prevents diagonal leaks)."""
        if self.fuel_grid is None:
            return
            
        # Use a 4-connected stepping algorithm (Manhattan steps)
        # to ensure fire cannot jump through diagonal corners.
        r, c = r1, c1
        dr = abs(r2 - r1)
        dc = abs(c2 - c1)
        sr = 1 if r1 < r2 else -1
        sc = 1 if c1 < c2 else -1
        err = dr - dc

        while True:
            # Mark current cell
            if 0 <= r < config.SIM_ROWS and 0 <= c < config.SIM_COLS:
                if self.fuel_grid[r, c] != 102:
                    self.fuel_grid[r, c] = 103
            
            if r == r2 and c == c2:
                break
            
            e2 = 2 * err
            # Step in rows first, then cols (preventing diagonal leap)
            if e2 > -dc:
                err -= dc
                r += sr
                # Intermediate step to close the diagonal corner
                if 0 <= r < config.SIM_ROWS and 0 <= c < config.SIM_COLS:
                    if self.fuel_grid[r, c] != 102:
                        self.fuel_grid[r, c] = 103

            if r == r2 and c == c2:
                break
                
            if e2 < dr:
                err += dr
                c += sc
                # Final step of this segment
                if 0 <= r < config.SIM_ROWS and 0 <= c < config.SIM_COLS:
                    if self.fuel_grid[r, c] != 102:
                        self.fuel_grid[r, c] = 103

        # We no longer write to disk here. 
        # File I/O is expensive and causes freezes in the WoZ console during drawing.
        # Forest.asc is now updated ONLY when simulation starts or precomputes.

    def _sync_woz_state(self):
        """Export established firebreak coordinates to the WoZ operator console."""
        if self.fuel_grid is None:
            return
        
        rows, cols = np.where(self.fuel_grid == 103)
        firebreaks = list(zip(rows.tolist(), cols.tolist()))
        write_state({
            "firebreaks": firebreaks,
            "show_grid": self.show_projection_grid,
            "paused": self.paused,
            "show_hud": self.show_hud_text,
            "burn_pct": self.burn_pct,
            "sim_time": self.sim_time_str,
            "status": self.sim_status
        })

    # ── Lifecycle ───────────────────────────────────────────

    def on_resize(self, width, height):
        if self.fullscreen:
            self.flip_canvas()
            return pyglet.event.EVENT_HANDLED
        return super().on_resize(width, height)

    def _cleanup(self):
        print("[App] Shutting down...")
        self.kinect.cleanup()
        self.sim_bridge.cleanup_all()
        print("[App] Goodbye.")

    def run(self):
        pyglet.app.run(1 / self.fps)


def main():
    """Entry point for the AR Sandbox application."""
    app = Cell2FireSandbox(force_windowed=True, fps=30, screen_id=0)
    app.run()


if __name__ == "__main__":
    main()
