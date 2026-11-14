import { useEffect, useState } from "react";
import { api, shortId } from "../api.js";
import { IconCalendar, IconMedications } from "../components/icons.jsx";
import { Alert, Card, Empty, SourceLink, Spinner } from "../components/ui.jsx";

function deduplicateVisitMedications(meds) {
  const seen = new Set();
  const deduped = [];
  for (const m of meds) {
    const key = [
      (m.name || "").trim().toLowerCase(),
      (m.dose || "").trim().toLowerCase(),
      (m.frequency || "").trim().toLowerCase(),
      (m.duration || "").trim().toLowerCase(),
    ].join("|");
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(m);
    }
  }
  return deduped;
}

function groupVisits(data) {
  if (data?.visits && Array.isArray(data.visits) && data.visits.length > 0) {
    return data.visits.map((v) => ({
      documentId: v.document_id,
      date: v.date,
      page: v.page ?? 1,
      medications: deduplicateVisitMedications(v.medications || []),
    }));
  }

  const items = data?.items || (Array.isArray(data) ? data : []);
  if (!items || items.length === 0) return [];

  const map = new Map();
  for (const item of items) {
    const key = `${item.document_id}_${item.start_date ?? "unknown"}`;
    if (!map.has(key)) {
      map.set(key, {
        documentId: item.document_id,
        date: item.start_date,
        page: item.page ?? 1,
        medications: [],
      });
    }
    map.get(key).medications.push(item);
  }

  return Array.from(map.values()).map((v) => ({
    ...v,
    medications: deduplicateVisitMedications(v.medications),
  }));
}

function formatVisitDate(dateStr) {
  if (!dateStr) return "Date not stated";
  try {
    const [y, m, d] = dateStr.split("-");
    if (y && m && d) {
      const dt = new Date(Date.UTC(Number(y), Number(m) - 1, Number(d)));
      return dt.toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
        timeZone: "UTC",
      });
    }
    return dateStr;
  } catch {
    return dateStr;
  }
}

export default function Medications() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/patient/medications")
      .then((r) => setData(r))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <Alert>{error}</Alert>;
  if (!data) return <Spinner label="Loading medications" />;

  const visits = groupVisits(data);

  return (
    <Card
      title="Medications in your prescriptions"
      subtitle="Prescriptions extracted from your documents, chronologically organized by clinical visit"
    >
      {visits.length === 0 ? (
        <Empty>No medications were found in your uploaded prescriptions.</Empty>
      ) : (
        <div className="space-y-6">
          {visits.map((visit, index) => (
            <section
              key={`${visit.documentId}_${visit.date ?? index}`}
              className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-2xs transition-all duration-150 hover:shadow-xs"
              aria-label={`Visit dated ${visit.date || "unknown"}`}
            >
              <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                    <IconCalendar className="h-4 w-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold tracking-tight text-slate-900">
                      Visit / Prescription — {formatVisitDate(visit.date)}
                    </h3>
                    <p className="mt-0.5 text-xs text-slate-500">
                      Document {shortId(visit.documentId)} ·{" "}
                      {visit.date
                        ? `Prescription dated ${visit.date}`
                        : "Date not stated in record"}
                    </p>
                  </div>
                </div>
                <SourceLink documentId={visit.documentId} page={visit.page} />
              </div>

              <ul className="divide-y divide-slate-100">
                {visit.medications.map((m, mIdx) => (
                  <li
                    key={m.id || `${m.name}_${m.dose}_${mIdx}`}
                    className="flex flex-col justify-between gap-1 py-3 transition-colors hover:bg-slate-50/50 sm:flex-row sm:items-center"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-500">
                        <IconMedications className="h-3.5 w-3.5" />
                      </div>
                      <div className="flex flex-wrap items-baseline gap-2">
                        <strong className="text-sm font-semibold text-slate-900">
                          {m.name}
                        </strong>
                        {m.dose && (
                          <span className="rounded-md border border-teal-200/80 bg-teal-50 px-2.5 py-0.5 text-xs font-semibold text-teal-800">
                            {m.dose}
                          </span>
                        )}
                        {m.frequency && (
                          <span className="text-xs text-slate-600">· {m.frequency}</span>
                        )}
                        {m.duration && (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">
                            {m.duration}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="mt-1 sm:mt-0">
                      <SourceLink documentId={m.document_id} page={m.page} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Card>
  );
}
