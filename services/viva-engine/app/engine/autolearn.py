"""Automatic learning: nobody has to add anything by hand.

Sources, all automatic:
  * the built-in knowledge pack (seeded at startup);
  * every analyzed project (topics, technologies, code) -> new topics to learn;
  * every finished viva (answers) -> new key points, agreed grades;
  * official documentation of each topic seen in projects (fetched by itself);
  * a language model as a teacher (Claude when enabled) for topics it does not know.

What a teacher model writes is stored as knowledge and questions the built-in engine
can reuse offline. It is never exported as training data: the fine-tuning export
contains professors' grades only (Anthropic's terms do not allow using Claude's
outputs to train a competing model).
"""

import logging
import re
import uuid
from collections import Counter
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.knowledge import builtin_pack, store
from app.models import (
    AutoLabel,
    BankQuestion,
    KnowledgeItem,
    KnowledgeSource,
    LearnedPoint,
    LearningEvent,
    Topic,
    VivaQA,
    VivaSession,
)
from app.providers.base import QUESTION_TYPES, ProviderError
from app.text.normalize import normalize, tokenize

log = logging.getLogger(__name__)
SYSTEM_USER = uuid.UUID(int=0)

# Official documentation the learner fetches by itself for each topic.
CATALOG = {
    "tech:flask": ["https://flask.palletsprojects.com/en/stable/quickstart/"],
    "tech:django": ["https://docs.djangoproject.com/en/stable/intro/overview/"],
    "tech:react": ["https://react.dev/learn"],
    "tech:mysql": ["https://dev.mysql.com/doc/refman/8.4/en/innodb-introduction.html"],
    "tech:postgresql": ["https://www.postgresql.org/docs/current/tutorial-concepts.html"],
    "vuln:sql_injection": [
        "https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"
    ],
    "vuln:xss": [
        "https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html"
    ],
    "vuln:command_injection": [
        "https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html"
    ],
    "vuln:hardcoded_secret": [
        "https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"
    ],
    "vuln:insecure_deserialization": [
        "https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html"
    ],
    "vuln:weak_hash": [
        "https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"
    ],
    "general:authentication": [
        "https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html"
    ],
}

AUTO_LABEL_MIN_CONFIDENCE = 0.8
POINT_MIN_SUPPORT = 3
_STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "will", "into", "when", "then",
    "they", "there", "which", "what", "because", "also", "uses", "used", "using",
    "التي", "الذي", "هذا", "هذه", "لان", "لكي", "حيث", "عند", "على", "الى", "مع", "ثم",
    "كان", "يتم", "باستخدام", "استخدام", "عن", "او", "في", "من", "ان", "لا", "ما",
}  # fmt: skip


def event(db: Session, kind: str, summary: str, **details) -> None:
    db.add(LearningEvent(kind=kind, summary=summary, details=details))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower().replace("spring boot", "spring"))


# -- built-in pack ---------------------------------------------------------------------


def seed_builtin(db: Session) -> int:
    """Load the built-in knowledge pack once. Returns the number of new topics."""
    added = 0
    for key, topic in builtin_pack.TOPICS.items():
        if db.get(Topic, key) is not None:
            continue
        db.add(
            Topic(
                key=key,
                title=topic["title"],
                source="builtin",
                docs_status="pending" if key in CATALOG else "none",
                teacher_status="skipped",
                learned_at=datetime.now(UTC),
            )
        )
        for language in ("ar", "en"):
            store.add_item(db, "builtin", key, topic[language], title=topic["title"])
        for language, kind, level, text, points in topic["questions"]:
            db.add(
                BankQuestion(topic=key, language=language, question_type=kind, level=level,
                             text=text, expected_points=points + topic["points"][:2],
                             source="builtin")
            )  # fmt: skip
        added += 1
    if added:
        event(db, "builtin", f"حُمّلت حزمة المعرفة المدمجة: {added} موضوعاً",
              version=builtin_pack.PACK_VERSION)  # fmt: skip
    db.commit()
    return added


# -- topics from projects --------------------------------------------------------------


def topics_from_context(context: dict) -> dict[str, str]:
    """topic key -> title, for everything a project uses or suffers from."""
    topics: dict[str, str] = {}
    for name in context.get("technologies", []):
        topics[f"tech:{_slug(name)}"] = name
    for vulnerability in context.get("vulnerabilities", []):
        key = builtin_pack.VULNERABILITY_TOPICS.get(vulnerability.get("type", ""))
        if key:
            topics[key] = vulnerability["type"]
    for issue in (context.get("database") or {}).get("issues", []):
        key = builtin_pack.DATABASE_TOPICS.get(issue.get("type", ""))
        if key:
            topics[key] = builtin_pack.TOPICS[key]["title"]
    if (context.get("database") or {}).get("tables"):
        topics.setdefault("db:keys", builtin_pack.TOPICS["db:keys"]["title"])
    if "MVC" in context.get("architecture", []):
        topics["arch:mvc"] = "MVC"
    if any(f.get("cyclomatic_complexity", 0) >= 10 for f in context.get("functions", [])):
        topics["code:complexity"] = builtin_pack.TOPICS["code:complexity"]["title"]
    return topics


def learn_from_project(db: Session, project_id: str, context: dict) -> dict:
    found = topics_from_context(context)
    new = []
    for key, title in found.items():
        topic = db.get(Topic, key)
        if topic is None:
            topic = Topic(key=key, title=title, source="project",
                          docs_status="pending" if key in CATALOG else "none",
                          teacher_status="pending")  # fmt: skip
            db.add(topic)
            new.append(key)
        topic.seen_in_projects = (topic.seen_in_projects or 0) + 1

    # The project's own code becomes searchable knowledge for staff. It is never put in
    # prompts or questions for other students.
    db.execute(delete(KnowledgeItem).where(KnowledgeItem.source_ref == f"project:{project_id}"))
    pieces = [f"{context.get('title', '')}: {', '.join(context.get('technologies', []))}"]
    for function in context.get("functions", []):
        if function.get("code"):
            pieces.append(f"{function['file']} {function['function']}\n{function['code']}")
    for table in (context.get("database") or {}).get("tables", []):
        pieces.append(f"table {table['name']} pk={table.get('primary_key')}")
    for piece in pieces:
        store.add_item(db, "project", f"project:{project_id}", piece, title=context.get("title"))
    event(db, "project",
          f"تعلّم من مشروع «{context.get('title', '')}»: {len(found)} مواضيع"
          + (f"، منها {len(new)} جديدة" if new else ""),
          topics=sorted(found), new_topics=new)  # fmt: skip
    db.commit()
    return {"topics": sorted(found), "new_topics": new}


def bank_questions(db: Session, topics: list[str], language: str, per_topic: int = 2) -> list:
    from app.providers.base import Question

    questions = []
    for topic in topics:
        rows = db.scalars(
            select(BankQuestion)
            .where(BankQuestion.topic == topic, BankQuestion.language == language)
            .order_by(BankQuestion.created_at)
            .limit(per_topic)
        )
        for row in rows:
            questions.append(
                Question(key=f"bank:{topic}:{str(row.id)[:8]}", type=row.question_type,
                         level=row.level, text=row.text, expected_points=row.expected_points,
                         source=row.source)
            )  # fmt: skip
    return questions


# -- learning from vivas ---------------------------------------------------------------


def _terms(text: str) -> set[str]:
    return {t.text for t in tokenize(text) if len(t.text) >= 4 and t.text not in _STOPWORDS}


def _discover_points(db: Session, template_key: str) -> list[tuple[str, int]]:
    rows = db.execute(
        select(VivaQA.answer, VivaQA.score, VivaQA.question, VivaQA.expected_points).where(
            VivaQA.template_key == template_key
        )
    ).all()
    strong = [_terms(a) for a, s, _, _ in rows if s >= 75]
    weak = [_terms(a) for a, s, _, _ in rows if s < 40]
    if len(strong) < POINT_MIN_SUPPORT:
        return []
    known = set()
    for _, _, question, expected in rows[:1]:
        known = _terms(question) | {normalize(p) for p in expected or []}
    strong_counts = Counter(term for terms in strong for term in terms)
    weak_counts = Counter(term for terms in weak for term in terms)
    points = []
    for term, count in strong_counts.items():
        if term in known or count < POINT_MIN_SUPPORT or count < len(strong) / 2:
            continue
        if weak and weak_counts[term] / len(weak) > 0.2:
            continue  # weak answers use it too: it does not show understanding
        points.append((term, count))
    return sorted(points, key=lambda p: -p[1])[:8]


def learned_points(db: Session, template_key: str, limit: int = 5) -> list[str]:
    return list(
        db.scalars(
            select(LearnedPoint.point)
            .where(LearnedPoint.template_key == template_key)
            .order_by(LearnedPoint.support.desc())
            .limit(limit)
        )
    )


def learn_from_session(db: Session, session: VivaSession) -> dict:
    answers = list(db.scalars(select(VivaQA).where(VivaQA.session_id == session.id)))
    labels = 0
    for qa in answers:
        graders = [k for k in (qa.provider_scores or {}) if k != "memory"]
        agreed = len(graders) >= 2 and qa.confidence >= AUTO_LABEL_MIN_CONFIDENCE
        if agreed and db.get(AutoLabel, qa.id) is None:
            db.add(AutoLabel(qa_id=qa.id, score=qa.score, verdict=qa.verdict,
                             agreement=qa.confidence))  # fmt: skip
            labels += 1
    db.flush()

    new_points = []
    for key in {qa.template_key for qa in answers}:
        for point, support in _discover_points(db, key):
            row = db.get(LearnedPoint, (key, point))
            if row is None:
                db.add(LearnedPoint(template_key=key, point=point, support=support))
                new_points.append((key, point))
            else:
                row.support = support
    if labels or new_points:
        event(db, "session",
              f"تعلّم من مناقشة: {labels} تقييم متفق عليه، {len(new_points)} نقطة إجابة جديدة",
              session_id=str(session.id), new_points=new_points[:20])  # fmt: skip
    return {"auto_labels": labels, "new_points": new_points}


# -- background cycle: documentation + teacher -----------------------------------------

TEACHER_SCHEMA = {
    "type": "object",
    "properties": {
        "explanation_ar": {"type": "string"},
        "explanation_en": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "language": {"type": "string", "enum": ["ar", "en"]},
                    "type": {"type": "string", "enum": list(QUESTION_TYPES)},
                    "level": {"type": "integer"},
                    "text": {"type": "string"},
                    "expected_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["language", "type", "level", "text", "expected_points"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["explanation_ar", "explanation_en", "key_points", "questions"],
    "additionalProperties": False,
}
TEACHER_SYSTEM = """You teach an automatic examiner of computer science graduation projects \
about one topic. Write a short accurate explanation in Arabic and in English (3-5 \
sentences each), the key points a student who understands the topic would mention, and \
6 viva questions (3 Arabic, 3 English) that apply to ANY project using this topic, at \
levels 1-4, each with the expected points of a good answer."""


def _teachers():
    from app.engine.dialogue import active_providers
    from app.providers.llm import LLMProvider

    models = [p for p in active_providers() if isinstance(p, LLMProvider)]
    return sorted(models, key=lambda p: p.name != "claude")  # Claude first when enabled


def teach(db: Session, topic: Topic) -> bool:
    for teacher in _teachers():
        try:
            data = teacher._complete_json(
                TEACHER_SYSTEM, f"Topic: {topic.title} ({topic.key})", TEACHER_SCHEMA, "medium"
            )
        except ProviderError as exc:
            log.warning("%s could not teach %s: %s", teacher.name, topic.key, exc)
            continue
        source = f"teacher:{teacher.name}"
        for language in ("ar", "en"):
            text = data.get(f"explanation_{language}", "").strip()
            if text:
                store.add_item(db, source, topic.key, text, title=topic.title)
        stored = 0
        for item in data.get("questions", [])[:8]:
            if item.get("type") in QUESTION_TYPES and item.get("text", "").strip():
                db.add(
                    BankQuestion(topic=topic.key, language=item["language"],
                                 question_type=item["type"],
                                 level=min(4, max(1, int(item.get("level", 2)))),
                                 text=item["text"].strip(),
                                 expected_points=(item.get("expected_points") or [])[:8],
                                 source=source)
                )  # fmt: skip
                stored += 1
        topic.teacher_status = "done"
        topic.learned_at = datetime.now(UTC)
        event(db, "teacher", f"{teacher.name} علّم النظام موضوع «{topic.title}»: {stored} أسئلة",
              topic=topic.key, teacher=teacher.name)  # fmt: skip
        return True
    return False


def fetch_docs(db: Session, topic: Topic) -> int:
    indexed = 0
    for url in CATALOG.get(topic.key, []):
        source = db.scalar(select(KnowledgeSource).where(KnowledgeSource.url == url))
        if source is None:
            source = KnowledgeSource(url=url, added_by=SYSTEM_USER)
            db.add(source)
            db.flush()
        store.ingest_url(db, source)
        if source.status == "indexed":
            indexed += source.items
    topic.docs_status = "done" if indexed else "pending"
    if indexed:
        event(db, "web", f"تعلّم من التوثيق الرسمي لـ «{topic.title}»: {indexed} مقاطع",
              topic=topic.key, urls=CATALOG.get(topic.key, []))  # fmt: skip
    return indexed


def run_cycle(db: Session) -> dict:
    """One learning round: docs and teacher for the topics most often seen first."""
    limit = get_settings().auto_learn_topics_per_cycle
    pending = db.scalars(
        select(Topic)
        .where((Topic.docs_status == "pending") | (Topic.teacher_status == "pending"))
        .where(Topic.attempts < 5)
        .order_by(Topic.seen_in_projects.desc(), Topic.key)
        .limit(limit)
    ).all()
    done = {"docs": 0, "taught": 0, "topics": [t.key for t in pending]}
    have_teacher = bool(_teachers())
    for topic in pending:
        topic.attempts += 1
        if topic.docs_status == "pending":
            done["docs"] += fetch_docs(db, topic)
        if topic.teacher_status == "pending" and have_teacher and teach(db, topic):
            done["taught"] += 1
        if topic.docs_status != "pending" and topic.teacher_status != "pending":
            topic.learned_at = topic.learned_at or datetime.now(UTC)
        db.commit()
    return done


def stats(db: Session) -> dict:
    def count(model, *where):
        query = select(func.count()).select_from(model)
        for condition in where:
            query = query.where(condition)
        return db.scalar(query)

    by_source = dict(
        db.execute(select(BankQuestion.source, func.count()).group_by(BankQuestion.source)).all()
    )
    return {
        "topics": count(Topic),
        "topics_waiting": count(Topic, Topic.teacher_status == "pending"),
        "question_bank": by_source,
        "auto_labels": count(AutoLabel),
        "learned_points": count(LearnedPoint),
        "knowledge_by_source": dict(
            db.execute(
                select(KnowledgeItem.source_type, func.count()).group_by(KnowledgeItem.source_type)
            ).all()
        ),
    }
