import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { IconExternalLink, IconRecords, IconTrash, IconUpload } from "../components/icons.jsx";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

const REASONS = {
  encrypted_pdf: "The PDF is password-protected.",
  unreadable_pdf: "The PDF could not be read.",
  too_many_pages: "The PDF has too many pages.",
  no_text_layer: "No text found (scanned PDFs are not supported).",
  consent_revoked: "Consent was revoked before processing.",
  enqueue_failed: "Queue unavailable; upload again to retry.",
  embedding_unavailable: "The AI service is not configured.",
  processing_error: "Processing failed; upload again to retry.",
};

export default function Records() {
  const [documents, setDocuments] = useState(null);
  const [message, setMessage] = useState(null);
  const [uploading, setUploading] = useState(false);

  const refresh = useCallback(
    async () => setDocuments((await api("/patient/documents?limit=100")).items),
    []
  );
  useEffect(() => {
    refresh().catch((e) => setMessage({ kind: "error", text: e.message }));
  }, [refresh]);

  useEffect(() => {
    if (!documents?.some((d) => d.status === "queued" || d.status === "processing")) return undefined;
    const timer = setInterval(() => refresh().catch(() => null), 3000);
    return () => clearInterval(timer);
  }, [documents, refresh]);

  async function onUpload(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      await api("/patient/documents", { method: "POST", form });
      setMessage({ kind: "success", text: "Document uploaded successfully. Processing has started." });
      await refresh();
    } catch (e) {
      setMessage({ kind: "error", text: e.message });
    } finally {
      setUploading(false);
    }
  }

  async function remove(id) {
    if (
      !window.confirm(
        "Delete this document and everything derived from it (results, chats that cited it, summaries)?"
      )
    )
      return;
    try {
      await api(`/patient/documents/${id}`, { method: "DELETE" });
      setMessage({ kind: "success", text: "Document deleted." });
      await refresh();
    } catch (e) {
      setMessage({ kind: "error", text: e.message });
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Medical records"
        subtitle="Upload and manage your health records, lab reports, prescriptions, and consultation notes"
      >
        <ConsentRequired>
          <div className="mb-6 rounded-2xl border-2 border-dashed border-teal-200/80 bg-teal-50/30 p-6 transition-colors hover:border-teal-300 hover:bg-teal-50/50">
            <label className="flex cursor-pointer flex-col items-center justify-center text-center">
              <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-600 text-white shadow-sm shadow-teal-600/20">
                <IconUpload className="h-6 w-6" />
              </div>
              <span className="text-sm font-semibold text-slate-900">
                Upload a digital PDF (lab report, prescription, imaging report, doctor note)
              </span>
              <span className="mt-1 text-xs text-slate-500">
                Digital text PDF format · Up to 50 pages · Stored in encrypted patient-isolated vault
              </span>
              <input
                type="file"
                accept="application/pdf"
                onChange={onUpload}
                disabled={uploading}
                className="mt-3 block text-xs text-slate-500 file:mr-3 file:rounded-xl file:border-0 file:bg-teal-600 file:px-4 file:py-2 file:text-xs file:font-semibold file:text-white file:shadow-xs file:transition-all hover:file:bg-teal-700"
              />
            </label>
            {uploading && <div className="mt-3 flex justify-center"><Spinner label="Uploading document" /></div>}
          </div>
        </ConsentRequired>

        {message && (
          <div className="mb-4">
            <Alert kind={message.kind}>{message.text}</Alert>
          </div>
        )}

        {documents === null ? (
          <Spinner label="Loading documents" />
        ) : documents.length === 0 ? (
          <Empty>No documents yet.</Empty>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1 text-xs font-semibold uppercase tracking-wider text-slate-500">
              <span>Document</span>
              <span>Actions</span>
            </div>
            <ul className="divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white">
              {documents.map((d) => (
                <li
                  key={d.id}
                  className="flex flex-wrap items-center justify-between gap-3 p-4 transition-colors hover:bg-slate-50/70"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                      <IconRecords className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge value={d.status} />
                        <span className="text-xs font-medium text-slate-700">
                          Uploaded {formatDate(d.uploaded_at)}
                        </span>
                        {d.pages ? (
                          <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                            {d.pages} page(s)
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 font-mono text-xs text-slate-400">
                        ID: {d.id}
                      </p>
                      {d.failure_reason && (
                        <p className="mt-1 text-xs font-medium text-rose-700">
                          {REASONS[d.failure_reason] ?? d.failure_reason}
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {d.status === "ready" && (
                      <a
                        className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-xs font-medium text-slate-700 shadow-2xs transition-colors hover:bg-slate-100 hover:text-slate-900"
                        href={`/api/v1/patient/documents/${d.id}/file`}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        <span>Open PDF</span>
                        <IconExternalLink className="h-3 w-3 opacity-60" />
                      </a>
                    )}
                    <Button
                      variant="danger"
                      onClick={() => remove(d.id)}
                      className="px-3 py-1.5 text-xs"
                    >
                      <IconTrash className="h-3.5 w-3.5" />
                      <span>Delete</span>
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}
