import { useState } from "react";
import { api, type LinkGroup, type LinkItem } from "../api";
import { Icon } from "../components/Icon";
import { ErrorBox, Field, Loading, Modal, PageTitle, Spinner } from "../components/ui";
import { useFetch } from "../lib/useFetch";

type LinkDraft = Omit<LinkItem, "id" | "position"> & { id?: number };
type GroupDraft = { id?: number; name: string; description: string; icon: string };

const emptyLink = (group_id: number, kind: "link" | "contact" = "link"): LinkDraft => ({
  group_id, kind, title: "", url: "", description: "", email: "", phone: "", location: "", hours: "", tags: "",
});

function move<T>(arr: T[], i: number, d: number): T[] {
  const j = i + d;
  if (j < 0 || j >= arr.length) return arr;
  const out = [...arr];
  [out[i], out[j]] = [out[j], out[i]];
  return out;
}

function LinkForm({ draft, groups, onDone }: { draft: LinkDraft; groups: LinkGroup[]; onDone: () => void }) {
  const [d, setD] = useState(draft);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const contact = d.kind === "contact";
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (d.id) await api.put(`/api/admin/links/${d.id}`, d);
      else await api.post("/api/admin/links", d);
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const input = (k: keyof LinkDraft, label: string, placeholder = "", hint?: string) => (
    <Field label={label} hint={hint}>
      <input className="input" value={String(d[k] ?? "")} placeholder={placeholder} onChange={(e) => setD({ ...d, [k]: e.target.value })} />
    </Field>
  );
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1 dark:bg-slate-900">
        {(["link", "contact"] as const).map((k) => (
          <button key={k} onClick={() => setD({ ...d, kind: k })}
            className={`rounded-xl py-2 text-sm font-semibold ${d.kind === k ? "bg-white text-brand-700 shadow dark:bg-slate-800 dark:text-brand-200" : "muted"}`}>
            {k === "link" ? "Link" : "Contatto / luogo"}
          </button>
        ))}
      </div>
      <Field label="Gruppo">
        <select className="input" value={d.group_id} onChange={(e) => setD({ ...d, group_id: Number(e.target.value) })}>
          {groups.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
      </Field>
      {input("title", "Titolo", contact ? "es. Segreteria studenti" : "es. Kairos: orari e aule")}
      {input("url", contact ? "Link (facoltativo)" : "Link", "https://...")}
      {input("description", "Descrizione (facoltativa)")}
      {contact && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {input("email", "Email")}
          {input("phone", "Telefono")}
          {input("location", "Indirizzo / luogo")}
          {input("hours", "Orari")}
        </div>
      )}
      {input("tags", "Parole per la ricerca", "es. certificati tasse", "Non visibili: aiutano a trovare il link cercando sinonimi.")}
      {err && <p className="text-sm font-medium text-red-600">{err}</p>}
      <div className="flex justify-end gap-2">
        <button className="btn-ghost" onClick={onDone}>Annulla</button>
        <button className="btn-primary" onClick={save} disabled={busy || !d.title}>{busy && <Spinner className="h-4 w-4 text-white" />}Salva</button>
      </div>
    </div>
  );
}

function GroupForm({ draft, onDone }: { draft: GroupDraft; onDone: () => void }) {
  const [d, setD] = useState(draft);
  const [err, setErr] = useState<string | null>(null);
  const save = async () => {
    try {
      if (d.id) await api.put(`/api/admin/link-groups/${d.id}`, d);
      else await api.post("/api/admin/link-groups", d);
      onDone();
    } catch (e) {
      setErr((e as Error).message);
    }
  };
  return (
    <div className="space-y-4">
      <Field label="Nome del gruppo"><input className="input" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="es. Segreterie e uffici" /></Field>
      <Field label="Descrizione (facoltativa)"><input className="input" value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} /></Field>
      {err && <p className="text-sm font-medium text-red-600">{err}</p>}
      <div className="flex justify-end gap-2">
        <button className="btn-ghost" onClick={onDone}>Annulla</button>
        <button className="btn-primary" onClick={save} disabled={!d.name}>Salva</button>
      </div>
    </div>
  );
}

export default function LinksAdmin() {
  const { data, error, loading, reload, setData } = useFetch<LinkGroup[]>("/api/links");
  const [link, setLink] = useState<LinkDraft | null>(null);
  const [group, setGroup] = useState<GroupDraft | null>(null);

  const reorderGroups = async (i: number, dir: number) => {
    if (!data) return;
    const next = move(data, i, dir);
    setData(next);
    await api.post("/api/admin/link-groups/order", { ids: next.map((g) => g.id) });
  };
  const reorderLinks = async (g: LinkGroup, i: number, dir: number) => {
    const links = move(g.links, i, dir);
    setData((data ?? []).map((x) => (x.id === g.id ? { ...x, links } : x)));
    await api.post("/api/admin/links/order", { ids: links.map((l) => l.id) });
  };
  const delGroup = async (g: LinkGroup) => {
    if (!confirm(`Eliminare il gruppo "${g.name}" e i suoi ${g.links.length} link?`)) return;
    await api.del(`/api/admin/link-groups/${g.id}`);
    reload();
  };
  const delLink = async (l: LinkItem) => {
    if (!confirm(`Eliminare "${l.title}"?`)) return;
    await api.del(`/api/admin/links/${l.id}`);
    reload();
  };

  return (
    <div>
      <PageTitle title="Link utili e contatti" subtitle="Organizza la pagina pubblica in gruppi. Gli utenti la cercano al volo."
        action={<button className="btn-primary" onClick={() => setGroup({ name: "", description: "", icon: "" })}><Icon name="plus" className="h-4 w-4" />Gruppo</button>} />
      {error && <ErrorBox message={error} onRetry={reload} />}
      {loading ? <Loading /> : (
        <div className="space-y-5">
          {data?.map((g, gi) => (
            <section key={g.id} className="card p-4">
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <div className="min-w-0 flex-1">
                  <h2 className="font-bold">{g.name}</h2>
                  {g.description && <p className="text-sm muted">{g.description}</p>}
                </div>
                <button className="btn-ghost h-8 w-8 !p-0" onClick={() => reorderGroups(gi, -1)} disabled={gi === 0} aria-label="Sposta su"><Icon name="up" className="h-4 w-4" /></button>
                <button className="btn-ghost h-8 w-8 !p-0" onClick={() => reorderGroups(gi, 1)} disabled={gi === data.length - 1} aria-label="Sposta giù"><Icon name="down" className="h-4 w-4" /></button>
                <button className="btn-ghost h-8 w-8 !p-0" onClick={() => setGroup({ id: g.id, name: g.name, description: g.description, icon: g.icon })} aria-label="Modifica gruppo"><Icon name="edit" className="h-4 w-4" /></button>
                <button className="btn-ghost h-8 w-8 !p-0 text-red-600" onClick={() => delGroup(g)} aria-label="Elimina gruppo"><Icon name="trash" className="h-4 w-4" /></button>
              </div>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {g.links.map((l, li) => (
                  <li key={l.id} className="flex items-center gap-2 py-2">
                    <Icon name={l.kind === "contact" ? "users" : "link"} className="h-4 w-4 shrink-0 text-slate-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{l.title}</p>
                      <p className="truncate text-xs muted">{[l.email, l.phone, l.location, l.url].filter(Boolean).join(" · ")}</p>
                    </div>
                    <button className="btn-ghost h-8 w-8 !p-0" onClick={() => reorderLinks(g, li, -1)} disabled={li === 0} aria-label="Sposta su"><Icon name="up" className="h-4 w-4" /></button>
                    <button className="btn-ghost h-8 w-8 !p-0" onClick={() => reorderLinks(g, li, 1)} disabled={li === g.links.length - 1} aria-label="Sposta giù"><Icon name="down" className="h-4 w-4" /></button>
                    <button className="btn-ghost h-8 w-8 !p-0" onClick={() => setLink({ ...l })} aria-label="Modifica"><Icon name="edit" className="h-4 w-4" /></button>
                    <button className="btn-ghost h-8 w-8 !p-0 text-red-600" onClick={() => delLink(l)} aria-label="Elimina"><Icon name="trash" className="h-4 w-4" /></button>
                  </li>
                ))}
              </ul>
              <div className="mt-2 flex gap-2">
                <button className="btn-soft !py-1.5" onClick={() => setLink(emptyLink(g.id))}><Icon name="plus" className="h-4 w-4" />Link</button>
                <button className="btn-soft !py-1.5" onClick={() => setLink(emptyLink(g.id, "contact"))}><Icon name="plus" className="h-4 w-4" />Contatto</button>
              </div>
            </section>
          ))}
        </div>
      )}
      <Modal open={!!link} onClose={() => setLink(null)} title={link?.id ? "Modifica" : "Nuovo elemento"}>
        {link && data && <LinkForm draft={link} groups={data} onDone={() => { setLink(null); reload(); }} />}
      </Modal>
      <Modal open={!!group} onClose={() => setGroup(null)} title={group?.id ? "Modifica gruppo" : "Nuovo gruppo"}>
        {group && <GroupForm draft={group} onDone={() => { setGroup(null); reload(); }} />}
      </Modal>
    </div>
  );
}
