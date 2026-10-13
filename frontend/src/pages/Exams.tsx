import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Exam, SourceInfo } from "../api";
import { Icon } from "../components/Icon";
import { Badge, Empty, ErrorBox, Highlight, Loading, PageTitle, SearchBox } from "../components/ui";
import { daysUntil, fmtDate, fmtDateTime, fmtDay, matchesQuery, nameCase, relTime, titleCase } from "../lib/format";
import { useFetch } from "../lib/useFetch";

type Filter = "all" | "open" | "soon";

function regState(e: Exam): { label: string; tone: "green" | "slate" | "amber" } | null {
  if (!e.reg_from || !e.reg_to) return null;
  const from = daysUntil(e.reg_from);
  const to = daysUntil(e.reg_to);
  if (from > 0) return { label: `Iscrizioni dal ${fmtDate(e.reg_from, { year: undefined })}`, tone: "slate" };
  if (to >= 0) return { label: to === 0 ? "Iscrizioni: ultimo giorno" : `Iscrizioni aperte, chiudono tra ${to} g`, tone: to <= 2 ? "amber" : "green" };
  return { label: "Iscrizioni chiuse", tone: "slate" };
}

function monthLabel(iso: string) {
  const s = new Date(`${iso}T12:00:00`).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function Exams() {
  const { data, error, loading, reload } = useFetch<{ exams: Exam[]; sources: (SourceInfo & { snapshot_at: string | null })[] }>("/api/exams");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const list = useMemo(() => {
    let xs = data?.exams ?? [];
    if (q) xs = xs.filter((e) => matchesQuery(q, e.title, e.name, e.appello, e.type, e.teachers.join(" "), e.code));
    if (filter === "open") xs = xs.filter((e) => regState(e)?.tone === "green" || regState(e)?.tone === "amber");
    if (filter === "soon") xs = xs.filter((e) => daysUntil(e.date) <= 14);
    return xs;
  }, [data, q, filter]);

  // Live data says "controllata X fa"; imported data (server cannot reach
  // ESSE3) carries its date instead, until a real check is newer.
  const src = data?.sources[0];
  const snapshotAt = src?.snapshot_at && (!src.last_ok_at || src.snapshot_at > src.last_ok_at) ? src.snapshot_at : null;
  const checkedAt = !snapshotAt ? src?.last_ok_at ?? null : null;

  const months = useMemo(() => {
    const out: { label: string; items: Exam[] }[] = [];
    for (const e of list) {
      const label = monthLabel(e.date);
      if (out.length && out[out.length - 1].label === label) out[out.length - 1].items.push(e);
      else out.push({ label, items: [e] });
    }
    return out;
  }, [list]);

  return (
    <div>
      <PageTitle title="Appelli d'esame"
        subtitle={<>Dalla bacheca pubblica ESSE3{checkedAt ? <>, controllata {relTime(checkedAt)}</> : null}. Per iscriverti usa sempre lo <a className="font-semibold text-brand-700 underline dark:text-brand-300" href="https://studenti.unifi.it/" target="_blank" rel="noopener noreferrer">Sportello studenti</a>.</>} />
      {snapshotAt && (
        <div className="mb-4 flex gap-3 rounded-2xl border border-amber-200 bg-amber-50/70 p-4 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100">
          <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0" />
          <p>
            Dati della bacheca aggiornati al <b>{fmtDateTime(snapshotAt)}</b>: al momento non riusciamo a controllarla in automatico.
            Date e orari potrebbero essere cambiati, verifica sempre sulla{" "}
            <a className="font-semibold underline" href="https://studenti.unifi.it/ListaAppelliOfferta.do" target="_blank" rel="noopener noreferrer">bacheca ufficiale</a>.
          </p>
        </div>
      )}

      <div className="sticky top-[calc(3.5rem+env(safe-area-inset-top))] z-20 -mx-4 mb-4 space-y-3 bg-[#f5f8ff]/90 px-4 pb-3 pt-1 backdrop-blur-xl dark:bg-[#0b1220]/90">
        <SearchBox value={q} onChange={setQ} placeholder="Cerca esame o docente..." />
        <div className="flex flex-wrap gap-2">
          {([["all", "Tutti"], ["open", "Iscrizioni aperte"], ["soon", "Prossimi 14 giorni"]] as [Filter, string][]).map(([k, l]) => (
            <button key={k} className={`chip shrink-0 ${filter === k ? "chip-on" : ""}`} onClick={() => setFilter(k)}>{l}</button>
          ))}
          <Link to="/notifiche" className="chip shrink-0"><Icon name="bell" className="h-3.5 w-3.5" />Avvisami</Link>
        </div>
      </div>

      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : !list.length ? (
        <Empty icon="calendar" title={q || filter !== "all" ? "Nessun appello trovato" : "Nessun appello rilevato"}>
          {q ? "Controlla il nome dell'insegnamento o prova con il cognome del docente." : "Appena vengono pubblicati li trovi qui."}
        </Empty>
      ) : (
        <div className="space-y-7">
          {months.map((m) => (
            <section key={m.label}>
              <h2 className="mb-2.5 px-1 text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">{m.label}</h2>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {m.items.map((e) => {
                  const d = fmtDay(e.date);
                  const reg = regState(e);
                  return (
                    <Link key={e.id} to={`/n/${e.id}`} state={{ backLabel: "Appelli" }} className="card flex gap-4 p-4 transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg dark:hover:border-brand-800">
                      <div className="flex w-14 shrink-0 flex-col items-center justify-center rounded-xl bg-gradient-to-b from-brand-50 to-brand-100/60 py-2 text-brand-800 dark:from-brand-900/50 dark:to-brand-900/20 dark:text-brand-100">
                        <span className="text-[11px] font-semibold uppercase">{d.weekday}</span>
                        <span className="text-2xl font-extrabold leading-none">{d.day}</span>
                        <span className="text-[11px] font-semibold uppercase">{d.month}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="mb-1 flex flex-wrap gap-1.5">
                          {e.recent && <Badge tone="brand">Nuovo</Badge>}
                          {e.changed && <Badge tone="amber">Modificato</Badge>}
                          {e.type && <Badge tone="slate">{e.type}</Badge>}
                        </div>
                        <h3 className="font-semibold leading-snug"><Highlight text={titleCase(e.name)} query={q} /></h3>
                        {e.appello && <p className="text-sm muted"><Highlight text={e.appello} query={q} /></p>}
                        <p className="mt-1.5 flex items-center gap-1.5 text-[13px] font-medium text-slate-700 dark:text-slate-300">
                          <Icon name="clock" className="h-3.5 w-3.5" /> ore {e.time || "n.d."}
                        </p>
                        {reg && (
                          <p className={`mt-1 text-[13px] font-medium ${reg.tone === "green" ? "text-emerald-700 dark:text-emerald-300" : reg.tone === "amber" ? "text-amber-700 dark:text-amber-300" : "muted"}`}>
                            {reg.label}
                          </p>
                        )}
                        {e.teachers.length > 0 && (
                          <p className="mt-1 line-clamp-1 text-xs muted">
                            <Highlight text={e.teachers.map(nameCase).join(", ")} query={q} />
                          </p>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
