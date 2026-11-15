import io
import time

import jwt
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.config import get_settings
from app.main import app
from app.render import BlockedResource, _no_external_resources, render_html, render_pdf
from tests.sample import REPORT

client = TestClient(app)


def token(role="service"):
    payload = {"sub": "svc", "role": role, "type": "access", "exp": time.time() + 60}
    return {"Authorization": "Bearer " + jwt.encode(payload, get_settings().jwt_secret, "HS256")}


def test_staff_report_has_everything():
    html = render_html({**REPORT, "audience": "staff"})
    for text in ("الدرجة المقترحة", "تفصيل الدرجة المقترحة", "أصالة المشروع (للدكتور فقط)",
                 "98% of the code matches", "calculate_fine", "SQL Injection", "سارة علي",
                 "<svg"):  # fmt: skip
        assert text in html, text


def test_student_report_hides_suspicion_and_suggestion():
    html = render_html({**REPORT, "audience": "student", "authenticity": None})
    assert "للدكتور فقط" not in html and "98% of the code" not in html
    assert "الدرجة المقترحة" not in html and "تفصيل الدرجة" not in html
    assert "أصالة المشروع" not in html  # not even its score in the summary
    assert "استخدم الاستعلامات المُعدّة" in html


def test_student_text_is_escaped():
    html = render_html({**REPORT, "audience": "staff"})
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_pdf_is_valid_and_fetches_nothing():
    pdf = render_pdf({**REPORT, "audience": "staff"})
    reader = PdfReader(io.BytesIO(pdf))
    assert pdf.startswith(b"%PDF") and 1 <= len(reader.pages) <= 6
    with pytest.raises(BlockedResource):
        _no_external_resources("file:///etc/passwd")
    # An image tag smuggled into a title stays text, so nothing is fetched.
    render_pdf({**REPORT, "project": {"title": '<img src="http://169.254.169.254/x">'}})


def test_endpoint_student_variant_strips_authenticity(monkeypatch):
    seen = {}

    def fake_render(payload):
        seen.update(payload)
        return b"%PDF-fake"

    monkeypatch.setattr("app.routes.reports.render_pdf", fake_render)
    body = {**REPORT, "audience": "student"}
    assert (
        client.post("/internal/reports/student", json=body, headers=token("admin")).status_code
        == 403
    )
    response = client.post("/internal/reports/student", json=body, headers=token())
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert seen["authenticity"] is None
