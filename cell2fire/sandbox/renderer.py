# coding: utf-8
"""
Image generation engine for the AR Sandbox fire simulation.
Produces numpy arrays (no display framework dependency).
"""
import math
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from matplotlib.colors import LightSource
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

from . import config


class SandboxRenderer:
    """Generates terrain and fire images as numpy arrays.

    Pure image generator — no Pyglet/Pygame dependency.
    The app layer converts these arrays to display textures.
    """

    def __init__(self, display_width=None, display_height=None):
        self.width = display_width or config.PROJECTOR_WIDTH
        self.height = display_height or config.PROJECTOR_HEIGHT
        self.sim_rows = config.SIM_ROWS
        self.sim_cols = config.SIM_COLS
        self.cell_w = self.width / self.sim_cols
        self.cell_h = self.height / self.sim_rows

        if HAS_MATPLOTLIB:
            self.lightsource = LightSource(
                azdeg=config.HILLSHADE_AZIMUTH,
                altdeg=config.HILLSHADE_ALTITUDE,
            )
        else:
            self.lightsource = None

        self._cached_terrain = None
        self._cached_hash = None

    # ── Terrain ──────────────────────────────────────────────

    def generate_terrain_image(self, elevation, fuel_grid=None):
        """Generate AR Sandbox-style hillshade terrain as RGB numpy array.

        Returns:
            np.ndarray of shape (height, width, 3) uint8 RGB.
        """
        elev_hash = hash(elevation.tobytes())
        if self._cached_terrain is not None and elev_hash == self._cached_hash:
            return self._cached_terrain.copy()

        if HAS_CV2 and HAS_MATPLOTLIB:
            elev_hires = cv2.resize(
                elevation, (self.width, self.height),
                interpolation=cv2.INTER_CUBIC,
            )
            rgba = self.lightsource.shade(
                elev_hires, cmap=plt.cm.gist_earth,
                vert_exag=config.HILLSHADE_VERT_EXAG,
                blend_mode=config.HILLSHADE_BLEND_MODE,
                dx=1, dy=1,
            )
            rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
            self._draw_contours(rgb, elev_hires)
        else:
            e_norm = (elevation - elevation.min()) / max(elevation.max() - elevation.min(), 1)
            rgb = np.zeros((self.sim_rows, self.sim_cols, 3), dtype=np.uint8)
            rgb[:, :, 1] = (80 + e_norm * 120).astype(np.uint8)
            rgb[:, :, 0] = (20 + e_norm * 40).astype(np.uint8)
            if HAS_CV2:
                rgb = cv2.resize(rgb, (self.width, self.height), interpolation=cv2.INTER_NEAREST)

        # Overlay water cells
        if fuel_grid is not None and HAS_CV2:
            water = cv2.resize(
                (fuel_grid == 102).astype(np.float32),
                (self.width, self.height), interpolation=cv2.INTER_CUBIC,
            )
            water = np.clip(water, 0, 1)
            wc = np.array(config.COLOR_WATER, dtype=np.float32)
            for ch in range(3):
                rgb[:, :, ch] = (rgb[:, :, ch] * (1 - water * 0.5) + wc[ch] * water * 0.5).astype(np.uint8)

        self._cached_terrain = rgb.copy()
        self._cached_hash = elev_hash
        return rgb

    def _draw_contours(self, image, elevation):
        """Draw elevation contour lines onto an RGB image."""
        emin, emax = elevation.min(), elevation.max()
        if emax - emin < 1:
            return
        n = config.CONTOUR_LEVELS
        norm = ((elevation - emin) / (emax - emin) * 255).astype(np.uint8)
        cr, cg, cb = config.CONTOUR_COLOR[:3]
        alpha = config.CONTOUR_COLOR[3] / 255.0
        for i in range(1, n):
            _, binary = cv2.threshold(norm, int(i * 255 / n), 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            overlay = image.copy()
            cv2.drawContours(overlay, contours, -1, (cr, cg, cb), 1, cv2.LINE_AA)
            cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)

    # ── Fire Overlay ─────────────────────────────────────────

    def generate_fire_overlay(self, fire_grid, frame):
        """Generate smooth fire RGBA overlay at display resolution.

        Returns:
            np.ndarray of shape (height, width, 4) uint8 RGBA.
        """
        if not HAS_CV2:
            return self._fire_fallback(fire_grid)

        burning = (fire_grid == 1).astype(np.float32)
        burned = (fire_grid == 2).astype(np.float32)

        # Upscale with smooth interpolation + Gaussian blur
        ks = max(int(self.cell_w * 0.8) | 1, 3)
        burn_hi = np.clip(cv2.GaussianBlur(
            cv2.resize(burning, (self.width, self.height), interpolation=cv2.INTER_CUBIC),
            (ks, ks), 0), 0, 1)
        burned_hi = np.clip(cv2.GaussianBlur(
            cv2.resize(burned, (self.width, self.height), interpolation=cv2.INTER_CUBIC),
            (ks, ks), 0), 0, 1)

        overlay = np.zeros((self.height, self.width, 4), dtype=np.uint8)

        # Animated flicker
        phase = frame * 0.15
        y = np.arange(self.height).reshape(-1, 1).astype(np.float32)
        x = np.arange(self.width).reshape(1, -1).astype(np.float32)
        noise = np.clip(
            np.sin(phase + y * 0.08 + x * 0.05) * 0.3
            + np.sin(phase * 1.7 + y * 0.12 - x * 0.09) * 0.2
            + 0.5, 0, 1
        )

        intensity = burn_hi * noise
        overlay[:, :, 0] = (intensity * 255).astype(np.uint8)
        overlay[:, :, 1] = (intensity * 120 * noise).astype(np.uint8)
        overlay[:, :, 2] = (intensity * 20).astype(np.uint8)
        overlay[:, :, 3] = (burn_hi * 220).astype(np.uint8)

        # Burned-out char (only where NOT actively burning)
        no_burn = burn_hi < 0.05
        overlay[:, :, 0] = np.where(no_burn, np.maximum(overlay[:, :, 0], (burned_hi * 40).astype(np.uint8)), overlay[:, :, 0])
        overlay[:, :, 1] = np.where(no_burn, np.maximum(overlay[:, :, 1], (burned_hi * 35).astype(np.uint8)), overlay[:, :, 1])
        overlay[:, :, 2] = np.where(no_burn, np.maximum(overlay[:, :, 2], (burned_hi * 30).astype(np.uint8)), overlay[:, :, 2])
        overlay[:, :, 3] = np.where(no_burn, np.maximum(overlay[:, :, 3], (burned_hi * 160).astype(np.uint8)), overlay[:, :, 3])

        return overlay

    def _fire_fallback(self, fire_grid):
        """Simple fire overlay without cv2."""
        h, w = self.height, self.width
        overlay = np.zeros((h, w, 4), dtype=np.uint8)
        for r in range(self.sim_rows):
            for c in range(self.sim_cols):
                state = int(fire_grid[r, c])
                if state == 0:
                    continue
                y1 = int(r * self.cell_h)
                y2 = int((r + 1) * self.cell_h)
                x1 = int(c * self.cell_w)
                x2 = int((c + 1) * self.cell_w)
                if state == 1:
                    overlay[y1:y2, x1:x2] = [255, 100, 0, 200]
                elif state == 2:
                    overlay[y1:y2, x1:x2] = [40, 35, 30, 160]
        return overlay

    # ── Compositing ──────────────────────────────────────────

    def composite(self, terrain_rgb, fire_rgba=None, ignition_point=None, show_marker=False):
        """Alpha-blend fire overlay onto terrain, optionally draw ignition marker.

        Returns:
            np.ndarray of shape (height, width, 3) uint8 RGB.
        """
        result = terrain_rgb.copy()

        if fire_rgba is not None:
            alpha = fire_rgba[:, :, 3:4].astype(np.float32) / 255.0
            fire_rgb = fire_rgba[:, :, :3].astype(np.float32)
            result = (result.astype(np.float32) * (1 - alpha) + fire_rgb * alpha).astype(np.uint8)

        if show_marker and ignition_point is not None and HAS_CV2:
            row, col = ignition_point
            cx = int((col + 0.5) * self.cell_w)
            cy = int((row + 0.5) * self.cell_h)
            r = int(max(self.cell_w, self.cell_h))
            cv2.circle(result, (cx, cy), r, (255, 255, 0), 2, cv2.LINE_AA)
            cv2.line(result, (cx - r, cy), (cx + r, cy), (255, 255, 0), 1, cv2.LINE_AA)
            cv2.line(result, (cx, cy - r), (cx, cy + r), (255, 255, 0), 1, cv2.LINE_AA)

        return result
