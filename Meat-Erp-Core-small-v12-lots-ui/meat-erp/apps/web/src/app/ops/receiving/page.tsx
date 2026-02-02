"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { enqueueLocalAction } from "@/lib/offlineQueue";

interface Item {
  id: number;
  sku: string;
  name: string;
  is_meat: boolean;
}

interface Supplier {
  id: number;
  name: string;
}

interface Location {
  id: number;
  name: string;
  kind: string;
}

interface ReceivingResponse {
  lot_id: number;
  lot_code: string;
  movement_id: number;
  lot_event_id: number;
}

export default function ReceivingPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);

  const [itemId, setItemId] = useState<number | "">("");
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [kg, setKg] = useState<string>("");
  const [locationId, setLocationId] = useState<number | "">("");
  const [notes, setNotes] = useState("");

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ReceivingResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [queuedTxn, setQueuedTxn] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [it, sp, lo] = await Promise.all([
        apiGet<Item[]>("/lookups/items"),
        apiGet<Supplier[]>("/lookups/suppliers"),
        apiGet<Location[]>("/lookups/locations"),
      ]);
      setItems(it);
      setSuppliers(sp);
      setLocations(lo);
    })().catch((e) => setError(String(e)));
  }, []);

  const canSubmit = useMemo(() => {
    const qty = Number(kg);
    return (
      typeof itemId === "number" &&
      typeof supplierId === "number" &&
      typeof locationId === "number" &&
      Number.isFinite(qty) &&
      qty > 0
    );
  }, [itemId, supplierId, locationId, kg]);

  async function submit() {
    setError("");
    setResult(null);
    setQueuedTxn(null);
    setBusy(true);
    try {
      const payload = {
        item_id: Number(itemId),
        supplier_id: Number(supplierId),
        quantity_kg: Number(kg),
        to_location_id: Number(locationId),
        notes: notes.trim() ? notes.trim() : null,
      };
      // Offline Policy B: Receiving is allowed offline.
      // If the browser is offline (or fetch fails), queue locally.
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        const q = enqueueLocalAction("receiving", payload);
        setQueuedTxn(q.client_txn_id);
        setKg("");
        setNotes("");
      } else {
        try {
          const resp = await apiPost<ReceivingResponse>("/receiving/lots", payload);
          setResult(resp);
          setKg("");
          setNotes("");
        } catch {
          const q = enqueueLocalAction("receiving", payload);
          setQueuedTxn(q.client_txn_id);
          setKg("");
          setNotes("");
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Receiving</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>
        <p className="text-sm text-gray-600 mt-1">Create a new lot from incoming goods. Lot code is auto-generated.</p>

        <div className="rounded-xl border p-4 mt-6 space-y-4">
          <div>
            <label className="text-sm font-medium">Item</label>
            <select className="mt-1 w-full border rounded-lg p-2" value={itemId} onChange={(e) => setItemId(e.target.value ? Number(e.target.value) : "")}>
              <option value="">Select item…</option>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name} ({i.sku})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium">Supplier</label>
            <select className="mt-1 w-full border rounded-lg p-2" value={supplierId} onChange={(e) => setSupplierId(e.target.value ? Number(e.target.value) : "")} disabled={itemId === ""}>
              <option value="">Select supplier…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {itemId === "" && <div className="text-xs text-gray-500 mt-1">Select item first.</div>}
          </div>

          <div>
            <label className="text-sm font-medium">Weight (kg)</label>
            <input className="mt-1 w-full border rounded-lg p-2" value={kg} onChange={(e) => setKg(e.target.value)} placeholder="e.g. 37.500" inputMode="decimal" />
          </div>

          <div>
            <label className="text-sm font-medium">Location</label>
            <select className="mt-1 w-full border rounded-lg p-2" value={locationId} onChange={(e) => setLocationId(e.target.value ? Number(e.target.value) : "")} disabled={!kg}>
              <option value="">Select location…</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.kind})
                </option>
              ))}
            </select>
            {!kg && <div className="text-xs text-gray-500 mt-1">Enter weight first.</div>}
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

          <button
            className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
            onClick={submit}
            disabled={!canSubmit || busy}
          >
            {busy ? "Saving…" : "Create Lot"}
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-4 rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
            <div className="font-medium">Created</div>
            <div>lot_code: {result.lot_code}</div>
            <div>lot_id: {result.lot_id}</div>
            <div>movement_id: {result.movement_id}</div>
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
