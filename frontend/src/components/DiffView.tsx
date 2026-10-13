import type { Attachment, DiffRow, VersionDiff } from "../api";
import { fileSize } from "../lib/format";
import { Icon } from "./Icon";

export function DiffLines({ rows }: { rows: DiffRow[] }) {
  if (!rows.some((r) => r.op !== "eq" && r.op !== "skip")) return <p className="text-sm muted">Nessuna differenza nel testo.</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 text-[14px] leading-relaxed dark:border-slate-800">
      {rows.map((r, i) => {
        if (r.op === "skip") {
          return (
            <div key={i} className="bg-slate-50 px-3 py-1 text-center text-xs muted dark:bg-slate-900/60">
              {r.count} {r.count === 1 ? "riga invariata" : "righe invariate"}
            </div>
          );
        }
        if (r.op === "change") {
          return (
            <div key={i} className="flex gap-2 border-l-4 border-amber-400 bg-amber-50/60 px-3 py-1.5 dark:bg-amber-950/20">
              <span className="w-3 shrink-0 select-none font-mono text-amber-600">~</span>
              <span className="min-w-0 whitespace-pre-wrap break-words">
                {r.parts.map((p, j) =>
                  p.op === "eq" ? <span key={j}>{p.text}</span>
                    : p.op === "add" ? <ins key={j} className="rounded bg-emerald-200/70 px-0.5 no-underline dark:bg-emerald-800/60">{p.text}</ins>
                      : <del key={j} className="rounded bg-red-200/60 px-0.5 text-red-900 dark:bg-red-900/50 dark:text-red-200">{p.text}</del>)}
              </span>
            </div>
          );
        }
        const style = {
          eq: "text-slate-600 dark:text-slate-400",
          add: "border-l-4 border-emerald-500 bg-emerald-50 text-emerald-950 dark:bg-emerald-950/30 dark:text-emerald-100",
          del: "border-l-4 border-red-400 bg-red-50 text-red-900 line-through decoration-red-400/60 dark:bg-red-950/30 dark:text-red-200",
        }[r.op];
        return (
          <div key={i} className={`flex gap-2 px-3 py-1.5 ${style}`}>
            <span className="w-3 shrink-0 select-none font-mono opacity-70">{r.op === "add" ? "+" : r.op === "del" ? "−" : ""}</span>
            <span className="min-w-0 whitespace-pre-wrap break-words">{r.text}</span>
          </div>
        );
      })}
    </div>
  );
}

function AttRow({ a, tone, label }: { a: Attachment; tone: string; label: string }) {
  return (
    <li className="flex items-center gap-3 py-2">
      <span className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase ${tone}`}>{label}</span>
      <a href={a.url} target="_blank" rel="noopener noreferrer" className="min-w-0 flex-1 truncate text-sm font-medium hover:text-brand-700 dark:hover:text-brand-300">
        {a.name}
      </a>
      {a.size ? <span className="shrink-0 text-xs muted">{fileSize(a.size)}</span> : null}
    </li>
  );
}

export default function DiffView({ diff }: { diff: VersionDiff }) {
  const att = diff.attachments;
  const anyAtt = att.added.length + att.removed.length + att.changed.length > 0;
  return (
    <div className="space-y-5">
      {diff.title_change && (
        <div>
          <h4 className="mb-2 text-xs font-bold uppercase tracking-wider muted">Titolo</h4>
          <p className="text-sm"><del className="text-red-700 dark:text-red-300">{diff.title_change.old}</del></p>
          <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-300">{diff.title_change.new}</p>
        </div>
      )}
      <div>
        <h4 className="mb-2 text-xs font-bold uppercase tracking-wider muted">{diff.previous ? "Testo" : "Testo della prima versione"}</h4>
        <DiffLines rows={diff.text} />
      </div>
      {anyAtt && (
        <div>
          <h4 className="mb-1 text-xs font-bold uppercase tracking-wider muted">Allegati</h4>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {att.added.map((a) => <AttRow key={a.url} a={a} label="nuovo" tone="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200" />)}
            {att.changed.map((a) => <AttRow key={a.url} a={a} label="aggiornato" tone="bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200" />)}
            {att.removed.map((a) => <AttRow key={a.url} a={a} label="rimosso" tone="bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200" />)}
          </ul>
          {att.changed.filter((a) => a.diff?.length).map((a) => (
            <details key={a.url} className="mt-3">
              <summary className="cursor-pointer text-sm font-semibold text-brand-700 dark:text-brand-300">
                <Icon name="file" className="mr-1 inline h-4 w-4" /> Cosa è cambiato in "{a.name}"
              </summary>
              <div className="mt-2"><DiffLines rows={a.diff!} /></div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
