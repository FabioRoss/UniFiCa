import { useEffect, useState, type ReactNode } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import type { ItemDetail, VersionDiff } from "../api";
import DiffView from "../components/DiffView";
import { Icon } from "../components/Icon";
import { Badge, ErrorBox, Loading } from "../components/ui";
import { fileSize, fmtDate, fmtDateTime, relTime, titleCase } from "../lib/format";
import { useFetch } from "../lib/useFetch";

const URL_RE = /(https?:\/\/[^\s)]+)/g;

function Linkified({ text }: { text: string }) {
  const parts = text.split(URL_RE);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? <a key={i} href={p} target="_blank" rel="noopener noreferrer" className="break-all font-medium text-brand-700 underline decoration-brand-300 underline-offset-2 dark:text-brand-300">{p}</a> : p)}
    </>
  );
}

function Content({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(<ul key={blocks.length} className="my-2 list-disc space-y-1 pl-5">{list.map((l, i) => <li key={i}><Linkified text={l} /></li>)}</ul>);
      list = [];
    }
  };
  for (const line of text.split("\n")) {
    if (line.startsWith("• ")) { list.push(line.slice(2)); continue; }
    flush();
    blocks.push(<p key={blocks.length} className="my-2"><Linkified text={line} /></p>);
  }
  flush();
  return <div className="text-[15px] leading-relaxed text-slate-800 dark:text-slate-200">{blocks}</div>;
}

export default function ItemPage() {
  const { id } = useParams();
  const [params, setSearchParams] = useSearchParams();
  const loc = useLocation();
  const navigate = useNavigate();
  // Pages that link here pass { backLabel }; keep it when ?v= changes
  const backLabel = (loc.state as { backLabel?: string } | null)?.backLabel;
  const setParams = (p: Record<string, string>) => setSearchParams(p, { replace: true, state: loc.state });
  const { data: item, error, loading, reload } = useFetch<ItemDetail>(`/api/items/${id}`);
  const latest = item?.versions[0]?.number ?? 1;
  const selected = Number(params.get("v")) || null;
  const showDiffFor = selected && selected > 1 ? selected : null;
  const { data: diff, loading: diffLoading } = useFetch<VersionDiff>(showDiffFor ? `/api/items/${id}/versions/${showDiffFor}/diff` : null);
  const [shared, setShared] = useState(false);

  useEffect(() => {
    if (item) document.title = `${item.title} · Open Unifi`;
    return () => { document.title = "Open Unifi"; };
  }, [item]);

  if (loading) return <Loading />;
  if (error || !item) return <ErrorBox message={error ?? "Contenuto non trovato"} onRetry={reload} />;

  const share = async () => {
    const url = `${location.origin}/n/${item.id}`;
    try {
      if (navigator.share) await navigator.share({ title: item.title, url });
      else { await navigator.clipboard.writeText(url); setShared(true); setTimeout(() => setShared(false), 2000); }
    } catch { /* cancelled */ }
  };

  const modifiedCount = item.versions.filter((v) => v.kind === "modified").length;
  const isExam = item.source.kind === "exams";
  // Came from a page of the app: go back to it (keeps its search and filters).
  // Opened directly (notification, shared link): go to the item's natural list.
  const goBack = () => (backLabel ? navigate(-1) : navigate(isExam ? "/esami" : "/"));

  return (
    <article className="mx-auto max-w-3xl">
      <button onClick={goBack} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300">
        <Icon name="chevronLeft" className="h-4 w-4" /> {backLabel ?? (isExam ? "Appelli" : "Novità")}
      </button>

      <div className="card p-5 sm:p-7">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs font-medium muted">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-2.5 py-1 text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
            {item.source.name}
          </span>
          {modifiedCount > 0 && <Badge tone="amber">Modificato {modifiedCount} {modifiedCount === 1 ? "volta" : "volte"}</Badge>}
        </div>
        <h1 className="text-[24px] font-bold leading-tight tracking-tight sm:text-[28px]">{item.source.kind === "exams" ? titleCase(item.title) : item.title}</h1>
        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] muted">
          {item.published_on && <div><dt className="inline">{item.source.kind === "page" ? "Aggiornata sul sito il: " : "Data: "}</dt><dd className="inline font-medium">{fmtDate(item.published_on)}</dd></div>}
          <div><dt className="inline">Ultima modifica rilevata: </dt><dd className="inline font-medium">{fmtDateTime(item.changed_at)}</dd></div>
          <div><dt className="inline">Controllato: </dt><dd className="inline font-medium">{relTime(item.checked_at)}</dd></div>
        </dl>
        <div className="mt-5 flex flex-wrap gap-2">
          <a href={item.url} target="_blank" rel="noopener noreferrer" className="btn-primary">
            {item.source.kind === "exams" ? "Apri su ESSE3" : "Sito ufficiale"} <Icon name="external" className="h-4 w-4" />
          </a>
          <button className="btn-soft" onClick={share}><Icon name="share" className="h-4 w-4" />{shared ? "Link copiato" : "Condividi"}</button>
        </div>

        {showDiffFor && (
          <section className="mt-7 rounded-2xl border border-amber-200 bg-amber-50/40 p-4 sm:p-5 dark:border-amber-900/60 dark:bg-amber-950/10">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-bold">Cosa è cambiato <span className="font-normal muted">(versione {showDiffFor})</span></h2>
              <button className="text-sm font-semibold text-brand-700 dark:text-brand-300" onClick={() => setParams({})}>Chiudi</button>
            </div>
            {diffLoading || !diff ? <Loading label="Calcolo delle differenze..." /> : <DiffView diff={diff} />}
          </section>
        )}

        <section className="mt-7">
          <h2 className="mb-1 text-xs font-bold uppercase tracking-wider muted">Contenuto attuale</h2>
          {item.content_text ? <Content text={item.content_text} /> : <p className="text-sm muted">Nessun testo: apri il sito ufficiale.</p>}
        </section>

        {item.attachments.length > 0 && (
          <section className="mt-7">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-wider muted">Allegati</h2>
            <ul className="space-y-2">
              {item.attachments.map((a) => (
                <li key={a.url}>
                  <a href={a.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-3 rounded-xl border border-slate-200 p-3 transition hover:border-brand-300 hover:bg-brand-50/50 dark:border-slate-800 dark:hover:bg-brand-900/20">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-brand-50 text-[10px] font-bold uppercase text-brand-700 dark:bg-brand-900/40 dark:text-brand-200">
                      {(a.file.split(".").pop() || "file").slice(0, 4)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold">{a.name}</span>
                      {a.size ? <span className="text-xs muted">{fileSize(a.size)}</span> : null}
                    </span>
                    <Icon name="external" className="h-4 w-4 shrink-0 text-slate-400" />
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        {item.links.length > 0 && (
          <section className="mt-7">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-wider muted">Link nella pagina</h2>
            <ul className="space-y-1.5 text-sm">
              {item.links.slice(0, 40).map((l) => (
                <li key={l.url}>
                  <a href={l.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline dark:text-brand-300">
                    <Icon name="link" className="h-3.5 w-3.5 shrink-0" /> <span className="break-words">{l.text}</span>
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <section className="card mt-5 p-5 sm:p-7">
        <h2 className="mb-4 font-bold">Cronologia</h2>
        <ol className="relative space-y-4 border-l-2 border-brand-100 pl-5 dark:border-brand-900">
          {item.versions.map((v) => {
            const active = (showDiffFor ?? latest) === v.number && v.number > 1;
            return (
              <li key={v.number} className="relative">
                <span className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full ring-4 ring-white dark:ring-[#111a2e] ${v.kind === "new" ? "bg-brand-500" : "bg-amber-400"}`} />
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-semibold">
                    {v.kind === "new" ? (v.baseline ? "Prima rilevazione" : "Pubblicato") : v.change_summary}
                  </p>
                  <span className="text-xs muted">{fmtDateTime(v.created_at)}</span>
                </div>
                {v.number > 1 && (
                  <button className={`mt-1 text-[13px] font-semibold ${active && showDiffFor ? "text-slate-400" : "text-brand-700 dark:text-brand-300"}`}
                    onClick={() => { setParams({ v: String(v.number) }); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                    Vedi le differenze
                  </button>
                )}
              </li>
            );
          })}
        </ol>
      </section>
    </article>
  );
}
