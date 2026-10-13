import { api } from "../api";
import { Icon, TelegramIcon } from "../components/Icon";
import { Badge, Empty, ErrorBox, Loading, PageTitle } from "../components/ui";
import { fmtDate, relTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";

interface Sub {
  id: number; channel: "push" | "telegram"; platform: string; active: boolean; is_admin: boolean; created_at: string;
  last_active_at: string; last_sent_at: string | null; failures: number; sources: string; keywords: string[]; mode: string;
}

const MODE: Record<string, string> = { instant: "subito", quiet: "silenzio notturno", digest: "riepilogo" };

export default function Subscribers() {
  const { data, error, loading, reload } = useFetch<Sub[]>("/api/admin/subscribers");
  const toggleAdmin = async (s: Sub) => {
    await api.put(`/api/admin/subscribers/${s.id}`, { is_admin: !s.is_admin });
    reload();
  };
  const remove = async (s: Sub) => {
    if (!confirm("Rimuovere questo iscritto?")) return;
    await api.del(`/api/admin/subscribers/${s.id}`);
    reload();
  };
  return (
    <div>
      <PageTitle title="Iscritti" subtitle="Anonimi: nessun nome o email, solo il canale e le preferenze." />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : !data?.length ? <Empty icon="users" title="Ancora nessun iscritto">Condividi il link del sito per iniziare.</Empty> : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs uppercase tracking-wider muted dark:border-slate-800">
                <th className="p-3 font-semibold">#</th><th className="p-3 font-semibold">Canale</th><th className="p-3 font-semibold">Segue</th>
                <th className="p-3 font-semibold">Modalità</th><th className="p-3 font-semibold">Iscritto</th><th className="p-3 font-semibold">Ultimo invio</th><th className="p-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.map((s) => (
                <tr key={s.id} className={s.active ? "" : "opacity-50"}>
                  <td className="p-3 tabular-nums muted">{s.id}</td>
                  <td className="p-3">
                    <span className="inline-flex items-center gap-1.5">
                      {s.channel === "telegram" ? <TelegramIcon className="h-4 w-4 text-[#229ED9]" /> : <Icon name="bell" className="h-4 w-4 text-brand-600" />}
                      {s.channel === "telegram" ? "Telegram" : s.platform}
                      {s.is_admin && <Badge>admin</Badge>}
                      {!s.active && <Badge tone="slate">in pausa</Badge>}
                    </span>
                  </td>
                  <td className="max-w-[260px] p-3">
                    <p className="truncate">{s.sources}</p>
                    {s.keywords.length > 0 && <p className="truncate text-xs muted">+ {s.keywords.join(", ")}</p>}
                  </td>
                  <td className="p-3">{MODE[s.mode] ?? s.mode}</td>
                  <td className="p-3 text-xs muted">{fmtDate(s.created_at)}</td>
                  <td className="p-3 text-xs muted">{relTime(s.last_sent_at) || "mai"}{s.failures > 0 && <span className="text-red-600"> · {s.failures} errori</span>}</td>
                  <td className="whitespace-nowrap p-3 text-right">
                    <button className="btn-ghost !px-2 !py-1 text-xs" onClick={() => toggleAdmin(s)}>{s.is_admin ? "Togli admin" : "Rendi admin"}</button>
                    <button className="btn-ghost !px-2 !py-1 text-red-600" onClick={() => remove(s)} aria-label="Rimuovi"><Icon name="trash" className="h-4 w-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
