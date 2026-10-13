import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { Icon } from "./Icon";

interface State {
  error: Error | null;
}

class Boundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Open Unifi render error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page-wash grid min-h-screen place-items-center px-4">
        <div className="card max-w-sm p-6 text-center">
          <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-red-50 text-red-600 dark:bg-red-950/50 dark:text-red-300">
            <Icon name="alert" />
          </div>
          <p className="font-bold">Qualcosa è andato storto</p>
          <p className="mt-1 text-sm muted">Ricarica la pagina per continuare. Se succede di nuovo, segnalacelo.</p>
          <button className="btn-primary mt-4 w-full" onClick={() => location.reload()}>Ricarica</button>
        </div>
      </div>
    );
  }
}

/** Instead of a blank page, a render error shows a reload card. Keyed by
 *  path, so navigating elsewhere also clears it. */
export default function ErrorBoundary({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  return <Boundary key={pathname}>{children}</Boundary>;
}
