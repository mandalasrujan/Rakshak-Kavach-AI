import { Badge, SourceLink } from "./ui.jsx";

// Renders snapshot content for the patient (with source links) or a doctor (sources shown as
// document/page text only when the share scope includes them).
function Source({ source, linkable }) {
  if (!source) return null;
  return linkable
    ? <SourceLink documentId={source.document_id} page={source.page} excerpt={source.excerpt} />
    : <span className="text-xs text-slate-500" title={source.excerpt}>Source: page {source.page} · “{source.excerpt}”</span>;
}

export default function SnapshotView({ content, linkable = true }) {
  const { medications = [], labs = [], documents, missing = {}, narrative, note } = content;
  return (
    <div className="space-y-4 text-sm">
      {narrative?.status === "ok" && (
        <section aria-label="AI summary" className="rounded-md bg-sky-50 p-3">
          <p className="mb-1 text-xs font-semibold uppercase text-sky-800">AI-generated summary — verify against the sources</p>
          <p>{narrative.text}</p>
        </section>
      )}
      {narrative && narrative.status !== "ok" && <p className="text-xs text-slate-500">No AI summary ({narrative.status}). The sections below come directly from the records.</p>}
      <section>
        <h3 className="mb-1 font-semibold">Medications</h3>
        {medications.length === 0 ? <p className="text-slate-500">{missing.medications}</p> : (
          <ul className="space-y-1">{medications.map((m, i) => (
            <li key={i}>{m.name} · {m.dose ?? "dose not stated"} · {m.frequency ?? "frequency not stated"} · {m.duration ?? "—"} <Source source={m.source} linkable={linkable} /></li>
          ))}</ul>
        )}
      </section>
      <section>
        <h3 className="mb-1 font-semibold">Lab results</h3>
        {labs.length === 0 ? <p className="text-slate-500">{missing.labs}</p> : (
          <ul className="space-y-2">{labs.map((l) => (
            <li key={l.test_code}>
              <strong>{l.test_name}</strong> <Badge value={l.status} />
              {l.latest && <div>Latest {l.latest.raw_value} {l.latest.raw_unit} ({l.latest.date ?? "date unknown"}) <Source source={l.latest.source} linkable={linkable} /></div>}
              {l.previous && <div>Previous {l.previous.raw_value} {l.previous.raw_unit} ({l.previous.date ?? "date unknown"}) <Source source={l.previous.source} linkable={linkable} /></div>}
              {l.change !== null && <div className="text-xs text-slate-500">Change {l.change > 0 ? "+" : ""}{l.change} {l.canonical_unit} · {l.reason.replaceAll("_", " ")}</div>}
            </li>
          ))}</ul>
        )}
      </section>
      {documents && (
        <section>
          <h3 className="mb-1 font-semibold">Documents</h3>
          {documents.length === 0 ? <p className="text-slate-500">{missing.documents}</p> : (
            <ul>{documents.map((d) => <li key={d.document_id}>Document {String(d.document_id).slice(0, 8)} · uploaded {new Date(d.uploaded_at).toLocaleDateString()} · {d.pages ?? "?"} page(s)</li>)}</ul>
          )}
        </section>
      )}
      <p className="text-xs text-slate-500">{note}</p>
    </div>
  );
}
