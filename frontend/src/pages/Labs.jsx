import { useEffect, useState } from "react";
import { api } from "../api.js";
import { IconCalendar, IconLabs } from "../components/icons.jsx";
import { Alert, Badge, Card, Empty, SourceLink, Spinner } from "../components/ui.jsx";

const point = (p) =>
  p && (
    <span className="inline-flex flex-wrap items-center gap-1.5 font-medium text-slate-800">
      <span>
        {p.raw_value} {p.raw_unit}
      </span>
      <span className="text-xs font-normal text-slate-500">
        ({p.effective_date ?? "date unknown"}
        {p.date_ambiguous ? ", date ambiguous" : ""})
      </span>
      <span className="text-slate-300">·</span>
      <SourceLink documentId={p.document_id} page={p.page} />
    </span>
  );

export default function Labs() {
  const [trends, setTrends] = useState(null);
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/patient/labs/trends")
      .then(setTrends)
      .catch((e) => setError(e.message));
    api("/patient/labs?limit=200")
      .then((r) => setResults(r.items))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <Alert>{error}</Alert>;
  if (!trends || !results) return <Spinner label="Loading lab results" />;

  return (
    <div className="space-y-6">
      {/* Trends Section */}
      <Card
        title="Trends (calculated from your reports)"
        subtitle={trends.note || "Deterministic comparison of your latest vs previous lab values"}
      >
        {trends.items.length === 0 ? (
          <Empty>No lab results found in your records yet.</Empty>
        ) : (
          <ul className="grid gap-4 md:grid-cols-2">
            {trends.items.map((t) => {
              const isImproved = t.status === "improved";
              const isWorsened = t.status === "worsened";
              return (
                <li
                  key={t.test_code}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs transition-all duration-150 hover:border-slate-300 hover:shadow-sm"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-3">
                      <div className="flex items-center gap-2">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                          <IconLabs className="h-4 w-4" />
                        </div>
                        <strong className="text-sm font-semibold text-slate-900">
                          {t.test_name}
                        </strong>
                      </div>
                      <Badge value={t.status} />
                    </div>

                    <div className="mt-3 space-y-2 text-xs text-slate-600">
                      {t.change !== null && (
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-700">Change:</span>
                          <span
                            className={`rounded-md px-2 py-0.5 font-medium ${
                              isImproved
                                ? "bg-emerald-50 text-emerald-800"
                                : isWorsened
                                ? "bg-amber-50 text-amber-900"
                                : "bg-slate-100 text-slate-700"
                            }`}
                          >
                            {t.change > 0 ? "+" : ""}
                            {t.change} {t.canonical_unit}
                            {t.percent_change !== null
                              ? ` (${t.percent_change > 0 ? "+" : ""}${t.percent_change}%)`
                              : ""}{" "}
                            · {t.direction}
                          </span>
                        </div>
                      )}

                      {t.latest && (
                        <div className="flex flex-wrap items-baseline gap-1.5 pt-1">
                          <span className="w-16 font-semibold text-slate-500">Latest:</span>
                          {point(t.latest)}
                        </div>
                      )}

                      {t.previous && (
                        <div className="flex flex-wrap items-baseline gap-1.5">
                          <span className="w-16 font-semibold text-slate-500">Previous:</span>
                          {point(t.previous)}
                        </div>
                      )}
                    </div>
                  </div>

                  <p className="mt-4 border-t border-slate-100 pt-2.5 text-[11px] text-slate-500">
                    {t.reason.replaceAll("_", " ")}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* All Results Table */}
      <Card
        title="All results"
        subtitle="Individual lab investigations extracted deterministically from your records"
      >
        {results.length === 0 ? (
          <Empty>No results.</Empty>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-100">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <th className="py-3 px-4">Test</th>
                  <th className="py-3 px-4">Value</th>
                  <th className="py-3 px-4">Reference</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Check</th>
                  <th className="py-3 px-4">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {results.map((r) => (
                  <tr
                    key={r.id}
                    className="transition-colors hover:bg-slate-50/70"
                  >
                    <td className="py-3 px-4 font-medium text-slate-900">{r.raw_name}</td>
                    <td className="py-3 px-4 font-medium text-slate-800">
                      {r.raw_value} {r.raw_unit}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-500">
                      {r.raw_reference || "—"}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-600">
                      {r.collected_on ?? r.reported_on ?? "—"}
                    </td>
                    <td className="py-3 px-4">
                      <Badge
                        value={r.validation_status === "ok" ? "ready" : r.validation_status}
                      />
                    </td>
                    <td className="py-3 px-4">
                      <SourceLink documentId={r.document_id} page={r.page} />
                    </td>
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
