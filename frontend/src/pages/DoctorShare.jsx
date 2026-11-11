import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { Alert, Button, Card, Field, Spinner, formatDate } from "../components/ui.jsx";
import SnapshotView from "../components/SnapshotView.jsx";

// Doctor view. The share token arrives in the URL fragment (never sent to servers), is moved
// into memory and stripped from the address bar immediately, and is never stored.
export function takeTokenFromUrl() {
  const match = window.location.hash.match(/(?:^#|&)t=([A-Za-z0-9_-]+)/);
  if (match) window.history.replaceState(null, "", window.location.pathname);
  return match ? match[1] : null;
}

export default function DoctorShare() {
  const token = useRef(null);
  const [phase, setPhase] = useState("loading");
  const [pin, setPin] = useState("");
  const [name, setName] = useState("");
  const [regNo, setRegNo] = useState("");
  const [view, setView] = useState(null);
  const [error, setError] = useState("");

  async function loadView() {
    setView(await api("/share/view"));
    setPhase("view");
  }

  useEffect(() => {
    token.current = takeTokenFromUrl();
    if (token.current) setPhase("pin");
    else loadView().catch(() => setPhase("missing"));  // resume an existing session
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/share/sessions", { method: "POST", json: { token: token.current, pin, declared_name: name || null, declared_reg_no: regNo || null } });
      setPin("");
      await loadView();
    } catch (e) {
      setPin("");
      setError(e.code === "invalid_pin" ? "Incorrect PIN. The share locks after five wrong attempts." : e.message);
      if (e.code === "share_unavailable") setPhase("missing");
    }
  }

  async function end() {
    await api("/share/session/end", { method: "POST" }).catch(() => null);
    setView(null);
    setPhase("ended");
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-6">
      <h1 className="mb-4 text-xl font-bold text-emerald-800">Rakshak Kavach AI · shared summary</h1>
      {phase === "loading" && <Spinner />}
      {phase === "missing" && <Alert>{error || "This share link is invalid, expired or revoked. Ask the patient for a new QR code."}</Alert>}
      {phase === "ended" && <Alert kind="info">Session ended.</Alert>}
      {phase === "pin" && (
        <Card title="Enter the PIN the patient gave you">
          <form onSubmit={submit} className="space-y-3">
            <Field id="pin" label="6-digit PIN" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6} required value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} />
            <Field id="name" label="Your name (optional, shown to the patient, unverified)" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
            <Field id="regno" label="Registration number (optional, unverified)" maxLength={60} value={regNo} onChange={(e) => setRegNo(e.target.value)} />
            {error && <Alert>{error}</Alert>}
            <Button type="submit">Open read-only summary</Button>
          </form>
        </Card>
      )}
      {phase === "view" && view && (
        <Card title={`Patient-approved summary (version ${view.snapshot_version})`} actions={<Button variant="secondary" onClick={end}>End session</Button>}>
          <p className="mb-3 text-xs text-slate-500">Read-only · scope: {view.scope.replace("_", " ")} · approved {formatDate(view.approved_at)} · session ends {formatDate(view.session_expires_at)}</p>
          <SnapshotView content={view.summary} linkable={false} />
        </Card>
      )}
    </main>
  );
}
