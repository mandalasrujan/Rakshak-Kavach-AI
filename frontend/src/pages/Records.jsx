import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

const REASONS = {
  encrypted_pdf: "The PDF is password-protected.", unreadable_pdf: "The PDF could not be read.",
  too_many_pages: "The PDF has too many pages.", no_text_layer: "No text found (scanned PDFs are not supported).",
  consent_revoked: "Consent was revoked before processing.", enqueue_failed: "Queue unavailable; upload again to retry.",
  embedding_unavailable: "The AI service is not configured.", processing_error: "Processing failed; upload again to retry.",
};

export default function Records() {
  const [documents, setDocuments] = useState(null);
  const [message, setMessage] = useState(null);
  const refresh = useCallback(async () => setDocuments((await api("/patient/documents?limit=100")).items), []);
  useEffect(() => { refresh().catch((e) => setMessage({ kind: "error", text: e.message })); }, [refresh]);
  useEffect(() => {  // poll while anything is still being processed
    if (!documents?.some((d) => d.status === "queued" || d.status === "processing")) return undefined;
    const timer = setInterval(() => refresh().catch(() => null), 3000);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  async function onUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      await api("/patient/documents", { method: "POST", form });
      setMessage({ kind: "success", text: "Uploaded. Processing has started." });
      await refresh();
    } catch (e) {
      setMessage({ kind: "error", text: e.message });
    }
  }

  async function remove(id) {
    if (!window.confirm("Delete this document and everything derived from it (results, chats that cited it, summaries)?")) return;
    try {
      await api(`/patient/documents/${id}`, { method: "DELETE" });
      setMessage({ kind: "success", text: "Document deleted." });
      await refresh();
    } catch (e) {
      setMessage({ kind: "error", text: e.message });
    }
  }

  return (
    <Card title="Medical records">
      <ConsentRequired>
        <label className="mb-4 block text-sm font-medium">
          Upload a digital PDF (lab report, prescription, imaging report, doctor note)
          <input type="file" accept="application/pdf" onChange={onUpload} className="mt-1 block text-sm" />
        </label>
      </ConsentRequired>
      {message && <div className="mb-3"><Alert kind={message.kind}>{message.text}</Alert></div>}
      {documents === null ? <Spinner label="Loading documents" /> : documents.length === 0 ? <Empty>No documents yet.</Empty> : (
        <ul className="divide-y divide-slate-100">
          {documents.map((d) => (
            <li key={d.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="text-sm">
                <Badge value={d.status} /> <span className="ml-2">Uploaded {formatDate(d.uploaded_at)}</span>
                {d.pages ? <span className="ml-2 text-slate-500">{d.pages} page(s)</span> : null}
                {d.failure_reason && <p className="text-xs text-red-700">{REASONS[d.failure_reason] ?? d.failure_reason}</p>}
              </div>
              <div className="flex gap-2">
                {d.status === "ready" && <a className="rounded-md bg-slate-100 px-3 py-2 text-sm" href={`/api/v1/patient/documents/${d.id}/file`} target="_blank" rel="noreferrer noopener">Open PDF</a>}
                <Button variant="danger" onClick={() => remove(d.id)}>Delete</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
