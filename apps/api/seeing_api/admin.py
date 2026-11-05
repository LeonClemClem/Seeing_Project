"""Administrator tab: the K and exact position of every site and the K history (more information will be
added here). The administrator never sees e-mails: a member is only "compte n°<id>"."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from seeing_api.api import SessionDep, clean
from seeing_api.auth import require_role
from seeing_api.measurements import KHistoryItem, account_label, k_history_items
from seeing_db import Site, User, UserRole

router = APIRouter(prefix="/api/admin")
Admin = Annotated[User, Depends(require_role(UserRole.admin))]


class AdminSite(BaseModel):
    slug: str
    name: str
    owner: str | None  # "compte n°<id>" for a personal place, None for a public site (no e-mail)
    lat: float  # exact position (for the grid cell setting), also of the members' places
    lon: float
    altitude_m: float | None
    active: bool
    k_tke: float
    k_cis: float
    k_conv: float
    k_saved_at: datetime | None


class AdminKEntry(KHistoryItem):
    site: str  # slug


class AdminAccount(BaseModel):
    label: str  # "compte n°<id>", as AdminSite.owner (never the e-mail)
    display_name: str | None
    role: str
    active: bool  # False: deleted (anonymized) or disabled account
    verified: bool  # e-mail address confirmed
    created_at: datetime
    last_login_at: datetime | None


class AdminOverview(BaseModel):
    sites: list[AdminSite]
    k_history: list[AdminKEntry]
    accounts: list[AdminAccount] = []


@router.get("/overview", response_model=AdminOverview)
def overview(session: SessionDep, user: Admin) -> AdminOverview:
    sites = session.scalars(select(Site).order_by(Site.name)).all()
    slug_of = {s.id: s.slug for s in sites}
    hist = k_history_items(session, None, True, limit=500)
    last = {}
    for site_id, item in hist:
        last.setdefault(site_id, item.saved_at)
    return AdminOverview(
        sites=[AdminSite(slug=s.slug, name=s.name, owner=account_label(s.owner_id), lat=s.lat, lon=s.lon,
                         altitude_m=clean(s.altitude_m), active=s.active, k_tke=s.k_tke, k_cis=s.k_cis,
                         k_conv=s.k_tke_conv, k_saved_at=last.get(s.id)) for s in sites],
        k_history=[AdminKEntry(site=slug_of.get(site_id, "?"), **item.model_dump()) for site_id, item in hist],
        accounts=[
            AdminAccount(label=account_label(u.id) or "", display_name=u.display_name, role=u.role.value, active=u.is_active,
                         verified=u.email_verified_at is not None, created_at=u.created_at, last_login_at=u.last_login_at)
            for u in session.scalars(select(User).order_by(User.id))
        ],
    )
