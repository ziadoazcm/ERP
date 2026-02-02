"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  received_qty_kg?: number;
  available_qty_kg?: number;
};

type ItemRow = { id: number; name: string };
type LocationRow = { id: number; name: string };
type LossTypeRow = { code: string; name: string };

export default function ReworkPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [items, setItems] = useState<ItemRow[]>([]);
  const [locations, setLocations] = useState<LocationRow[]>([]);
  const [lossTypes, setLossTypes] = useState<LossTypeRow[]>([]);

  const [inputLotId, setInputLotId] = useState<number | "">("");
  const [outputItemId, setOutputItemId] = useState<number | "">("");
  const [toLocationId, setToLocationId] = useState<number | "">("");
  const [reworkKg, setReworkKg] = useState<string>("");
  const [notes, setNotes] = useState("");

  const [losses, setLosses] = useState<Array<{ loss_type: string; quantity_kg: string; notes: string }>>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);

  async function refresh() {
    const [l, it, locs, lt] = await Promise.all([
      apiGet<any[]>("/lots?limit=800"),
      apiGet<ItemRow[]>("/lookups/items"),
      apiGet<LocationRow[]>("/lookups/locations"),
      apiGet<LossTypeRow[]>("/loss-types"),
    ]);
    setLots(
      l.map((r) => ({
        id: r.id,
        lot_code: r.lot_code,
        state: r.state,
        item_name: r.item_name,
        received_qty_kg: r.received_qty_kg,
        available_qty_kg: r.available_qty_kg,
      }))
    );
    setItems(it);
    setLocations(locs);
    setLossTypes(lt);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  const eligibleLots = useMemo(() => {
    // keep consistent with backend guard
    return lots.filter((l) => !["quarantined", "disposed", "sold"].includes(l.state));
  }, [lots]);

  const selectedLot = useMemo(() => lots.find((x) => x.id === inputLotId) || null, [lots, inputLotId]);

  // Default rework quantity to full available when lot changes
  useEffect(() => {
    if (!selectedLot) return;
    const avail = Number(selectedLot.available_qty_kg ?? 0);
    if (avail > 0) setReworkKg(avail.toFixed(3));
  }, [selectedLot?.id]);

  // Auto-fill rework qty to full available when lot changes
  useEffect(() => {
    if (!selectedLot) return;
    const avail = Number(selectedLot.available_qty_kg ?? 0);
    if (avail > 0) setReworkKg(avail.toFixed(3));
  }, [selectedLot?.id]);

  const availKg = Number(selectedLot?.available_qty_kg ?? 0);
  const reworkKgNum = Number(reworkKg || 0);
  const remainderKg = Math.max(0, availKg - reworkKgNum);

  function addLoss() {
    setLosses((prev) => [...prev, { loss_type: "", quantity_kg: "", notes: "" }]);
  }

  function updateLoss(idx: number, patch: Partial<{ loss_type: string; quantity_kg: string; notes: string }>) {
    setLosses((prev) => prev.map((l, i) => (i === idx ? { ...l, ...patch } : l)));
  }

  function removeLoss(idx: number) {
    setLosses((prev) => prev.filter((_, i) => i !== idx));
  }

  async function submit() {
    setError("");
    setResult(null);
    if (typeof inputLotId !== "number") return setError("Select an input lot.");
    if (typeof outputItemId !== "number") return setError("Select an output item.");
    if (typeof toLocationId !== "number") return setError("Select a destination location.");

    if (!(availKg > 0)) return setError("Selected lot has no available quantity.");
    if (!(reworkKgNum > 0)) return setError("Rework qty must be > 0.");
    if (reworkKgNum > availKg + 0.001) return setError("Rework qty cannot exceed available.");

    const payload = {
      input_lot_id: inputLotId,
      output_item_id: outputItemId,
      to_location_id: toLocationId,
      rework_quantity_kg: Number(reworkKgNum),
      losses: losses
        .filter((x) => x.loss_type && x.quantity_kg)
        .map((x) => ({
          loss_type: x.loss_type,
          quantity_kg: Number(x.quantity_kg),
          notes: x.notes.trim() ? x.notes.trim() : null,
        })),
      notes: notes.trim() ? notes.trim() : null,
    };

    setBusy(true);
    try {
      const res = await apiPost("/rework", payload);
      setResult(res);
      setNotes("");
      setLosses([]);
      await refresh();
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
          <h1 className="text-xl font-semibold">Rework / Regrade</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <div className="rounded-xl border p-4 mt-6">
          <div className="font-medium">Create Rework</div>
          <div className="text-sm text-gray-600 mt-1">
            Partial rework supported: the original lot is consumed once and split into a reworked lot + a remainder lot (traceable).
          </div>

          <div className="mt-4 space-y-3">
            <div>
              <label className="text-sm font-medium">Input Lot</label>
              <select
                className="mt-1 w-full border rounded-lg p-2"
                value={inputLotId}
                onChange={(e) => setInputLotId(e.target.value ? Number(e.target.value) : "")}
              >
                <option value="">Select…</option>
                {eligibleLots.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.lot_code} — {l.item_name}
                  </option>
                ))}
              </select>

              {selectedLot && (
                <div className="mt-2 text-xs text-gray-700 rounded-lg border bg-gray-50 p-2">
                  <div>
                    <span className="font-medium">State:</span> {selectedLot.state}
                  </div>
                  <div>
                    <span className="font-medium">Received:</span>{" "}
                    <span className="font-mono">{Number(selectedLot.received_qty_kg ?? 0).toFixed(3)}</span> kg
                  </div>
                  <div>
                    <span className="font-medium">Available:</span>{" "}
                    <span className="font-mono">{Number(selectedLot.available_qty_kg ?? 0).toFixed(3)}</span> kg
                  </div>
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-medium">Rework Qty (kg)</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2"
                  value={reworkKg}
                  onChange={(e) => setReworkKg(e.target.value)}
                  inputMode="decimal"
                  placeholder="0.000"
                />
                {selectedLot && (
                  <div className="text-xs text-gray-600 mt-1">
                    Remainder: <span className="font-mono">{remainderKg.toFixed(3)}</span> kg
                  </div>
                )}
              </div>

              <div>
                <label className="text-sm font-medium">Output Item</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={outputItemId}
                  onChange={(e) => setOutputItemId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {items.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium">Destination Location</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={toLocationId}
                  onChange={(e) => setToLocationId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {locations.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </select>
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

            <div className="rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <div className="font-medium">Losses (optional)</div>
                <button className="text-sm underline" type="button" onClick={addLoss}>
                  Add loss
                </button>
              </div>

              {losses.length === 0 ? (
                <div className="text-sm text-gray-600 mt-2">No losses.</div>
              ) : (
                <div className="mt-3 space-y-3">
                  {losses.map((l, idx) => (
                    <div key={idx} className="rounded-lg border p-3">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        <div>
                          <label className="text-xs text-gray-600">Loss Type</label>
                          <select
                            className="mt-1 w-full border rounded-lg p-2 text-sm"
                            value={l.loss_type}
                            onChange={(e) => updateLoss(idx, { loss_type: e.target.value })}
                          >
                            <option value="">Select…</option>
                            {lossTypes.map((t) => (
                              <option key={t.code} value={t.code}>
                                {t.name}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="text-xs text-gray-600">Qty (kg)</label>
                          <input
                            className="mt-1 w-full border rounded-lg p-2 text-sm"
                            value={l.quantity_kg}
                            onChange={(e) => updateLoss(idx, { quantity_kg: e.target.value })}
                            inputMode="decimal"
                            placeholder="0.000"
                          />
                        </div>

                        <div>
                          <label className="text-xs text-gray-600">Notes</label>
                          <input
                            className="mt-1 w-full border rounded-lg p-2 text-sm"
                            value={l.notes}
                            onChange={(e) => updateLoss(idx, { notes: e.target.value })}
                            placeholder="Optional…"
                          />
                        </div>
                      </div>

                      <div className="mt-2">
                        <button className="text-xs underline" type="button" onClick={() => removeLoss(idx)}>
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <button
              className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
              onClick={submit}
              disabled={busy}
            >
              {busy ? "Saving…" : "Create Rework"}
            </button>
          </div>
        </div>

        {result && (
          <div className="mt-4 rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
            <div className="font-medium">Rework Created</div>
            <div>production_order_id: {result.production_order_id}</div>
            <div>
              output: <span className="font-mono">{result.output_lot?.lot_code}</span> ({Number(result.output_lot?.quantity_kg ?? 0).toFixed(3)} kg)
            </div>
            {result.remainder_lot && (
              <div>
                remainder: <span className="font-mono">{result.remainder_lot?.lot_code}</span> ({Number(result.remainder_lot?.quantity_kg ?? 0).toFixed(3)} kg)
              </div>
            )}
            <div>loss_total: {Number(result.loss_total_kg ?? 0).toFixed(3)} kg</div>
          </div>
        )}
      </div>
    </main>
  );
}
