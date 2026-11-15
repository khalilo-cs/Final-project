import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { useMemo, useRef, useState } from "react";
import { ApiError, get } from "../api";
import { Badge, Card, useLoad } from "../components/ui";

type NodeType = "file" | "class" | "function" | "table";
interface GraphNode { id: string; type: NodeType; label: string; file?: string; line?: number; kind?: string; complexity?: number; owner?: string }
interface GraphEdge { source: string; target: string; type: string }
interface Issue { principle: string; severity: string; where: string; file?: string; line?: number; evidence_ar: string }
interface Graph {
  stats: { nodes: Record<string, number>; edges: Record<string, number> };
  nodes: GraphNode[]; edges: GraphEdge[]; truncated: boolean;
  dependencies: {
    file_cycles: string[][];
    coupling: { class: string; file: string; afferent: number; efferent: number; instability: number }[];
    key_components: { name: string; file: string; line: number; used_by: number; uses: number }[];
    tables: { table: string; used_by: string[] }[];
    external_packages: Record<string, number>;
  };
  design_patterns: { pattern: string; name_ar: string; classes: string[]; evidence_ar: string }[];
  solid: { counts: Record<string, number>; issues: Issue[] };
}

// Categorical slots 1-4 of the validated palette, in fixed order; shape is the second cue.
const TYPES: { type: NodeType; label: string; color: string }[] = [
  { type: "file", label: "ملف", color: "#2a78d6" },
  { type: "class", label: "كلاس", color: "#eb6834" },
  { type: "function", label: "دالة", color: "#1baf7a" },
  { type: "table", label: "جدول", color: "#eda100" },
];
const COLOR = Object.fromEntries(TYPES.map((t) => [t.type, t.color])) as Record<NodeType, string>;
const EDGE_AR: Record<string, string> = {
  contains: "يحتوي", calls: "يستدعي", creates: "ينشئ", imports: "يستورد", extends: "يرث", implements: "يطبّق", uses_table: "يستخدم جدول",
};
const PRINCIPLE_AR: Record<string, string> = {
  SRP: "مسؤولية واحدة", OCP: "مفتوح للإضافة مغلق للتعديل", LSP: "استبدال ليسكوف", ISP: "فصل الواجهات", DIP: "عكس الاعتماد",
};
const W = 900, H = 560;

interface SimNode extends SimulationNodeDatum, GraphNode {}

function layout(graph: Graph, visible: Set<NodeType>) {
  const nodes: SimNode[] = graph.nodes.filter((n) => visible.has(n.type)).map((n) => ({ ...n }));
  const ids = new Set(nodes.map((n) => n.id));
  const links = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ ...e }));
  const simulation = forceSimulation(nodes)
    .force("link", forceLink<SimNode, (typeof links)[number] & { source: string | SimNode; target: string | SimNode }>(links).id((d) => d.id).distance((l) => (l.type === "contains" ? 40 : 90)).strength(0.3))
    .force("charge", forceManyBody().strength(-180))
    .force("x", forceX(W / 2).strength(0.04))
    .force("y", forceY(H / 2).strength(0.06))
    .force("collide", forceCollide(16))
    .stop();
  for (let i = 0; i < 300; i++) simulation.tick();
  // Fit the drawing to the canvas (labels need room on the right).
  if (nodes.length) {
    const xs = nodes.map((n) => n.x ?? 0), ys = nodes.map((n) => n.y ?? 0);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const scale = Math.min((W - 180) / Math.max(maxX - minX, 1), (H - 60) / Math.max(maxY - minY, 1), 2.5);
    const offsetX = 30 + ((W - 180) - (maxX - minX) * scale) / 2, offsetY = 30 + ((H - 60) - (maxY - minY) * scale) / 2;
    nodes.forEach((n) => { n.x = offsetX + ((n.x ?? 0) - minX) * scale; n.y = offsetY + ((n.y ?? 0) - minY) * scale; });
  }
  const position = new Map(nodes.map((n) => [n.id, n]));
  return { nodes, links: links.map((l) => ({ ...l, s: position.get(typeof l.source === "string" ? l.source : (l.source as SimNode).id)!, t: position.get(typeof l.target === "string" ? l.target : (l.target as SimNode).id)! })) };
}

function Shape({ node, faded, onEnter, onLeave }: { node: SimNode; faded: boolean; onEnter: () => void; onLeave: () => void }) {
  const x = node.x ?? 0, y = node.y ?? 0, color = COLOR[node.type];
  const common = { fill: color, stroke: "#fcfcfb", strokeWidth: 2, opacity: faded ? 0.15 : 1, onMouseEnter: onEnter, onMouseLeave: onLeave, style: { cursor: "pointer" } };
  if (node.type === "file") return <rect x={x - 7} y={y - 7} width={14} height={14} rx={3} {...common} />;
  if (node.type === "table") return <rect x={x - 9} y={y - 6} width={18} height={12} rx={2} {...common} />;
  if (node.type === "class") return <path d={`M${x} ${y - 9} L${x + 9} ${y} L${x} ${y + 9} L${x - 9} ${y} Z`} {...common} />;
  return <circle cx={x} cy={y} r={Math.min(4 + (node.complexity ?? 1) / 2, 9)} {...common} />;
}

function GraphView({ graph }: { graph: Graph }) {
  const [visible, setVisible] = useState<Set<NodeType>>(new Set(["file", "class", "function", "table"]));
  const [hover, setHover] = useState<string | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number } | null>(null);
  const { nodes, links } = useMemo(() => layout(graph, visible), [graph, visible]);
  const neighbours = useMemo(() => {
    if (!hover) return null;
    const set = new Set([hover]);
    links.forEach((l) => { if (l.s.id === hover) set.add(l.t.id); if (l.t.id === hover) set.add(l.s.id); });
    return set;
  }, [hover, links]);
  const hovered = nodes.find((n) => n.id === hover);

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-sm">
        {TYPES.map((t) => (
          <label key={t.type} className="flex items-center gap-1.5">
            <input type="checkbox" checked={visible.has(t.type)} onChange={() => {
              const next = new Set(visible);
              if (next.has(t.type)) next.delete(t.type); else next.add(t.type);
              setVisible(next);
            }} />
            <svg width="14" height="14" aria-hidden><rect width="14" height="14" rx={t.type === "function" ? 7 : 3} fill={t.color} /></svg>
            {t.label} ({graph.stats.nodes[t.type] ?? 0})
          </label>
        ))}
        <span className="text-xs text-slate-500">مرّر على عنصر لترى ما يرتبط به؛ اسحب للتحريك، والعجلة للتكبير.</span>
      </div>
      <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-[#fcfcfb]" dir="ltr">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-[28rem] w-full touch-none select-none"
          onWheel={(e) => { const k = Math.min(4, Math.max(0.4, view.k * (e.deltaY < 0 ? 1.1 : 0.9))); setView({ ...view, k }); }}
          onPointerDown={(e) => { drag.current = { x: e.clientX - view.x, y: e.clientY - view.y }; }}
          onPointerMove={(e) => { if (drag.current) setView({ ...view, x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); }}
          onPointerUp={() => { drag.current = null; }} onPointerLeave={() => { drag.current = null; }}>
          <g transform={`translate(${view.x} ${view.y}) translate(${W / 2} ${H / 2}) scale(${view.k}) translate(${-W / 2} ${-H / 2})`}>
            {links.map((l, i) => {
              const active = neighbours?.has(l.s.id) && neighbours?.has(l.t.id) && (l.s.id === hover || l.t.id === hover);
              return <line key={i} x1={l.s.x} y1={l.s.y} x2={l.t.x} y2={l.t.y}
                stroke={active ? "#52514e" : "#c9c8c2"} strokeWidth={active ? 1.5 : 1}
                strokeDasharray={l.type === "extends" || l.type === "implements" ? "4 3" : undefined}
                opacity={neighbours && !active ? 0.15 : l.type === "contains" ? 0.5 : 0.9} />;
            })}
            {nodes.map((n) => <Shape key={n.id} node={n} faded={Boolean(neighbours && !neighbours.has(n.id))}
              onEnter={() => setHover(n.id)} onLeave={() => setHover(null)} />)}
            {nodes.filter((n) => n.type !== "function" || neighbours?.has(n.id)).map((n) => (
              <text key={`t${n.id}`} x={(n.x ?? 0) + 11} y={(n.y ?? 0) + 4} fontSize={10}
                fill={neighbours && !neighbours.has(n.id) ? "#c9c8c2" : "#52514e"} pointerEvents="none">{n.label}</text>
            ))}
          </g>
        </svg>
        {hovered && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow">
            <div className="font-bold text-slate-900">{hovered.label}</div>
            <div className="text-slate-500">{TYPES.find((t) => t.type === hovered.type)?.label}{hovered.kind && hovered.kind !== "class" ? ` (${hovered.kind})` : ""}</div>
            {hovered.file && <div className="text-slate-500">{hovered.file}{hovered.line ? `:${hovered.line}` : ""}</div>}
            {hovered.complexity !== undefined && <div className="text-slate-500">complexity {hovered.complexity}</div>}
            <div className="text-slate-500">{(neighbours?.size ?? 1) - 1} links</div>
          </div>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        الخطوط المتقطعة وراثة/تطبيق واجهة، والباقي احتواء واستدعاء وإنشاء واستيراد واستخدام جداول.
        {graph.truncated && " المشروع كبير: عُرضت الدوال الأكثر ارتباطاً فقط، والتحليل يشمل الكل."}
      </p>
      <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
        {Object.entries(graph.stats.edges).map(([k, v]) => <Badge key={k}>{EDGE_AR[k] ?? k}: {v}</Badge>)}
      </div>
    </div>
  );
}

function Dependencies({ deps }: { deps: Graph["dependencies"] }) {
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <div>
        <h3 className="mb-2 font-bold">المكونات المحورية</h3>
        <p className="mb-2 text-xs text-slate-500">أكثر الدوال اعتماداً عليها: تغييرها يؤثر على أجزاء كثيرة.</p>
        <table className="w-full text-sm">
          <tbody>
            {deps.key_components.map((k) => (
              <tr key={k.name + k.file} className="border-t border-slate-100">
                <td className="ltr py-1 text-left"><code>{k.name}</code> <span className="text-xs text-slate-400">{k.file}:{k.line}</span></td>
                <td className="text-left">يعتمد عليها {k.used_by}</td>
              </tr>
            ))}
            {deps.key_components.length === 0 && <tr><td className="text-slate-500">لا توجد دالة يستدعيها أكثر من جزء.</td></tr>}
          </tbody>
        </table>
      </div>
      <div>
        <h3 className="mb-2 font-bold">الاعتماد الدائري</h3>
        {deps.file_cycles.length === 0 ? <p className="text-sm text-slate-500">لا يوجد ✓</p> : (
          <ul className="space-y-1 text-sm">
            {deps.file_cycles.map((c, i) => <li key={i} className="ltr text-left"><code className="text-xs">{[...c, c[0]].join(" → ")}</code></li>)}
          </ul>
        )}
        <h3 className="mb-2 mt-4 font-bold">الجداول ومن يستخدمها</h3>
        <ul className="space-y-1 text-sm">
          {deps.tables.map((t) => <li key={t.table}><Badge tone="amber">{t.table}</Badge> <span className="ltr inline-block text-xs text-slate-600">{t.used_by.join(", ")}</span></li>)}
          {deps.tables.length === 0 && <li className="text-slate-500">لم تُكتشف استعلامات SQL في الكود.</li>}
        </ul>
      </div>
      <div className="md:col-span-2">
        <h3 className="mb-2 font-bold">الترابط بين الكلاسات</h3>
        <table className="w-full text-sm">
          <thead><tr className="text-xs text-slate-500"><th className="text-right">الكلاس</th><th>يعتمد عليه</th><th>يعتمد على</th><th>عدم الاستقرار</th></tr></thead>
          <tbody>
            {deps.coupling.slice(0, 10).map((c) => (
              <tr key={c.class + c.file} className="border-t border-slate-100 text-center">
                <td className="ltr py-1 text-left"><code>{c.class}</code></td><td>{c.afferent}</td><td>{c.efferent}</td><td>{c.instability}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-slate-500">عدم الاستقرار = يعتمد على ÷ (يعتمد على + يعتمد عليه). الكلاسات التي يعتمد عليها الكثير يُفضّل أن تكون مستقرة.</p>
      </div>
    </div>
  );
}

export function CodeGraphPanel({ id }: { id: string }) {
  const [graph] = useLoad(
    () => get<Graph>("projects", `/api/v1/analysis/code/${id}/graph`).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))),
    [id],
  );
  const [tab, setTab] = useState<"graph" | "deps" | "patterns" | "solid">("graph");
  if (!graph) return null;
  const tabs = [
    ["graph", "الرسم"], ["deps", "التبعيات"], ["patterns", `أنماط التصميم (${graph.design_patterns.length})`],
    ["solid", `مبادئ SOLID (${Object.values(graph.solid.counts).reduce((a, b) => a + b, 0)})`],
  ] as const;
  return (
    <Card title="🕸️ خريطة الكود (Knowledge Graph)">
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" onClick={() => setTab(key)}
            className={`rounded-md px-3 py-1.5 text-sm font-semibold ${tab === key ? "bg-white shadow" : "text-slate-500"}`}>{label}</button>
        ))}
      </div>
      {tab === "graph" && <GraphView graph={graph} />}
      {tab === "deps" && <Dependencies deps={graph.dependencies} />}
      {tab === "patterns" && (graph.design_patterns.length === 0 ? <p className="text-sm text-slate-500">لم يُكتشف نمط تصميم معروف.</p> : (
        <ul className="space-y-2">
          {graph.design_patterns.map((p, i) => (
            <li key={i} className="rounded-lg border border-slate-200 p-3">
              <div className="font-bold">{p.name_ar}</div>
              <div className="text-sm text-slate-600">{p.evidence_ar}</div>
              <div className="ltr mt-1 text-left text-xs text-slate-500">{p.classes.join(", ")}</div>
            </li>
          ))}
          <li className="text-xs text-slate-500">الأنماط مستنتجة من بنية الكود وأسمائه؛ هي مادة للمناقشة لا حكم نهائي.</li>
        </ul>
      ))}
      {tab === "solid" && (graph.solid.issues.length === 0 ? <p className="text-sm text-slate-500">لم تُرصد مخالفات واضحة ✓</p> : (
        <ul className="space-y-2">
          {graph.solid.issues.map((issue, i) => (
            <li key={i} className="rounded-lg border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={issue.severity === "Medium" ? "amber" : "gray"}>{issue.principle}</Badge>
                <span className="text-xs text-slate-500">{PRINCIPLE_AR[issue.principle]}</span>
                {issue.file && <span className="ltr text-xs text-slate-400">{issue.file}:{issue.line}</span>}
              </div>
              <div className="mt-1">{issue.evidence_ar}</div>
            </li>
          ))}
          {Object.entries(graph.solid.counts).some(([p, n]) => n > graph.solid.issues.filter((x) => x.principle === p).length) && (
            <li className="text-xs text-slate-500">عُرضت أقوى 5 ملاحظات لكل مبدأ: {Object.entries(graph.solid.counts).map(([p, n]) => `${p}: ${n}`).join("، ")}</li>
          )}
        </ul>
      ))}
    </Card>
  );
}
