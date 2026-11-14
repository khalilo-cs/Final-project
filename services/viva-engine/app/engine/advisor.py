"""Turns rule-based findings into a readable summary when a language model is available."""

import json

from app.engine.dialogue import active_providers
from app.providers.base import ProviderError
from app.providers.llm import LLMProvider

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
    "additionalProperties": False,
}
SYSTEM = """You are a supportive but honest supervisor of a graduation project. You get \
findings produced by automatic analysis (strengths, weaknesses, suggested improvements) \
with their evidence. Write a short summary for the student: what is good, what matters \
most to fix first and why, in plain language. Use only the given findings; do not invent \
new ones."""


def summarize(findings: dict, language: str) -> dict | None:
    for provider in active_providers():
        if not isinstance(provider, LLMProvider):
            continue
        prompt = (
            f"Language: {'Arabic' if language == 'ar' else 'English'}\n<findings>\n"
            + json.dumps(findings, ensure_ascii=False)[:20000]
            + "\n</findings>"
        )
        try:
            data = provider._complete_json(SYSTEM, prompt, SUMMARY_SCHEMA, "low")
        except ProviderError:
            continue
        if data.get("summary"):
            return {"summary": data["summary"], "written_by": provider.name}
    return None
