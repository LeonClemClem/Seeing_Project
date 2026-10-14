import numpy as np
def compute_c2n(T, P, dTdz, dUdz, dVdz):
    """
    Compute the refractive index structure constant C_n^2 based on Masciadri et al. (2001).
    Parameters:
    T : float
        Absolute temperature (K)
    P : float
        Pressure (hPa)
    dTdz : float
        Temperature gradient (K/m)
    dUdz : float
        Wind shear in the U component (m/s per m)
    dVdz : float
        Wind shear in the V component (m/s per m)
    Returns:
    Cn2 : float
        Refractive index structure constant (m^(-2/3))
    """
    # Constants
    g = 9.81  # Gravity acceleration (m/s^2)
    k = 0.4    # von Kármán constant
    A = 79e-6  # Empirical constant for turbulence
    # Potential temperature gradient term
    Theta = T  # Approximation since Theta ~ T at low altitudes
    dTheta_dz = dTdz + (g / 1004)  # Dry adiabatic lapse rate correction (1004 J/kgK for air)
    # Wind shear term
    Wind_shear = np.sqrt(dUdz**2 + dVdz**2)
    # C_n^2 calculation (Masciadri et al. 2001)
    Cn2 = A * (P / T**2)**2 * np.abs(dTheta_dz) * Wind_shear**(2/3)
    return Cn2

# EXEMPLE ~A la con 
T = 280  # Temperature in Kelvin
P = 750  # Pressure in hPa
dTdz = -0.0065  # Temperature gradient in K/m
dUdz = 0.01  # Wind shear U-component in m/s per m
dVdz = 0.02  # Wind shear V-component in m/s per m

Cn2 = compute_c2n(T, P, dTdz, dUdz, dVdz)
print(f"C_n^2: {Cn2:.3e} m^(-2/3)")
