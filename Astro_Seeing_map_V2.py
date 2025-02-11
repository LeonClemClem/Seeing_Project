# -*- coding: utf-8 -*-
"""
Created on Wed Feb  5 17:21:38 2025

@author: clement
"""
import sympy as smp
import requests
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

import scipy as sp
#from scipy.integrate import quad
#from scipy.integrate import cumulative_trapezoid

x=smp.symbols('x', real=True)



# 1️⃣ Define the region for the map
center_lat, center_lon = 44.0, 4.4  # Example: Uzès, France
center_lat, center_lon = 48.0, 2.4  # Example: Paris, France
center_lat, center_lon = 44.381, 5.428  # Example: verclause, France
center_lat, center_lon = 43, 1

lat_range = np.linspace(center_lat - 10, center_lat + 10, 20)
lon_range = np.linspace(center_lon - 10, center_lon + 10, 20)

#lat_range = np.linspace(center_lat - 1, center_lat + 1, 4)
#lon_range = np.linspace(center_lon - 1, center_lon + 1, 4)


# 2️⃣ Function to fetch data and calculate seeing
def calculate_seeing(lat, lon):
#    print("------------------------------")

    api_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&hourly=temperature_1000hPa,temperature_850hPa,temperature_700hPa,"
        "temperature_500hPa,temperature_300hPa,temperature_200hPa,"
        "windspeed_1000hPa,windspeed_850hPa,windspeed_700hPa,"
        "windspeed_500hPa,windspeed_300hPa,windspeed_200hPa&timezone=auto"
    )
    response = requests.get(api_url)
    data = response.json()
    latest_index = 2                    #pourquoi -1 ???
    # Extract temperature and wind speed
    temp_levels = [
        np.array(data['hourly']['temperature_1000hPa'])[latest_index],
        np.array(data['hourly']['temperature_850hPa'])[latest_index],
        np.array(data['hourly']['temperature_700hPa'])[latest_index],
        np.array(data['hourly']['temperature_500hPa'])[latest_index],
        np.array(data['hourly']['temperature_300hPa'])[latest_index],
        np.array(data['hourly']['temperature_200hPa'])[latest_index],
    ]
#    temp_levels = [
#        np.array(data['hourly']['temperature_1000hPa']),
#        np.array(data['hourly']['temperature_850hPa']),
#        np.array(data['hourly']['temperature_700hPa']),
#        np.array(data['hourly']['temperature_500hPa']),
#        np.array(data['hourly']['temperature_300hPa']),
#        np.array(data['hourly']['temperature_200hPa']),
#        ]      
#    print("temp_levels:", temp_levels)
#    print("dimension:",len(temp_levels))
#    wind_levels = [
#        np.array(data['hourly']['windspeed_1000hPa'])[latest_index],
#        np.array(data['hourly']['windspeed_850hPa'])[latest_index],
#        np.array(data['hourly']['windspeed_700hPa'])[latest_index],
#        np.array(data['hourly']['windspeed_500hPa'])[latest_index],
#        np.array(data['hourly']['windspeed_300hPa'])[latest_index],
#        np.array(data['hourly']['windspeed_200hPa'])[latest_index],
#    ]
    
#    wind_levels = [
#        np.array(data['hourly']['windspeed_1000hPa']),
#        np.array(data['hourly']['windspeed_850hPa']),
#        np.array(data['hourly']['windspeed_700hPa']),
#        np.array(data['hourly']['windspeed_500hPa']),
#        np.array(data['hourly']['windspeed_300hPa']),
#        np.array(data['hourly']['windspeed_200hPa']),
#    ]
    
#    print("Wind Speed Levels:", wind_levels)
#    print("dimension:",len(wind_levels))
    
    z         =     [100, 1500, 3000, 5500, 9000, 12000]  # Altitudes in km
    p         =     [1000, 850, 700, 500, 300, 200]

    # Calculate Cn^2
    gamma     =     0.0098 # mettre vraie valeure plus tard
    T         =     np.array(temp_levels)
    print ("Temperatures", T)
    delta_T     =   np.gradient(T, z)
    print ("delta_T", delta_T)

    Cn2 = []

    for k in range(len(p) - 1):  
            pression = p[k+1]  
            print(f"Iteration {k}: pression = {pression}")  # Debugging output
            print("p =", pression)
            T           =   temp_levels[k+1] + 273.15
            print ("Temperatures", T)

 ######################
            L = 0.3 #pour l'instant       Method of estimation of turbulence characteristic scales / V.A. Kulikov 1*, M.S. Andreeva 2, A.V. Koryabin 3, V.I. Shmalhausen 
##        L**(4/3)  (h)    =  10  **  (1.57   +  40   * S)    troposphere
##        L**(4/3)  (h)    =  10  **  (0.503  +  51.2 * S)  stratosphere
            M2         =    (((-79 * 10**-6 * pression) / T**2 ) * (delta_T[k+1] + gamma))*2
            Cn2_layer  =    2.8 * M2 * L**(4/3)
#    #################
##        temp_grad = np.gradient(delta_T, delta_z)#delta_T / delta_z
##        wind_avg = (wind_levels[i+1] + wind_levels[i]) / 2
##        temp_grad[temp_grad <= 0] = np.nan               # inf ou egal à zero ? Physique ?
##        Cn2_layer = (temp_grad **2) * wind_avg      
            
            Cn2.append(Cn2_layer)
            
    Cn2_integrated = np.nansum(Cn2, axis=0)  #yooo whaaaat heum,l'histoire d'additionner des nan maybe pas tres catholique
    print("Cn2_integrated", Cn2_integrated)
    lambda_wave = 500e-9
    o = 2 * np.pi / lambda_wave
    r0 = (0.423 * o**2 * Cn2_integrated) ** (-3/5)
    print("r0:", r0)
    seeing = (0.98 * lambda_wave / r0) * (206265)
#    print("Seeing:", seeing)
    return np.nanmean(seeing)
    


# 3️⃣ Generate seeing data for the grid
seeing_grid = np.zeros((len(lat_range), len(lon_range)))

for i, lat in enumerate(lat_range):
    for j, lon in enumerate(lon_range):
        try:
            seeing_grid[i, j] = calculate_seeing(lat, lon)
        except:
            seeing_grid[i, j] = np.nan



# 4️⃣ Plot the Seeing Map
plt.figure(figsize=(12, 8))
m = Basemap(projection='merc', llcrnrlat=lat_range.min(), urcrnrlat=lat_range.max(),
            llcrnrlon=lon_range.min(), urcrnrlon=lon_range.max(), resolution='i')
m.drawcoastlines()
m.drawcountries()
m.drawparallels(np.arange(-90., 91., 0.5), labels=[1, 0, 0, 0], fontsize=10)
m.drawmeridians(np.arange(-180., 181., 0.5), labels=[0, 0, 0, 1], fontsize=10)

lon_grid, lat_grid = np.meshgrid(lon_range, lat_range)
x, y = m(lon_grid, lat_grid)

cs = m.contourf(x, y, seeing_grid, cmap='plasma')
cbar = m.colorbar(cs, location='right', pad="5%")
cbar.set_label('Astronomical Seeing (arcseconds)')

plt.title('Astronomical Seeing Forecast Map')
plt.show()
