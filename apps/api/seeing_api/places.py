"""Personal places: `sites` rows owned by an account (`owner_id`), computed by the batch like the
curated sites. Private by default; a shared place is shown to the community without its name and
with a position blurred by 5-11 km."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from seeing_api.api import SessionDep, site_out
from seeing_api.auth import require_json, require_role
from seeing_api.schemas import SiteOut
from seeing_db import Site, User, UserRole

router = APIRouter(prefix="/api/places", dependencies=[Depends(require_json)])
LoggedIn = Annotated[User, Depends(require_role())]

MAX_PLACES = 5  # per account (the administrator is not limited)
# AROME 0.025 domain
LAT_RANGE, LON_RANGE = (37.5, 55.4), (-12.0, 16.0)
K_MAX = 150.0
# Starting K of a new place: the global map K (the K of the curated sites stay confidential).
DEFAULT_K = (2.0, 57.0, 0.1)  # K_TKE, K_CIS, K_conv


class PlaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    lat: float = Field(ge=LAT_RANGE[0], le=LAT_RANGE[1])
    lon: float = Field(ge=LON_RANGE[0], le=LON_RANGE[1])
    altitude_m: float | None = Field(default=None, ge=-500, le=5000)
    shared: bool = False


class PlacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    shared: bool | None = None
    k_tke: float | None = Field(default=None, gt=0, le=K_MAX)
    k_cis: float | None = Field(default=None, gt=0, le=K_MAX)
    k_conv: float | None = Field(default=None, ge=0, le=K_MAX)


def own_place(session, slug: str, user: User) -> Site:
    site = session.scalar(select(Site).where(Site.slug == slug, Site.owner_id == user.id))
    if site is None:
        raise HTTPException(404, f"Unknown place '{slug}'")
    return site


@router.post("", response_model=SiteOut, status_code=201)
def create_place(body: PlaceIn, session: SessionDep, user: LoggedIn) -> SiteOut:
    n = session.scalar(select(func.count()).select_from(Site).where(Site.owner_id == user.id))
    if user.role != UserRole.admin and n >= MAX_PLACES:
        raise HTTPException(409, f"At most {MAX_PLACES} places per account")
    k_tke, k_cis, k_conv = DEFAULT_K
    site = Site(
        slug=f"p{user.id}-{secrets.token_hex(4)}", name=body.name.strip(), lat=body.lat, lon=body.lon,
        altitude_m=body.altitude_m, k_tke=k_tke, k_cis=k_cis, k_tke_conv=k_conv, active=True,
        visibility="shared" if body.shared else "private", owner_id=user.id,
    )
    session.add(site)
    session.commit()
    return site_out(site, user)


@router.patch("/{slug}", response_model=SiteOut)
def update_place(slug: str, body: PlacePatch, session: SessionDep, user: LoggedIn) -> SiteOut:
    site = own_place(session, slug, user)
    if body.name is not None:
        site.name = body.name.strip()
    if body.shared is not None:
        site.visibility = "shared" if body.shared else "private"
    for field, column in (("k_tke", "k_tke"), ("k_cis", "k_cis"), ("k_conv", "k_tke_conv")):
        value = getattr(body, field)
        if value is not None:
            setattr(site, column, value)
    session.commit()
    return site_out(site, user)


@router.delete("/{slug}", status_code=204)
def delete_place(slug: str, session: SessionDep, user: LoggedIn) -> Response:
    session.delete(own_place(session, slug, user))  # forecasts and Cn2 profiles: ON DELETE CASCADE
    session.commit()
    return Response(status_code=204)
