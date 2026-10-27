from datetime import datetime

from pydantic import BaseModel

from seeing_api.auth import UserOut


class SiteOut(BaseModel):
    slug: str
    name: str
    lat: float
    lon: float
    altitude_m: float | None
    visibility: str
    # Personal place of the logged-in account.
    owned: bool = False
    # (K_TKE, K_CIS, K_conv): only for the owner, the administrator and the team for its own site.
    k: list[float] | None = None


class RunOut(BaseModel):
    run_time: datetime
    finished_at: datetime | None
    status: str


class ForecastPoint(BaseModel):
    lead_hour: int
    valid_time: datetime
    seeing_arcsec: float | None
    r0_m: float | None
    integral_cn2: float | None
    h_coulim_m: float | None
    # Ground altitude of the AROME grid point [m] (absolute altitudes, e.g. the jet stream band).
    model_altitude_m: float | None = None
    # Model variables {t2, dth, u10, u100, u500, shl, shj, tke}, null for older forecasts.
    variables: dict[str, float | None] | None = None


class ForecastOut(BaseModel):
    site: SiteOut
    run_time: datetime
    points: list[ForecastPoint]


class Cn2Out(BaseModel):
    site: SiteOut
    run_time: datetime
    valid_times: list[datetime]
    heights_m: list[float]
    cn2: list[list[float | None]]


class MeOut(BaseModel):
    #: Identity asserted by IAP (header), independent of the app account.
    email: str | None
    env: str
    #: The logged-in app account, or None.
    user: UserOut | None = None


class Health(BaseModel):
    status: str


class MapGridOut(BaseModel):
    ny: int
    nx: int
    lat0: float
    lon0: float
    dlat: float
    dlon: float


class MapFrameOut(BaseModel):
    lead_hour: int
    valid_time: datetime


class MapOut(BaseModel):
    """Global seeing map of a run. A frame is GET /api/map/frame?run=...&lead=... : ny * nx bytes,
    row-major, code c -> seeing = exp(ln(see_min) + c / 254 * (ln(see_max) - ln(see_min))), 255 = none."""

    run_time: datetime
    grid: MapGridOut
    see_min: float
    see_max: float
    frames: list[MapFrameOut]
    # GET /api/map/relief serves the model orography of the grid (contour lines)
    relief: bool = False
