import type { SourceInfo } from "../api";
import { Icon } from "../components/Icon";
import { PageTitle } from "../components/ui";
import { useConfig } from "../lib/app";
import { relTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";

const KIND = { news: "Notizie", page: "Pagina monitorata", exams: "Appelli ESSE3" } as const;

function every(min: number): string {
  if (min < 60) return `ogni ${min} min`;
  if (min < 1440) return `ogni ${Math.round(min / 60)} h`;
  return "ogni giorno";
}

export default function Info() {
  const cfg = useConfig();
  const { data: sources } = useFetch<SourceInfo[]>("/api/sources");
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageTitle title="Come funziona" />

      <section className="card p-5 sm:p-6">
        <p className="text-[15px] leading-relaxed">{cfg?.site.intro}</p>
        <ul className="mt-4 space-y-3 text-[15px]">
          <li className="flex gap-3"><Icon name="refresh" className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />Controlliamo periodicamente le pagine pubbliche dei siti UniFI, rispettando i loro server.</li>
          <li className="flex gap-3"><Icon name="sparkle" className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />Quando compare qualcosa di nuovo, o un testo, una data o un allegato cambiano, salviamo una nuova versione.</li>
          <li className="flex gap-3"><Icon name="bell" className="mt-0.5 h-5 w-5 shrink-0 text-brand-600" />Ti avvisiamo con una notifica push o su Telegram, e puoi vedere esattamente cosa è cambiato.</li>
        </ul>
      </section>

      <section className="card p-5 sm:p-6">
        <h2 className="mb-3 text-lg font-bold">Fonti monitorate</h2>
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {(sources ?? []).map((s) => (
            <li key={s.id} className="flex items-center gap-3 py-3">
              <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" title="Attiva" />
              <div className="min-w-0 flex-1">
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="block truncate font-medium hover:text-brand-700 dark:hover:text-brand-300">{s.name}</a>
                <p className="text-xs muted">{KIND[s.kind]} · {every(s.interval_minutes)}{s.last_ok_at ? ` · controllata ${relTime(s.last_ok_at)}` : ""}</p>
              </div>
              <a href={`/rss/${s.slug}.xml`} className="btn-ghost h-9 w-9 !p-0" title="Feed RSS" aria-label={`Feed RSS di ${s.name}`}>
                <Icon name="rss" className="h-4 w-4" />
              </a>
            </li>
          ))}
        </ul>
        <a href="/rss.xml" className="btn-soft mt-4"><Icon name="rss" className="h-4 w-4" />Feed RSS di tutte le fonti</a>
      </section>

      <section className="card p-5 sm:p-6">
        <h2 className="mb-2 text-lg font-bold">Privacy</h2>
        <p className="text-[15px] leading-relaxed muted">
          Nessun account e nessun dato personale: per le notifiche salviamo solo l'indirizzo tecnico fornito dal browser
          (o l'id della chat Telegram) e le tue preferenze. Disattivando le notifiche vengono cancellati.
        </p>
      </section>

      <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-5 text-[14px] leading-relaxed text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100">
        <p className="mb-1 font-bold">Progetto non ufficiale</p>
        <p>{cfg?.site.disclaimer}</p>
        {cfg?.site.contact_email && (
          <p className="mt-2">Segnalazioni: <a className="font-semibold underline" href={`mailto:${cfg.site.contact_email}`}>{cfg.site.contact_email}</a></p>
        )}
      </section>
    </div>
  );
}
