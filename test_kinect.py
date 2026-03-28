import traceback
import sys

try:
    from pykinect2 import PyKinectV2
    from pykinect2 import PyKinectRuntime
    print("IMPORT SUCCESS")
except Exception as e:
    with open("trace.txt", "w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    print("Failed")
