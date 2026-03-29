import cv2
import numpy as np
import time
from cell2fire.sandbox.kinect_capture import KinectCapture
from cell2fire.sandbox import config

# Global variables for mouse callback
drawing = False
ix, iy = -1, -1
fx, fy = -1, -1
aspect_ratio = 1.6  # 16:10

def draw_rectangle(event, x, y, flags, param):
    global ix, iy, fx, fy, drawing, aspect_ratio

    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y
        fx, fy = x, y

    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            # Calculate width based on mouse movement
            width = x - ix
            
            # Force height to maintain 16:10 aspect ratio depending on width direction
            if width != 0:
                sign_y = 1 if (y - iy) >= 0 else -1
                height = int(abs(width) / aspect_ratio) * sign_y
                
                fx = x
                fy = iy + height

    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        width = x - ix
        if width != 0:
            sign_y = 1 if (y - iy) >= 0 else -1
            height = int(abs(width) / aspect_ratio) * sign_y
            
            fx = x
            fy = iy + height
            
        # Ensure coordinates are top-left to bottom-right
        x1 = min(ix, fx)
        x2 = max(ix, fx)
        y1 = min(iy, fy)
        y2 = max(iy, fy)
        
        print("\n=== NEW ROI COORDINATES (16:10) ===")
        print("Update your config.py with these values:")
        print(f"KINECT_ROI = {{")
        print(f"    'x1': {x1},")
        print(f"    'y1': {y1},")
        print(f"    'x2': {x2},")
        print(f"    'y2': {y2},")
        print(f"}}")
        print("===================================\n")
        print("Press 'ESC' to close the calibration window.")

def main():
    print("Initializing Kinect...")
    capture = KinectCapture()
    
    # Wait a bit for the sensor to warm up and get a valid frame
    time.sleep(1)
    
    cv2.namedWindow('Kinect Calibration (Draw 16:10 Box)')
    cv2.setMouseCallback('Kinect Calibration (Draw 16:10 Box)', draw_rectangle)
    
    print("\n--- INSTRUCTIONS ---")
    print("1. Click and drag on the image to draw a rectangle over your sand.")
    print("2. The script will automatically force it to be a 16:10 ratio.")
    print("3. Check the console for the final coordinates when you release the mouse.")
    print("4. Press ESC to quit.")
    print("--------------------\n")

    while True:
        depth = capture.get_depth_frame()
        
        if depth is None:
            print("Failed to get frame. Retrying...")
            time.sleep(0.5)
            continue
            
        # Normalize depth to 8-bit for visualization
        # Clamp between DEPTH_MIN and DEPTH_MAX to make sand visible
        depth_clamped = np.clip(depth, config.DEPTH_MIN_MM, config.DEPTH_MAX_MM)
        depth_norm = cv2.normalize(depth_clamped, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        
        # Convert to BGR so we can draw colored rectangles
        display_img = cv2.cvtColor(depth_norm, cv2.COLOR_GRAY2BGR)
        
        # Apply a colormap to make depth differences easier to see
        display_img = cv2.applyColorMap(display_img, cv2.COLORMAP_JET)

        # Draw current rectangle
        if fx != -1 and fy != -1:
            cv2.rectangle(display_img, (ix, iy), (fx, fy), (0, 255, 0), 2)
            
            # Show width/height info
            w = abs(fx - ix)
            h = abs(fy - iy)
            cv2.putText(display_img, f"W:{w} H:{h} Ratio:{w/max(1,h):.2f}", 
                        (min(ix, fx), min(iy, fy) - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow('Kinect Calibration (Draw 16:10 Box)', display_img)
        
        key = cv2.waitKey(30) & 0xFF
        if key == 27:  # ESC
            break

    capture.cleanup()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
