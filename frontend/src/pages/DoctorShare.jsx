import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { IconShield } from "../components/icons.jsx";
import SnapshotView from "../components/SnapshotView.jsx";
import { Alert, Button, Card, Field, Spinner, formatDate } from "../components/ui.jsx";

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
    else loadView().catch(() => setPhase("missing")); // resume an existing session
  }, []);

  async function submit(event) {
    event.preventDefault();
    setError("");
    try {
      await api("/share/sessions", {
        method: "POST",
        json: {
          token: token.current,
          pin,
          declared_name: name || null,
          declared_reg_no: regNo || null,
        },
      });
      setPin("");
      await loadView();
    } catch (e) {
      setPin("");
      setError(
        e.code === "invalid_pin"
          ? "Incorrect PIN. The share locks after five wrong attempts."
          : e.message
      );
      if (e.code === "share_unavailable") setPhase("missing");
    }
  }

  async function end() {
    await api("/share/session/end", { method: "POST" }).catch(() => null);
    setView(null);
    setPhase("ended");
  }

  return (
    <div className="min-h-screen bg-slate-50/80 py-8">
      <main className="mx-auto max-w-3xl px-4 sm:px-6">
        {/* Doctor Portal Header */}
        <div className="mb-6 flex items-center justify-between border-b border-slate-200/80 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-teal-600 text-white shadow-sm ring-2 ring-teal-500/20">
              <IconShield className="h-6 w-6" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-slate-900">
                Rakshak Kavach AI · shared summary
              </h1>
              <p className="text-xs text-slate-500">
                Verified physician read-only patient health portal
              </p>
            </div>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            Secure Consult Mode
          </span>
        </div>

        {phase === "loading" && <Spinner label="Verifying authorization" />}
        {phase === "missing" && (
          <Alert>
            {error ||
              "This share link is invalid, expired or revoked. Ask the patient for a new QR code."}
          </Alert>
        )}
        {phase === "ended" && (
          <Alert kind="info">Session ended. Patient data removed from session memory.</Alert>
        )}

        {/* PIN Entry Form */}
        {phase === "pin" && (
          <Card
            title="Enter the PIN the patient gave you"
            subtitle="The patient must verbally state their 6-digit one-time authorization PIN"
          >
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label htmlFor="pin" className="block text-sm font-medium text-slate-700">
                  <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-600">
                    6-digit PIN
                  </span>
                  <input
                    id="pin"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    pattern="\d{6}"
                    maxLength={6}
                    required
                    placeholder="000000"
                    value={pin}
                    onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                    className="mt-1 block w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center font-mono text-2xl font-bold tracking-[0.3em] text-slate-900 shadow-xs placeholder:text-slate-300 focus:border-teal-500 focus:outline-none focus:ring-4 focus:ring-teal-500/10"
                  />
                </label>
              </div>

              <Field
                id="name"
                label="Your name (optional, shown to the patient, unverified)"
                maxLength={120}
                placeholder="Dr. Full Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />

              <Field
                id="regno"
                label="Registration number (optional, unverified)"
                maxLength={60}
                placeholder="Medical council registration number"
                value={regNo}
                onChange={(e) => setRegNo(e.target.value)}
              />

              {error && <Alert>{error}</Alert>}

              <Button type="submit" className="w-full py-2.5 font-semibold">
                Open read-only summary
              </Button>
            </form>
          </Card>
        )}

        {/* Doctor Read-Only View */}
        {phase === "view" && view && (
          <Card
            title={`Patient-approved summary (version ${view.snapshot_version})`}
            subtitle={`Read-only · scope: ${view.scope.replace("_", " ")} · approved ${formatDate(
              view.approved_at
            )} · session ends ${formatDate(view.session_expires_at)}`}
            actions={
              <Button variant="secondary" onClick={end} className="px-3.5 py-1.5 text-xs">
                End session
              </Button>
            }
          >
            <SnapshotView content={view.summary} linkable={false} />
          </Card>
        )}
      </main>
    </div>
  );
}
