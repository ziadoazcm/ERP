"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  ready_at?: string | null;
  current_location_id?: number | null;
  received_qty_kg?: number | null;
  available_qty_kg?: number | null;
};

type ItemRow = { id: number; name: string; sku?: string | null };
type LocationRow = { id: number; name: string; kind?: string | null };
type ProcessProfileRow = { id: number; name: string; allows_lot_mixing: boolean };

type InputLine = {
  lot_id: number | "";
  quantity_kg: string;
};

export default function MixingPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [items, setItems] = useState<ItemRow[]>([]);
  const [locations, setLocations] = useState<LocationRow[]>([]);
  const [profiles, setProfiles] = useState<ProcessProfileRow[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [result, setResult] = useState<any>(null);

  const [search, setSearch] = useState("");
  const [processProfileId, setProcessProfileId] = useState<number | "">("");
  const [outputItemId, setOutputItemId] = useState<number | "">("");
  const [outputLocationId, setOutputLocationId] = useState<number | "">("");
  const [notes, setNotes] = useState("");

  const [inputs, setInputs] = useState<InputLine[]>([
    { lot_id: "", quantity_kg: "" },
    { lot_id: "", quantity_kg: "" },
  ]);

  const isOnline = typeof navigator !== "undefined" ? navigator.onLine : true;

  async function refresh() {
    const [lotsResp, itemsResp, locsResp, profResp] = await Promise.all([
      apiGet<any[]>("/lots?limit=1500"),
      apiGet<ItemRow[]>("/lookups/items"),
      apiGet<LocationRow[]>("/lookups/locations"),
      apiGet<ProcessProfileRow[]>("/lookups/process-profiles?allows_lot_mixing=true"),
    ]);

    setLots(
      lotsResp.map((r) => ({
        id: r.id,
        lot_code: r.lot_code,
        state: r.state,
        item_name: r.item_name,
        ready_at: r.ready_at ?? null,
        current_location_id: r.current_location_id ?? null,
        received_qty_kg: r.received_qty_kg ?? null,
        available_qty_kg: r.available_qty_kg ?? null,
      }))
    );
    setItems(itemsResp);
    setLocations(locsResp);
    setProfiles(profResp.filter((p) => p.allows_lot_mixing));

    if (processProfileId === "" && profResp.length > 0) {
      const first = profResp.find((p) => p.allows_lot_mixing);
      if (first) setProcessProfileId(first.id);
    }
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const lotById = useMemo(() => {
    const m = new Map<number, LotRow>();
    for (const l of lots) m.set(l.id, l);
    return m;
  }, [lots]);

  const filteredLots = useMemo(() => {
    const q = search.trim().toLowerCase();
    const base = lots;
    if (!q) return base;
    return base.filter(
      (l) => l.lot_code.toLowerCase().includes(q) || l.item_name.toLowerCase().includes(q)
    );
  }, [lots, search]);

  const totalInputsKg = useMemo(() => {
    return inputs.reduce((sum, ln) => sum + (Number(ln.quantity_kg) || 0), 0);
  }, [inputs]);

  function setInput(idx: number, patch: Partial<InputLine>) {
    setInputs((prev) => prev.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  }

  function addInput() {
    setInputs((prev) => [...prev, { lot_id: "", quantity_kg: "" }]);
  }

  function removeInput(idx: number) {
    setInputs((prev) => prev.filter((_, i) => i !== idx));
  }

  async function submit() {
    setError("");
    setResult(null);

    if (!isOnline) {
      setError("Mixing is online-only (Policy B). Go online to proceed.");
      return;
    }
    if (typeof processProfileId !== "number") return setError("Select a process profile.");
    if (typeof outputItemId !== "number") return setError("Select an output item.");
    if (typeof outputLocationId !== "number") return setError("Select an output location.");

    const clean = inputs
      .map((x) => ({ lot_id: typeof x.lot_id === "number" ? x.lot_id : null, quantity_kg: Number(x.quantity_kg) }))
      .filter((x) => x.lot_id !== null && x.quantity_kg > 0) as { lot_id: number; quantity_kg: number }[];

    if (clean.length < 2) return setError("Add at least 2 input lots with weights.");

    // disallow duplicates (backend also aggregates, but ops UI should be clear)
    const uniq = new Set(clean.map((x) => x.lot_id));
    if (uniq.size < 2) return setError("Choose at least 2 distinct input lots.");

    // Client-side sanity checks using available_qty_kg if present
    for (const ln of clean) {
      const lot = lotById.get(ln.lot_id);
      if (!lot) continue;
      const avail = Number(lot.available_qty_kg ?? 0);
      if (ln.quantity_kg - avail > 0.001) {
        return setError(
          `Input lot ${lot.lot_code}: requested ${ln.quantity_kg.toFixed(3)} kg exceeds available ${avail.toFixed(3)} kg.`
        );
      }
    }

    setBusy(true);
    try {
      const resp = await apiPost("/production/mix", {
        process_profile_id: processProfileId,
        inputs: clean,
        output_item_id: outputItemId,
        output_location_id: outputLocationId,
        notes: notes.trim() ? notes.trim() : null,
      });
      setResult(resp);
      setNotes("");
      // reset inputs but keep 2 rows
      setInputs([
        { lot_id: "", quantity_kg: "" },
        { lot_id: "", quantity_kg: "" },
      ]);
      await refresh();
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
          <h1 className="text-xl font-semibold">Mixing</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        <div className="mt-2 text-sm text-gray-600">
          Sausage/burger mixing only. Online-only (Policy B). Inputs must be released + ready.
        </div>

        {!isOnline ? (
          <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            You appear to be offline. Mixing is not allowed offline.
          </div>
        ) : null}

        {error ? (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        ) : null}

        {result ? (
          <div className="mt-4 rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
            <div className="font-medium">Mix Created</div>
            <div className="mt-1">production_order_id: {result.production_order_id}</div>
            <div>output lot: <span className="font-mono">{result.output_lot_code}</span> (id {result.output_lot_id})</div>
          </div>
        ) : null}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          {/* Form */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Create Mix Batch</div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-sm font-medium">Search lots</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="lot code or item…"
                />
              </div>

              <div>
                <label className="text-sm font-medium">Process profile (mixing-enabled)</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={processProfileId}
                  onChange={(e) => setProcessProfileId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Output item</label>
                  <select
                    className="mt-1 w-full border rounded-lg p-2"
                    value={outputItemId}
                    onChange={(e) => setOutputItemId(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">Select…</option>
                    {items.map((it) => (
                      <option key={it.id} value={it.id}>
                        {it.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Output location</label>
                  <select
                    className="mt-1 w-full border rounded-lg p-2"
                    value={outputLocationId}
                    onChange={(e) => setOutputLocationId(e.target.value ? Number(e.target.value) : "")}
                  >
                    <option value="">Select…</option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.name}
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
                  placeholder="Optional…"
                />
              </div>

              <div className="rounded-xl border p-3">
                <div className="flex items-baseline justify-between">
                  <div className="font-medium">Inputs</div>
                  <button className="text-sm underline" type="button" onClick={addInput}>
                    + Add input
                  </button>
                </div>

                <div className="mt-3 space-y-3">
                  {inputs.map((ln, idx) => {
                    const lot = typeof ln.lot_id === "number" ? lotById.get(ln.lot_id) : null;
                    const avail = lot ? Number(lot.available_qty_kg ?? 0) : 0;
                    const readyAt = lot?.ready_at ? new Date(lot.ready_at).toLocaleString() : "—";
                    return (
                      <div key={idx} className="rounded-lg border p-3">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                          <div className="sm:col-span-2">
                            <label className="text-sm font-medium">Input lot</label>
                            <select
                              className="mt-1 w-full border rounded-lg p-2"
                              value={ln.lot_id}
                              onChange={(e) => setInput(idx, { lot_id: e.target.value ? Number(e.target.value) : "" })}
                            >
                              <option value="">Select…</option>
                              {filteredLots.map((l) => (
                                <option key={l.id} value={l.id}>
                                  {l.lot_code} — {l.item_name} — state:{l.state} — avail:{Number(l.available_qty_kg ?? 0).toFixed(3)}
                                </option>
                              ))}
                            </select>
                            {lot ? (
                              <div className="mt-2 text-xs text-gray-600">
                                <div>
                                  <span className="font-medium">State:</span> {lot.state}
                                </div>
                                <div>
                                  <span className="font-medium">Ready at:</span> {readyAt}
                                </div>
                                <div>
                                  <span className="font-medium">Available:</span> <span className="font-mono">{avail.toFixed(3)}</span> kg
                                </div>
                              </div>
                            ) : null}
                          </div>

                          <div>
                            <label className="text-sm font-medium">Qty (kg)</label>
                            <input
                              className="mt-1 w-full border rounded-lg p-2"
                              value={ln.quantity_kg}
                              onChange={(e) => setInput(idx, { quantity_kg: e.target.value })}
                              inputMode="decimal"
                              placeholder="0.000"
                            />
                            <div className="mt-2 flex items-center justify-between">
                              <div className="text-xs text-gray-600">Max: {avail.toFixed(3)}</div>
                              {inputs.length > 2 ? (
                                <button
                                  type="button"
                                  className="text-xs underline"
                                  onClick={() => removeInput(idx)}
                                >
                                  Remove
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="mt-3 text-sm">
                  Total inputs: <span className="font-mono">{totalInputsKg.toFixed(3)}</span> kg
                </div>
              </div>

              <button
                className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
                disabled={busy || !isOnline}
                onClick={submit}
              >
                {busy ? "Saving…" : "Create Mix Batch"}
              </button>
            </div>
          </div>

          {/* Guidance */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Mixing rules</div>
            <ul className="mt-3 text-sm text-gray-700 space-y-2 list-disc ml-5">
              <li>Online-only (Policy B).</li>
              <li>Requires a process profile that allows lot mixing.</li>
              <li>Inputs must be <span className="font-medium">released</span> and <span className="font-medium">ready</span>.</li>
              <li>Quarantined lots cannot be used.</li>
              <li>Each input qty must be ≤ available.</li>
              <li>Output lot code is auto-assigned and shown after creation.</li>
            </ul>
            <div className="mt-4 text-sm text-gray-600">
              Tip: Use the Search box to quickly find lots by lot code or item name.
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
