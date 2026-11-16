import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.routes.deps import CurrentPrincipal, DbSession
from app.services import uploads

router = APIRouter(prefix="/api/v1/uploads", tags=["resumable uploads"])


class NewUpload(BaseModel):
    kind: Literal["code", "report", "database"]
    filename: str = Field(min_length=1, max_length=300)
    size: int = Field(gt=0)


def _out(session) -> dict:
    return {
        "id": str(session.id),
        "kind": session.kind,
        "filename": session.filename,
        "size": session.size,
        "offset": session.received,
        "complete": session.received == session.size,
        "chunk_size": uploads.RECOMMENDED_CHUNK_BYTES,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create(data: NewUpload, db: DbSession, principal: CurrentPrincipal):
    """Start an upload that survives dropped connections (see PATCH)."""
    if not principal.is_student:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only students submit projects")
    return _out(uploads.create(db, principal.id, data.kind, data.filename, data.size))


@router.get("/{upload_id}")
def progress(upload_id: uuid.UUID, db: DbSession, principal: CurrentPrincipal):
    """Where to continue from after a disconnect."""
    return _out(uploads.get_own(db, principal.id, upload_id))


@router.patch("/{upload_id}")
async def append(
    upload_id: uuid.UUID,
    request: Request,
    db: DbSession,
    principal: CurrentPrincipal,
    upload_offset: Annotated[int, Header(ge=0)],
    x_chunk_crc32: Annotated[int, Header(ge=0, le=0xFFFFFFFF)],
):
    """Append one piece at `Upload-Offset`. 409 returns the real offset to continue from."""
    session = uploads.get_own(db, principal.id, upload_id)
    data = bytearray()
    async for piece in request.stream():
        data += piece
        if len(data) > uploads.MAX_CHUNK_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Piece is too large")
    uploads.append(db, session, upload_offset, bytes(data), x_chunk_crc32)
    return _out(session)
