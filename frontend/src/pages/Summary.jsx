import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { IconCheck, IconSummary } from "../components/icons.jsx";
import SnapshotView from "../components/SnapshotView.jsx";
import { Alert, Badge, Button, Card, Empty, Spinner, formatDate } from "../components/ui.jsx";
import { ConsentRequired } from "./Dashboard.jsx";

export const snapshotState = (s) =>
  s.invalidated_at ? "invalidated" : s.approved_at ? "approved" : "draft";

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

  useEffect(() => {
    load()
      .then((items) => setSelected(items[0] ?? null))
      .catch((e) => setError(e.message));
  }, [load]);

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
      const approved = await api(`/patient/snapshots/${selected.id}/approve`, {
        method: "POST",
      });
      setSelected(approved);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[18rem_1fr]">
      {/* Left: Summary Versions */}
      <Card
        title="Versions"
        subtitle="Snapshot audit trail"
        actions={
          <ConsentRequired>
            <Button onClick={generate} disabled={busy} className="px-3 py-1.5 text-xs">
              <IconSummary className="h-3.5 w-3.5" />
              <span>{busy ? "Generating…" : "Generate"}</span>
            </Button>
          </ConsentRequired>
        }
      >
        {snapshots === null ? (
          <Spinner />
        ) : snapshots.length === 0 ? (
          <Empty>No summaries yet.</Empty>
        ) : (
          <ul className="space-y-1.5">
            {snapshots.map((s) => {
              const state = snapshotState(s);
              return (
                <li key={s.id}>
                  <button
                    onClick={() => setSelected(s)}
                    className={`flex w-full items-center justify-between rounded-xl px-3 py-2 text-left text-xs transition-all ${
                      selected?.id === s.id
                        ? "bg-teal-50/90 font-semibold text-teal-900 ring-1 ring-teal-200/80 shadow-2xs"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                    }`}
                  >
                    <span>Version {s.version}</span>
                    <Badge value={state} />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* Right: Selected Snapshot Viewer */}
      <Card
        title={selected ? `Summary version ${selected.version}` : "Summary"}
        subtitle="Immutable patient summary generated directly from validated records"
        actions={
          selected &&
          snapshotState(selected) === "draft" && (
            <ConsentRequired>
              <Button onClick={approve} className="px-3.5 py-1.5 text-xs">
                <IconCheck className="h-3.5 w-3.5" />
                <span>Approve for sharing</span>
              </Button>
            </ConsentRequired>
          )
        }
      >
        {error && (
          <div className="mb-4">
            <Alert>{error}</Alert>
          </div>
        )}

        {!selected ? (
          <Empty>
            Generate a summary to preview it. You approve it before any doctor can see it;
            approved summaries never change.
          </Empty>
        ) : snapshotState(selected) === "invalidated" ? (
          <Alert kind="info">
            This summary was withdrawn because a source document was deleted.
          </Alert>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 px-3.5 py-2 text-xs text-slate-500">
              <span>
                Generated {formatDate(selected.generated_at)}
                {selected.approved_at
                  ? ` · approved ${formatDate(selected.approved_at)}`
                  : " · draft (unapproved)"}
              </span>
              <Badge value={snapshotState(selected)} />
            </div>

            <SnapshotView content={selected.content_json} />
          </div>
        )}
      </Card>
    </div>
  );
}
