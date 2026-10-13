import { useEffect, useState } from "react";
import { watchForUpdates } from "../lib/updates";
import { Icon } from "./Icon";

/** "New version available" bar, shown when an update lands while the app is in use. */
export default function UpdateBar() {
  const [apply, setApply] = useState<(() => void) | null>(null);

  useEffect(() => {
    if (!import.meta.env.PROD) return;
    return watchForUpdates((fn) => setApply(() => fn));
  }, []);

  if (!apply) return null;
  return (
    <div className="fixed inset-x-0 bottom-24 z-40 flex justify-center px-4 md:bottom-6" role="status">
      <div className="card flex w-full max-w-md items-center gap-3 px-4 py-3 shadow-lg">
        <Icon name="sparkle" className="h-5 w-5 shrink-0 text-brand-600" />
        <p className="min-w-0 flex-1 text-sm font-medium">Nuova versione disponibile</p>
        <button className="btn-primary shrink-0 !py-1.5" onClick={apply}>Aggiorna</button>
      </div>
    </div>
  );
}
