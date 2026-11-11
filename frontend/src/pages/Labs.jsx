import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Card, Empty, SourceLink, Spinner } from "../components/ui.jsx";

const point = (p) => p && (
  <span>{p.raw_value} {p.raw_unit} <span className="text-slate-500">({p.effective_date ?? "date unknown"}{p.date_ambiguous ? ", date ambiguous" : ""})</span> · <SourceLink documentId={p.document_id} page={p.page} /></span>
);

export default function Labs() {
  const [trends, setTrends] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api("/patient/labs/trends").then(setTrends).catch((e) => setError(e.message));
    api("/patient/labs?limit=200").then((r) => setResults(r.items)).catch((e) => setError(e.message));
  }, []);
  if (error) return <Alert>{error}</Alert>;
  if (!trends || !results) return <Spinner label="Loading lab results" />;

  return (
    <div className="space-y-4">
      <Card title="Trends (calculated from your reports)">
        <p className="mb-3 text-xs text-slate-500">{trends.note}</p>
        {trends.items.length === 0 ? <Empty>No lab results found in your records yet.</Empty> : (
          <ul className="grid gap-3 md:grid-cols-2">
            {trends.items.map((t) => (
              <li key={t.test_code} className="rounded-md border border-slate-200 p-3 text-sm">
                <div className="flex items-center justify-between"><strong>{t.test_name}</strong><Badge value={t.status} /></div>
                {t.change !== null && <p>Change: {t.change > 0 ? "+" : ""}{t.change} {t.canonical_unit}{t.percent_change !== null ? ` (${t.percent_change > 0 ? "+" : ""}${t.percent_change}%)` : ""} · {t.direction}</p>}
                {t.latest && <p>Latest: {point(t.latest)}</p>}
                {t.previous && <p>Previous: {point(t.previous)}</p>}
                <p className="text-xs text-slate-500">{t.reason.replaceAll("_", " ")}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card title="All results">
        {results.length === 0 ? <Empty>No results.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b text-slate-500"><th className="py-2 pr-3">Test</th><th className="pr-3">Value</th><th className="pr-3">Reference</th><th className="pr-3">Date</th><th className="pr-3">Check</th><th>Source</th></tr></thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100">
                    <td className="py-2 pr-3">{r.raw_name}</td>
                    <td className="pr-3">{r.raw_value} {r.raw_unit}</td>
                    <td className="pr-3">{r.raw_reference || "—"}</td>
                    <td className="pr-3">{r.collected_on ?? r.reported_on ?? "—"}</td>
                    <td className="pr-3"><Badge value={r.validation_status === "ok" ? "ready" : r.validation_status} /></td>
                    <td><SourceLink documentId={r.document_id} page={r.page} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
