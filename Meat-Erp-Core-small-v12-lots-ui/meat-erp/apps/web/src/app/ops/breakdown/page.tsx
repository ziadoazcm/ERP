"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Item, Location, LossType } from "@/lib/types";
import { enqueueLocalAction } from "@/lib/offlineQueue";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_id: number;
  item_name: string;
  received_at: string;
  received_qty_kg: number;
  available_qty_kg: number;
};

type BreakdownOutput = {
  item_id: number | "";
  quantity_kg: string;
  to_location_id: number | "";
};

type LossRow = {
  loss_type: string;
  quantity_kg: string;
  notes?: string;
};

type BreakdownRequest = {
  input_lot_id: number;
  input_quantity_kg: number;
  outputs: { item_id: number; quantity_kg: number; to_location_id: number }[];
  losses: { loss_type: string; quantity_kg: number; notes?: string | null }[];
  notes: string | null;
};

type BreakdownResponse = {
  production_order_id: number;
  input_movement_id: number;
  outputs: { id: number; lot_code: string }[];
  output_movement_ids: number[];
  loss_ids: number[];
  loss_movement_ids: number[];
  lot_event_ids: number[];
};

export default function BreakdownPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [lossTypes, setLossTypes] = useState<LossType[]>([]);

  const [inputLotId, setInputLotId] = useState<number | "">("");
  const [inputKg, setInputKg] = useState<string>("");

  const [outputs, setOutputs] = useState<BreakdownOutput[]>([
    { item_id: "", quantity_kg: "", to_location_id: "" },
  ]);

  const [losses, setLosses] = useState<LossRow[]>([]);
  const [notes, setNotes] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BreakdownResponse | null>(null);
  const [queuedTxn, setQueuedTxn] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [lotRows, it, lo, lt] = await Promise.all([
        apiGet<LotRow[]>("/lots?limit=200"),
        apiGet<Item[]>("/lookups/items"),
        apiGet<Location[]>("/lookups/locations"),
        apiGet<LossType[]>("/lookups/loss-types"),
      ]);
      setLots(lotRows);
      setItems(it);
      setLocations(lo);
      setLossTypes(lt);
    })().catch((e) => setError(String(e)));
  }, []);

  const inputLot = useMemo(() => lots.find((l) => l.id === inputLotId), [lots, inputLotId]);

  const totals = useMemo(() => {
    const outSum = outputs.reduce((acc, o) => acc + (Number(o.quantity_kg) || 0), 0);
    const lossSum = losses.reduce((acc, l) => acc + (Number(l.quantity_kg) || 0), 0);
    const input = Number(inputKg) || 0;
    return { input, outSum, lossSum, totalOut: outSum + lossSum, delta: input - (outSum + lossSum) };
  }, [outputs, losses, inputKg]);

  const canSubmit = useMemo(() => {
    if (busy) return false;
    if (typeof inputLotId !== "number") return false;
    if (!(Number(inputKg) > 0)) return false;

    if (outputs.length < 1) return false;

    for (const o of outputs) {
      if (typeof o.item_id !== "number") return false;
      if (!(Number(o.quantity_kg) > 0)) return false;
      if (typeof o.to_location_id !== "number") return false;
    }

    for (const l of losses) {
      if (l.loss_type.trim().length < 2) return false;
      if (!(Number(l.quantity_kg) > 0)) return false;
    }

    return Math.abs(totals.delta) <= 0.001;
  }, [busy, inputLotId, inputKg, outputs, losses, totals.delta]);

  function addOutput() {
    setOutputs((prev) => [...prev, { item_id: "", quantity_kg: "", to_location_id: "" }]);
  }

  function removeOutput(idx: number) {
    setOutputs((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateOutput(idx: number, patch: Partial<BreakdownOutput>) {
    setOutputs((prev) => prev.map((o, i) => (i === idx ? { ...o, ...patch } : o)));
  }

  function addLoss() {
    setLosses((prev) => [...prev, { loss_type: "trim", quantity_kg: "", notes: "" }]);
  }
  function removeLoss(idx: number) {
    setLosses((prev) => prev.filter((_, i) => i !== idx));
  }
  function updateLoss(idx: number, patch: Partial<LossRow>) {
    setLosses((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }

  async function submit() {
    setError("");
    setResult(null);
    setQueuedTxn(null);
    setBusy(true);

    try {
      const payload: BreakdownRequest = {
        input_lot_id: inputLotId as number,
        input_quantity_kg: Number(inputKg),
        outputs: outputs.map((o) => ({
          item_id: Number(o.item_id),
          quantity_kg: Number(o.quantity_kg),
          to_location_id: Number(o.to_location_id),
        })),
        losses: losses
          .filter((l) => (Number(l.quantity_kg) || 0) > 0)
          .map((l) => ({
            loss_type: l.loss_type.trim(),
            quantity_kg: Number(l.quantity_kg),
            notes: l.notes?.trim() || null,
          })),
        notes: notes.trim() || null,
      };

      // Offline Policy B: Breakdown (single-input) is allowed offline.
      // If the browser is offline (or fetch fails), queue locally.
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        const q = enqueueLocalAction("breakdown", payload);
        setQueuedTxn(q.client_txn_id);
      } else {
        try {
          const resp = await apiPost<BreakdownResponse>("/production/breakdown", payload);
          setResult(resp);
        } catch {
          const q = enqueueLocalAction("breakdown", payload);
          setQueuedTxn(q.client_txn_id);
        }
      }

      setInputKg("");
      setInputLotId("");
      setOutputs([{ item_id: "", quantity_kg: "", to_location_id: "" }]);
      setLosses([]);
      setNotes("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Breakdown</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        <div className="rounded-xl border p-4 mt-6 space-y-4">
          <div>
            <label className="text-sm font-medium">Input Lot</label>
            <select className="mt-1 w-full border rounded-lg p-2" value={inputLotId} onChange={(e) => setInputLotId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Select input lot…</option>
              {lots.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.lot_code} — {l.item_name} — {l.state}
                </option>
              ))}
            </select>
            {inputLot && (
              <div className="text-xs text-gray-600 mt-1">
                Selected: <span className="font-medium">{inputLot.lot_code}</span> ({inputLot.item_name})<br />
                State: <span className="font-mono">{inputLot.state}</span><br />
                Received: <span className="font-mono">{Number(inputLot.received_qty_kg).toFixed(3)}</span> kg<br />
                Available: <span className="font-mono">{Number(inputLot.available_qty_kg).toFixed(3)}</span> kg
              </div>
            )}
          </div>

          <div>
            <label className="text-sm font-medium">Input Weight (kg)</label>
            <input className="mt-1 w-full border rounded-lg p-2" value={inputKg} onChange={(e) => setInputKg(e.target.value)} placeholder="e.g. 10.000" inputMode="decimal" />
          </div>

          <div className="pt-2">
            <div className="flex items-center justify-between">
              <div className="font-medium">Outputs</div>
              <button className="text-sm underline" onClick={addOutput} type="button">
                + Add output
              </button>
            </div>

            <div className="space-y-3 mt-3">
              {outputs.map((o, idx) => (
                <div key={idx} className="rounded-xl border p-3">
                  <div className="flex justify-between items-center">
                    <div className="text-sm font-medium">Output #{idx + 1}</div>
                    {outputs.length > 1 && (
                      <button className="text-sm underline" onClick={() => removeOutput(idx)} type="button">
                        Remove
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label className="text-sm font-medium">Item</label>
                      <select
                        className="mt-1 w-full border rounded-lg p-2"
                        value={o.item_id}
                        onChange={(e) => updateOutput(idx, { item_id: e.target.value ? Number(e.target.value) : "" })}
                      >
                        <option value="">Select…</option>
                        {items.map((it) => (
                          <option key={it.id} value={it.id}>
                            {it.name} ({it.sku})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-sm font-medium">Qty (kg)</label>
                      <input
                        className="mt-1 w-full border rounded-lg p-2"
                        value={o.quantity_kg}
                        onChange={(e) => updateOutput(idx, { quantity_kg: e.target.value })}
                        inputMode="decimal"
                        placeholder="e.g. 3.500"
                      />
                    </div>
                  </div>

                  <div className="mt-3">
                    <label className="text-sm font-medium">Output Location</label>
                    <select
                      className="mt-1 w-full border rounded-lg p-2"
                      value={o.to_location_id}
                      onChange={(e) => updateOutput(idx, { to_location_id: e.target.value ? Number(e.target.value) : "" })}
                    >
                      <option value="">Select location…</option>
                      {locations.map((l) => (
                        <option key={l.id} value={l.id}>
                          {l.name} ({l.kind})
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="pt-2">
            <div className="flex items-center justify-between">
              <div className="font-medium">Losses</div>
              <button className="text-sm underline" onClick={addLoss} type="button">
                + Add loss
              </button>
            </div>

            {losses.length === 0 && (
              <div className="text-sm text-gray-600 mt-2">
                No losses. If there is trim/bone/purge/spoilage, add it here.
              </div>
            )}

            <div className="space-y-3 mt-3">
              {losses.map((l, idx) => (
                <div key={idx} className="rounded-xl border p-3">
                  <div className="flex justify-between items-center">
                    <div className="text-sm font-medium">Loss #{idx + 1}</div>
                    <button className="text-sm underline" onClick={() => removeLoss(idx)} type="button">
                      Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                    <div>
                      <label className="text-sm font-medium">Type</label>
                      <select
                        className="mt-1 w-full border rounded-lg p-2"
                        value={l.loss_type}
                        onChange={(e) => updateLoss(idx, { loss_type: e.target.value })}
                      >
                        <option value="">Select…</option>
                        {lossTypes.map((t) => (
                          <option key={t.code} value={t.code}>{t.name}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-sm font-medium">Qty (kg)</label>
                      <input
                        className="mt-1 w-full border rounded-lg p-2"
                        value={l.quantity_kg}
                        onChange={(e) => updateLoss(idx, { quantity_kg: e.target.value })}
                        inputMode="decimal"
                        placeholder="e.g. 0.500"
                      />
                    </div>

                    <div>
                      <label className="text-sm font-medium">Notes</label>
                      <input
                        className="mt-1 w-full border rounded-lg p-2"
                        value={l.notes || ""}
                        onChange={(e) => updateLoss(idx, { notes: e.target.value })}
                        placeholder="optional"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="text-sm font-medium">Notes</label>
            <input
              className="mt-1 w-full border rounded-lg p-2"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional notes…"
            />
          </div>

          <div className="rounded-xl border p-3 bg-gray-50">
            <div className="text-sm font-medium">Balance Check (no unassigned weight)</div>
            <div className="text-sm mt-2 space-y-1">
              <div>Input: <span className="font-mono">{totals.input.toFixed(3)}</span></div>
              <div>Outputs: <span className="font-mono">{totals.outSum.toFixed(3)}</span></div>
              <div>Losses: <span className="font-mono">{totals.lossSum.toFixed(3)}</span></div>
              <div>Total Out: <span className="font-mono">{totals.totalOut.toFixed(3)}</span></div>
              <div>
                Delta:{" "}
                <span className={`font-mono ${Math.abs(totals.delta) <= 0.001 ? "text-green-700" : "text-red-700"}`}>
                  {totals.delta.toFixed(3)}
                </span>
              </div>
            </div>
          </div>

          <button
            className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
            disabled={!canSubmit}
            onClick={submit}
          >
            {busy ? "Saving…" : "Submit Breakdown"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-4 rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
            <div className="font-medium">Breakdown Created</div>
            <div>production_order_id: {result.production_order_id}</div>
            <div className="mt-2">
              Outputs:
              <ul className="list-disc ml-5">
                {result.outputs.map((o: any) => (
                  <li key={o.id}><span className="font-mono">{o.lot_code}</span> (id {o.id})</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {queuedTxn && (
          <div className="mt-4 rounded-xl border border-blue-300 bg-blue-50 p-3 text-sm text-blue-900">
            <div className="font-medium">Queued offline</div>
            <div>
              txn_id: <span className="font-mono">{queuedTxn}</span>
            </div>
            <div className="text-xs text-blue-900/80 mt-1">Go to Offline Sync to push/apply when online.</div>
          </div>
        )}
      </div>
    </main>
  );
}
