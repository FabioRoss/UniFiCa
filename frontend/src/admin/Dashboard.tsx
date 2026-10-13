import { Link } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { Badge, ErrorBox, Loading, PageTitle } from "../components/ui";
import { fmtDateTime, relTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import BarChart from "./BarChart";

interface Stats {
  subscribers: { total: number; push: number; telegram: number; new_7d: number; platforms: Record<string, number>; modes: Record<string, number>; admins: number; inactive: number };
  updates: { day: number; week: number; month: number };
  updates_per_day: { date: string; count: number }[];
  notifications: { week: number; month: number };
  pending: number;
  items: number;
  top_keywords: [string, number][];
  sources: { id: number; name: string; enabled: boolean; followers: number; ok: boolean; last_run_at: string | null; last_ok_at: string | null; error: string | null }[];
  alerts: number;
  telegram: { enabled: boolean; bot: string | null; channel: string };
  backup: { count: number; last: string | null; last_at: string | null };
}

interface Alert { id: number; created_at: string; level: string; message: string; resolved: boolean }

function Tile({ label, value, sub }: { label: string; value: number | string; sub?: string }) {
  return (
    <div className="card p-4">
      <p className="text-[13px] font-medium muted">{label}</p>
      <p className="mt-1 text-[28px] font-extrabold leading-none tracking-tight">{value}</p>
      {sub && <p className="mt-1.5 text-xs muted">{sub}</p>}
    </div>
  );
}

const PLATFORM: Record<string, string> = { ios: "iPhone", android: "Android", desktop: "Computer", telegram: "Telegram", other: "Altro" };

export default function Dashboard() {
  const { data: s, error, loading, reload } = useFetch<Stats>("/api/admin/stats");
  const { data: alerts, reload: reloadAlerts } = useFetch<Alert[]>("/api/admin/alerts");
  if (loading) return <Loading />;
  if (error || !s) return <ErrorBox message={error ?? "Errore"} onRetry={reload} />;
  const open = (alerts ?? []).filter((a) => !a.resolved);
  const failing = s.sources.filter((x) => x.enabled && !x.ok);

  return (
    <div className="space-y-6">
      <PageTitle title="Panoramica" subtitle="Iscritti, attività dei controlli e salute delle fonti." />

      {(open.length > 0 || failing.length > 0) && (
        <div className="card border-red-200 p-4 dark:border-red-900">
          <p className="mb-2 flex items-center gap-2 font-bold text-red-700 dark:text-red-300"><Icon name="alert" className="h-5 w-5" />Da controllare</p>
          <ul className="space-y-2 text-sm">
            {open.map((a) => (
              <li key={a.id} className="flex items-start justify-between gap-3">
                <span>{a.message} <span className="muted">({relTime(a.created_at)})</span></span>
                <button className="btn-ghost shrink-0 !py-1" onClick={async () => { await api.post(`/api/admin/alerts/${a.id}/resolve`); reloadAlerts(); }}>Risolto</button>
              </li>
            ))}
            {failing.filter((f) => !open.some((a) => a.message.startsWith(f.name))).map((f) => (
              <li key={f.id}><b>{f.name}</b>: {f.error}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Iscritti attivi" value={s.subscribers.total} sub={`+${s.subscribers.new_7d} negli ultimi 7 giorni`} />
        <Tile label="Push / Telegram" value={`${s.subscribers.push} / ${s.subscribers.telegram}`} sub={s.subscribers.inactive ? `${s.subscribers.inactive} disattivati` : undefined} />
        <Tile label="Aggiornamenti (7 g)" value={s.updates.week} sub={`${s.updates.day} oggi · ${s.updates.month} in 30 g`} />
        <Tile label="Notifiche inviate (7 g)" value={s.notifications.week} sub={`${s.notifications.month} in 30 g${s.pending ? ` · ${s.pending} in attesa` : ""}`} />
      </div>

      <div className="card p-5">
        <h2 className="font-bold">Aggiornamenti rilevati al giorno</h2>
        <p className="mb-3 text-sm muted">Nuove pubblicazioni e modifiche, ultimi 30 giorni</p>
        <BarChart data={s.updates_per_day} label="Aggiornamenti rilevati al giorno, ultimi 30 giorni" />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-bold">Fonti</h2>
            <Link to="/admin/fonti" className="text-sm font-semibold text-brand-700 dark:text-brand-300">Gestisci</Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs uppercase tracking-wider muted"><th className="pb-2 font-semibold">Fonte</th><th className="pb-2 text-right font-semibold">Seguita da</th><th className="pb-2 text-right font-semibold">Ultimo controllo</th></tr></thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {s.sources.map((x) => (
                  <tr key={x.id}>
                    <td className="py-2 pr-2">
                      <span className="inline-flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full ${!x.enabled ? "bg-slate-300" : x.ok ? "bg-emerald-500" : "bg-red-500"}`} />
                        <span className={x.enabled ? "" : "muted"}>{x.name}</span>
                        {!x.ok && x.enabled && <Badge tone="red">errore</Badge>}
                      </span>
                    </td>
                    <td className="py-2 text-right tabular-nums">{x.followers}</td>
                    <td className="py-2 text-right text-xs muted" title={fmtDateTime(x.last_run_at)}>{relTime(x.last_run_at) || "mai"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-6">
          <div className="card p-5">
            <h2 className="mb-3 font-bold">Dispositivi</h2>
            <ul className="space-y-1.5 text-sm">
              {Object.entries(s.subscribers.platforms).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <li key={k} className="flex justify-between"><span>{PLATFORM[k] ?? k}</span><span className="font-semibold tabular-nums">{v}</span></li>
              ))}
              {!Object.keys(s.subscribers.platforms).length && <li className="muted">Ancora nessun iscritto</li>}
            </ul>
            <p className="mt-3 text-xs muted">
              Modalità: {s.subscribers.modes.instant ?? 0} subito · {s.subscribers.modes.quiet ?? 0} silenzio notturno · {s.subscribers.modes.digest ?? 0} riepilogo
            </p>
          </div>
          <div className="card p-5">
            <h2 className="mb-3 font-bold">Parole chiave più seguite</h2>
            {s.top_keywords.length ? (
              <div className="flex flex-wrap gap-2">
                {s.top_keywords.map(([k, n]) => <span key={k} className="chip">{k} <b className="tabular-nums">{n}</b></span>)}
              </div>
            ) : <p className="text-sm muted">Nessuna per ora.</p>}
          </div>
          <div className="card p-5 text-sm">
            <h2 className="mb-2 font-bold">Sistema</h2>
            {s.telegram.enabled ? (
              <p>Bot {s.telegram.bot ? <b>@{s.telegram.bot}</b> : "in avvio"}{s.telegram.channel ? <> · canale <b>{s.telegram.channel}</b></> : null}</p>
            ) : <p className="muted">Non configurato (OPENUNIFI_TELEGRAM_BOT_TOKEN).</p>}
            <p className="mt-2">
              Backup automatico: {s.backup.last_at ? <>ultimo {relTime(s.backup.last_at)} ({s.backup.count} conservati)</> : <span className="text-amber-700 dark:text-amber-300">ancora nessuno (ogni notte alle 4)</span>}
            </p>
            <p className="mt-2 muted">{s.items} contenuti archiviati · {s.subscribers.admins} destinatari avvisi admin</p>
          </div>
        </div>
      </div>
    </div>
  );
}
