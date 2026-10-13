import { Link } from "react-router-dom";
import { Empty } from "../components/ui";

export default function NotFound() {
  return (
    <Empty title="Pagina non trovata">
      <Link to="/" className="font-semibold text-brand-700 dark:text-brand-300">Torna alle novità</Link>
    </Empty>
  );
}
