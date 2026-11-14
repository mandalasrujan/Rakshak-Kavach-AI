import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api.js";
import { IconCheck, IconSharing, IconTrash } from "../components/icons.jsx";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

// The token and PIN exist only in this component's memory, are shown once, and are cleared
// when dismissed. They are never written to storage or logged.
export function CreatedShare({ created, onDone }) {
  const [qr, setQr] = useState("");
  useEffect(() => {
    QRCode.toDataURL(created.share_url, { margin: 1, width: 240 }).then(setQr);
  }, [created.share_url]);

  return (
    <div className="rounded-2xl border-2 border-teal-500 bg-gradient-to-b from-teal-50/40 to-white p-6 shadow-md">
      <div className="mb-4">
        <h3 className="text-base font-bold text-slate-900">Share QR code created</h3>
        <p className="text-xs text-slate-600">
          Show this QR code to your doctor, and tell them the PIN separately.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-6">
        <div className="rounded-2xl border border-slate-200/80 bg-white p-3 shadow-xs">
          {qr ? (
            <img src={qr} alt="Share QR code" className="h-48 w-48 rounded-xl object-contain" />
          ) : (
            <Spinner label="Drawing QR code" />
          )}
        </div>

        <div className="space-y-3">
          <div>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              6-Digit Security PIN
            </span>
            <div className="mt-1">
              <span
                className="inline-block rounded-2xl border border-teal-200/90 bg-teal-50/90 px-5 py-2.5 font-mono text-3xl font-bold tracking-[0.2em] text-teal-900 shadow-inner sm:text-4xl"
                aria-label="Share PIN"
              >
                {created.pin}
              </span>
            </div>
          </div>

          <div className="space-y-1 text-xs text-slate-500">
            <p className="font-medium text-slate-700">
              Expires {formatDate(created.expires_at)} · scope {created.scope.replace("_", " ")}
            </p>
            <p>
              You won't be able to see this PIN or QR code again. Five wrong PINs lock the share.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 border-t border-teal-100 pt-4">
        <Button variant="secondary" onClick={onDone} className="px-5">
          Done
        </Button>
      </div>
    </div>
  );
}

export default function Sharing() {
  const [snapshots, setSnapshots] = useState(null);
  const [shares, setShares] = useState(null);
  const [form, setForm] = useState({
    snapshot_id: "",
    scope: "summary_only",
    expires_in_minutes: 60,
  });
  const [created, setCreated] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [snaps, list] = await Promise.all([api("/patient/snapshots"), api("/patient/shares")]);
    const approved = snaps.items.filter((s) => s.approved_at && !s.invalidated_at);
    setSnapshots(approved);
    setShares(list.items);
    setForm((f) => ({ ...f, snapshot_id: f.snapshot_id || approved[0]?.id || "" }));
  }, []);

  useEffect(() => {
    load().catch((e) => setError(e.message));
  }, [load]);

  async function create(event) {
    event.preventDefault();
    setError("");
    try {
      setCreated(
        await api("/patient/shares", {
          method: "POST",
          json: { ...form, expires_in_minutes: Number(form.expires_in_minutes) },
        })
      );
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function revoke(id) {
    await api(`/patient/shares/${id}`, { method: "DELETE" });
    await load();
  }

  if (!snapshots || !shares)
    return error ? <Alert>{error}</Alert> : <Spinner label="Loading shares" />;

  return (
    <div className="space-y-6">
      {/* Create Share Card */}
      <Card
        title="Share with a doctor"
        subtitle="Generate time-limited, PIN-protected QR access to your approved medical summary"
      >
        {created ? (
          <CreatedShare created={created} onDone={() => setCreated(null)} />
        ) : (
          <ConsentRequired>
            {snapshots.length === 0 ? (
              <Empty>
                Approve a summary on the Summary tab first. Doctors only ever see an approved
                summary.
              </Empty>
            ) : (
              <form onSubmit={create} className="grid gap-4 sm:grid-cols-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Summary version
                  </label>
                  <select
                    className="mt-1.5 block w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-2xs focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/10"
                    value={form.snapshot_id}
                    onChange={(e) => setForm({ ...form, snapshot_id: e.target.value })}
                  >
                    {snapshots.map((s) => (
                      <option key={s.id} value={s.id}>
                        Version {s.version} (approved {new Date(s.approved_at).toLocaleDateString()})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                    Expires after
                  </label>
                  <select
                    className="mt-1.5 block w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-2xs focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/10"
                    value={form.expires_in_minutes}
                    onChange={(e) => setForm({ ...form, expires_in_minutes: e.target.value })}
                  >
                    {[
                      [30, "30 minutes"],
                      [60, "1 hour"],
                      [240, "4 hours"],
                      [1440, "24 hours"],
                    ].map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>

                <fieldset className="sm:col-span-3">
                  <legend className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                    What the doctor sees
                  </legend>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {[
                      ["summary_only", "Summary only", "Doctor sees AI summary, medications, and lab trends."],
                      [
                        "full_records",
                        "Summary + document list and sources",
                        "Doctor also sees individual document names and specific record citations.",
                      ],
                    ].map(([value, label, desc]) => (
                      <label
                        key={value}
                        className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-xs transition-all ${
                          form.scope === value
                            ? "border-teal-500 bg-teal-50/50 ring-1 ring-teal-500/30"
                            : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="radio"
                          name="scope"
                          value={value}
                          checked={form.scope === value}
                          onChange={() => setForm({ ...form, scope: value })}
                          className="mt-0.5 text-teal-600 focus:ring-teal-500"
                        />
                        <div>
                          <span className="font-semibold text-slate-900">{label}</span>
                          <p className="mt-0.5 text-slate-500">{desc}</p>
                        </div>
                      </label>
                    ))}
                  </div>
                </fieldset>

                <div className="sm:col-span-3 pt-2">
                  <Button type="submit" className="px-6 py-2.5">
                    <IconSharing className="h-4 w-4" />
                    <span>Create share</span>
                  </Button>
                </div>
              </form>
            )}
          </ConsentRequired>
        )}
        {error && (
          <div className="mt-4">
            <Alert>{error}</Alert>
          </div>
        )}
      </Card>

      {/* Access Log Card */}
      <Card
        title="Shares and access log"
        subtitle="Complete immutable log of all active and past doctor sharing authorizations"
      >
        {shares.length === 0 ? (
          <Empty>You haven't shared anything.</Empty>
        ) : (
          <ul className="space-y-3">
            {shares.map((s) => (
              <li
                key={s.id}
                className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-2xs transition-all hover:shadow-xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge value={s.status} />
                    <span className="text-xs font-semibold text-slate-800">
                      Scope: {s.scope.replace("_", " ")}
                    </span>
                    <span className="text-xs text-slate-500">
                      · Created {formatDate(s.created_at)} · Expires {formatDate(s.expires_at)}
                    </span>
                  </div>
                  {s.status === "active" && (
                    <Button variant="danger" onClick={() => revoke(s.id)} className="px-3 py-1 text-xs">
                      Revoke
                    </Button>
                  )}
                </div>

                {s.failed_pin_attempts > 0 && (
                  <p className="mt-2 text-xs font-medium text-amber-800">
                    ⚠️ {s.failed_pin_attempts} wrong PIN attempt(s)
                  </p>
                )}

                <div className="mt-3 text-xs">
                  {s.sessions.length === 0 ? (
                    <p className="text-slate-400 italic">Not opened yet.</p>
                  ) : (
                    <ul className="space-y-1 rounded-xl bg-slate-50 p-2.5">
                      {s.sessions.map((v) => (
                        <li key={v.id} className="text-slate-600">
                          Opened {formatDate(v.created_at)} by{" "}
                          <strong className="text-slate-800">
                            {v.declared_name ?? "an unnamed viewer"}
                          </strong>
                          {v.declared_reg_no ? ` (reg. ${v.declared_reg_no})` : ""} — self-declared,
                          unverified · {v.views} view(s)
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
