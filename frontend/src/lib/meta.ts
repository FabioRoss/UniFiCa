import { useEffect } from "react";

// Title, description and canonical URL while moving around the app. The
// server writes the same tags into the first HTML (backend seo.py); this
// keeps them right after in-app navigation, for Google's rendering too.
const SITE = "Open Unifi";

function setMeta(selector: string, attr: string, value: string, create: () => HTMLElement) {
  let el = document.head.querySelector<HTMLElement>(selector);
  if (!el) { el = create(); document.head.appendChild(el); }
  el.setAttribute(attr, value);
}

export function usePageMeta(title: string | null | undefined, description?: string | null) {
  useEffect(() => {
    if (!title) return;
    document.title = title.includes(SITE) ? title : `${title} · ${SITE}`;
    if (description) {
      setMeta('meta[name="description"]', "content", description, () => {
        const m = document.createElement("meta"); m.setAttribute("name", "description"); return m;
      });
    }
    setMeta('link[rel="canonical"]', "href", location.origin + location.pathname, () => {
      const l = document.createElement("link"); l.setAttribute("rel", "canonical"); return l;
    });
  }, [title, description]);
}
