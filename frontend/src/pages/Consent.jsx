import { useState } from "react";
import { api } from "../api.js";
import { IconConsent, IconShield } from "../components/icons.jsx";
import { Alert, Badge, Button, Card, Spinner, formatDate } from "../components/ui.jsx";
import { useConsent } from "./Dashboard.jsx";

export default function Consent() {
  const { consent, setConsent } = useConsent();
  const [error, setError] = useState("");
  if (!consent) return <Spinner label="Loading consent" />;

  async function change(method) {
    setError("");
    try {
      setConsent(
        await api(
          "/patient/consent",
          method === "POST"
            ? { method, json: { notice_version: consent.notice_version } }
            : { method }
        )
      );
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Consent"
        subtitle="Manage your privacy authorization and data processing consent"
        actions={<Badge value={consent.granted ? "active" : "revoked"} />}
      >
        <div className="mb-4 flex items-center gap-2 rounded-xl bg-slate-50 px-3.5 py-2 text-xs font-medium text-slate-600">
          <IconConsent className="h-4 w-4 text-teal-600" />
          <span>Notice version {consent.notice_version}</span>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-2xs">
          <p className="text-sm leading-relaxed text-slate-800">{consent.notice_text}</p>
        </div>

        {consent.granted_at && (
          <p className="mt-4 text-xs text-slate-500">
            Granted {formatDate(consent.granted_at)}
            {consent.revoked_at ? ` · revoked ${formatDate(consent.revoked_at)}` : ""}
          </p>
        )}

        {error && (
          <div className="mt-4">
            <Alert>{error}</Alert>
          </div>
        )}

        <div className="mt-6 border-t border-slate-100 pt-4">
          {consent.granted ? (
            <Button variant="danger" onClick={() => change("DELETE")}>
              Revoke consent (also revokes active shares)
            </Button>
          ) : (
            <Button onClick={() => change("POST")} className="px-6 py-2.5">
              I agree
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
