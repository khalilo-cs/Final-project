import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import token


def bearer(sub, role):
    return token(sub, role)["Authorization"].removeprefix("Bearer ")


def test_websocket_viva_answer_and_end(client, people, started):
    sid = started["session_id"]
    with client.websocket_connect(f"/ws/viva/{sid}") as ws:
        ws.send_json({"type": "auth", "token": bearer(people["student"], "student")})
        state = ws.receive_json()
        assert state["type"] == "state" and state["question_number"] == 1
        assert "transcript" not in state  # no grading details during the viva
        ws.send_json({"type": "answer", "answer": "الدالة تحسب الغرامة", "question_number": 1})
        after = ws.receive_json()
        assert after["question_number"] == 2
        # A repeated answer for question 1 (after a reconnect) is ignored.
        ws.send_json({"type": "answer", "answer": "مكرر", "question_number": 1})
        assert ws.receive_json()["question_number"] == 2
        ws.send_json({"type": "heartbeat"})
        assert ws.receive_json()["status"] == "in_progress"
        ws.send_json({"type": "end"})
        final = ws.receive_json()
        assert final["status"] != "in_progress" and final["overall_score"] is not None
    results = client.get(f"/api/v1/viva/{sid}/results", headers=token(people["student"], "student"))
    assert results.status_code == 200 and results.json()["questions"] == 1


def test_websocket_rejects_bad_tokens_and_strangers(client, people, started):
    sid = started["session_id"]
    with client.websocket_connect(f"/ws/viva/{sid}") as ws:
        ws.send_json({"type": "auth", "token": "not-a-token"})
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 4401
    with client.websocket_connect(f"/ws/viva/{sid}") as ws:
        ws.send_json({"type": "auth", "token": bearer(people["other"], "student")})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_staff_cannot_answer_over_the_socket(client, people, started):
    with client.websocket_connect(f"/ws/viva/{started['session_id']}") as ws:
        ws.send_json({"type": "auth", "token": bearer(people["faculty"], "faculty")})
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "answer", "answer": "x"})
        reply = ws.receive_json()
        assert reply["type"] == "error" and reply["status"] == 403


def test_next_question_and_results_over_http(client, people, started):
    sid = started["session_id"]
    student = token(people["student"], "student")
    nxt = client.get(f"/api/v1/viva/{sid}/next-question", headers=student).json()
    assert nxt["question_number"] == 1 and nxt["current_question"]["text"]
    assert client.get(f"/api/v1/viva/{sid}/results", headers=student).status_code == 409
    assert client.get(f"/api/v1/viva/{sid}/results",
                      headers=token(people["faculty"], "faculty")).status_code == 200  # fmt: skip
