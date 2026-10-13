import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

/** GET a URL, re-fetching when it changes. `reload` refetches the same URL. */
export function useFetch<T>(url: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!url);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!url) return;
    const n = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const d = await api.get<T>(url);
      if (n === seq.current) setData(d);
    } catch (e) {
      if (n === seq.current) setError((e as Error).message || "Errore di rete");
    } finally {
      if (n === seq.current) setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}
