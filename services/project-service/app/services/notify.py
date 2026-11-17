"""In-app notifications (and e-mail when SMTP is configured).

Callers add notifications inside their own transaction; e-mails go out after the
commit on a background thread so a slow or broken mail server never blocks a request.
"""

import logging
import smtplib
import threading
import uuid
from collections.abc import Iterable
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.course import Course
from app.models.notification import Notification
from app.models.project import Project
from app.services.internal_http import lookup_users

log = logging.getLogger(__name__)


def notify(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    kind: str,
    title: str,
    body: str = "",
    project: Project | None = None,
    link: str | None = None,
) -> list[Notification]:
    if link is None and project is not None:
        link = f"/projects/{project.id}"
    created = []
    for user_id in dict.fromkeys(user_ids):  # unique, order kept
        notification = Notification(
            user_id=user_id,
            kind=kind,
            title=title[:300],
            body=body,
            link=link,
            project_id=project.id if project is not None else None,
        )
        db.add(notification)
        created.append(notification)
    return created


def course_faculty(db: Session, course_id: uuid.UUID) -> list[uuid.UUID]:
    faculty = db.scalar(select(Course.faculty_id).where(Course.id == course_id))
    return [faculty] if faculty is not None else []


def send_emails(notifications: list[Notification]) -> None:
    """Best effort, after commit. No-op unless SMTP_HOST is set."""
    settings = get_settings()
    if not settings.smtp_host or not notifications:
        return
    messages = [(n.user_id, n.title, n.body, n.link) for n in notifications]
    threading.Thread(target=_deliver, args=(messages,), daemon=True).start()


def _deliver(messages: list[tuple]) -> None:
    settings = get_settings()
    users = lookup_users({user_id for user_id, *_ in messages})
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            for user_id, title, body, link in messages:
                address = (users.get(str(user_id)) or {}).get("email")
                if not address:
                    continue
                message = EmailMessage()
                message["Subject"] = title
                message["From"] = settings.smtp_from
                message["To"] = address
                url = f"{settings.public_url.rstrip('/')}{link}" if link else settings.public_url
                message.set_content(f"{body}\n\n{url}\n\n— مِحَكّ (Mihakk)")
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException):
        log.warning("could not send notification e-mails", exc_info=True)
