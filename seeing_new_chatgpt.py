# -*- coding: utf-8 -*-
"""
Created on Thu Jul 31 00:23:20 2025

@author: clement
"""
# DIMM Seeing Monitor for ZWO ASI Camera with Live Plot

import cv2
import numpy as np
import zwoasi as asi
import time
import matplotlib.pyplot as plt
from collections import deque

# ========= Configuration =========
pixel_scale = 0.4  # arcsec/pixel
baseline = 0.25    # sub-aperture separation (meters)
wavelength = 500e-9  # meters

# ========= Initialize Camera =========
asi.init()  # Assumes ASI SDK path is set via environment variable or asi.init(path)
cameras = asi.list_cameras()
if not cameras:
    raise RuntimeError("No ZWO ASI cameras detected")

camera = asi.Camera(0)
camera.set_control_value(asi.ASI_GAIN, 100)
camera.set_control_value(asi.ASI_EXPOSURE, 1000)  # microseconds
camera.set_image_type(asi.ASI_IMG_RAW8)
camera.start_video_capture()

# ========= Centroid Detection =========
def detect_centroids(frame, threshold=50):
    gray = cv2.cvtColor(frame, cv2.COLOR_BAYER_RG2GRAY)
    _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centroids = []
    for cnt in contours:
        if cv2.contourArea(cnt) > 5:
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centroids.append((cx, cy))
    return centroids

# ========= Seeing Calculation =========
def compute_seeing(diffs):
    if len(diffs) < 2:
        return None
    arr = np.array(diffs)
    var_x = np.var(arr[:, 0]) * (pixel_scale * np.pi / 648000)**2
    var_y = np.var(arr[:, 1]) * (pixel_scale * np.pi / 648000)**2
    try:
        r0_x = (0.358 * wavelength**2 * baseline**(-1/3) / var_x)**(3/5)
        r0_y = (0.358 * wavelength**2 * baseline**(-1/3) / var_y)**(3/5)
        r0 = (r0_x + r0_y) / 2
        seeing = 0.98 * wavelength / r0
        
        
        D_hole = 0.06
        #############################################
        factor_x_b = 2 * wavelength**2 * (0.179 * D_hole**(-1/3) - 0.0968 * baseline**(-1/3))
        factor_y_b = 2 * wavelength**2 * (0.179 * D_hole**(-1/3) - 0.145 * baseline**(-1/3))
        # print(factor_y_b, factor_x_b, 'factor_xy_b')
        
        r0_xb = (factor_x_b / var_x**2)**(3/5)
        r0_yb = (factor_y_b / var_y**2)**(3/5)
        print(r0_xb, r0_yb, 'r0_xy_b')
        
        r0b = (r0_xb + r0_yb) / 2
        seeing = 0.98 * wavelength / r0b
        ##############################################
        
        
        
        
        
        return np.degrees(seeing) * 3600
    except ZeroDivisionError:
        return None

# ========= Live Plot =========
plt.ion()
fig, ax = plt.subplots()
x_vals, y_vals = deque(maxlen=300), deque(maxlen=300)
start_time = time.time()

# ========= Main Loop =========
diffs = deque(maxlen=50)
prev_sep = None

try:
    while True:
        frame = camera.capture_video_frame()
        centroids = detect_centroids(frame)

        if len(centroids) == 2:
            x1, y1 = centroids[0]
            x2, y2 = centroids[1]
            dx, dy = x1 - x2, y1 - y2
            if prev_sep is not None:
                ddx, ddy = dx - prev_sep[0], dy - prev_sep[1]
                diffs.append([ddx, ddy])
                seeing = compute_seeing(diffs)
                if seeing:
                    elapsed = time.time() - start_time
                    x_vals.append(elapsed)
                    y_vals.append(seeing)
                    ax.clear()
                    ax.set_title("Live Seeing Monitor")
                    ax.set_xlabel("Time (s)")
                    ax.set_ylabel("Seeing (arcsec)")
                    ax.set_ylim(0, 5)
                    ax.scatter(x_vals, y_vals, color='blue')
                    plt.pause(0.001)
            prev_sep = (dx, dy)

        cv2.imshow("DIMM Frame", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    camera.stop_video_capture()
    camera.close()
    cv2.destroyAllWindows()
    plt.ioff()
    plt.show()
