from datetime import datetime

from pydantic import BaseModel


class SiteOut(BaseModel):
    slug: str
    name: str
    lat: float
    lon: float
    altitude_m: float | None


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
    email: str | None
    env: str


class Health(BaseModel):
    status: str
