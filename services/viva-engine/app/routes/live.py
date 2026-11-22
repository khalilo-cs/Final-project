"""Live viva over a WebSocket: WS /ws/viva/{session_id} (plan, section 4.4).

The HTTP endpoints stay the reference (they survive weak connections best); the
socket is the same dialogue with pushed updates of the clock and state.

Protocol (JSON text frames):
  client -> {"type": "auth", "token": "<access token>"}       first frame, within 10 s
  client -> {"type": "heartbeat"}
  client -> {"type": "answer", "answer": "...", "question_number": 3}
  client -> {"type": "end"}
  server -> {"type": "state", ...the same object as GET /api/v1/viva/{id}}
  server -> {"type": "error", "detail": "..."}
The token travels in a frame, not in the URL, so it never reaches access logs.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.database import SessionLocal
from app.engine import dialogue
from app.routes.deps import Principal, principal_from_token
from app.routes.viva import _load, _state

router = APIRouter(tags=["viva"])

AUTH_TIMEOUT = 10
TICK_SECONDS = 15
MAX_FRAME = 16_000


def _handle(session_id: str, principal: Principal, message: dict) -> dict:
    with SessionLocal() as db:
        session = _load(db, session_id, principal)
        is_student = principal.id == str(session.student_id)
        kind = message.get("type")
        if kind in ("heartbeat", "state") and is_student:
            dialogue.touch(db, session)
        elif kind == "answer":
            if not is_student:
                raise HTTPException(403, "Only the student answers")
            text = str(message.get("answer") or "").strip()[:8000]
            if not text:
                raise HTTPException(422, "Empty answer")
            if session.status != "in_progress" or session.current is None:
                raise HTTPException(409, "The viva has ended")
            dialogue.touch(db, session)
            number = message.get("question_number")
            current = len(dialogue.transcript(db, session)) + 1
            if number is None or number == current:
                dialogue.answer(db, session, text)
        elif kind == "end":
            if session.status == "in_progress":
                dialogue.end(db, session)
        elif kind not in ("heartbeat", "state"):
            raise HTTPException(400, "Unknown message type")
        return {"type": "state", **_state(db, session, principal)}


@router.websocket("/ws/viva/{session_id}")
async def live_viva(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        first = json.loads(await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT))
        principal = principal_from_token(str(first.get("token", "")))
        await websocket.send_json(await run_in_threadpool(_handle, session_id, principal,
                                                          {"type": "state"}))  # fmt: skip
    except (TimeoutError, ValueError, AttributeError, HTTPException):
        await websocket.close(code=4401)
        return
    except WebSocketDisconnect:
        return
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), TICK_SECONDS)
            except TimeoutError:
                raw = '{"type": "state"}'  # push the clock regularly
            if len(raw) > MAX_FRAME:
                await websocket.send_json({"type": "error", "detail": "Message too large"})
                continue
            try:
                message = json.loads(raw)
                if not isinstance(message, dict):
                    raise ValueError
                reply = await run_in_threadpool(_handle, session_id, principal, message)
            except ValueError:
                reply = {"type": "error", "detail": "Invalid JSON"}
            except HTTPException as exc:
                reply = {"type": "error", "detail": exc.detail, "status": exc.status_code}
            await websocket.send_json(reply)
            if reply.get("type") == "state" and reply.get("status") != "in_progress":
                await websocket.close(code=1000)
                return
    except WebSocketDisconnect:
        return
