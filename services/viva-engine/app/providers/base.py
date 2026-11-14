"""A provider writes questions and grades answers. The built-in one needs no model."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

QUESTION_TYPES = ("understanding", "technical", "challenge", "verification")
VERDICTS = ("correct", "partial", "wrong", "evasive")


@dataclass
class Question:
    key: str  # stable template/topic key, used to learn which questions work
    type: str
    level: int  # 1-4
    text: str
    expected_points: list[str] = field(default_factory=list)
    related_file: str | None = None
    related_lines: str | None = None
    code: str | None = None  # snippet shown next to the question
    source: str = "template"


@dataclass
class Evaluation:
    score: float  # 0-100
    verdict: str
    reasoning: str = ""
    confidence: float = 0.5


class ProviderError(Exception):
    pass


class Provider(ABC):
    name: str

    def available(self) -> bool:
        return True

    @abstractmethod
    def generate_questions(
        self, context: dict, language: str, count: int, examples: list[dict], knowledge: list[str]
    ) -> list[Question]: ...

    @abstractmethod
    def evaluate(
        self, question: Question, answer: str, language: str, examples: list[dict]
    ) -> Evaluation: ...
