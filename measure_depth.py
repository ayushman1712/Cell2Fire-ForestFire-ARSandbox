import cv2
import numpy as np
import time
from cell2fire.sandbox.kinect_capture import KinectCapture

mouseX, mouseY = -1, -1
current_depth = 0

def mouse_callback(event, x, y, flags, param):
    global mouseX, mouseY
    if event == cv2.EVENT_MOUSEMOVE:
        mouseX, mouseY = x, y

def main():
    print("Initializing Kinect for Depth Measurement...")
    capture = KinectCapture()
    
    time.sleep(1) # Let the sensor warm up
    
    cv2.namedWindow('Kinect Depth Meter')
    cv2.setMouseCallback('Kinect Depth Meter', mouse_callback)

    print("\n--- INSTRUCTIONS ---")
    print("1. Flatten the sand completely (or clear a spot to the bottom of the box).")
    print("2. Point your mouse at the flat bottom to find DEPTH_MAX_MM.")
    print("3. Pile up a huge mountain of sand to the maximum height you would ever build.")
    print("4. Point your mouse at the peak to find DEPTH_MIN_MM.")
    print("5. Press ESC to quit when you have your numbers.")
    print("--------------------\n")

    while True:
        depth = capture.get_depth_frame()
        if depth is None:
            time.sleep(0.5)
            continue
            
        # Draw the depth map (normalized for display)
        # Using 500mm to 1500mm as a standard display range just to see the image
        display_img = np.clip(depth, 500, 1500) 
        display_img = cv2.normalize(display_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
        display_img = cv2.cvtColor(display_img, cv2.COLOR_GRAY2BGR)
        display_img = cv2.applyColorMap(display_img, cv2.COLORMAP_JET)

        if mouseX != -1 and mouseY != -1:
            # Get the exact raw millimeter depth at the mouse pointer
            current_depth = depth[mouseY, mouseX]
            
            # Draw a crosshair
            cv2.drawMarker(display_img, (mouseX, mouseY), (255, 255, 255), cv2.MARKER_CROSS, 20, 2)
            
            # Draw the depth text
            text = f"Depth: {current_depth} mm"
            cv2.putText(display_img, text, (mouseX + 15, mouseY - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(display_img, text, (mouseX + 15, mouseY - 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)

        cv2.imshow('Kinect Depth Meter', display_img)
        
        key = cv2.waitKey(30) & 0xFF
        if key == 27:  # ESC
            break

    capture.cleanup()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
