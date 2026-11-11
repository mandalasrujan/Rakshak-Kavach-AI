import { useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Button, Card, Spinner, formatDate } from "../components/ui.jsx";
import { useConsent } from "./Dashboard.jsx";

export default function Consent() {
  const { consent, setConsent } = useConsent();
  const [error, setError] = useState("");
  if (!consent) return <Spinner label="Loading consent" />;

  async function change(method) {
    setError("");
    try {
      setConsent(await api("/patient/consent", method === "POST" ? { method, json: { notice_version: consent.notice_version } } : { method }));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <Card title="Consent" actions={<Badge value={consent.granted ? "active" : "revoked"} />}>
      <p className="mb-2 text-xs text-slate-500">Notice version {consent.notice_version}</p>
      <p className="mb-4 text-sm leading-relaxed">{consent.notice_text}</p>
      {consent.granted_at && <p className="mb-3 text-xs text-slate-500">Granted {formatDate(consent.granted_at)}{consent.revoked_at ? ` · revoked ${formatDate(consent.revoked_at)}` : ""}</p>}
      {error && <Alert>{error}</Alert>}
      {consent.granted
        ? <Button variant="danger" onClick={() => change("DELETE")}>Revoke consent (also revokes active shares)</Button>
        : <Button onClick={() => change("POST")}>I agree</Button>}
    </Card>
  );
}
