import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import SnapshotView from "../components/SnapshotView.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

export const snapshotState = (s) => (s.invalidated_at ? "invalidated" : s.approved_at ? "approved" : "draft");

export default function Summary() {
  const [snapshots, setSnapshots] = useState(null);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    const items = (await api("/patient/snapshots")).items;
    setSnapshots(items);
    return items;
  }, []);
  useEffect(() => { load().then((items) => setSelected(items[0] ?? null)).catch((e) => setError(e.message)); }, [load]);

  async function generate() {
    setBusy(true);
    setError("");
    try {
      const created = await api("/patient/snapshots", { method: "POST" });
      await load();
      setSelected(created);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    try {
      const approved = await api(`/patient/snapshots/${selected.id}/approve`, { method: "POST" });
      setSelected(approved);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="grid gap-4 md:grid-cols-[16rem_1fr]">
      <Card title="Versions" actions={<ConsentRequired><Button onClick={generate} disabled={busy}>{busy ? "Generating…" : "Generate"}</Button></ConsentRequired>}>
        {snapshots === null ? <Spinner /> : snapshots.length === 0 ? <Empty>No summaries yet.</Empty> : (
          <ul className="space-y-1">{snapshots.map((s) => (
            <li key={s.id}>
              <button onClick={() => setSelected(s)} className={`w-full rounded px-2 py-1 text-left text-sm ${selected?.id === s.id ? "bg-emerald-50 font-semibold" : "hover:bg-slate-50"}`}>
                Version {s.version} <Badge value={snapshotState(s)} />
              </button>
            </li>
          ))}</ul>
        )}
      </Card>
      <Card title={selected ? `Summary version ${selected.version}` : "Summary"}
        actions={selected && snapshotState(selected) === "draft" && <ConsentRequired><Button onClick={approve}>Approve for sharing</Button></ConsentRequired>}>
        {error && <div className="mb-3"><Alert>{error}</Alert></div>}
        {!selected ? <Empty>Generate a summary to preview it. You approve it before any doctor can see it; approved summaries never change.</Empty>
          : snapshotState(selected) === "invalidated" ? <Alert kind="info">This summary was withdrawn because a source document was deleted.</Alert>
          : (
            <>
              <p className="mb-3 text-xs text-slate-500">Generated {formatDate(selected.generated_at)}{selected.approved_at ? ` · approved ${formatDate(selected.approved_at)}` : " · draft"}</p>
              <SnapshotView content={selected.content_json} />
            </>
          )}
      </Card>
    </div>
  );
}
