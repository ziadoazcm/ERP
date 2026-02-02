"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import {
  clearLocalQueue,
  getClientId,
  groupByTxn,
  listLocalQueue,
  removeLocalActions,
  type OfflineQueuedAction,
} from "@/lib/offlineQueue";

type ApplyResult = {
  offline_queue_id: number;
  client_txn_id: string;
  status: "applied" | "conflict" | "rejected";
  server_refs?: Record<string, any> | null;
  reason?: string | null;
};

type ApplyResponse = {
  applied: number;
  conflicts: number;
  rejected: number;
  results: ApplyResult[];
};

type ConflictRow = {
  id: number;
  client_id: string;
  client_txn_id: string;
  action_type: string;
  status: string;
  created_at: string;
  conflict_reason: string | null;
  payload: any;
};

export default function OfflineSyncPage() {
  const [clientId, setClientId] = useState<string>("");
  const [localQueue, setLocalQueue] = useState<OfflineQueuedAction[]>([]);
  const [conflicts, setConflicts] = useState<ConflictRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [lastApply, setLastApply] = useState<ApplyResponse | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    setClientId(getClientId());
    setLocalQueue(listLocalQueue());
    refreshConflicts().catch(() => void 0);
  }, []);

  async function refreshConflicts() {
    const rows = await apiGet<ConflictRow[]>("/offline/conflicts?status=conflict");
    setConflicts(rows);
  }

  function refreshLocal() {
    setLocalQueue(listLocalQueue());
  }

  const filteredLocal = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return localQueue;
    return localQueue.filter((r) => {
      const hay = `${r.client_txn_id} ${r.action_type} ${JSON.stringify(r.payload ?? {})}`.toLowerCase();
      return hay.includes(q);
    });
  }, [localQueue, search]);

  const grouped = useMemo(() => groupByTxn(filteredLocal), [filteredLocal]);
  const txnIds = useMemo(() => Object.keys(grouped).sort(), [grouped]);

  async function pushLocalToServer() {
    setError("");
    setBusy(true);
    try {
      const rows = listLocalQueue();
      if (!rows.length) {
        setBusy(false);
        return;
      }
      await apiPost("/offline/queue", {
        client_id: clientId,
        submitted_by: 1, // TODO: from login
        actions: rows.map((r) => ({
          client_txn_id: r.client_txn_id,
          action_type: r.action_type,
          payload: r.payload,
        })),
      });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applyServerQueue() {
    setError("");
    setBusy(true);
    try {
      const resp = await apiPost<ApplyResponse>("/offline/sync/apply", {
        client_id: clientId,
        limit: 500,
      });
      setLastApply(resp);
      await refreshConflicts();
      // Optimistic cleanup: if server applied/duplicated the local rows, you can clear locally.
      // We keep local queue until you choose to clear, to avoid hiding unsynced actions.
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function syncNow() {
    await pushLocalToServer();
    await applyServerQueue();
  }

  function removeTxn(txnId: string) {
    const rows = listLocalQueue();
    const ids = rows.filter((r) => r.client_txn_id === txnId).map((r) => r.local_id);
    removeLocalActions(ids);
    refreshLocal();
  }

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Offline Sync</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        <div className="mt-2 text-sm text-gray-600">
          Client ID: <span className="font-mono">{clientId}</span>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          {/* Local Queue */}
          <div className="rounded-xl border p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium">Local Queue (device)</div>
                <div className="text-sm text-gray-600">Receiving / Breakdown / Sales actions queued while offline.</div>
              </div>
              <div className="text-sm">Count: <span className="font-mono">{localQueue.length}</span></div>
            </div>

            <div className="mt-3">
              <label className="text-sm font-medium">Search</label>
              <input
                className="mt-1 w-full border rounded-lg p-2"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="txn id, action type, payload…"
              />
            </div>

            <div className="mt-3 flex gap-2">
              <button
                className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                disabled={busy || localQueue.length === 0}
                onClick={pushLocalToServer}
              >
                Push to server
              </button>
              <button
                className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50"
                disabled={busy || localQueue.length === 0}
                onClick={() => { clearLocalQueue(); refreshLocal(); }}
              >
                Clear local
              </button>
              <button
                className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                disabled={busy}
                onClick={syncNow}
                title="Push local queue then apply server queue"
              >
                Sync now
              </button>
            </div>

            <div className="mt-4 space-y-2 max-h-[560px] overflow-auto">
              {txnIds.length === 0 ? (
                <div className="text-sm text-gray-600">No queued actions on this device.</div>
              ) : (
                txnIds.map((txnId) => {
                  const rows = grouped[txnId] || [];
                  return (
                    <div key={txnId} className="rounded-lg border p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <div className="font-mono text-sm">{txnId}</div>
                          <div className="text-xs text-gray-600">{rows.length} action(s)</div>
                        </div>
                        <button
                          className="rounded-lg border px-2 py-1 text-xs"
                          onClick={() => removeTxn(txnId)}
                          disabled={busy}
                          title="Remove this transaction from local queue"
                        >
                          Remove
                        </button>
                      </div>

                      <div className="mt-2 space-y-1">
                        {rows.map((r) => (
                          <div key={r.local_id} className="text-xs">
                            <span className="font-mono">{r.action_type}</span>
                            <span className="text-gray-500"> · {new Date(r.created_at).toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Server Apply + Conflicts */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Server Sync</div>
            <div className="text-sm text-gray-600">Apply queued actions and review conflicts (supervisor review).</div>

            <div className="mt-3 flex gap-2">
              <button
                className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                disabled={busy}
                onClick={applyServerQueue}
              >
                Apply server queue
              </button>
              <button
                className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50"
                disabled={busy}
                onClick={refreshConflicts}
              >
                Refresh conflicts
              </button>
            </div>

            {lastApply && (
              <div className="mt-4 rounded-xl border bg-gray-50 p-3 text-sm">
                <div className="font-medium">Last apply result</div>
                <div className="mt-1">
                  Applied: <span className="font-mono">{lastApply.applied}</span> · Conflicts: <span className="font-mono">{lastApply.conflicts}</span> · Rejected: <span className="font-mono">{lastApply.rejected}</span>
                </div>
                <div className="mt-2 max-h-40 overflow-auto">
                  {lastApply.results.slice(0, 50).map((r, idx) => (
                    <div key={`${r.offline_queue_id}-${idx}`} className="text-xs">
                      <span className="font-mono">{r.client_txn_id}</span> — {r.status}
                      {r.reason ? <span className="text-gray-600"> · {r.reason}</span> : null}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-4">
              <div className="font-medium">Conflicts</div>
              <div className="text-sm text-gray-600">Items that need review (inventory/safety constraints changed).</div>
            </div>

            <div className="mt-2 space-y-2 max-h-[520px] overflow-auto">
              {conflicts.length === 0 ? (
                <div className="text-sm text-gray-600">No conflicts.</div>
              ) : (
                conflicts.map((c) => (
                  <div key={c.id} className="rounded-lg border p-3">
                    <div className="flex justify-between gap-2">
                      <div>
                        <div className="font-mono text-sm">{c.client_txn_id}</div>
                        <div className="text-xs text-gray-600">{c.action_type} · {new Date(c.created_at).toLocaleString()}</div>
                      </div>
                      <div className="text-xs font-medium text-red-700">CONFLICT</div>
                    </div>
                    {c.conflict_reason && (
                      <div className="mt-2 text-xs text-red-800 whitespace-pre-wrap">{c.conflict_reason}</div>
                    )}
                    <details className="mt-2">
                      <summary className="text-xs cursor-pointer">Payload</summary>
                      <pre className="mt-2 text-xs bg-gray-50 border rounded-lg p-2 overflow-auto">{JSON.stringify(c.payload, null, 2)}</pre>
                    </details>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
