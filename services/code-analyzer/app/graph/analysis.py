"""What the knowledge graph says about the design: dependencies (FR-03.8), design
patterns (FR-03.5) and SOLID (FR-03.6). Every finding names its classes and evidence;
patterns and principles are inferred from structure, so they are hints for the viva
and the professor, not verdicts."""

import itertools
import re
from collections import defaultdict

import networkx as nx

from app.graph.build import MAX_VIEW_NODES, ProjectGraph, simple

_SINGLETON_METHODS = {"getinstance", "instance", "get_instance", "shared", "getdefault"}
_DEPENDENCY_SUFFIXES = (
    "Service",
    "Repository",
    "Repo",
    "Dao",
    "DAO",
    "Manager",
    "Gateway",
    "Client",
    "Provider",
)
_SUBSCRIBE = re.compile(r"^(subscribe|attach|register|on[A-Z]|add\w*listener|addobserver)", re.I)
_NOTIFY = re.compile(r"^(notify|emit|fire|publish|dispatch|broadcast)", re.I)
GOD_CLASS_METHODS = 15
GOD_CLASS_EFFERENT = 7
OCP_TYPE_CHECKS = 4
ISP_INTERFACE_METHODS = 8


def pagerank(graph: nx.DiGraph, damping: float = 0.85, rounds: int = 50) -> dict[str, float]:
    """Plain power iteration (networkx's version needs scipy)."""
    count = graph.number_of_nodes()
    if not count or not graph.number_of_edges():
        return {}
    rank = dict.fromkeys(graph, 1 / count)
    for _ in range(rounds):
        dangling = sum(rank[n] for n in graph if graph.out_degree(n) == 0)
        new = dict.fromkeys(graph, (1 - damping) / count + damping * dangling / count)
        for node in graph:
            out = graph.out_degree(node)
            if out:
                share = damping * rank[node] / out
                for target in graph.successors(node):
                    new[target] += share
        rank = new
    return rank


def _edges(graph: nx.MultiDiGraph, kinds: set[str]):
    return ((u, v) for u, v, kind in graph.edges(data="type") if kind in kinds)


def file_dependencies(pg: ProjectGraph) -> nx.DiGraph:
    """file A -> file B when A imports B or a class in A extends one in B."""
    deps = nx.DiGraph()
    deps.add_nodes_from(n for n, t in pg.g.nodes(data="type") if t == "file")
    for u, v in _edges(pg.g, {"imports", "extends", "implements"}):
        a, b = pg.g.nodes[u].get("file"), pg.g.nodes[v].get("file")
        if a and b and a != b:
            deps.add_edge(f"file:{a}", f"file:{b}")
    return deps


def class_dependencies(pg: ProjectGraph) -> nx.DiGraph:
    deps = nx.DiGraph()
    deps.add_nodes_from(pg.classes)
    for u, v in _edges(pg.g, {"calls", "creates", "extends", "implements"}):
        a = u if u in pg.classes else (pg.functions[u].owner if u in pg.functions else None)
        b = v if v in pg.classes else (pg.functions[v].owner if v in pg.functions else None)
        if a and b and a != b:
            deps.add_edge(a, b)
    return deps


def _label(pg: ProjectGraph, node: str) -> str:
    data = pg.g.nodes[node]
    if data["type"] == "file":
        return data["file"]
    if data["type"] == "function" and data.get("owner"):
        return f"{pg.g.nodes[data['owner']]['label']}.{data['label']}"
    return data["label"]


def dependencies(pg: ProjectGraph) -> dict:
    files = file_dependencies(pg)
    cycles = []
    for cycle in itertools.islice(nx.simple_cycles(files, length_bound=6), 5):
        cycles.append([pg.g.nodes[n]["file"] for n in cycle])
    classes = class_dependencies(pg)
    coupling = []
    for node in classes:
        ca, ce = classes.in_degree(node), classes.out_degree(node)
        if ca + ce:
            coupling.append(
                {
                    "class": _label(pg, node),
                    "file": pg.classes[node].file,
                    "afferent": ca,
                    "efferent": ce,
                    "instability": round(ce / (ca + ce), 2),
                }
            )
    coupling.sort(key=lambda c: c["afferent"] + c["efferent"], reverse=True)

    calls = nx.DiGraph()
    calls.add_nodes_from(pg.functions)
    calls.add_edges_from((u, v) for u, v in _edges(pg.g, {"calls"}) if u != v)
    rank = pagerank(calls)
    key = sorted(
        (n for n in calls if calls.in_degree(n) >= 2),
        key=lambda n: (calls.in_degree(n), rank.get(n, 0)),
        reverse=True,
    )[:8]
    tables = defaultdict(list)
    for u, v in _edges(pg.g, {"uses_table"}):
        tables[pg.g.nodes[v]["label"]].append(_label(pg, u))
    return {
        "file_cycles": cycles,
        "coupling": coupling[:15],
        "key_components": [
            {
                "name": _label(pg, n),
                "file": pg.functions[n].file,
                "line": pg.functions[n].info.line,
                "used_by": calls.in_degree(n),
                "uses": calls.out_degree(n),
            }
            for n in key
        ],
        "tables": [
            {"table": t, "used_by": sorted(set(users))[:10]} for t, users in sorted(tables.items())
        ],
        "external_packages": dict(sorted(pg.packages.items(), key=lambda kv: -kv[1])[:15]),
    }


def _methods(pg: ProjectGraph, class_id: str):
    return [f for f in pg.functions.values() if f.owner == class_id]


def design_patterns(pg: ProjectGraph) -> list[dict]:
    found: list[dict] = []

    def add(pattern: str, name_ar: str, classes: list[str], evidence_ar: str) -> None:
        found.append(
            {"pattern": pattern, "name_ar": name_ar, "classes": classes, "evidence_ar": evidence_ar}
        )

    implementations: dict[str, list[str]] = defaultdict(list)
    for u, v in _edges(pg.g, {"extends", "implements"}):
        implementations[v].append(u)

    for class_id, klass in pg.classes.items():
        name = simple(klass.info.name)
        methods = _methods(pg, class_id)
        lowered = {m.info.name.lower() for m in methods}
        if lowered & _SINGLETON_METHODS and any(
            name in m.info.instantiates or m.info.name.lower() in _SINGLETON_METHODS
            for m in methods
        ):
            add(
                "Singleton",
                "النسخة الوحيدة (Singleton)",
                [name],
                f"الكلاس {name} يوفّر دالة للحصول على نسخة واحدة مشتركة",
            )
        if name.endswith("Factory") or any(
            re.match(r"(create|make|build|new)[A-Z_]", m.info.name)
            and len({c for c in m.info.instantiates if c in pg.class_by_name}) >= 2
            for m in methods
        ):
            add(
                "Factory",
                "المصنع (Factory)",
                [name],
                f"{name} مسؤول عن إنشاء الكائنات بدل إنشائها في كل مكان",
            )
        if name.endswith("Builder") and "build" in lowered:
            add("Builder", "الباني (Builder)", [name], f"{name} يبني الكائن خطوة بخطوة")
        if any(_SUBSCRIBE.match(m.info.name) for m in methods) and any(
            _NOTIFY.match(m.info.name) for m in methods
        ):
            add("Observer", "المراقب (Observer)", [name], f"{name} يسجّل مستمعين ويُبلغهم بالتغييرات")
        if re.search(r"(Repository|Repo|Dao|DAO)$", name):
            add(
                "Repository",
                "المستودع (Repository / DAO)",
                [name],
                f"{name} يعزل الوصول لقاعدة البيانات عن باقي الكود",
            )
        if name.endswith("Adapter"):
            add("Adapter", "المحوّل (Adapter)", [name], f"{name} يكيّف واجهة مع أخرى")
        if name.endswith("Facade"):
            add("Facade", "الواجهة المبسطة (Facade)", [name], f"{name} يبسّط نظاماً فرعياً")
        children = implementations.get(class_id, [])
        if klass.info.kind in ("interface", "abstract") and len(children) >= 2:
            names = [pg.g.nodes[c]["label"] for c in children][:6]
            add(
                "Strategy / Polymorphism",
                "الاستراتيجية / تعدد الأشكال",
                [name, *names],
                f"{name} له {len(children)} تطبيقات بديلة: {', '.join(names)}",
            )
    controllers = [k for k in pg.classes.values() if simple(k.info.name).endswith("Controller")]
    if controllers and any(
        re.search(r"(Model|Entity|View)$", simple(k.info.name)) for k in pg.classes.values()
    ):
        add(
            "MVC",
            "النموذج - العرض - المتحكم (MVC)",
            [simple(k.info.name) for k in controllers][:6],
            f"{len(controllers)} متحكمات (Controllers) منفصلة عن النماذج والعرض",
        )
    return found


def solid(pg: ProjectGraph) -> list[dict]:
    issues: list[dict] = []
    classes = class_dependencies(pg)

    def add(principle, severity, where, evidence, evidence_ar, file=None, line=None):
        issues.append(
            {
                "principle": principle,
                "severity": severity,
                "where": where,
                "file": file,
                "line": line,
                "evidence": evidence,
                "evidence_ar": evidence_ar,
            }
        )

    for class_id, klass in pg.classes.items():
        name, info = simple(klass.info.name), klass.info
        methods = _methods(pg, class_id)
        efferent = classes.out_degree(class_id) if class_id in classes else 0
        tables = {t for m in methods for t in m.info.sql_tables}
        if (
            len(info.methods) >= GOD_CLASS_METHODS
            or efferent >= GOD_CLASS_EFFERENT
            or (len(tables) >= 4 and len(info.methods) >= 8)
        ):
            add(
                "SRP",
                "Medium",
                name,
                f"{name} has {len(info.methods)} methods, depends on {efferent} classes and "
                f"touches {len(tables)} tables",
                f"الكلاس {name} يقوم بأكثر من مسؤولية: {len(info.methods)} دالة، ويعتمد على "
                f"{efferent} كلاسات، ويتعامل مع {len(tables)} جداول",
                klass.file,
                info.line,
            )
        concrete = sorted(
            {
                c
                for m in methods
                for c in m.info.instantiates
                if c.endswith(_DEPENDENCY_SUFFIXES) and c in pg.class_by_name
            }
        )
        if len(concrete) >= 2:
            add(
                "DIP",
                "Low",
                name,
                f"{name} creates its own dependencies ({', '.join(concrete)})",
                f"الكلاس {name} ينشئ تبعياته بنفسه ({', '.join(concrete)}) بدل استقبالها "
                "(Dependency Injection)، فيصعب اختباره واستبدالها",
                klass.file,
                info.line,
            )
        if info.kind == "interface" and len(info.methods) >= ISP_INTERFACE_METHODS:
            add(
                "ISP",
                "Low",
                name,
                f"Interface {name} has {len(info.methods)} methods",
                f"الواجهة {name} كبيرة ({len(info.methods)} دالة)؛ من يطبّقها يُجبر على دوال "
                "لا يحتاجها",
                klass.file,
                info.line,
            )
        ancestors = pg._family(class_id) - {class_id}
        inherited = {
            f.info.name: f for f in pg.functions.values()
            if f.owner in ancestors and not f.info.only_raises and not f.info.empty
        }  # fmt: skip
        if inherited:
            for method in methods:
                if method.info.only_raises and method.info.name in inherited:
                    add(
                        "LSP",
                        "Medium",
                        f"{name}.{method.info.name}",
                        f"{name}.{method.info.name} only throws: it refuses inherited behaviour",
                        f"الدالة {name}.{method.info.name} ترمي استثناءً فقط: الكلاس يرفض سلوكاً "
                        "ورثه، فلا يمكن استخدامه مكان أصله",
                        klass.file,
                        method.info.line,
                    )
    for function in pg.functions.values():
        if function.info.type_checks >= OCP_TYPE_CHECKS:
            where = _label(pg, function.id)
            add(
                "OCP",
                "Low",
                where,
                f"{where} checks the type {function.info.type_checks} times",
                f"الدالة {where} تفحص نوع الكائن {function.info.type_checks} مرات؛ إضافة نوع "
                "جديد تتطلب تعديلها، وتعدد الأشكال أفضل",
                function.file,
                function.info.line,
            )
            issues[-1]["weight"] = function.info.type_checks
    return issues


def solid_summary(issues: list[dict], per_principle: int = 5) -> dict:
    """The strongest findings per principle, and how many there were in total."""
    order = {"Medium": 0, "Low": 1}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for issue in issues:
        grouped[issue["principle"]].append(issue)
    shown = []
    for principle in ("SRP", "OCP", "LSP", "ISP", "DIP"):
        items = sorted(
            grouped.get(principle, []),
            key=lambda i: (order.get(i["severity"], 2), -i.get("weight", 0)),
        )
        shown.extend(items[:per_principle])
    for issue in issues:
        issue.pop("weight", None)
    return {"issues": shown, "counts": {p: len(v) for p, v in grouped.items()}}


def view(pg: ProjectGraph) -> dict:
    """Nodes and edges for drawing; the least connected functions are left out when big."""
    nodes = list(pg.g.nodes)
    truncated = False
    if len(nodes) > MAX_VIEW_NODES:
        truncated = True
        keep = {n for n, t in pg.g.nodes(data="type") if t != "function"}
        functions = sorted((n for n in nodes if n not in keep), key=pg.g.degree, reverse=True)
        keep.update(functions[: max(0, MAX_VIEW_NODES - len(keep))])
        nodes = [n for n in nodes if n in keep][:MAX_VIEW_NODES]
    chosen = set(nodes)
    seen = set()
    edges = []
    for u, v, kind in pg.g.edges(data="type"):
        if u in chosen and v in chosen and (u, v, kind) not in seen:
            seen.add((u, v, kind))
            edges.append({"source": u, "target": v, "type": kind})
    return {
        "nodes": [
            {"id": n, **{k: v for k, v in pg.g.nodes[n].items() if v is not None}} for n in nodes
        ],
        "edges": edges,
        "truncated": truncated,
    }


def knowledge_graph(files) -> dict:
    pg = ProjectGraph(files)
    counts = defaultdict(int)
    for _, kind in pg.g.nodes(data="type"):
        counts[kind] += 1
    edge_counts = defaultdict(int)
    for _, _, kind in pg.g.edges(data="type"):
        edge_counts[kind] += 1
    return {
        "stats": {"nodes": dict(counts), "edges": dict(edge_counts)},
        "dependencies": dependencies(pg),
        "design_patterns": design_patterns(pg),
        "solid": solid_summary(solid(pg)),
        **view(pg),
    }
