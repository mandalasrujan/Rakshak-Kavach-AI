import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Card, Empty, SourceLink, Spinner } from "../components/ui.jsx";

export default function Medications() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api("/patient/medications").then((r) => setItems(r.items)).catch((e) => setError(e.message)); }, []);
  if (error) return <Alert>{error}</Alert>;
  if (!items) return <Spinner label="Loading medications" />;
  return (
    <Card title="Medications in your prescriptions">
      {items.length === 0 ? <Empty>No medications were found in your uploaded prescriptions.</Empty> : (
        <ul className="divide-y divide-slate-100">
          {items.map((m) => (
            <li key={m.id} className="py-2 text-sm">
              <strong>{m.name}</strong> · {m.dose ?? "dose not stated"} · {m.frequency ?? "frequency not stated"} · {m.duration ?? "duration not stated"}
              <div className="text-xs text-slate-500">Prescription dated {m.start_date ?? "unknown"} · <SourceLink documentId={m.document_id} page={m.page} /></div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
