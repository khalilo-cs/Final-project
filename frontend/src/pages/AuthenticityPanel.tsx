import { ApiError, get } from "../api";
import { Badge, Card, Score, severityTone, useLoad } from "../components/ui";

interface Component { factor: string; label_ar: string; weight: number; score: number | null }
interface Flag { type: string; severity: string; evidence: string; evidence_ar?: string }
interface Match { file: string; lines: [number, number]; other_file: string; other_lines: [number, number]; fingerprints: number }
interface Similar { document_id: string; submitted: "earlier" | "later"; title: string; student_name: string | null; course: string | null; similarity: number; reverse_similarity: number | null; matched_files: Match[] }
interface Git { available: boolean; error?: string; total_commits?: number; span_days?: number; active_days?: number; authors?: { author: string; commits: number }[]; flags?: Flag[] }
interface Style { files_compared: number; outliers: { file: string; lines: number; differs: Record<string, { file: string; project: string }> }[] }
interface FunctionMatch { file: string; name: string; lines: [number, number]; other_file: string; other_name: string; other_lines: [number, number]; similarity: number; methods: string[]; token_coverage: number; rewritten: boolean }
interface Rewritten { document_id: string; submitted: "earlier" | "later"; title: string; student_name: string | null; course: string | null; similarity: number; matched_functions: number; rewritten_functions: number; functions: FunctionMatch[] }
interface Authenticity { authenticity_score: number | null; coverage: number; components: Component[]; flags: Flag[]; similar_projects: Similar[]; rewritten_code?: Rewritten[]; semantic_methods?: string[] | null; git: Git | null; style: Style }

/** Arabic number agreement: 1 and 2 have their own forms, 3-10 plural, 11+ singular. */
function countAr(n: number, one: string, two: string, few: string, many: string) {
  if (n === 1) return one;
  if (n === 2) return two;
  return n % 100 >= 3 && n % 100 <= 10 ? `${n} ${few}` : `${n} ${many}`;
}

function rewording(coverage: number) {
  if (coverage >= 0.9) return <Badge tone="red">منسوخة كما هي</Badge>;
  if (coverage >= 0.5) return <Badge tone="amber">أعيدت صياغتها جزئياً</Badge>;
  return <Badge tone="amber">أعيدت صياغتها</Badge>;
}

const FEATURE_AR: Record<string, string> = { naming: "التسمية", indent: "المسافات البادئة", comments: "التعليقات", quotes: "علامات الاقتباس", braces: "الأقواس" };

export function AuthenticityPanel({ id }: { id: string }) {
  const [data] = useLoad(
    () => get<Authenticity>("projects", `/api/v1/fraud/${id}/results`).catch((e) => (e instanceof ApiError && e.status === 404 ? null : Promise.reject(e))),
    [id],
  );
  if (!data) return null;
  return (
    <Card title="🕵️ أصالة المشروع">
      <div className="flex flex-wrap items-center gap-8">
        <Score value={data.authenticity_score} label="درجة الأصالة" />
        <div className="grid flex-1 grid-cols-2 gap-2 text-sm md:grid-cols-5">
          {data.components.map((c) => (
            <div key={c.factor} className="rounded-lg bg-slate-50 p-2 text-center">
              <div className="text-xs text-slate-500">{c.label_ar} ({c.weight}%)</div>
              <div className="font-bold">{c.score ?? <span className="text-slate-400">لا بيانات</span>}</div>
            </div>
          ))}
        </div>
      </div>
      {data.flags.length > 0 && (
        <ul className="mt-4 space-y-1 text-sm">
          {data.flags.map((f, i) => <li key={i} className="flex items-center gap-2"><Badge tone={severityTone(f.severity)}>{f.severity}</Badge><span>{f.evidence_ar ?? f.evidence}</span></li>)}
        </ul>
      )}
      {data.similar_projects.length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 font-bold">مشاريع متشابهة</h3>
          <div className="space-y-3">
            {data.similar_projects.map((s) => (
              <div key={s.document_id} className="rounded-lg border border-rose-200 bg-rose-50/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={s.similarity >= 0.5 ? "red" : "amber"}>تشابه <span className="ltr inline-block">{Math.round(s.similarity * 100)}%</span></Badge>
                  <span className="font-semibold">{s.title}</span>
                  <Badge tone={s.submitted === "earlier" ? "red" : "amber"}>{s.submitted === "earlier" ? "سُلِّم قبله: هذا المشروع يشبه سابقاً" : "سُلِّم بعده: ربما شارك كوده"}</Badge>
                  {s.student_name && <span className="text-sm text-slate-600">— {s.student_name}</span>}
                  {s.course && <span className="text-xs text-slate-400">{s.course}</span>}
                </div>
                <table className="ltr mt-2 w-full text-left text-xs">
                  <tbody>
                    {s.matched_files.map((m, i) => (
                      <tr key={i} className="border-t border-rose-100">
                        <td className="py-1"><code>{m.file}:{m.lines[0]}-{m.lines[1]}</code></td>
                        <td className="text-slate-400">≈</td>
                        <td><code>{m.other_file}:{m.other_lines[0]}-{m.other_lines[1]}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">المقارنة تتجاهل أسماء المتغيرات والتعليقات وتنسيق الكود، فتغيير الأسماء لا يخفي النسخ. القالب المشترك بين أغلب المشاريع لا يُحسب.</p>
        </div>
      )}
      {(data.rewritten_code?.length ?? 0) > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 font-bold">دوال متطابقة في البنية</h3>
          <div className="space-y-3">
            {data.rewritten_code!.map((s) => (
              <div key={s.document_id} className="rounded-lg border border-amber-200 bg-amber-50/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={s.similarity >= 0.5 ? "red" : "amber"}>
                    <span className="ltr inline-block">{Math.round(s.similarity * 100)}%</span> من أسطر الدوال
                  </Badge>
                  <span className="font-semibold">{s.title}</span>
                  <Badge tone={s.submitted === "earlier" ? "red" : "amber"}>{s.submitted === "earlier" ? "سُلِّم قبله" : "سُلِّم بعده"}</Badge>
                  {s.student_name && <span className="text-sm text-slate-600">— {s.student_name}</span>}
                  <span className="text-xs text-slate-500">
                    {countAr(s.matched_functions, "دالة واحدة", "دالتان", "دوال", "دالة")}
                    {s.rewritten_functions > 0 && `، ${s.rewritten_functions === s.matched_functions ? "كلها" : countAr(s.rewritten_functions, "واحدة منها", "اثنتان منها", "منها", "منها")} أعيدت صياغتها`}
                  </span>
                </div>
                <table className="mt-2 w-full text-xs">
                  <tbody>
                    {s.functions.map((f, i) => (
                      <tr key={i} className="border-t border-amber-100">
                        <td className="ltr py-1 text-left"><code>{f.name}</code> <span className="text-slate-400">{f.file}:{f.lines[0]}-{f.lines[1]}</span></td>
                        <td className="px-2 text-slate-400">≈</td>
                        <td className="ltr text-left"><code>{f.other_name}</code> <span className="text-slate-400">{f.other_file}:{f.other_lines[0]}-{f.other_lines[1]}</span></td>
                        <td className="px-2 text-left"><span className="ltr inline-block">{Math.round(f.similarity * 100)}%</span></td>
                        <td>{rewording(f.token_coverage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            تُقارن بنية كل دالة (الحلقات والشروط والاستدعاءات بترتيبها) بعد حذف الأسماء، فتغيير الأسماء أو نوع الحلقة أو الترجمة إلى لغة مشابهة
            لا يخفي النسخ{data.semantic_methods?.includes("embedding") ? "، مع رأي ثانٍ من نموذج لفهم الكود" : ""}. الأنماط الشائعة بين أغلب المشاريع لا تُحسب. التشابه قرينة تحتاج حكم الدكتور.
          </p>
        </div>
      )}
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-2 font-bold">تاريخ Git</h3>
          {!data.git ? <p className="text-sm text-slate-500">لم يُرفق مجلد ‎.git مع الكود.</p> : !data.git.available ? (
            <p className="text-sm text-slate-500">{data.git.error}</p>
          ) : (
            <div className="text-sm text-slate-700">
              <b>{data.git.total_commits}</b> commit خلال <b>{data.git.span_days}</b> يوم ({data.git.active_days} أيام عمل)
              <div className="mt-1 text-xs text-slate-500 ltr">{data.git.authors?.map((a) => `${a.author} (${a.commits})`).join(", ")}</div>
            </div>
          )}
        </div>
        <div>
          <h3 className="mb-2 font-bold">أسلوب الكتابة</h3>
          {data.style.outliers.length === 0 ? (
            <p className="text-sm text-slate-500">أسلوب متّسق في {data.style.files_compared} ملفات.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {data.style.outliers.map((o) => (
                <li key={o.file}><code className="text-xs">{o.file}</code> يختلف في: {Object.keys(o.differs).map((k) => FEATURE_AR[k] ?? k).join("، ")}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}
