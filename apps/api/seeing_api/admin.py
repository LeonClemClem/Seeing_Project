"""Administrator tab: the K of every site and their history (more information will be added here)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from seeing_api.api import SessionDep
from seeing_api.auth import require_role
from seeing_api.measurements import KHistoryItem, k_history_items
from seeing_db import Site, User, UserRole

router = APIRouter(prefix="/api/admin")
Admin = Annotated[User, Depends(require_role(UserRole.admin))]


class AdminSite(BaseModel):
    slug: str
    name: str
    owner: str | None  # e-mail of the owner of a personal place, None for a public site
    active: bool
    k_tke: float
    k_cis: float
    k_conv: float
    k_saved_at: datetime | None


class AdminKEntry(KHistoryItem):
    site: str  # slug


class AdminOverview(BaseModel):
    sites: list[AdminSite]
    k_history: list[AdminKEntry]


@router.get("/overview", response_model=AdminOverview)
def overview(session: SessionDep, user: Admin) -> AdminOverview:
    sites = session.execute(select(Site, User.email).outerjoin(User, User.id == Site.owner_id).order_by(Site.name)).all()
    slug_of = {s.id: s.slug for s, _ in sites}
    hist = k_history_items(session, None, True, limit=500)
    last = {}
    for site_id, item in hist:
        last.setdefault(site_id, item.saved_at)
    return AdminOverview(
        sites=[AdminSite(slug=s.slug, name=s.name, owner=email, active=s.active, k_tke=s.k_tke, k_cis=s.k_cis,
                         k_conv=s.k_tke_conv, k_saved_at=last.get(s.id)) for s, email in sites],
        k_history=[AdminKEntry(site=slug_of.get(site_id, "?"), **item.model_dump()) for site_id, item in hist],
    )
