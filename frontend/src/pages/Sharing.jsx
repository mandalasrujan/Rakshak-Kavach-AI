import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api.js";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

// The token and PIN exist only in this component's memory, are shown once, and are cleared
// when dismissed. They are never written to storage or logged.
export function CreatedShare({ created, onDone }) {
  const [qr, setQr] = useState("");
  useEffect(() => { QRCode.toDataURL(created.share_url, { margin: 1, width: 240 }).then(setQr); }, [created.share_url]);
  return (
    <div className="rounded-md border-2 border-emerald-600 p-4">
      <p className="mb-2 font-semibold">Show this QR code to your doctor, and tell them the PIN separately.</p>
      <div className="flex flex-wrap items-center gap-6">
        {qr ? <img src={qr} alt="Share QR code" className="h-48 w-48" /> : <Spinner label="Drawing QR code" />}
        <div>
          <p className="text-sm text-slate-600">PIN</p>
          <p className="font-mono text-4xl tracking-widest" aria-label="Share PIN">{created.pin}</p>
          <p className="mt-2 text-xs text-slate-500">Expires {formatDate(created.expires_at)} · scope {created.scope.replace("_", " ")}</p>
          <p className="text-xs text-slate-500">You won't be able to see this PIN or QR code again. Five wrong PINs lock the share.</p>
        </div>
      </div>
      <Button className="mt-3" variant="secondary" onClick={onDone}>Done</Button>
    </div>
  );
}

export default function Sharing() {
  const [snapshots, setSnapshots] = useState(null);
  const [shares, setShares] = useState(null);
  const [form, setForm] = useState({ snapshot_id: "", scope: "summary_only", expires_in_minutes: 60 });
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [snaps, list] = await Promise.all([api("/patient/snapshots"), api("/patient/shares")]);
    const approved = snaps.items.filter((s) => s.approved_at && !s.invalidated_at);
    setSnapshots(approved);
    setShares(list.items);
    setForm((f) => ({ ...f, snapshot_id: f.snapshot_id || approved[0]?.id || "" }));
  }, []);
  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      setCreated(await api("/patient/shares", { method: "POST", json: { ...form, expires_in_minutes: Number(form.expires_in_minutes) } }));
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function revoke(id) {
    await api(`/patient/shares/${id}`, { method: "DELETE" });
    await load();
  }

  if (!snapshots || !shares) return error ? <Alert>{error}</Alert> : <Spinner label="Loading shares" />;
  return (
    <div className="space-y-4">
      <Card title="Share with a doctor">
        {created ? <CreatedShare created={created} onDone={() => setCreated(null)} /> : (
          <ConsentRequired>
            {snapshots.length === 0 ? <Empty>Approve a summary on the Summary tab first. Doctors only ever see an approved summary.</Empty> : (
              <form onSubmit={create} className="grid gap-3 sm:grid-cols-3">
                <label className="text-sm font-medium">Summary
                  <select className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-2" value={form.snapshot_id} onChange={(e) => setForm({ ...form, snapshot_id: e.target.value })}>
                    {snapshots.map((s) => <option key={s.id} value={s.id}>Version {s.version} (approved {new Date(s.approved_at).toLocaleDateString()})</option>)}
                  </select>
                </label>
                <fieldset className="text-sm">
                  <legend className="font-medium">What the doctor sees</legend>
                  {[["summary_only", "Summary only"], ["full_records", "Summary + document list and sources"]].map(([value, label]) => (
                    <label key={value} className="mt-1 flex items-center gap-2"><input type="radio" name="scope" value={value} checked={form.scope === value} onChange={() => setForm({ ...form, scope: value })} />{label}</label>
                  ))}
                </fieldset>
                <label className="text-sm font-medium">Expires after
                  <select className="mt-1 block w-full rounded-md border border-slate-300 px-2 py-2" value={form.expires_in_minutes} onChange={(e) => setForm({ ...form, expires_in_minutes: e.target.value })}>
                    {[[30, "30 minutes"], [60, "1 hour"], [240, "4 hours"], [1440, "24 hours"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
                <Button type="submit" className="sm:col-span-3 sm:w-48">Create share</Button>
              </form>
            )}
          </ConsentRequired>
        )}
        {error && <div className="mt-3"><Alert>{error}</Alert></div>}
      </Card>
      <Card title="Shares and access log">
        {shares.length === 0 ? <Empty>You haven't shared anything.</Empty> : (
          <ul className="space-y-3">{shares.map((s) => (
            <li key={s.id} className="rounded-md border border-slate-200 p-3 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span><Badge value={s.status} /> {s.scope.replace("_", " ")} · created {formatDate(s.created_at)} · expires {formatDate(s.expires_at)}</span>
                {s.status === "active" && <Button variant="danger" onClick={() => revoke(s.id)}>Revoke</Button>}
              </div>
              {s.failed_pin_attempts > 0 && <p className="text-xs text-amber-800">{s.failed_pin_attempts} wrong PIN attempt(s)</p>}
              {s.sessions.length === 0 ? <p className="text-xs text-slate-500">Not opened yet.</p> : (
                <ul className="mt-1 text-xs text-slate-600">{s.sessions.map((v) => (
                  <li key={v.id}>Opened {formatDate(v.created_at)} by {v.declared_name ?? "an unnamed viewer"}{v.declared_reg_no ? ` (reg. ${v.declared_reg_no})` : ""} — self-declared, unverified · {v.views} view(s)</li>
                ))}</ul>
              )}
            </li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}
