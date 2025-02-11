# -*- coding: utf-8 -*-
"""
Created on Wed Feb  5 17:21:38 2025

@author: clement
"""

import requests
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

# 1️⃣ Define the region for the map
center_lat, center_lon = 44.0, 4.4  # Example: Uzès, France
center_lat, center_lon = 48.0, 2.4  # Example: Paris, France
center_lat, center_lon = 44.381, 5.428  # Example: verclause, France
center_lat, center_lon = 47, 0

lat_range = np.linspace(center_lat - 10, center_lat + 10, 20)
lon_range = np.linspace(center_lon - 10, center_lon + 10, 20)

lat_range = np.linspace(center_lat - 1, center_lat + 1, 5)
lon_range = np.linspace(center_lon - 1, center_lon + 1, 5)


# 2️⃣ Function to fetch data and calculate seeing
def calculate_seeing(lat, lon):
    api_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&hourly=temperature_1000hPa,temperature_850hPa,temperature_700hPa,"
        "temperature_500hPa,temperature_300hPa,temperature_200hPa,"
        "windspeed_1000hPa,windspeed_850hPa,windspeed_700hPa,"
        "windspeed_500hPa,windspeed_300hPa,windspeed_200hPa&timezone=auto"
    )
    response = requests.get(api_url)
    data = response.json()

    # Extract temperature and wind speed
    temp_levels = [
        np.array(data['hourly']['temperature_1000hPa']),
        np.array(data['hourly']['temperature_850hPa']),
        np.array(data['hourly']['temperature_700hPa']),
        np.array(data['hourly']['temperature_500hPa']),
        np.array(data['hourly']['temperature_300hPa']),
        np.array(data['hourly']['temperature_200hPa']),
    ]
    wind_levels = [
        np.array(data['hourly']['windspeed_1000hPa']),
        np.array(data['hourly']['windspeed_850hPa']),
        np.array(data['hourly']['windspeed_700hPa']),
        np.array(data['hourly']['windspeed_500hPa']),
        np.array(data['hourly']['windspeed_300hPa']),
        np.array(data['hourly']['windspeed_200hPa']),
    ]

    altitudes = [0.1, 1.5, 3.0, 5.5, 9.0, 12.0]  # Altitudes in km

    # Calculate Cn^2
    Cn2 = []
    for i in range(len(altitudes) - 1):
        delta_T = temp_levels[i+1] - temp_levels[i]
        delta_z = altitudes[i+1] - altitudes[i]
        temp_grad = delta_T / delta_z
        wind_avg = (wind_levels[i+1] + wind_levels[i]) / 2
        temp_grad[temp_grad <= 0] = np.nan
        Cn2_layer = (temp_grad ** 2) * wind_avg
        Cn2.append(Cn2_layer)

    Cn2_integrated = np.nansum(Cn2, axis=0)  #yooo whaaaat
    lambda_wave = 500e-9
    k = 2 * np.pi / lambda_wave
    r0 = (0.423 * k**2 * Cn2_integrated) ** (-3/5)
    seeing = (0.98 * lambda_wave / r0) * (206265)

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
