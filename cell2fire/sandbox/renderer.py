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
    from matplotlib.colors import LightSource, LinearSegmentedColormap
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
            # Build a custom colormap exactly matching config.py biomes!
            colors = []
            for upper_pct, grid_val, _ in config.FUEL_BANDS:
                r, g, b = config.FUEL_COLORS[grid_val]
                colors.append((r / 255.0, g / 255.0, b / 255.0))
            self.custom_cmap = LinearSegmentedColormap.from_list("custom_biomes", colors)
        else:
            self.lightsource = None
            self.custom_cmap = None

        self._cached_terrain = None
        self._cached_hash = None

    # ── Terrain ──────────────────────────────────────────────

    def generate_terrain_image(self, elevation, fuel_grid=None):
        """Generate AR Sandbox-style hillshade terrain as RGB numpy array.

        Returns:
            np.ndarray of shape (height, width, 3) uint8 RGB.
        """
        elev_hash = hash(elevation.tobytes())
        fuel_hash = hash(fuel_grid.tobytes()) if fuel_grid is not None else 0
        state_hash = hash((elev_hash, fuel_hash))
        
        if self._cached_terrain is not None and state_hash == getattr(self, "_cached_hash", None):
            return self._cached_terrain.copy()

        if HAS_CV2 and HAS_MATPLOTLIB:
            elev_hires = cv2.resize(
                elevation, (self.width, self.height),
                interpolation=cv2.INTER_CUBIC,
            )
            rgba = self.lightsource.shade(
                elev_hires, cmap=self.custom_cmap,
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
        self._cached_hash = state_hash
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

    def generate_fire_overlay(self, fire_grid, next_fire_grid=None, blend=0.0, frame=0):
        """Generate smooth fire RGBA overlay at display resolution with cross-fading.

        Returns:
            np.ndarray of shape (height, width, 4) uint8 RGBA.
        """
        if not HAS_CV2:
            return self._fire_fallback(fire_grid)

        burning_curr = (fire_grid == 1).astype(np.float32)
        burned_curr = (fire_grid == 2).astype(np.float32)

        if next_fire_grid is not None and blend > 0:
            burning_next = (next_fire_grid == 1).astype(np.float32)
            burned_next = (next_fire_grid == 2).astype(np.float32)
            
            burning = burning_curr * (1.0 - blend) + burning_next * blend
            burned = burned_curr * (1.0 - blend) + burned_next * blend
        else:
            burning = burning_curr
            burned = burned_curr

        # Upscale with smooth interpolation + Gaussian blur (Linear prevents ringing artifacts)
        ks = max(int(self.cell_w * 0.8) | 1, 3)
        burn_hi = np.clip(cv2.GaussianBlur(
            cv2.resize(burning, (self.width, self.height), interpolation=cv2.INTER_LINEAR),
            (ks, ks), 0), 0, 1)
        burned_hi = np.clip(cv2.GaussianBlur(
            cv2.resize(burned, (self.width, self.height), interpolation=cv2.INTER_LINEAR),
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

        r_f, g_f, b_f = config.COLOR_BURNING[0]   # Base dark flame
        r_c, g_c, b_c = config.COLOR_BURNING[2]   # Bright core flame
        r_b, g_b, b_b = getattr(config, 'COLOR_BURNED', (20, 20, 20)) # Burned charcoal

        # Calculate floating-point colors and alphas
        fire_r = (r_f + (r_c - r_f) * noise).astype(np.float32)
        fire_g = (g_f + (g_c - g_f) * noise).astype(np.float32)
        fire_b = (b_f + (b_c - b_f) * noise).astype(np.float32)
        fire_a = np.clip(burn_hi * 255.0, 0, 255).astype(np.float32) / 255.0

        char_r = np.full_like(fire_r, r_b)
        char_g = np.full_like(fire_g, g_b)
        char_b = np.full_like(fire_b, b_b)
        char_a = np.clip(burned_hi * 230.0, 0, 255).astype(np.float32) / 255.0

        # Mathematically stack the Fire layer ON TOP of the Charcoal layer
        # so the edges of the flame fade into charcoal, not into bright rock.
        out_a = fire_a + char_a * (1.0 - fire_a)
        
        # Prevent divide-by-zero where both alphas are perfectly 0
        safe_a = np.where(out_a > 0.001, out_a, 1.0)
        
        out_r = (fire_r * fire_a + char_r * char_a * (1.0 - fire_a)) / safe_a
        out_g = (fire_g * fire_a + char_g * char_a * (1.0 - fire_a)) / safe_a
        out_b = (fire_b * fire_a + char_b * char_a * (1.0 - fire_a)) / safe_a

        overlay[:, :, 0] = np.clip(out_r, 0, 255).astype(np.uint8)
        overlay[:, :, 1] = np.clip(out_g, 0, 255).astype(np.uint8)
        overlay[:, :, 2] = np.clip(out_b, 0, 255).astype(np.uint8)
        overlay[:, :, 3] = np.clip(out_a * 255.0, 0, 255).astype(np.uint8)

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

    def composite(self, terrain_rgb, fire_rgba=None, ignition_point=None, show_marker=False, fuel_grid=None, frame=0):
        """Alpha-blend fire overlay onto terrain, optionally draw ignition marker and firebreaks.

        Returns:
            np.ndarray of shape (height, width, 3) uint8 RGB.
        """
        result = terrain_rgb.copy()
        
        # 1. Overlay Firebreaks (Config.FUEL_FIREBREAK) as Black with pulsing/glowing red/orange edge effect
        if fuel_grid is not None and HAS_CV2:
            break_mask = (fuel_grid == config.FUEL_FIREBREAK).astype(np.float32)
            if np.any(break_mask > 0):
                # Scale mask up
                mask_hi = cv2.resize(break_mask, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
                
                # Base black color
                base_color = np.array([10, 10, 10], dtype=np.float32)
                
                # Glowing border 
                edge_mask = cv2.GaussianBlur(mask_hi, (15, 15), 0) - mask_hi
                edge_mask = np.clip(edge_mask * 3.0, 0, 1)
                
                # Pulse over time
                pulse = (np.sin(frame * 0.1) * 0.5 + 0.5)
                glow_color = np.array([255, 60 + pulse * 40, pulse * 20], dtype=np.float32)
                
                # Blend black body
                for ch in range(3):
                    result[:, :, ch] = np.where(mask_hi > 0, base_color[ch], result[:, :, ch])
                
                # Add glowing edges
                for ch in range(3):
                    result[:, :, ch] = np.minimum(255, result[:, :, ch] + glow_color[ch] * edge_mask)

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
