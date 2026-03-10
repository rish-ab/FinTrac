# =============================================================
# src/api/routes/alerts.py
# =============================================================

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_current_user
from src.db.models import AlertQueue, UserIdentity
from src.db.session import get_db
from pydantic import BaseModel

router = APIRouter()


class AlertResponse(BaseModel):
    id:            str
    alert_type:    str
    trigger_value: Optional[float]
    triggered_at:  datetime
    delivered_at:  Optional[datetime]
    status:        str
    channel:       str

    model_config = {"from_attributes": True}


@router.get(
    "/",
    response_model = List[AlertResponse],
    summary        = "List your alerts",
)
async def list_alerts(
    status:       Optional[str] = Query(default=None, description="Filter by status: PENDING, SENT"),
    limit:        int           = Query(default=50, le=200),
    current_user: UserIdentity  = Depends(get_current_user),
    db:           AsyncSession  = Depends(get_db),
) -> List[AlertResponse]:

    query = (
        select(AlertQueue)
        .where(AlertQueue.user_id == current_user.id)
        .order_by(AlertQueue.triggered_at.desc())
        .limit(limit)
    )

    if status:
        query = query.where(AlertQueue.status == status.upper())

    result = await db.execute(query)
    alerts = result.scalars().all()
    return [AlertResponse.model_validate(a) for a in alerts]