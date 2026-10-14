"""Physical constants and fixed grids (from research/SeeingAromeV2_correction_conv_tke.py)."""

import numpy as np

G = 9.81
R_OVER_CP = 0.286
P0_HPA = 1000.0
LAMBDA = 500e-9  # wavelength [m]
ARCSEC = 206265.0

# Free-convection closure (w'theta'_0 from SP3:sshf).
KAPPA = 0.4
CP_AIR = 1005.0
R_D = 287.05
C_FC = 2.1  # free-convection constant (Wyngaard-Izumi-Collins, a~4.9 b~9) -- to be calibrated
SSHF_SIGN = -1.0  # -1 if sshf is positive downwards (ECMWF-like convention); to be verified

# Top of the AROME heightAboveGround grids (HP1/HP2). This is a grid limit, not a physical one:
# the boundary between the boundary-layer (TKE) and free-atmosphere (shear) models is H_COULIM.
HAG_TOP_M = 3000.0

# heightAboveGround levels of HP1/HP2 [m AGL].
HEIGHTS = np.array([
    10, 20, 35, 50, 75, 100, 150, 200, 250,
    375, 500, 625, 750, 875, 1000, 1125, 1250,
    1375, 1500, 1750, 2000, 2250, 2500, 2750, 3000
], dtype=float)

# Display grid of the stored Cn2 profiles: DISPLAY_Z0, DISPLAY_Z0 + DISPLAY_DZ, ... [m AGL].
DISPLAY_Z0 = 10.0
DISPLAY_DZ = 100.0
