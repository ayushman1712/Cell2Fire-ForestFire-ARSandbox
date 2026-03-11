# coding: utf-8
"""
Pygame-based renderer for the AR Sandbox fire simulation.
Renders terrain, fire state, wind indicator, and HUD overlay.
"""
import math
import numpy as np

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

from . import config


class SandboxRenderer:
    """Renders the fire simulation state onto a Pygame display surface.

    Layers (back to front):
        1. Terrain biome coloring (from fuel grid)
        2. Elevation contour lines
        3. Fire state overlay (burning/burned)
        4. Wind direction indicator
        5. HUD (weather info, simulation time)
    """

    def __init__(
        self,
        width: int = None,
        height: int = None,
        sim_rows: int = None,
        sim_cols: int = None,
    ):
        if not HAS_PYGAME:
            raise ImportError("pygame is required for the sandbox renderer")

        self.width = width or config.PROJECTOR_WIDTH
        self.height = height or config.PROJECTOR_HEIGHT
        self.sim_rows = sim_rows or config.SIM_ROWS
        self.sim_cols = sim_cols or config.SIM_COLS

        # Calculate cell display size (pixels per simulation cell)
        self.cell_w = self.width / self.sim_cols
        self.cell_h = self.height / self.sim_rows

        # Initialize Pygame display
        pygame.init()
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Cell2Fire AR Sandbox")
        self.clock = pygame.time.Clock()

        # Font for HUD
        pygame.font.init()
        self.font_large = pygame.font.SysFont("Consolas", 18)
        self.font_small = pygame.font.SysFont("Consolas", 14)

        # Pre-allocate surfaces
        self.terrain_surface = pygame.Surface((self.width, self.height))
        self.fire_surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA
        )

    def render_terrain(self, fuel_grid: np.ndarray, elevation: np.ndarray = None):
        """Draw terrain biome coloring from the fuel type grid.

        Args:
            fuel_grid: 2D int array (rows × cols) with FBP fuel type codes.
            elevation: Optional 2D float array for contour lines.
        """
        self.terrain_surface.fill(config.COLOR_BACKGROUND)

        for r in range(self.sim_rows):
            for c in range(self.sim_cols):
                fuel_val = int(fuel_grid[r, c])
                color = config.FUEL_COLORS.get(fuel_val, config.COLOR_CONIFER)

                rect = pygame.Rect(
                    int(c * self.cell_w),
                    int(r * self.cell_h),
                    int(self.cell_w) + 1,
                    int(self.cell_h) + 1,
                )
                pygame.draw.rect(self.terrain_surface, color, rect)

        # Draw elevation contour lines if provided
        if elevation is not None:
            self._draw_contours(elevation)

    def _draw_contours(self, elevation: np.ndarray, n_contours: int = 8):
        """Draw subtle contour lines on the terrain surface."""
        elev_min = elevation.min()
        elev_max = elevation.max()
        if elev_max - elev_min < 1:
            return

        contour_step = (elev_max - elev_min) / n_contours
        contour_color = (255, 255, 255, 40)  # semi-transparent white

        contour_surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA
        )

        for level in range(1, n_contours):
            threshold = elev_min + level * contour_step

            for r in range(self.sim_rows - 1):
                for c in range(self.sim_cols - 1):
                    # Check if contour crosses this cell
                    vals = [
                        elevation[r, c],
                        elevation[r, c + 1],
                        elevation[r + 1, c],
                        elevation[r + 1, c + 1],
                    ]
                    crosses = (min(vals) <= threshold <= max(vals))
                    if crosses:
                        cx = int((c + 0.5) * self.cell_w)
                        cy = int((r + 0.5) * self.cell_h)
                        pygame.draw.circle(
                            contour_surface, contour_color, (cx, cy), 1
                        )

        self.terrain_surface.blit(contour_surface, (0, 0))

    def render_fire_state(self, fire_grid: np.ndarray, frame: int):
        """Draw the fire overlay on top of terrain.

        Args:
            fire_grid: 2D int array (rows × cols) with states:
                0 = unburned, 1 = burning, 2 = burned out
            frame: Current frame number (for flickering animation).
        """
        self.fire_surface.fill((0, 0, 0, 0))  # clear transparent

        for r in range(self.sim_rows):
            for c in range(self.sim_cols):
                state = int(fire_grid[r, c])

                if state == 0:
                    continue  # unburned = transparent

                rect = pygame.Rect(
                    int(c * self.cell_w),
                    int(r * self.cell_h),
                    int(self.cell_w) + 1,
                    int(self.cell_h) + 1,
                )

                if state == 1:  # burning
                    # Flickering fire color
                    idx = (frame + r * 3 + c * 7) % len(config.COLOR_BURNING)
                    color = config.COLOR_BURNING[idx]
                    alpha = 200 + int(40 * math.sin(frame * 0.3 + r + c))
                    alpha = max(160, min(255, alpha))
                    pygame.draw.rect(
                        self.fire_surface, (*color, alpha), rect
                    )

                elif state == 2:  # burned out
                    pygame.draw.rect(
                        self.fire_surface, (*config.COLOR_BURNED, 180), rect
                    )

    def render_ignition_marker(self, row: int, col: int):
        """Draw a pulsing ignition marker at the given grid cell."""
        cx = int((col + 0.5) * self.cell_w)
        cy = int((row + 0.5) * self.cell_h)
        radius = int(max(self.cell_w, self.cell_h) * 0.8)

        # Draw crosshair
        pygame.draw.circle(self.screen, (255, 255, 0), (cx, cy), radius, 2)
        pygame.draw.line(
            self.screen, (255, 255, 0),
            (cx - radius, cy), (cx + radius, cy), 1
        )
        pygame.draw.line(
            self.screen, (255, 255, 0),
            (cx, cy - radius), (cx, cy + radius), 1
        )

    def render_wind_indicator(self, direction_deg: float, speed: float):
        """Draw a wind direction arrow in the top-right corner.

        Args:
            direction_deg: Wind direction in compass degrees (0=N, 90=E, ...).
            speed: Wind speed in km/h.
        """
        # Arrow center position (top-right corner)
        cx = self.width - 60
        cy = 60
        arrow_len = 35

        # Convert compass bearing to math angle (0° = up/north)
        angle_rad = math.radians(direction_deg)
        dx = arrow_len * math.sin(angle_rad)
        dy = -arrow_len * math.cos(angle_rad)  # negative because y increases down

        # Arrow tip
        tip_x = cx + dx
        tip_y = cy + dy

        # Arrow base
        base_x = cx - dx * 0.3
        base_y = cy - dy * 0.3

        # Draw arrow
        pygame.draw.line(
            self.screen, config.COLOR_WIND_ARROW,
            (int(base_x), int(base_y)), (int(tip_x), int(tip_y)), 3
        )

        # Arrowhead
        head_len = 10
        left_angle = angle_rad + math.radians(150)
        right_angle = angle_rad - math.radians(150)

        left_x = tip_x + head_len * math.sin(left_angle)
        left_y = tip_y - head_len * math.cos(left_angle)
        right_x = tip_x + head_len * math.sin(right_angle)
        right_y = tip_y - head_len * math.cos(right_angle)

        pygame.draw.polygon(
            self.screen, config.COLOR_WIND_ARROW,
            [(int(tip_x), int(tip_y)),
             (int(left_x), int(left_y)),
             (int(right_x), int(right_y))],
        )

        # Wind circle background
        pygame.draw.circle(
            self.screen, (40, 40, 60), (cx, cy), 50, 2
        )

        # Speed label
        speed_text = self.font_small.render(f"{speed:.0f} km/h", True, config.COLOR_UI_TEXT)
        self.screen.blit(speed_text, (cx - speed_text.get_width() // 2, cy + 42))

        # "WIND" label
        label = self.font_small.render("WIND", True, config.COLOR_UI_TEXT)
        self.screen.blit(label, (cx - label.get_width() // 2, cy - 50))

    def render_hud(self, weather_params: dict, time_step: int, sim_status: str = ""):
        """Draw a HUD with current simulation info.

        Args:
            weather_params: Dict with current weather parameters.
            time_step: Current simulation time step index.
            sim_status: Status string to display.
        """
        y = 10
        x = 10
        line_height = 20

        lines = [
            f"Step: {time_step}",
            f"Temp: {weather_params.get('TMP', '?')}°C",
            f"RH: {weather_params.get('RH', '?')}%",
        ]

        if sim_status:
            lines.append(sim_status)

        # Background panel
        panel_h = len(lines) * line_height + 10
        panel = pygame.Surface((180, panel_h), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 120))
        self.screen.blit(panel, (x - 5, y - 5))

        for line in lines:
            text_surf = self.font_small.render(line, True, config.COLOR_UI_TEXT)
            self.screen.blit(text_surf, (x, y))
            y += line_height

    def render_controls_help(self):
        """Draw controls help at the bottom of the screen."""
        help_lines = [
            "SPACE: Capture Terrain | Click: Ignite | Arrows: Wind Dir",
            "+/-: Wind Speed | R: Reset | ESC: Quit",
        ]
        y = self.height - 40
        for line in help_lines:
            text_surf = self.font_small.render(line, True, (180, 180, 180))
            self.screen.blit(
                text_surf,
                (self.width // 2 - text_surf.get_width() // 2, y),
            )
            y += 18

    def update(
        self,
        fuel_grid: np.ndarray,
        elevation: np.ndarray,
        fire_grid: np.ndarray,
        weather_params: dict,
        frame: int,
        time_step: int,
        sim_status: str = "",
        ignition_point: tuple = None,
    ):
        """Composite all layers and update the display.

        Args:
            fuel_grid: 2D int array with fuel types.
            elevation: 2D float array with elevation.
            fire_grid: 2D int array with fire states (or None if no fire).
            weather_params: Current weather dict.
            frame: Animation frame counter.
            time_step: Simulation time step.
            sim_status: Status string.
            ignition_point: Optional (row, col) tuple for ignition marker.
        """
        # Layer 1: Terrain
        self.render_terrain(fuel_grid, elevation)
        self.screen.blit(self.terrain_surface, (0, 0))

        # Layer 2: Fire overlay
        if fire_grid is not None:
            self.render_fire_state(fire_grid, frame)
            self.screen.blit(self.fire_surface, (0, 0))

        # Layer 3: Ignition marker
        if ignition_point is not None:
            self.render_ignition_marker(*ignition_point)

        # Layer 4: Wind indicator
        wind_deg = weather_params.get("WD", 270)
        wind_spd = weather_params.get("WS", 20)
        self.render_wind_indicator(wind_deg, wind_spd)

        # Layer 5: HUD
        self.render_hud(weather_params, time_step, sim_status)

        # Layer 6: Controls help
        self.render_controls_help()

        pygame.display.flip()

    def tick(self, fps: int = None):
        """Cap the frame rate."""
        self.clock.tick(fps or config.TARGET_FPS)

    def cleanup(self):
        """Shutdown Pygame."""
        pygame.quit()
