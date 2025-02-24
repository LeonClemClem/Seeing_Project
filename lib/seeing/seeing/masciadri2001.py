import numba as nb

nb.jit(nopython=True, parallel=True)


def potential_temperature(t, p, p_std, ra, cp):
    """
    Calculate the potential temperature.

    theta = t * (p_std / p) ** (ra / cp)

    Args:
        t (float): temperature
        p (float): pressure
        p_std (float): standard pressure
        ra (float): gas constant for dry air
        cp (float): specific heat capacity at constant pressure
    """
    return t * (p_std / p) ** (ra / cp)


nb.jit(nopython=True, parallel=True)


def finite_centered_difference(y1, y2, dx):
    """
    Calculate the finite centered difference.

    dy = (y2 - y1) / dx

    Args:
        y1 (float): value at x1
        y2 (float): value at x2
        dx (float): difference in x
    """
    return (y2 - y1) / dx


nb.jit(nopython=True, parallel=True)


def cn_square(p, theta, theta_prime, tke, ra, cp):
    """Optical tubulence parameter.

    Computed as:


    Args:
        p (float): pressure
        theta (float): potential temperature
        theta_prime (float): potential temperature fluctuation
        tke (float): turbulent kinetic energy
        ra (float): gas constant for dry air
        cp (float): specific heat capacity at constant pressure
    """
    cn2 = (
        3.35e-6
        * p ** (2(1 - 2 * ra / cp))
        * theta ** (-10 / 3)
        * theta_prime ** (4 / 3)
        * tke ** (2 / 3)
    )
