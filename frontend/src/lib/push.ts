// Web Push subscription flow and the device token that owns its preferences.
import { api, type Prefs, type Subscription } from "../api";

const TOKEN_KEY = "openunifi.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: the subscription still works, prefs just are not editable later */
  }
}

export type Platform = "ios" | "android" | "desktop" | "other";

export function platform(): Platform {
  const ua = navigator.userAgent;
  // iPadOS reports itself as a Mac; touch support gives it away
  if (/iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return "ios";
  if (/Android/.test(ua)) return "android";
  if (/Windows|Macintosh|Linux|CrOS/.test(ua)) return "desktop";
  return "other";
}

export function isStandalone(): boolean {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as unknown as { standalone?: boolean }).standalone === true
  );
}

export function iosVersion(): number | null {
  const m = navigator.userAgent.match(/OS (\d+)_(\d+)/);
  return m ? parseFloat(`${m[1]}.${m[2]}`) : null;
}

export function pushSupported(): boolean {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

/** What the notifications page should offer on this device. */
export type PushState =
  | "ready" // can subscribe now
  | "ios-install" // iPhone in Safari: must add to Home Screen first
  | "ios-old" // iOS < 16.4: no web push at all
  | "unsupported"
  | "denied";

export function pushState(): PushState {
  if (platform() === "ios") {
    const v = iosVersion();
    if (v !== null && v < 16.4) return "ios-old";
    if (!isStandalone()) return "ios-install";
  }
  if (!pushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  return "ready";
}

function urlB64ToUint8Array(base64: string): Uint8Array {
  const pad = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

export async function registerSW(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch {
    return null;
  }
}

/** Ask permission, subscribe with the browser's push service, register with us. */
export async function subscribe(vapidKey: string, prefs?: Partial<Prefs>): Promise<Subscription> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("Permesso per le notifiche non concesso");
  const reg = (await navigator.serviceWorker.getRegistration()) ?? (await registerSW());
  if (!reg) throw new Error("Service worker non disponibile");
  await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlB64ToUint8Array(vapidKey) as BufferSource,
    });
  }
  const res = await api.post<Subscription>("/api/subscription/push", {
    subscription: sub.toJSON(),
    prefs,
    platform: platform(),
  });
  setToken(res.token);
  return res;
}

export async function unsubscribe(token: string): Promise<void> {
  try {
    const reg = await navigator.serviceWorker.getRegistration();
    const sub = await reg?.pushManager.getSubscription();
    await sub?.unsubscribe();
  } finally {
    await api.del(`/api/subscription/${token}`).catch(() => undefined);
    setToken(null);
  }
}
