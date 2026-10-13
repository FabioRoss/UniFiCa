import { useState } from "react";
import { Link } from "react-router-dom";
import { api, qs } from "../api";
import { Icon } from "../components/Icon";
import { Badge, ErrorBox, Loading, PageTitle, SearchBox, useDebounced } from "../components/ui";
import { relTime } from "../lib/format";
import { useFetch } from "../lib/useFetch";

interface AdminItem { id: number; title: string; url: string; source: string; hidden: boolean; versions: number; changed_at: string }

export default function Items() {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 300);
  const { data, error, loading, reload } = useFetch<AdminItem[]>(`/api/admin/items${qs({ q: dq })}`);
  const toggle = async (i: AdminItem) => {
    await api.put(`/api/admin/items/${i.id}`, { hidden: !i.hidden });
    reload();
  };
  return (
    <div>
      <PageTitle title="Contenuti" subtitle="Tutto ciò che è stato archiviato. Nascondi un elemento per toglierlo da feed, ricerca e RSS." />
      <div className="mb-4"><SearchBox value={q} onChange={setQ} placeholder="Cerca per titolo..." /></div>
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : (
        <div className="card divide-y divide-slate-100 dark:divide-slate-800">
          {data?.map((i) => (
            <div key={i.id} className={`flex items-center gap-3 p-3 ${i.hidden ? "opacity-50" : ""}`}>
              <div className="min-w-0 flex-1">
                <Link to={`/n/${i.id}`} state={{ backLabel: "Contenuti" }} className="block truncate text-sm font-medium hover:text-brand-700">{i.title}</Link>
                <p className="text-xs muted">{i.source} · {i.versions} versioni · {relTime(i.changed_at)}</p>
              </div>
              {i.hidden && <Badge tone="slate">nascosto</Badge>}
              <button className="btn-ghost h-9 w-9 !p-0" onClick={() => toggle(i)} title={i.hidden ? "Mostra" : "Nascondi"}>
                <Icon name={i.hidden ? "eye" : "eyeOff"} className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
