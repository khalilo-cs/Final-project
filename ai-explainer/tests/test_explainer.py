"""اختبارات شارح الأخطاء (بلا شبكة): الحارس، الاحتياطي، الذاكرة المؤقتة، شكل طلب Claude، وخط الأنابيب كاملًا."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dhad_explainer import guard, knowledge, prompt  # noqa: E402
from dhad_explainer.explainer import Cache, dhad_binary, explain, explain_file  # noqa: E402
from dhad_explainer.providers import ClaudeProvider, OfflineProvider, ProviderError, ProviderUnavailable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "tests" / "corpus"
DHAD = dhad_binary()
ERR = {"code": 1003, "codeStr": "ضاد-1003", "message": "لا يمكن جمع نص مع عدد", "line": 3, "severity": "error"}
SRC = "دع العمر = ٢٥\nدع الاسم = \"ليلى\"\nدع الرسالة = \"العمر: \" + العمر\nاطبع(الرسالة)"


class FakeProvider:
    name = "fake"
    model = "fake-1"

    def __init__(self, *texts: str, exc: Exception | None = None):
        self.texts = list(texts)
        self.exc = exc
        self.calls = 0

    def generate(self, system: str, user: str) -> str:
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.texts.pop(0)


class GuardTests(unittest.TestCase):
    def ok(self, text, level, err=ERR):
        return guard.check(text, err, level, DHAD)

    def test_accepts_good_explanations(self):
        self.assertTrue(self.ok("حاولت أن تجمع كلمات مع رقم، واللغة لا تعرف كيف تجمعهما معًا.", 1).ok)
        self.assertTrue(self.ok("في السطر ٣ تجمع النص \"العمر: \" مع العدد في المتغير العمر، والجمع يعمل بين عددين أو بين نصين فقط.", 2).ok)
        self.assertTrue(self.ok("هكذا تضم نصًا وعددًا:\n```dhad\nاطبع(\"النتيجة: \" + نص(٧))\n```", 3).ok)
        self.assertTrue(self.ok("في السطر 3 حوّل العدد إلى نص:\n```dhad\nدع الرسالة = \"العمر: \" + نص(العمر)\n```", 4).ok)

    def test_rejections(self):
        cases = [
            ("You tried to add text and a number together, which is not allowed.", 1, "ليس بالعربية"),
            ("هذا الخطأ ضاد-1001 يعني أن المتغير غير معرّف.", 1, "كود خطأ آخر"),
            ("المشكلة في السطر ٥ حيث تجمع نصًا مع عدد.", 2, "سطرًا غير"),
            ("تجمع نصًا مع عدد، والجمع يعمل بين عددين فقط.", 2, "لا يذكر السطر"),
            ("الحل:\n```dhad\nاطبع(١)\n```", 1, "كتل الكود"),
            ("في السطر ٣:\n```dhad\nدع = = \n```", 4, "ليست ضادًا"),
            ("كلمة " * 70, 1, "طويل"),
            ("اضغط هنا <script>alert(1)</script> للحل", 1, "غير آمن"),
            ("في السطر ٣:\n```python\nprint('x')\n```", 4, "بلغة أخرى"),
        ]
        for text, level, reason in cases:
            r = self.ok(text, level)
            self.assertFalse(r.ok, text)
            self.assertTrue(any(reason in x for x in r.reasons), (text, r.reasons))


class PipelineTests(unittest.TestCase):
    def test_system_prompt_is_stable_and_complete(self):
        a, b = prompt.system_prompt(), prompt.system_prompt()
        self.assertEqual(a, b, "موجّه النظام يجب أن يكون ثابتًا بايتًا ببايت ليُخزَّن مؤقتًا")
        for code in knowledge.pages():
            self.assertIn(f"# ضاد-{code:04d}", a)

    def test_user_message_marks_line(self):
        m = prompt.user_message(ERR, SRC, 2)
        self.assertIn("→ 3 │ دع الرسالة", m)
        self.assertIn("المستوى المطلوب: 2", m)

    def test_valid_output_passes_and_is_cached(self):
        p = FakeProvider("حاولت أن تجمع كلمات مع رقم، واللغة لا تعرف كيف تجمعهما.")
        with tempfile.TemporaryDirectory() as d:
            cache = Cache(Path(d) / "c.json")
            r1 = explain(ERR, SRC, 1, p, cache, DHAD)
            self.assertFalse(r1.fallback_used)
            r2 = explain(ERR, SRC, 1, p, Cache(Path(d) / "c.json"), DHAD)
            self.assertTrue(r2.cached)
            self.assertEqual(r1.text, r2.text)
            self.assertEqual(p.calls, 1)

    def test_guard_rejection_falls_back_to_docs(self):
        r = explain(ERR, SRC, 1, FakeProvider("This is an English answer only."), None, DHAD)
        self.assertTrue(r.fallback_used)
        self.assertFalse(r.guard_ok)
        self.assertIn("نص", r.text)

    def test_provider_failure_falls_back(self):
        for exc in (ProviderUnavailable("down"), ProviderError("bad key")):
            r = explain(ERR, SRC, 2, FakeProvider(exc=exc), None, DHAD)
            self.assertTrue(r.fallback_used)
            self.assertIn("السطر 3", r.text)

    def test_offline_examples_are_valid_dhad(self):
        off = OfflineProvider()
        for code in knowledge.pages():
            e = {"code": code, "codeStr": f"ضاد-{code:04d}", "message": "م", "line": 1}
            for level in (1, 2, 3, 4):
                text = off.explain(e, "اطبع(١)", level)
                self.assertTrue(text.strip(), (code, level))
                if level >= 3:
                    for _, body in guard.CODE_BLOCK.findall(text):
                        self.assertFalse(guard.syntax_error(body, DHAD), (code, body))


class ClaudeRequestTests(unittest.TestCase):
    """شكل الطلب المرسل إلى Anthropic API، بعميل وهمي."""

    def make(self, stop_reason="end_turn", text="شرح بالعربية للمبتدئ."):
        captured = {}

        def create(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                stop_reason=stop_reason,
                content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
                usage=SimpleNamespace(cache_read_input_tokens=0),
            )

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        return ClaudeProvider(client=client), captured

    def test_request_shape(self):
        p, captured = self.make()
        out = p.generate("نظام", "مستخدم")
        self.assertEqual(out, "شرح بالعربية للمبتدئ.")
        self.assertEqual(captured["model"], "claude-opus-5-5")
        self.assertEqual(captured["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", captured["betas"])
        self.assertEqual(captured["output_config"], {"effort": "low"})
        self.assertEqual(captured["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertNotIn("thinking", captured, "الثينكنج يبقى تلقائيًا (adaptive)")
        self.assertNotIn("temperature", captured)

    def test_missing_credentials_falls_back(self):
        def create(**_):
            raise TypeError("Could not resolve authentication method")

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        r = explain(ERR, SRC, 1, ClaudeProvider(client=client), None, DHAD)
        self.assertTrue(r.fallback_used)
        self.assertIn("بيانات اعتماد", r.error_reason)

    def test_refusal_and_truncation_raise(self):
        for stop in ("refusal", "max_tokens"):
            p, _ = self.make(stop_reason=stop)
            with self.assertRaises(ProviderError):
                p.generate("ن", "م")


@unittest.skipUnless(DHAD, "يحتاج الأمر dhad (cargo build)")
class FileTests(unittest.TestCase):
    def test_static_error(self):
        err, res = explain_file(CORPUS / "خطأ_1003.ضاد", [1, 2, 3, 4], OfflineProvider())
        self.assertEqual(err["code"], 1003)
        self.assertEqual([r.level for r in res], [1, 2, 3, 4])

    def test_runtime_error(self):
        err, _ = explain_file(CORPUS / "خطأ_2001.ضاد", [1], OfflineProvider())
        self.assertEqual(err["code"], 2001)

    def test_clean_program(self):
        err, res = explain_file(REPO / "examples" / "مرحبا.ضاد", [1], OfflineProvider())
        self.assertIsNone(err)
        self.assertEqual(res, [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
