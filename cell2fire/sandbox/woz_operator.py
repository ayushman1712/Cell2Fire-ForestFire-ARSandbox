# coding: utf-8
"""
Wizard-of-Oz Operator Console for AR Sandbox Fire Simulation.

Shows a live view of the Kinect's cropped ROI (the exact region used for
depth-to-terrain mapping). The operator clicks on this window to set the
fire ignition point — the coordinates are forwarded to the running Pyglet
sandbox app via a shared JSON command file.

This creates the illusion for the end-user that a physical "fire token"
was detected automatically, when in reality the wizard clicked it.

Usage:
    python -m cell2fire.sandbox.woz_operator
"""
import os
import sys
import json
import time
import numpy as np
import cv2

# Ensure the package is importable
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from cell2fire.sandbox import config

# Try to import Kinect
try:
    from pykinect2 import PyKinectV2, PyKinectRuntime
    HAS_PYKINECT = True
except Exception:
    HAS_PYKINECT = False

# ═══════════════════════════════════════════════════════════
# IPC: Shared command file
# ═══════════════════════════════════════════════════════════
WOZ_COMMAND_FILE = os.path.join(
    os.environ.get("TEMP", os.path.join(os.path.expanduser("~"), ".tmp")),
    "cell2fire_woz_command.json",
)
WOZ_STATE_FILE = os.path.join(
    os.environ.get("TEMP", os.path.join(os.path.expanduser("~"), ".tmp")),
    "cell2fire_woz_state.json",
)


def send_command(cmd_dict: dict):
    """Append a command to the shared command file for the sandbox app."""
    cmd_dict["timestamp"] = time.time()
    os.makedirs(os.path.dirname(WOZ_COMMAND_FILE), exist_ok=True)
    
    # Read existing commands
    cmds = []
    if os.path.isfile(WOZ_COMMAND_FILE):
        try:
            with open(WOZ_COMMAND_FILE, "r") as f:
                cmds = json.load(f)
                if not isinstance(cmds, list): cmds = []
        except:
            pass

    cmds.append(cmd_dict)
    
    # Write back
    with open(WOZ_COMMAND_FILE, "w") as f:
        json.dump(cmds, f)
    
    if cmd_dict["type"] == "ignite":
        print(f"[WoZ] Sent ignition command: row={cmd_dict.get('row')}, col={cmd_dict.get('col')}")
    elif cmd_dict["type"] != "firebreak_line": # Don't spam curve segments
        print(f"[WoZ] Sent command: {cmd_dict['type']}")


def read_commands():
    """Read and consume all pending commands (returns list)."""
    if not os.path.isfile(WOZ_COMMAND_FILE):
        return []
    try:
        with open(WOZ_COMMAND_FILE, "r") as f:
            cmds = json.load(f)
        # Consume it so we don't re-read
        os.remove(WOZ_COMMAND_FILE)
        return cmds if isinstance(cmds, list) else []
    except (json.JSONDecodeError, IOError, OSError):
        return []


def read_command():
    """Legacy wrapper for backward compatibility."""
    cmds = read_commands()
    return cmds[0] if cmds else None


def write_state(state_dict: dict):
    """Write the current sandbox state for the operator console."""
    try:
        with open(WOZ_STATE_FILE, "w") as f:
            json.dump(state_dict, f)
    except (IOError, OSError):
        pass


def read_state():
    """Read the current sandbox state (returns dict or None)."""
    if not os.path.isfile(WOZ_STATE_FILE):
        return None
    try:
        with open(WOZ_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


# ═══════════════════════════════════════════════════════════
# Operator Console
# ═══════════════════════════════════════════════════════════

class WizardOfOzConsole:
    """Live Kinect ROI viewer with click-to-ignite functionality.

    Shows the cropped depth region that the terrain generator uses,
    rendered as a colorized depth image. Clicking sets the ignition
    point in simulation grid coordinates.
    """

    WINDOW_NAME = "WoZ Operator - Kinect ROI (Click to Ignite)"
    # Display scale: how much to scale the cropped ROI for comfortable viewing
    DISPLAY_SCALE = 2.5
    PANEL_HEIGHT = 180  # Height of the controls reference at the bottom

    def __init__(self):
        self.kinect = None
        self.has_kinect = False
        self.roi = config.KINECT_ROI
        self.roi_w = self.roi["x2"] - self.roi["x1"]
        self.roi_h = self.roi["y2"] - self.roi["y1"]

        # Scaled display dimensions
        self.display_w = int(self.roi_w * self.DISPLAY_SCALE)
        self.display_h = int(self.roi_h * self.DISPLAY_SCALE)

        # Grid overlay
        self.show_grid = True
        self.last_click = None  # (row, col) in sim grid

        # Firebreak modes
        self.firebreak_mode = False
        self.curve_mode = False
        self.firebreak_clicks = []
        
        # Freehand drawing state
        self.is_dragging = False
        self.last_grid_point = None

        # Persistent state from sandbox app
        self.app_state = {}

        # Initialize Kinect
        if HAS_PYKINECT:
            try:
                self.kinect = PyKinectRuntime.PyKinectRuntime(
                    PyKinectV2.FrameSourceTypes_Depth
                )
                self.has_kinect = True
                print("[WoZ] Kinect v2 initialized.")
            except Exception as e:
                print(f"[WoZ] Kinect init failed: {e}")
        else:
            print("[WoZ] pykinect2 not available. Using fallback depth image.")

        # Mouse callback
        cv2.namedWindow(self.WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.WINDOW_NAME, self._on_mouse)

        print(f"[WoZ] ROI: x=[{self.roi['x1']}:{self.roi['x2']}], "
              f"y=[{self.roi['y1']}:{self.roi['y2']}]  "
              f"({self.roi_w}x{self.roi_h})")
        print(f"[WoZ] Simulation grid: {config.SIM_ROWS}x{config.SIM_COLS}")
        print(f"[WoZ] Display size: {self.display_w}x{self.display_h}")
        print()
        print("=" * 50)
        print("  WIZARD OF OZ OPERATOR CONSOLE")
        print("=" * 50)
        print("  LEFT CLICK  → Set fire ignition point")
        print("  SPACE       → Capture terrain")
        print("  F           → Precompute simulation")
        print("  P           → Play cached simulation")
        print("  W/A/S/D     → Wind direction (N/W/S/E)")
        print("  +/-         → Adjust wind speed")
        print("  < / >       → Slower / Faster fire spread")
        print("  R           → Send reset command")
        print("  G           → Toggle grid overlay")
        print("  B           → Toggle Straight Firebreak Mode")
        print("  C           → Toggle Curved (Freehand) Mode")
        print("  ESC / Q     → Quit")
        print("=" * 50)

    def _on_mouse(self, event, x, y, flags, param):
        """Handle mouse click and drag on the operator window."""
        # Convert display coords → simulation grid coords
        # Since the image is now mirrored to match the grid, we map directly
        grid_col = int(x / self.display_w * config.SIM_COLS)
        grid_row = int(y / self.display_h * config.SIM_ROWS)

        # Clamp to valid range
        grid_row = max(0, min(grid_row, config.SIM_ROWS - 1))
        grid_col = max(0, min(grid_col, config.SIM_COLS - 1))

        if event == cv2.EVENT_LBUTTONDOWN:
            self.is_dragging = True
            self.last_grid_point = (grid_row, grid_col)

            # Standard Ignition
            if not self.firebreak_mode and not self.curve_mode:
                if y < self.display_h:
                    self.last_click = (grid_row, grid_col)
                    send_command({"type": "ignite", "row": grid_row, "col": grid_col})
            
            # Straight Firebreak (first click)
            elif self.firebreak_mode:
                if y < self.display_h:
                    self.firebreak_clicks.append((grid_row, grid_col))
                    if len(self.firebreak_clicks) == 2:
                        r1, c1 = self.firebreak_clicks[0]
                        r2, c2 = self.firebreak_clicks[1]
                        send_command({
                            "type": "firebreak_line",
                            "r1": r1, "c1": c1, "r2": r2, "c2": c2
                        })
                        self.firebreak_clicks.clear()
                    else:
                        print(f"[WoZ] First firebreak point: ({grid_row},{grid_col})")

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.is_dragging and self.curve_mode and y < self.display_h:
                curr_point = (grid_row, grid_col)
                if curr_point != self.last_grid_point:
                    r1, c1 = self.last_grid_point
                    r2, c2 = curr_point
                    send_command({
                        "type": "firebreak_line",
                        "r1": r1, "c1": c1, "r2": r2, "c2": c2
                    })
                    self.last_grid_point = curr_point

        elif event == cv2.EVENT_LBUTTONUP:
            self.is_dragging = False
            self.last_grid_point = None

    def _get_depth_frame(self):
        """Get a raw depth frame from Kinect or fallback."""
        if self.has_kinect and self.kinect is not None:
            if self.kinect.has_new_depth_frame():
                depth = self.kinect.get_last_depth_frame()
                return depth.reshape(
                    (config.KINECT_FRAME_HEIGHT, config.KINECT_FRAME_WIDTH)
                )
        # Fallback: load static depth image
        return self._load_fallback()

    def _load_fallback(self):
        """Load the fallback depth image."""
        path = config.FALLBACK_DEPTH_IMAGE
        if not os.path.isfile(path):
            # Generate synthetic
            h, w = config.KINECT_FRAME_HEIGHT, config.KINECT_FRAME_WIDTH
            y, x = np.mgrid[0:h, 0:w].astype(np.float32)
            cx, cy = 0.5, 0.5
            dist = np.sqrt((x / w - cx) ** 2 + (y / h - cy) ** 2)
            hill = np.clip(1.0 - dist * 2.0, 0, 1)
            rng = np.random.RandomState(42)
            noise = rng.rand(h, w).astype(np.float32) * 0.1
            normalized = 1.0 - (hill * 0.7 + noise * 0.3)
            return (
                config.DEPTH_MIN_MM
                + normalized * (config.DEPTH_MAX_MM - config.DEPTH_MIN_MM)
            ).astype(np.uint16)

        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            return np.zeros(
                (config.KINECT_FRAME_HEIGHT, config.KINECT_FRAME_WIDTH),
                dtype=np.uint16,
            )
        if img.ndim == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.resize(
            img, (config.KINECT_FRAME_WIDTH, config.KINECT_FRAME_HEIGHT)
        )
        if img.dtype != np.uint16:
            img = (
                config.DEPTH_MIN_MM
                + (img / 255.0) * (config.DEPTH_MAX_MM - config.DEPTH_MIN_MM)
            ).astype(np.uint16)
        return img

    def _colorize_depth(self, depth_roi):
        """Colorize using raw Kinect depth range (no custom clamping).

        Normalizes over the actual min/max of the ROI so the full
        depth variation is visible — tokens naturally stand out as
        brighter (closer) objects against the sand.
        """
        d = depth_roi.astype(np.float32)

        # Use the actual range present in the frame
        d_min = np.min(d[d > 0]) if np.any(d > 0) else 0
        d_max = np.max(d)

        # Normalize to 0..255
        d_norm = np.clip((d - d_min) / max(d_max - d_min, 1), 0, 1)
        # Invert: closer = brighter
        d_u8 = ((1.0 - d_norm) * 255).astype(np.uint8)

        # Use COLORMAP_JET — closest to the standard Kinect depth palette
        colored = cv2.applyColorMap(d_u8, cv2.COLORMAP_JET)

        # Zero-depth pixels (invalid) → black
        colored[d == 0] = 0

        return colored

    def _draw_grid_overlay(self, image):
        """Draw the simulation grid lines on the display image."""
        if not self.show_grid:
            return

        h, w = image.shape[:2]
        cell_w = w / config.SIM_COLS
        cell_h = h / config.SIM_ROWS

        # Vertical lines
        for c in range(1, config.SIM_COLS):
            x = int(c * cell_w)
            cv2.line(image, (x, 0), (x, h), (255, 255, 255), 1, cv2.LINE_AA)

        # Horizontal lines
        for r in range(1, config.SIM_ROWS):
            y = int(r * cell_h)
            cv2.line(image, (0, y), (w, y), (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_click_marker(self, image):
        """Draw a crosshair on the last-clicked cell."""
        if self.last_click is None:
            return

        row, col = self.last_click
        h, w = image.shape[:2]
        cell_w = w / config.SIM_COLS
        cell_h = h / config.SIM_ROWS

        # The image is already mirrored to match the grid
        disp_col = col
        disp_row = row

        cx = int((disp_col + 0.5) * cell_w)
        cy = int((disp_row + 0.5) * cell_h)

        # Pulsing radius for visibility
        r = int(cell_w * 0.8)

        # Bright yellow crosshair
        cv2.circle(image, (cx, cy), r, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.line(image, (cx - r - 5, cy), (cx + r + 5, cy),
                 (0, 255, 255), 1, cv2.LINE_AA)
        cv2.line(image, (cx, cy - r - 5), (cx, cy + r + 5),
                 (0, 255, 255), 1, cv2.LINE_AA)

        # Label
        label = f"FIRE ({row},{col})"
        cv2.putText(image, label, (cx + r + 5, cy - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1,
                    cv2.LINE_AA)

    def _draw_firebreak_markers(self, image):
        """Draw markers for the first click and mode status while in firebreak mode."""
        if not self.firebreak_mode:
            return

        h, w = image.shape[:2]
        cell_w = w / config.SIM_COLS
        cell_h = h / config.SIM_ROWS

        cv2.putText(image, "FIREBREAK MODE [ON]", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)

        for (row, col) in self.firebreak_clicks:
            cx = int((col + 0.5) * cell_w)
            cy = int((row + 0.5) * cell_h)
            cv2.circle(image, (cx, cy), 15, (0, 0, 255), -1)

    def _draw_persistent_firebreaks(self, image):
        """Draw firebreaks already established in the sandbox app."""
        firebreaks = self.app_state.get("firebreaks", [])
        if not firebreaks:
            return

        h, w = image.shape[:2]
        cell_w = w / config.SIM_COLS
        cell_h = h / config.SIM_ROWS

        for (row, col) in firebreaks:
            cx = int((col + 0.5) * cell_w)
            cy = int((row + 0.5) * cell_h)
            # Use same brown color but small square to represent established firebreak
            cv2.rectangle(image, 
                          (int(col * cell_w) + 1, int(row * cell_h) + 1),
                          (int((col + 1) * cell_w) - 1, int((row + 1) * cell_h) - 1),
                          (50, 50, 100), -1)  # BGR match for COLOR_FIREBREAK (100,50,50)

    def _draw_status_bar(self, image):
        """Draw a status bar at the bottom of the display."""
        h, w = image.shape[:2]
        bar_h = 30
        cv2.rectangle(image, (0, h - bar_h), (w, h), (30, 30, 30), -1)

        status = "LIVE KINECT" if self.has_kinect else "FALLBACK IMAGE"
        grid_text = f"Grid: {config.SIM_ROWS}x{config.SIM_COLS}"
        click_text = (
            f"Last: ({self.last_click[0]},{self.last_click[1]})"
            if self.last_click
            else "Ready"
        )
        if self.curve_mode:
            mode_text = "| MODE: CURVED BREAK"
        elif self.firebreak_mode:
            mode_text = "| MODE: STRAIGHT BREAK"
        else:
            mode_text = "| MODE: IGNITION"

        cv2.putText(image, f"[{status}]  {grid_text}  |  {click_text}  {mode_text}",
                    (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (200, 200, 200), 1, cv2.LINE_AA)

        # Grid toggle indicator
        g_text = "[G]rid: ON" if self.show_grid else "[G]rid: OFF"
        cv2.putText(image, g_text, (w - 120, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1,
                    cv2.LINE_AA)

    def _draw_controls_panel(self):
        """Build a panel image showing all operator controls."""
        panel = np.zeros((self.PANEL_HEIGHT, self.display_w, 3), dtype=np.uint8)
        panel[:] = (40, 40, 40) # Dark grey background

        # Header
        cv2.putText(panel, "OPERATOR CONTROLS", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
        
        cv2.line(panel, (20, 40), (200, 40), (0, 255, 255), 1)

        # Labels
        controls = [
            ("L-CLICK", "Ignite Fire"),
            ("SPACE", "Capture Depth"),
            ("B", "Straight Break"),
            ("C", "Curved Break"),
            ("F", "Precompute"),
            ("P", "Play Cache"),
            ("R", "Reset Mode"),
            ("G", "Grid Toggle"),
            ("W/A/S/D", "Wind Direction"),
            ("+ / -", "Wind Speed"),
            ("< / >", "Visual Speed"),
            ("ESC / Q", "Quit Console")
        ]

        # Two-column layout
        col1_x = 30
        col2_x = self.display_w // 2 + 30
        row_y = 70
        dy = 25

        for i, (key_name, desc) in enumerate(controls):
            cx = col1_x if i < 6 else col2_x
            cy = row_y + (i % 6) * dy
            
            # Key pill
            cv2.putText(panel, f"[{key_name}]", (cx, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 255), 1, cv2.LINE_AA)
            # Description
            cv2.putText(panel, f": {desc}", (cx + 80, cy),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

        return panel

    def run(self):
        """Main loop: capture, display, handle input."""
        print("[WoZ] Starting operator console... Press ESC or Q to quit.")

        last_frame = None

        while True:
            # Grab depth
            depth = self._get_depth_frame()
            if depth is not None:
                last_frame = depth
            elif last_frame is not None:
                depth = last_frame
            else:
                # No frame at all yet — show placeholder
                placeholder = np.zeros(
                    (self.display_h, self.display_w, 3), dtype=np.uint8
                )
                cv2.putText(
                    placeholder, "Waiting for Kinect...",
                    (20, self.display_h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
                )
                cv2.imshow(self.WINDOW_NAME, placeholder)
                if cv2.waitKey(100) & 0xFF in (27, ord("q")):
                    break
                continue

            # Crop to ROI
            roi = self.roi
            cropped = depth[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]

            # Colorize
            display = self._colorize_depth(cropped)

            # Mirror image to match simulation grid orientation
            if getattr(config, "MIRROR_KINECT_X", False):
                display = cv2.flip(display, 1)  # Horizontal flip
            if getattr(config, "MIRROR_KINECT_Y", True):
                display = cv2.flip(display, 0)  # Vertical flip

            # Scale up for comfortable viewing
            display = cv2.resize(
                display,
                (self.display_w, self.display_h),
                interpolation=cv2.INTER_LINEAR,
            )

            # Overlays
            self._draw_grid_overlay(display)
            self._draw_click_marker(display)
            self._draw_persistent_firebreaks(display)
            self._draw_firebreak_markers(display)
            self._draw_status_bar(display)

            # Add controls panel at the bottom
            panel = self._draw_controls_panel()
            canvas = np.vstack([display, panel])

            cv2.imshow(self.WINDOW_NAME, canvas)

            # Key handling
            k = cv2.waitKey(30) & 0xFF
            if k in (27, ord("q")):
                break
            elif k == ord("g"):
                self.show_grid = not self.show_grid
                print(f"[WoZ] Grid overlay: {'ON' if self.show_grid else 'OFF'}")
            elif k == ord("b") or k == ord("B"):
                self.firebreak_mode = not self.firebreak_mode
                self.curve_mode = False
                if not self.firebreak_mode:
                    self.firebreak_clicks.clear()
                print(f"[WoZ] Firebreak mode: {'ON' if self.firebreak_mode else 'OFF'}")
            elif k == ord("c") or k == ord("C"):
                self.curve_mode = not self.curve_mode
                self.firebreak_mode = False
                print(f"[WoZ] Curve mode: {'ON' if self.curve_mode else 'OFF'}")
            elif k == ord(" "):
                send_command({"type": "capture"})
            elif k == ord("f") or k == ord("F"):
                send_command({"type": "precompute"})
            elif k == ord("p") or k == ord("P"):
                send_command({"type": "play"})
            elif k == ord("r") or k == ord("R"):
                send_command({"type": "reset"})
                self.last_click = None
            elif k == ord("w") or k == ord("W"):
                send_command({"type": "wind_dir", "dir": "N"})
            elif k == ord("s") or k == ord("S"):
                send_command({"type": "wind_dir", "dir": "S"})
            elif k == ord("a") or k == ord("A"):
                send_command({"type": "wind_dir", "dir": "W"})
            elif k == ord("d") or k == ord("D"):
                send_command({"type": "wind_dir", "dir": "E"})
            elif k in (ord("+"), ord("=")):
                send_command({"type": "wind_speed", "delta": 5})
            elif k == ord("-"):
                send_command({"type": "wind_speed", "delta": -5})
            elif k == ord(","):  # Slower animation (more frames per step)
                send_command({"type": "anim_speed", "delta": 5})
            elif k == ord("."):  # Faster animation (fewer frames per step)
                send_command({"type": "anim_speed", "delta": -5})

            # Poll for state updates from sandbox app
            new_state = read_state()
            if new_state:
                self.app_state = new_state

        # Cleanup
        cv2.destroyAllWindows()
        if self.kinect is not None:
            try:
                self.kinect.close()
            except Exception:
                pass
        print("[WoZ] Operator console closed.")


def main():
    console = WizardOfOzConsole()
    console.run()


if __name__ == "__main__":
    main()
