import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.models.notification import Notification
from app.routes.deps import CurrentPrincipal, DbSession, not_found
from app.services.grading import now_utc

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])
LIMIT = 50


class NotificationOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    body: str
    link: str | None
    project_id: uuid.UUID | None
    created_at: str
    read: bool


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


def _out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, kind=n.kind, title=n.title, body=n.body, link=n.link,
        project_id=n.project_id, created_at=n.created_at.isoformat(), read=n.read_at is not None,
    )  # fmt: skip


@router.get("", response_model=NotificationList)
def my_notifications(db: DbSession, principal: CurrentPrincipal, unread_only: bool = False):
    """The caller's latest notifications, newest first."""
    query = select(Notification).where(Notification.user_id == principal.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    items = db.scalars(query.order_by(Notification.created_at.desc()).limit(LIMIT)).all()
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == principal.id, Notification.read_at.is_(None))
    )
    return NotificationList(unread=unread or 0, items=[_out(n) for n in items])


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(notification_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    notification = db.get(Notification, notification_id)
    if notification is None or notification.user_id != principal.id:
        raise not_found("Notification")
    if notification.read_at is None:
        notification.read_at = now_utc()
        db.commit()
    return _out(notification)


@router.post("/read-all")
def mark_all_read(db: DbSession, principal: CurrentPrincipal):
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == principal.id, Notification.read_at.is_(None))
        .values(read_at=now_utc())
    )
    db.commit()
    return {"marked": result.rowcount}
