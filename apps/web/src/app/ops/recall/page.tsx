"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_id: number;
  item_name: string;
  received_at: string;
};

type RecallResponse = {
  lot_id: number;
  backward_lot_ids: number[];
  forward_lot_ids: number[];
  affected_customers: { id: number; name: string }[];
};

export default function RecallPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [selectedLotId, setSelectedLotId] = useState<number | "">("");
  const [search, setSearch] = useState<string>("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [recall, setRecall] = useState<RecallResponse | null>(null);

  const [performedBy, setPerformedBy] = useState<string>("1");
  const [reason, setReason] = useState<string>("Recall quarantine: forward lots");
  const [quarantineResult, setQuarantineResult] = useState<any>(null);

  useEffect(() => {
    (async () => {
      const lotRows = await apiGet<LotRow[]>("/lots?limit=500");
      setLots(lotRows);
    })().catch((e) => setError(String(e)));
  }, []);

  const filteredLots = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return lots;
    return lots.filter(
      (l) =>
        l.lot_code.toLowerCase().includes(q) ||
        l.item_name.toLowerCase().includes(q)
    );
  }, [lots, search]);

  const selectedLot = useMemo(
    () => lots.find((l) => l.id === selectedLotId) || null,
    [lots, selectedLotId]
  );

  const lotById = useMemo(() => {
    const m = new Map<number, LotRow>();
    for (const l of lots) m.set(l.id, l);
    return m;
  }, [lots]);

  const backwardLots = useMemo(() => {
    if (!recall) return [];
    return recall.backward_lot_ids
      .map(
        (id) =>
          lotById.get(id) || {
            id,
            lot_code: `#${id}`,
            state: "?",
            item_id: 0,
            item_name: "Unknown",
            received_at: "",
          }
      )
      .sort((a, b) => a.lot_code.localeCompare(b.lot_code));
  }, [recall, lotById]);

  const forwardLots = useMemo(() => {
    if (!recall) return [];
    return recall.forward_lot_ids
      .map(
        (id) =>
          lotById.get(id) || {
            id,
            lot_code: `#${id}`,
            state: "?",
            item_id: 0,
            item_name: "Unknown",
            received_at: "",
          }
      )
      .sort((a, b) => a.lot_code.localeCompare(b.lot_code));
  }, [recall, lotById]);

  async function runRecall() {
    setError("");
    setRecall(null);

    if (typeof selectedLotId !== "number") {
      setError("Select a lot first.");
      return;
    }

    setBusy(true);
    try {
      const resp = await apiGet<RecallResponse>(`/recall/${selectedLotId}`);
      setRecall(resp);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function quarantineForward() {
    setError("");
    setQuarantineResult(null);

    if (!recall || typeof selectedLotId !== "number") return;

    if (reason.trim().length < 2) {
      setError("Enter a reason.");
      return;
    }

    setBusy(true);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/recall/${selectedLotId}/quarantine-forward`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            performed_by: Number(performedBy),
            reason: reason.trim(),
          }),
        }
      );

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setQuarantineResult(data);

      const lotRows = await apiGet<LotRow[]>("/lots?limit=500");
      setLots(lotRows);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Recall</h1>
          <a className="text-sm underline" href="/">
            Ops Index
          </a>
        </div>

        <p className="text-sm text-gray-600 mt-1">
          Select a lot and trace backward (sources) + forward (derived lots) +
          affected customers.
        </p>

        <div className="rounded-xl border p-4 mt-6 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label className="text-sm font-medium">Search lots</label>
              <input
                className="mt-1 w-full border rounded-lg p-2"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by lot code or item…"
              />
            </div>

            <div className="sm:col-span-2">
              <label className="text-sm font-medium">Lot</label>
              <select
                className="mt-1 w-full border rounded-lg p-2"
                value={selectedLotId}
                onChange={(e) =>
                  setSelectedLotId(
                    e.target.value ? Number(e.target.value) : ""
                  )
                }
              >
                <option value="">Select a lot…</option>
                {filteredLots.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.lot_code} — {l.item_name} — {l.state}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {selectedLot && (
            <div className="rounded-xl border p-3 bg-gray-50 text-sm">
              <div className="font-medium">Selected Lot</div>
              <div className="mt-1">
                <span className="font-mono">
                  {selectedLot.lot_code}
                </span>{" "}
                — {selectedLot.item_name} —{" "}
                <span className="font-medium">
                  {selectedLot.state}
                </span>
              </div>
              <div className="text-gray-600">
                lot_id: {selectedLot.id}
              </div>
            </div>
          )}

          <button
            className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
            onClick={runRecall}
            disabled={busy || typeof selectedLotId !== "number"}
          >
            {busy ? "Tracing…" : "Run Recall Trace"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        {recall && (
          <>
            <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div className="rounded-xl border p-4">
                <div className="font-medium">Backward Trace</div>
                <div className="text-sm text-gray-600 mt-1">
                  Source lots (inputs)
                </div>
                <div className="mt-3 space-y-2">
                  {backwardLots.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No ancestors found.
                    </div>
                  ) : (
                    backwardLots.map((l) => (
                      <div
                        key={l.id}
                        className="rounded-lg border p-2"
                      >
                        <div className="font-mono text-sm">
                          {l.lot_code}
                        </div>
                        <div className="text-xs text-gray-600">
                          {l.item_name} — {l.state} — id {l.id}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-xl border p-4">
                <div className="font-medium">Forward Trace</div>
                <div className="text-sm text-gray-600 mt-1">
                  Derived lots (outputs)
                </div>
                <div className="mt-3 space-y-2">
                  {forwardLots.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No descendants found.
                    </div>
                  ) : (
                    forwardLots.map((l) => (
                      <div
                        key={l.id}
                        className="rounded-lg border p-2"
                      >
                        <div className="font-mono text-sm">
                          {l.lot_code}
                        </div>
                        <div className="text-xs text-gray-600">
                          {l.item_name} — {l.state} — id {l.id}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-xl border p-4">
                <div className="font-medium">Affected Customers</div>
                <div className="text-sm text-gray-600 mt-1">
                  Customers who bought this lot or its descendants
                </div>
                <div className="mt-3 space-y-2">
                  {recall.affected_customers.length === 0 ? (
                    <div className="text-sm text-gray-600">
                      No customers found.
                    </div>
                  ) : (
                    recall.affected_customers.map((c) => (
                      <div
                        key={c.id}
                        className="rounded-lg border p-2"
                      >
                        <div className="text-sm font-medium">
                          {c.name}
                        </div>
                        <div className="text-xs text-gray-600">
                          customer_id: {c.id}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            <div className="rounded-xl border p-4 mt-4">
              <div className="font-medium">Recall Actions</div>
              <div className="text-sm text-gray-600 mt-1">
                Quarantines all{" "}
                <span className="font-medium">
                  forward (descendant)
                </span>{" "}
                lots found in the trace.
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                <div>
                  <label className="text-sm font-medium">
                    Performed By (user id)
                  </label>
                  <input
                    className="mt-1 w-full border rounded-lg p-2"
                    value={performedBy}
                    onChange={(e) =>
                      setPerformedBy(e.target.value)
                    }
                    inputMode="numeric"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="text-sm font-medium">
                    Reason
                  </label>
                  <input
                    className="mt-1 w-full border rounded-lg p-2"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                  />
                </div>
              </div>

              <button
                className="mt-3 w-full rounded-lg bg-red-600 text-white p-2 disabled:opacity-50"
                disabled={
                  busy ||
                  !recall ||
                  recall.forward_lot_ids.length === 0
                }
                onClick={quarantineForward}
              >
                {busy
                  ? "Quarantining…"
                  : `Quarantine all forward lots (${recall.forward_lot_ids.length})`}
              </button>

              {recall.forward_lot_ids.length === 0 && (
                <div className="text-sm text-gray-600 mt-2">
                  No forward lots found — nothing to quarantine.
                </div>
              )}

              {quarantineResult && (
                <div className="mt-3 rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
                  <div className="font-medium">
                    Quarantine complete
                  </div>
                  <div>
                    Quarantined:{" "}
                    {quarantineResult.quarantined_count}
                  </div>
                  <div>
                    Already quarantined:{" "}
                    {quarantineResult.already_quarantined_count}
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

