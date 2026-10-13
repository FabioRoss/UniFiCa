// Keep installed copies of the app current.
//
// An app added to the iOS home screen is often resumed from memory instead of
// reloaded, so it can keep running an old build for days. We compare the
// build id baked into this bundle with /version.json whenever the app comes
// back to the foreground (and every 30 minutes while open):
// - just resumed: reload straight away, before the user starts tapping;
// - in use: tell the caller, which shows an "update available" bar.

const CHECK_EVERY_MS = 30 * 60 * 1000;
const RELOAD_GUARD = "openunifi.reloadedFor";

async function latestBuild(): Promise<string | null> {
  try {
    const res = await fetch("/version.json", { cache: "no-store" });
    if (!res.ok) return null;
    return ((await res.json()) as { build?: string }).build ?? null;
  } catch {
    return null; // offline: try again later
  }
}

function alreadyReloadedFor(build: string): boolean {
  try {
    return sessionStorage.getItem(RELOAD_GUARD) === build;
  } catch {
    return false;
  }
}

function reloadInto(build: string): void {
  try {
    sessionStorage.setItem(RELOAD_GUARD, build);
  } catch {
    /* private mode */
  }
  location.reload();
}

export function watchForUpdates(onAvailable: (apply: () => void) => void): () => void {
  let notified = false;

  const check = async (resumed: boolean) => {
    navigator.serviceWorker?.getRegistration().then((r) => r?.update()).catch(() => undefined);
    const build = await latestBuild();
    if (!build || build === __BUILD_ID__) return;
    // A reload that did not bring the new build (some cache in between)
    // must not loop: fall back to the bar.
    if (resumed && !alreadyReloadedFor(build)) {
      reloadInto(build);
    } else if (!notified) {
      notified = true;
      onAvailable(() => reloadInto(build));
    }
  };

  const onVisibility = () => {
    if (document.visibilityState === "visible") check(true);
  };
  document.addEventListener("visibilitychange", onVisibility);
  const timer = window.setInterval(() => check(false), CHECK_EVERY_MS);
  check(false);
  return () => {
    document.removeEventListener("visibilitychange", onVisibility);
    window.clearInterval(timer);
  };
}
