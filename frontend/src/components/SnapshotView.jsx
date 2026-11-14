import { IconAssistant, IconLabs, IconMedications, IconRecords } from "./icons.jsx";
import { Badge, SourceLink } from "./ui.jsx";

// Renders snapshot content for the patient (with source links) or a doctor (sources shown as
// document/page text only when the share scope includes them).
function Source({ source, linkable }) {
  if (!source) return null;
  return linkable ? (
    <SourceLink documentId={source.document_id} page={source.page} excerpt={source.excerpt} />
  ) : (
    <span className="text-xs font-normal text-slate-500" title={source.excerpt}>
      Source: page {source.page} · “{source.excerpt}”
    </span>
  );
}

export default function SnapshotView({ content, linkable = true }) {
  const { medications = [], labs = [], documents, missing = {}, narrative, note } = content;
  return (
    <div className="space-y-6 text-sm">
      {/* AI Narrative Section */}
      {narrative?.status === "ok" && (
        <section
          aria-label="AI summary"
          className="rounded-2xl border border-sky-200/80 bg-gradient-to-r from-sky-50/80 to-teal-50/50 p-4 shadow-2xs sm:p-5"
        >
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sky-900">
            <div className="flex h-5 w-5 items-center justify-center rounded-md bg-sky-200/80 text-sky-800">
              <IconAssistant className="h-3 w-3" />
            </div>
            <span>AI-generated summary — verify against the sources</span>
          </div>
          <p className="leading-relaxed text-slate-800 text-sm">{narrative.text}</p>
        </section>
      )}

      {narrative && narrative.status !== "ok" && (
        <p className="text-xs text-slate-500 italic">
          No AI summary ({narrative.status}). The sections below come directly from the records.
        </p>
      )}

      {/* Medications Section */}
      <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
        <div className="mb-3 flex items-center gap-2 border-b border-slate-100 pb-2.5">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
            <IconMedications className="h-3.5 w-3.5" />
          </div>
          <h3 className="font-semibold tracking-tight text-slate-900">Medications</h3>
        </div>
        {medications.length === 0 ? (
          <p className="text-xs text-slate-500">{missing.medications}</p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {medications.map((m, i) => (
              <li key={i} className="flex flex-wrap items-baseline justify-between gap-2 py-2 text-xs sm:text-sm">
                <div className="flex flex-wrap items-baseline gap-1.5">
                  <strong className="font-semibold text-slate-900">{m.name}</strong>
                  {m.dose && (
                    <span className="rounded bg-teal-50 px-2 py-0.5 text-xs font-medium text-teal-800 border border-teal-200/70">
                      {m.dose}
                    </span>
                  )}
                  {m.frequency && (
                    <span className="text-slate-600">· {m.frequency}</span>
                  )}
                  {m.duration && m.duration !== "—" && (
                    <span className="text-slate-500">· {m.duration}</span>
                  )}
                </div>
                <Source source={m.source} linkable={linkable} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Labs Section */}
      <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
        <div className="mb-3 flex items-center gap-2 border-b border-slate-100 pb-2.5">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
            <IconLabs className="h-3.5 w-3.5" />
          </div>
          <h3 className="font-semibold tracking-tight text-slate-900">Lab results</h3>
        </div>
        {labs.length === 0 ? (
          <p className="text-xs text-slate-500">{missing.labs}</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2">
            {labs.map((l) => (
              <li
                key={l.test_code}
                className="rounded-xl border border-slate-200/70 bg-slate-50/50 p-3.5 text-xs"
              >
                <div className="flex items-center justify-between border-b border-slate-200/60 pb-2">
                  <strong className="font-semibold text-slate-900">{l.test_name}</strong>
                  <Badge value={l.status} />
                </div>
                <div className="mt-2 space-y-1 text-slate-600">
                  {l.latest && (
                    <div className="flex flex-wrap items-baseline justify-between gap-1">
                      <span>
                        Latest: <strong className="text-slate-800">{l.latest.raw_value} {l.latest.raw_unit}</strong> ({l.latest.date ?? "date unknown"})
                      </span>
                      <Source source={l.latest.source} linkable={linkable} />
                    </div>
                  )}
                  {l.previous && (
                    <div className="flex flex-wrap items-baseline justify-between gap-1">
                      <span>
                        Previous: {l.previous.raw_value} {l.previous.raw_unit} ({l.previous.date ?? "date unknown"})
                      </span>
                      <Source source={l.previous.source} linkable={linkable} />
                    </div>
                  )}
                  {l.change !== null && (
                    <div className="pt-1 text-[11px] text-slate-500">
                      Change {l.change > 0 ? "+" : ""}{l.change} {l.canonical_unit} · {l.reason.replaceAll("_", " ")}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Documents Section */}
      {documents && (
        <section className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
          <div className="mb-3 flex items-center gap-2 border-b border-slate-100 pb-2.5">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
              <IconRecords className="h-3.5 w-3.5" />
            </div>
            <h3 className="font-semibold tracking-tight text-slate-900">Documents</h3>
          </div>
          {documents.length === 0 ? (
            <p className="text-xs text-slate-500">{missing.documents}</p>
          ) : (
            <ul className="space-y-1.5 text-xs text-slate-600">
              {documents.map((d) => (
                <li
                  key={d.document_id}
                  className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-1.5"
                >
                  <IconRecords className="h-3.5 w-3.5 text-slate-400" />
                  <span>
                    Document {String(d.document_id).slice(0, 8)} · uploaded{" "}
                    {new Date(d.uploaded_at).toLocaleDateString()} · {d.pages ?? "?"} page(s)
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {note && <p className="text-xs text-slate-500 italic">{note}</p>}
    </div>
  );
}
