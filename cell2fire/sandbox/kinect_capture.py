# coding: utf-8
"""
Kinect v2 depth frame capture with fallback to a static image.
"""
import os
import numpy as np
import cv2

from . import config

# Try to import PyKinectV2 (Windows-only, Python 3.7-3.9)
try:
    from pykinect2 import PyKinectV2, PyKinectRuntime
    HAS_PYKINECT = True
except Exception as e:
    HAS_PYKINECT = False
    print(f"[KinectCapture] Exception importing pykinect2: {e}")


class KinectCapture:
    """Captures depth frames from an Xbox Kinect v2 sensor.

    Falls back to loading a static depth.png image if the sensor is
    unavailable or the pykinect2 library is not installed.
    """

    def __init__(self):
        self.kinect = None
        self.has_kinect = False
        self._last_valid_frame = None

        if HAS_PYKINECT:
            try:
                self.kinect = PyKinectRuntime.PyKinectRuntime(
                    PyKinectV2.FrameSourceTypes_Depth
                )
                self.has_kinect = True
                print("[KinectCapture] Kinect v2 initialized successfully.")
            except Exception as e:
                print(f"[KinectCapture] Kinect init failed: {e}. Using fallback.")
        else:
            print("[KinectCapture] pykinect2 not installed. Using fallback depth image.")

    def get_depth_frame(self) -> np.ndarray:
        """Return a 424×512 uint16 depth frame (millimeters).

        Returns the live Kinect frame if available, otherwise loads
        the fallback depth.png and converts it to a simulated depth array.

        Returns:
            np.ndarray of shape (424, 512) with dtype uint16, or None on failure.
        """
        # ── Live Kinect path ──
        if self.has_kinect and self.kinect is not None:
            if self.kinect.has_new_depth_frame():
                depth = self.kinect.get_last_depth_frame()
                self._last_valid_frame = depth.reshape(
                    (config.KINECT_FRAME_HEIGHT, config.KINECT_FRAME_WIDTH)
                )
            
            if self._last_valid_frame is not None:
                return self._last_valid_frame

        # ── Fallback: load depth.png ──
        return self._load_fallback_image()

    def _load_fallback_image(self) -> np.ndarray:
        """Load and convert a static depth image to a simulated depth array."""
        fallback_path = config.FALLBACK_DEPTH_IMAGE
        if not os.path.isfile(fallback_path):
            print(f"[KinectCapture] Fallback image not found: {fallback_path}")
            print("[KinectCapture] Generating synthetic depth frame.")
            return self._generate_synthetic_depth()

        depth_img = cv2.imread(fallback_path, cv2.IMREAD_UNCHANGED)
        if depth_img is None:
            print("[KinectCapture] Failed to read fallback image. Using synthetic.")
            return self._generate_synthetic_depth()

        # Convert to grayscale if needed
        if depth_img.ndim == 3:
            depth_img = cv2.cvtColor(depth_img, cv2.COLOR_BGR2GRAY)

        # Resize to Kinect dimensions
        depth_img = cv2.resize(
            depth_img,
            (config.KINECT_FRAME_WIDTH, config.KINECT_FRAME_HEIGHT),
        )

        # Scale 0-255 grayscale → millimeter depth range
        if depth_img.dtype != np.uint16:
            depth_img = (
                config.DEPTH_MIN_MM
                + (depth_img / 255.0) * (config.DEPTH_MAX_MM - config.DEPTH_MIN_MM)
            ).astype(np.uint16)

        return depth_img

    @staticmethod
    def _generate_synthetic_depth() -> np.ndarray:
        """Generate a synthetic depth frame with a hill-like shape for testing."""
        h, w = config.KINECT_FRAME_HEIGHT, config.KINECT_FRAME_WIDTH
        y, x = np.mgrid[0:h, 0:w].astype(np.float32)

        # Normalize to 0..1
        y_norm = y / h
        x_norm = x / w

        # Create a dome/hill in the center
        cx, cy = 0.5, 0.5
        dist = np.sqrt((x_norm - cx) ** 2 + (y_norm - cy) ** 2)
        hill = np.clip(1.0 - dist * 2.0, 0, 1)  # 0 at edges, 1 at center

        # Add some noise for natural variation
        rng = np.random.RandomState(42)
        noise = rng.rand(h, w).astype(np.float32) * 0.1

        # Combine: higher depth value = farther from sensor = lower elevation
        # Invert so the center hill is "closer" (lower depth value = higher terrain)
        normalized = 1.0 - (hill * 0.7 + noise * 0.3)

        depth = (
            config.DEPTH_MIN_MM
            + normalized * (config.DEPTH_MAX_MM - config.DEPTH_MIN_MM)
        ).astype(np.uint16)

        return depth

    def cleanup(self):
        """Release Kinect resources."""
        if self.kinect is not None:
            try:
                self.kinect.close()
            except Exception:
                pass
            self.kinect = None
            self.has_kinect = False
        print("[KinectCapture] Resources released.")
