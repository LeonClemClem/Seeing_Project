# -*- coding: utf-8 -*-
"""
Created on Sun Jul 20 14:42:56 2025

@author: clement
"""
import cv2
import numpy as np
import zwoasi as asi
import time
import matplotlib.pyplot as plt
from collections import deque

# --- Telescope and camera physical parameters ---
# D = 0.4           # Aperture diameter in meters (example: 15 cm)  on s'en fout y'a la baseline
D_hole = 0.09      # test pour equations papierBoumis et al., 2001 seeing measurment at Skinakas blablabla
baseline = 0.1     # Distance between DIMM holes in meters (example: 20 cm)
focal_length = 1  # Telescope focal length in meters (example: 1.2 m)
pixel_size = 3.75e-6  # Camera pixel size in meters (example: 3.75 microns)
wavelength = 5e-7   # Wavelength in meters (example: 500 nm)

def open_camera(camera_index=0):
    camera = asi.Camera(camera_index)
    camera.set_control_value(asi.ASI_GAIN, 100)
    camera.set_control_value(asi.ASI_EXPOSURE, 1000)
    camera.set_image_type(asi.ASI_IMG_RAW8)
    return camera

def detect_star_centroids(frame, threshold=50):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centroids = []
    for cnt in contours:
        if cv2.contourArea(cnt) > 5:
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                centroids.append((cx, cy))
    return centroids

def compute_seeing(diff_positions):
    """
    Compute seeing in arcseconds from differential image motion in pixels.
    diff_positions: numpy array shape (N,2), differences dx, dy in pixels
    """
    if len(diff_positions) < 2:
        return None

    #print (diff_positions, 'diff_positions')
    diff_radians = diff_positions * pixel_size / focal_length
    #print (diff_radians, 'diff_radians')
    var_x_b = np.var(diff_radians[:,0])
    var_y_b = np.var(diff_radians[:,1])
    #print(diff_radians[:,1],'diff_radians [:, 1')
    #print (var_x_b, var_y_b, 'var X Y')

    try:
        #  Version avec taille trous
        factor_x_b = 2 * wavelength**2 * (0.179 * D_hole**(-1/3) - 0.0968 * baseline**(-1/3))
        factor_y_b = 2 * wavelength**2 * (0.179 * D_hole**(-1/3) - 0.145 * baseline**(-1/3))
        #print(factor_y_b, factor_x_b, 'factor_xy_b')
        
        r0_xb = (factor_x_b / var_x_b**2)**(3/5)
        r0_yb = (factor_y_b / var_y_b**2)**(3/5)
        #print(r0_xb, r0_yb, 'r0_xy_b')
        
    except ZeroDivisionError:
        return None
    # Version avec taille trous
    r0_b = (r0_xb + r0_yb) / 2                                      
    seeing_rad_b = 0.98 * wavelength / r0_b                        
    seeing_arcsec_b = np.degrees(seeing_rad_b) * 3600   
    #print(r0_b, 'r0_b)')   
    # print(seeing_arcsec_b, 'seeing_b')         
    print(f"Seeing Methode b: {seeing_arcsec_b:.2f} arcsec")

    return seeing_arcsec_b#, seeing_arcsec_b

def main():
    asi.init()
    cameras_found = asi.list_cameras()
    if len(cameras_found) == 0:
        print("No ZWO ASI cameras found")
        return

    cam = open_camera(0)
    cam.start_video_capture()

    prev_centroids = None
    diff_positions = []
    
    # Live plot setup
    plt.ion()
    fig, ax = plt.subplots()
    x_data, y_data = deque(maxlen=300), deque(maxlen=300)  # Last ~30s if 10Hz
    line, = ax.plot([], [], 'g-')
    # scatter = ax.scatter([], [], c='b', label="Seeing (points)")
    # ax.set_ylim(0, 5)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Seeing (arcsec)')
    ax.set_title('Live Seeing Measurement')
    start_time = time.time()

    try:
        while True:
            frame_raw = cam.capture_video_frame()
            frame = cv2.cvtColor(frame_raw, cv2.COLOR_BAYER_RG2BGR)
            
            centroids = detect_star_centroids(frame)
            if len(centroids) == 2:
                if prev_centroids is not None:
                    
                    x1, y1 = centroids[0]
                    print(centroids[0], 'centroid 1')
                    print(centroids[1], 'centroid 2')
                    x2, y2 = centroids[1]
                    sep_x = x1 - x2
                    sep_y = y1 - y2
                    delta_x = (x1 - x2)
                    delta_y = (y1 - y2)
                    print(delta_x, delta_y, 'delta x et y')

                if prev_centroids is not None:
                    prev_x1, prev_y1 = prev_centroids[0]
                    prev_x2, prev_y2 = prev_centroids[1]
                    prev_sep_x = prev_x1 - prev_x2
                    prev_sep_y = prev_y1 - prev_y2

                    diff_x = sep_x - prev_sep_x
                    diff_y = sep_y - prev_sep_y
                    diff_positions.append([diff_x, diff_y])
                    # diff_positions.append([delta_x, delta_y])
                    # variance sur 10 images successives arbitraire
                    if len(diff_positions) > 10:
                        diff_positions.pop(0)
                    #print (centroids, 'çentroids')
                    #print (diff_positions, 'diff poz')

                    diff_arr = np.array(diff_positions)
                    seeing = compute_seeing(diff_arr)

                    if seeing is not None:
                        cv2.putText(frame, f"Seeing: {seeing:.2f} arcsec", (10,30),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
                        print(f"Seeing: {seeing:.2f} arcsec")
                        
                        #######  Update live plot ##################
                        x_data.append(time.time() - start_time)
                        y_data.append(seeing)
                        # ax.scatter(x_data, y_data, c='blue')
                        line.set_data(x_data, y_data)
                        # ax.scatter(x_data, y_data, c='blue')
                        # scatter.set_offsets(np.c_[ooo, ooo])
                        ax.relim()
                        ax.autoscale_view()
                        plt.draw()
                        plt.pause(0.001)
                        ###########UPDATE live plot #################
                        
                prev_centroids = centroids
                # Draw star circles
                for (cx, cy) in centroids:
                    cv2.circle(frame, (cx, cy), 5, (0,255,0), 2)

            else:
                # Not exactly 2 stars detected: skip update, keep prev_centroids
                cv2.putText(frame, "Waiting for 2 stars...", (10,30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

            cv2.imshow("DIMM Seeing Monitor", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

            time.sleep(0.01)

    finally:
        cam.stop_video_capture()
        cam.close()
        cv2.destroyAllWindows()
        plt.ioff()
        plt.show()

if __name__ == "__main__":
    main()

