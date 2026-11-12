"""مزودو الشرح: Claude عبر Anthropic API، نموذج محلي عبر Ollama، ومزود حتمي بلا شبكة.

كلها خلف واجهة واحدة `generate(system, user) -> str` لتسهيل المقارنة التجريبية.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from . import knowledge
from .levels import LEVELS


class ProviderError(Exception):
    """فشل لا يُرجى معه إعادة المحاولة (مفتاح غير صالح، طلب مرفوض)."""


class ProviderUnavailable(ProviderError):
    """الخدمة غير متاحة الآن (شبكة، ضغط، حدود معدل) — يُستخدم الشرح الحتمي بدلًا منها."""


class ClaudeProvider:
    """Claude عبر حزمة anthropic الرسمية.

    - موجّه النظام (القواعد + مرجع الأخطاء كاملًا) ثابت ومُعلَّم بـ cache_control،
      فيُقرأ من الذاكرة المؤقتة في الطلبات التالية.
    - fallbacks="default": إن رفض النموذج طلبًا لأسباب أمان، يعيد الخادم تشغيله
      على نموذج بديل مناسب داخل الطلب نفسه.
    """

    name = "claude"

    def __init__(self, model: str | None = None, effort: str | None = None, client=None):
        self.model = model or os.environ.get("DHAD_LLM_MODEL", "claude-opus-5-5")
        self.effort = effort or os.environ.get("DHAD_LLM_EFFORT", "low")
        if client is None:
            import anthropic

            client = anthropic.Anthropic(timeout=60.0, max_retries=2)
        self.client = client
        self.last_usage = None

    def generate(self, system: str, user: str) -> str:
        import anthropic

        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort},
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError as e:
            raise ProviderError("مفتاح Anthropic API غير صالح") from e
        except TypeError as e:
            # تثيره الحزمة عند غياب أي بيانات اعتماد (لا مفتاح ولا ملف تعريف).
            raise ProviderError("لا توجد بيانات اعتماد لـ Anthropic API (اضبط ANTHROPIC_API_KEY)") from e
        except anthropic.BadRequestError as e:
            raise ProviderError(f"طلب مرفوض: {e.message}") from e
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            raise ProviderUnavailable(str(e)) from e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                raise ProviderUnavailable(f"خطأ خادم {e.status_code}") from e
            raise ProviderError(e.message) from e

        self.last_usage = response.usage
        if response.stop_reason == "refusal":
            raise ProviderError("رفض النموذج الطلب")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if response.stop_reason == "max_tokens" or not text:
            raise ProviderError("شرح ناقص أو فارغ")
        return text


class OllamaProvider:
    """نموذج مفتوح يعمل محليًا عبر Ollama: لا يغادر كود الطالب الجهاز."""

    name = "ollama"

    def __init__(self, model: str | None = None, url: str | None = None):
        self.model = model or os.environ.get("DHAD_OLLAMA_MODEL", "aya-expanse:8b")
        self.url = url or os.environ.get("DHAD_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")

    def generate(self, system: str, user: str) -> str:
        body = json.dumps({
            "model": self.model,
            "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 32768},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }).encode()
        req = urllib.request.Request(self.url, data=body, headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise ProviderUnavailable(f"Ollama غير متاح: {e}") from e
        text = (data.get("message") or {}).get("content", "").strip()
        if not text:
            raise ProviderError("استجابة فارغة من Ollama")
        return text


class OfflineProvider:
    """شرح حتمي مأخوذ حرفيًا من صفحات التوثيق — بلا شبكة ولا نموذج.

    يعمل احتياطيًا عند أي فشل، وخطَّ أساس في التقييم التجريبي.
    """

    name = "offline"
    model = "docs"

    def explain(self, error: dict, source: str, level: int) -> str:
        code = int(error["code"])
        md = knowledge.page(code) or ""
        meaning = knowledge.section(md, "ماذا يعني؟") or error.get("explanation") or error["message"]
        fix_section = knowledge.section(md, "كيف أصلحه؟")
        help_text = (fix_section.split("```")[0].strip() if fix_section else "") or error.get("help", "")
        line = error.get("line")
        if level == 1:
            return meaning
        if level == 2:
            where = f"المشكلة في السطر {line}: {error['message']}." if line else f"المشكلة: {error['message']}."
            return f"{where} {meaning}"
        blocks = knowledge.code_blocks(md)
        fixed = blocks[-1] if blocks else ""
        if level == 3:
            return f"إليك مثالًا مشابهًا يعمل بشكل صحيح:\n\n```dhad\n{fixed}\n```"
        where = f"في السطر {line}: " if line else ""
        return f"{where}{help_text}\n\n```dhad\n{fixed}\n```"

    def generate(self, system: str, user: str) -> str:  # للتوافق مع الواجهة
        raise NotImplementedError("استخدم explain() مباشرة")


def make(name: str):
    if name == "claude":
        return ClaudeProvider()
    if name == "ollama":
        return OllamaProvider()
    if name == "offline":
        return OfflineProvider()
    raise ValueError(f"مزود غير معروف: {name}")


__all__ = ["ClaudeProvider", "OllamaProvider", "OfflineProvider", "ProviderError", "ProviderUnavailable", "make", "LEVELS"]
