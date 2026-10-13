import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, qs, type Announcement, type FeedEntry, type SourceInfo } from "../api";
import { Icon } from "../components/Icon";
import { Badge, Empty, ErrorBox, Highlight, Loading, SearchBox, Spinner, useDebounced } from "../components/ui";
import { useConfig } from "../lib/app";
import { fmtDate, parseDate, relTime, titleCase } from "../lib/format";
import { getToken, pushState } from "../lib/push";
import { useFetch } from "../lib/useFetch";

type Kind = "" | "new" | "modified";

function dayLabel(iso: string): string {
  const d = parseDate(iso);
  const key = (x: Date) => x.toLocaleDateString("it-IT", { timeZone: "Europe/Rome" });
  const today = new Date();
  const yesterday = new Date(Date.now() - 86400000);
  if (key(d) === key(today)) return "Oggi";
  if (key(d) === key(yesterday)) return "Ieri";
  return d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Rome" });
}

export function FeedCard({ e, query = "" }: { e: FeedEntry; query?: string }) {
  const modified = e.kind === "modified";
  const kindIcon = e.item.source.kind === "exams" ? "calendar" : e.item.source.kind === "page" ? "file" : "news";
  return (
    <Link to={`/n/${e.item.id}?v=${e.number}`}
      className="card group block p-4 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg dark:hover:border-brand-800">
      <div className="mb-2 flex items-center gap-2">
        {!e.baseline && (modified ? <Badge tone="amber"><Icon name="pencil" className="h-3 w-3" strokeWidth={2.4} />Modificato</Badge>
          : <Badge tone="brand"><Icon name="sparkle" className="h-3 w-3" strokeWidth={2.4} />Nuovo</Badge>)}
        <span className="inline-flex min-w-0 flex-1 items-center gap-1.5 text-xs font-medium muted">
          <Icon name={kindIcon} className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{e.item.source.name}</span>
        </span>
        <span className="shrink-0 text-xs muted">{relTime(e.created_at)}</span>
      </div>
      <h3 className="text-[16px] font-semibold leading-snug group-hover:text-brand-700 dark:group-hover:text-brand-300">
        <Highlight text={e.item.source.kind === "exams" ? titleCase(e.item.title) : e.item.title} query={query} />
      </h3>
      {modified ? (
        <p className="mt-1.5 text-sm text-amber-800 dark:text-amber-200/90">{e.change_summary}</p>
      ) : e.item.summary ? (
        <p className="mt-1.5 line-clamp-2 text-sm muted"><Highlight text={e.item.summary} query={query} /></p>
      ) : null}
      {(e.item.attachments > 0 || e.item.published_on) && (
        <div className="mt-3 flex items-center gap-3 text-xs muted">
          {e.item.published_on && e.item.source.kind === "news" && <span>Pubblicato il {fmtDate(e.item.published_on)}</span>}
          {e.item.attachments > 0 && (
            <span className="inline-flex items-center gap-1"><Icon name="file" className="h-3.5 w-3.5" />{e.item.attachments} allegat{e.item.attachments === 1 ? "o" : "i"}</span>
          )}
        </div>
      )}
    </Link>
  );
}

function PushCta() {
  const cfg = useConfig();
  if (getToken() || pushState() === "denied") return null;
  return (
    <Link to="/notifiche" className="brand-gradient relative mb-6 block overflow-hidden rounded-2xl p-5 text-white shadow-lg shadow-brand-700/25">
      <div className="absolute -right-6 -top-10 h-36 w-36 rounded-full bg-white/10" />
      <div className="absolute -bottom-12 right-16 h-28 w-28 rounded-full bg-white/10" />
      <div className="relative flex items-center gap-4">
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-white/15 ring-1 ring-white/25">
          <Icon name="bell" className="h-6 w-6" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-bold">Non perderti più nulla</p>
          <p className="text-sm text-white/85">
            Attiva le notifiche{cfg?.telegram_enabled ? " o usa Telegram" : ""}: ti avvisiamo appena qualcosa cambia.
          </p>
        </div>
        <Icon name="chevronRight" className="h-5 w-5 shrink-0 opacity-80" />
      </div>
    </Link>
  );
}

function Announcements() {
  const { data } = useFetch<Announcement[]>("/api/announcements");
  if (!data?.length) return null;
  return (
    <div className="mb-6 space-y-3">
      {data.slice(0, 3).map((a) => (
        <div key={a.id} className="card flex gap-3 border-brand-200 bg-gradient-to-br from-brand-50 to-white p-4 dark:border-brand-900 dark:from-brand-900/30 dark:to-[#111a2e]">
          <Icon name="megaphone" className="mt-0.5 h-5 w-5 shrink-0 text-brand-600 dark:text-brand-300" />
          <div className="min-w-0">
            <p className="font-semibold">{a.title}</p>
            {a.body && <p className="mt-1 whitespace-pre-line text-sm muted">{a.body}</p>}
            {a.url && (
              <a href={a.url} className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand-700 dark:text-brand-300"
                {...(a.url.startsWith("http") ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
                Apri <Icon name="external" className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function Feed() {
  const cfg = useConfig();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const kind = (params.get("tipo") ?? "") as Kind;
  const source = params.get("fonte") ?? "";
  const dq = useDebounced(q.trim(), 300);
  const { data: sources } = useFetch<SourceInfo[]>("/api/sources");

  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [next, setNext] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [more, setMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    setParams(p, { replace: true });
  };

  useEffect(() => {
    const p = new URLSearchParams(params);
    if (dq) p.set("q", dq); else p.delete("q");
    if (p.toString() !== params.toString()) setParams(p, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dq]);

  const base = useMemo(() => ({ q: dq, kind, source }), [dq, kind, source]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.get<{ entries: FeedEntry[]; next: number | null }>(`/api/feed${qs({ ...base, limit: 30 })}`)
      .then((r) => { if (alive) { setEntries(r.entries); setNext(r.next); } })
      .catch((e) => alive && setError(e.message))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [base, nonce]);

  const loadMore = async () => {
    if (!next) return;
    setMore(true);
    try {
      const r = await api.get<{ entries: FeedEntry[]; next: number | null }>(`/api/feed${qs({ ...base, before: next, limit: 30 })}`);
      setEntries((x) => [...x, ...r.entries]);
      setNext(r.next);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMore(false);
    }
  };

  const groups = useMemo(() => {
    const out: { label: string; items: FeedEntry[] }[] = [];
    for (const e of entries) {
      const label = dayLabel(e.created_at);
      if (out.length && out[out.length - 1].label === label) out[out.length - 1].items.push(e);
      else out.push({ label, items: [e] });
    }
    return out;
  }, [entries]);

  const newsSources = (sources ?? []).filter((s) => s.kind !== "exams");
  const filtered = !!(dq || kind || source);

  return (
    <div>
      <section className="mb-6">
        <h1 className="text-[28px] font-extrabold tracking-tight sm:text-[34px]">
          Le novità di <span className="brand-text">UniFI</span>, in un posto solo
        </h1>
        <p className="mt-2 max-w-2xl text-[15px] muted">{cfg?.site.intro}</p>
      </section>

      <PushCta />
      <Announcements />

      <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-4 mb-4 space-y-3 bg-[#f5f8ff]/90 px-4 pb-3 pt-1 backdrop-blur-xl dark:bg-[#0b1220]/90">
        <SearchBox value={q} onChange={setQ} placeholder="Cerca negli avvisi, anche nel testo..." />
        <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4">
          {([["", "Tutto"], ["new", "Nuovi"], ["modified", "Modificati"]] as [Kind, string][]).map(([k, l]) => (
            <button key={k} className={`chip shrink-0 ${kind === k ? "chip-on" : ""}`} onClick={() => set("tipo", k)}>{l}</button>
          ))}
          <span className="mx-1 w-px shrink-0 bg-slate-200 dark:bg-slate-700" />
          <select className={`chip shrink-0 cursor-pointer pr-2 ${source ? "chip-on" : ""}`} value={source}
            onChange={(e) => set("fonte", e.target.value)} aria-label="Filtra per fonte">
            <option value="">Tutte le fonti</option>
            {newsSources.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={() => setNonce((n) => n + 1)} />}
      {loading ? <Loading /> : !entries.length ? (
        filtered ? <Empty title="Nessun risultato">Prova a cambiare parole o filtri.</Empty>
          : <Empty icon="news" title="Ancora nessun aggiornamento">Il primo controllo dei siti è in corso: torna tra qualche minuto.</Empty>
      ) : (
        <div className="space-y-7">
          {groups.map((g) => (
            <section key={g.label}>
              <h2 className="mb-2.5 px-1 text-xs font-bold uppercase tracking-wider text-slate-500 first-letter:uppercase dark:text-slate-400">{g.label}</h2>
              <div className="grid gap-3 md:grid-cols-2">
                {g.items.map((e) => <FeedCard key={e.id} e={e} query={dq} />)}
              </div>
            </section>
          ))}
          {next && (
            <div className="flex justify-center">
              <button className="btn-soft" onClick={loadMore} disabled={more}>
                {more ? <Spinner className="h-4 w-4" /> : <Icon name="down" className="h-4 w-4" />} Carica altri
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
