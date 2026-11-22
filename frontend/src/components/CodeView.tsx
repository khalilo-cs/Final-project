// Code shown next to a viva question (FR-07.9): numbered with the file's real line
// numbers, so the student and the examiner can point at "line 42".
export function CodeView({ code, file, lines }: { code: string; file?: string | null; lines?: string | null }) {
  const start = Number.parseInt((lines ?? "").split("-")[0] ?? "", 10);
  const first = Number.isFinite(start) && start > 0 ? start : 1;
  const rows = code.replace(/\n$/, "").split("\n");
  return (
    <figure className="mt-3 overflow-hidden rounded-lg border border-slate-800 bg-slate-900" dir="ltr">
      {file && (
        <figcaption className="border-b border-slate-700 px-3 py-1.5 font-mono text-xs text-slate-300">
          {file}{lines ? `:${lines}` : ""}
        </figcaption>
      )}
      <div className="max-h-80 overflow-auto">
        <table className="w-full border-collapse font-mono text-xs leading-5">
          <tbody>
            {rows.map((text, i) => (
              <tr key={i} className="hover:bg-indigo-500/20">
                <td className="select-none border-r border-slate-700 px-3 text-right text-slate-500">{first + i}</td>
                <td className="whitespace-pre px-3 text-slate-100">{text || " "}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
