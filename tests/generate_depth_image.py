# coding: utf-8
"""
Generate a fallback depth.png image for development without a Kinect sensor.
Run this script to create cell2fire/sandbox/depth.png
"""
import os
import sys
import numpy as np

# Ensure we can import from the project
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def generate_depth_image(output_path: str):
    """Generate a synthetic depth image simulating sandbox terrain."""
    try:
        import cv2
    except ImportError:
        print("opencv-python required: pip install opencv-python")
        return

    h, w = 424, 512

    # Create coordinate grids
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    y_norm = y / h
    x_norm = x / w

    # Multiple terrain features
    rng = np.random.RandomState(42)

    # Central mountain
    cx1, cy1 = 0.45, 0.4
    hill1 = np.exp(-((x_norm - cx1)**2 + (y_norm - cy1)**2) / 0.04) * 0.6

    # Ridge on the right
    cx2, cy2 = 0.75, 0.5
    ridge = np.exp(-((x_norm - cx2)**2) / 0.01 - ((y_norm - cy2)**2) / 0.08) * 0.4

    # Valley on the left
    cx3, cy3 = 0.2, 0.6
    valley = -np.exp(-((x_norm - cx3)**2 + (y_norm - cy3)**2) / 0.03) * 0.2

    # Small hill
    cx4, cy4 = 0.6, 0.2
    small_hill = np.exp(-((x_norm - cx4)**2 + (y_norm - cy4)**2) / 0.02) * 0.3

    # Combine features
    terrain = hill1 + ridge + valley + small_hill

    # Add fine noise for natural texture
    noise = rng.rand(h, w).astype(np.float32) * 0.08

    combined = terrain + noise

    # Normalize to 0-255 (closer = brighter = higher elevation)
    combined = (combined - combined.min()) / (combined.max() - combined.min())
    depth_img = (combined * 255).astype(np.uint8)

    # Invert so that higher terrain = lower depth value (closer to sensor)
    depth_img = 255 - depth_img

    cv2.imwrite(output_path, depth_img)
    print(f"Generated depth image: {output_path} ({w}x{h})")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sandbox_dir = os.path.join(script_dir, "..", "cell2fire", "sandbox")
    output = os.path.join(sandbox_dir, "depth.png")
    generate_depth_image(output)
