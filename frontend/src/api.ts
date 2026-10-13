// Typed fetch helpers for the Open Unifi API.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      // Required by the server on admin writes (CSRF defence)
      "X-OpenUnifi": "1",
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = `Errore ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = "Dati non validi: controlla i campi";
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
  put: <T>(url: string, body?: unknown) => request<T>("PUT", url, body ?? {}),
  del: <T>(url: string) => request<T>("DELETE", url),
};

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ── Types ────────────────────────────────────────────────────────────────

export interface SiteTexts {
  intro: string;
  disclaimer: string;
  contact_email: string;
  telegram_channel_url: string;
}

export interface AppConfig {
  site_name: string;
  base_url: string;
  vapid_public_key: string;
  telegram_bot: string | null;
  telegram_enabled: boolean;
  site: SiteTexts;
}

export type SourceKind = "news" | "page" | "exams";

export interface SourceInfo {
  id: number;
  slug: string;
  name: string;
  category: string;
  kind: SourceKind;
  url: string;
  last_ok_at: string | null;
  interval_minutes: number;
}

export interface FeedEntry {
  id: number;
  number: number;
  kind: "new" | "modified";
  baseline: boolean;
  created_at: string;
  change_summary: string;
  item: {
    id: number;
    title: string;
    summary: string;
    url: string;
    published_on: string | null;
    attachments: number;
    source: { id: number; name: string; category: string; kind: SourceKind };
  };
}

export interface Attachment {
  url: string;
  name: string;
  file: string;
  size?: number | null;
  type?: string;
  diff?: DiffRow[];
}

export interface ItemDetail {
  id: number;
  title: string;
  summary: string;
  url: string;
  published_on: string | null;
  content_text: string;
  attachments: Attachment[];
  links: { url: string; text: string }[];
  first_seen_at: string;
  changed_at: string;
  checked_at: string;
  source: SourceInfo;
  versions: { number: number; kind: "new" | "modified"; baseline: boolean; created_at: string; change_summary: string }[];
}

export type DiffPart = { op: "eq" | "add" | "del"; text: string };
export type DiffRow =
  | { op: "eq" | "add" | "del"; text: string }
  | { op: "change"; parts: DiffPart[] }
  | { op: "skip"; count: number };

export interface VersionDiff {
  number: number;
  kind: string;
  created_at: string;
  change_summary: string;
  title: string;
  previous: { number: number; created_at: string } | null;
  title_change?: { old: string; new: string } | null;
  text: DiffRow[];
  attachments: { added: Attachment[]; removed: Attachment[]; changed: Attachment[] };
}

export interface Exam {
  id: number;
  title: string;
  url: string;
  date: string;
  time: string;
  name: string;
  appello: string;
  code: string;
  codes?: string[];
  type: string;
  teachers: string[];
  reg_from: string | null;
  reg_to: string | null;
  changed: boolean;
  recent: boolean;
  source_id: number;
}

export interface LinkItem {
  id: number;
  kind: "link" | "contact";
  title: string;
  url: string;
  description: string;
  email: string;
  phone: string;
  location: string;
  hours: string;
  tags: string;
  position: number;
  group_id: number;
}

export interface LinkGroup {
  id: number;
  name: string;
  description: string;
  icon: string;
  links: LinkItem[];
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  url: string;
  pinned: boolean;
  created_at: string;
}

export interface Prefs {
  sources: number[] | null;
  keywords: string[];
  notify_new: boolean;
  notify_modified: boolean;
  announcements: boolean;
  quiet: { start: string; end: string } | null;
  digest: string | null;
}

export interface Subscription {
  token: string;
  channel: "push" | "telegram";
  prefs: Prefs;
  active: boolean;
  is_admin: boolean;
  platform: string;
}
