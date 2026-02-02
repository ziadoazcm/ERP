"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  received_qty_kg: number;
  available_qty_kg: number;
  ready_at?: string | null;
};

type CustomerRow = { id: number; name: string };

type ReservationRow = {
  id: number;
  lot_id: number;
  lot_code: string;
  lot_state: string;
  customer_id: number;
  customer_name: string;
  quantity_kg: number;
  reserved_at: string;
};

function fmtKg(x: number) {
  if (Number.isNaN(x)) return "0.000";
  return Number(x).toFixed(3);
}

export default function ReservationsPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [customers, setCustomers] = useState<CustomerRow[]>([]);
  const [reservations, setReservations] = useState<ReservationRow[]>([]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // create form
  const [lotSearch, setLotSearch] = useState("");
  const [selectedLotId, setSelectedLotId] = useState<number | "">("");
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | "">("");
  const [qtyKg, setQtyKg] = useState("1.000");

  // cancel notes per reservation
  const [cancelNotes, setCancelNotes] = useState<Record<number, string>>({});

  async function refresh() {
    const [l, c, r] = await Promise.all([
      apiGet<LotRow[]>("/lots?limit=1000"),
      apiGet<CustomerRow[]>("/lookups/customers"),
      apiGet<ReservationRow[]>("/reservations?limit=500"),
    ]);
    setLots(l);
    setCustomers(c);
    setReservations(r);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  const reservationsByLot = useMemo(() => {
    const m = new Map<number, number>();
    for (const r of reservations) {
      m.set(r.lot_id, (m.get(r.lot_id) ?? 0) + Number(r.quantity_kg));
    }
    return m;
  }, [reservations]);

  const filteredLots = useMemo(() => {
    const q = lotSearch.trim().toLowerCase();
    const all = lots.filter((x) => x.available_qty_kg > 0.0005);
    if (!q) return all;
    return all.filter((l) => l.lot_code.toLowerCase().includes(q) || l.item_name.toLowerCase().includes(q));
  }, [lots, lotSearch]);

  const selectedLot = useMemo(() => {
    if (typeof selectedLotId !== "number") return null;
    return lots.find((x) => x.id === selectedLotId) ?? null;
  }, [lots, selectedLotId]);

  const selectedReserved = useMemo(() => {
    if (!selectedLot) return 0;
    return reservationsByLot.get(selectedLot.id) ?? 0;
  }, [selectedLot, reservationsByLot]);

  const selectedReservable = useMemo(() => {
    if (!selectedLot) return 0;
    return Math.max(0, Number(selectedLot.available_qty_kg) - Number(selectedReserved));
  }, [selectedLot, selectedReserved]);

  async function createReservation() {
    setError("");
    if (typeof selectedLotId !== "number") return setError("Select a lot.");
    if (typeof selectedCustomerId !== "number") return setError("Select a customer.");
    const q = Number(qtyKg);
    if (!(q > 0)) return setError("Enter a quantity > 0.");

    setBusy(true);
    try {
      await apiPost("/reservations", {
        lot_id: selectedLotId,
        customer_id: selectedCustomerId,
        quantity_kg: q,
      });
      setQtyKg("1.000");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function cancelReservation(resId: number) {
    setError("");
    const notes = (cancelNotes[resId] ?? "").trim();
    if (notes.length < 2) return setError("Cancel notes are required.");
    if (!confirm("Cancel this reservation?")) return;

    setBusy(true);
    try {
      await apiPost(`/reservations/${resId}/cancel`, { notes });
      setCancelNotes((prev) => {
        const next = { ...prev };
        delete next[resId];
        return next;
      });
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Reservations</h1>
          <Link className="text-sm underline" href="/">Ops Index</Link>
        </div>

        {error ? (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        ) : null}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          {/* Create */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Create Reservation</div>
            <div className="text-sm text-gray-600 mt-1">Soft allocation. Reduces sellable quantity.</div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-sm font-medium">Search lot</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2"
                  value={lotSearch}
                  onChange={(e) => setLotSearch(e.target.value)}
                  placeholder="lot code or item…"
                />
              </div>

              <div>
                <label className="text-sm font-medium">Lot (available only)</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={selectedLotId}
                  onChange={(e) => setSelectedLotId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {filteredLots.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.lot_code} — {l.item_name} (avail {fmtKg(l.available_qty_kg)} kg)
                    </option>
                  ))}
                </select>

                {selectedLot ? (
                  <div className="mt-2 text-xs text-gray-700 rounded-lg border bg-gray-50 p-2">
                    <div>
                      <span className="font-medium">State:</span> {selectedLot.state}
                    </div>
                    <div className="grid grid-cols-3 gap-2 mt-1">
                      <div>
                        <div className="text-gray-600">Received</div>
                        <div className="font-mono">{fmtKg(selectedLot.received_qty_kg)} kg</div>
                      </div>
                      <div>
                        <div className="text-gray-600">Available</div>
                        <div className="font-mono">{fmtKg(selectedLot.available_qty_kg)} kg</div>
                      </div>
                      <div>
                        <div className="text-gray-600">Reserved</div>
                        <div className="font-mono">{fmtKg(selectedReserved)} kg</div>
                      </div>
                    </div>
                    <div className="mt-2">
                      <span className="text-gray-600">Reservable:</span> <span className="font-mono">{fmtKg(selectedReservable)} kg</span>
                    </div>
                  </div>
                ) : null}
              </div>

              <div>
                <label className="text-sm font-medium">Customer</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={selectedCustomerId}
                  onChange={(e) => setSelectedCustomerId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium">Quantity (kg)</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2 font-mono"
                  value={qtyKg}
                  onChange={(e) => setQtyKg(e.target.value)}
                  inputMode="decimal"
                />
              </div>

              <button
                className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
                disabled={busy}
                onClick={createReservation}
              >
                {busy ? "Saving…" : "Create Reservation"}
              </button>
            </div>
          </div>

          {/* List */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Current Reservations</div>
            <div className="text-sm text-gray-600 mt-1">Cancel requires notes (audited as lot event).</div>

            <div className="mt-4 overflow-auto max-h-[640px]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left border-b">
                    <th className="py-2 pr-2">Lot</th>
                    <th className="py-2 pr-2">Customer</th>
                    <th className="py-2 pr-2">Qty (kg)</th>
                    <th className="py-2 pr-2">Notes</th>
                    <th className="py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {reservations.length === 0 ? (
                    <tr>
                      <td className="py-3 text-gray-600" colSpan={6}>
                        No reservations.
                      </td>
                    </tr>
                  ) : (
                    reservations.map((r) => (
                      <tr key={r.id} className="border-b align-top">
                        <td className="py-2 pr-2">
                          <div className="font-mono">{r.lot_code}</div>
                          <div className="text-xs text-gray-600">state: {r.lot_state}</div>
                        </td>
                        <td className="py-2 pr-2">{r.customer_name}</td>
                        <td className="py-2 pr-2 font-mono">{fmtKg(r.quantity_kg)}</td>
                        <td className="py-2 pr-2">
                          <input
                            className="w-full border rounded-lg p-2"
                            value={cancelNotes[r.id] ?? ""}
                            onChange={(e) =>
                              setCancelNotes((prev) => ({ ...prev, [r.id]: e.target.value }))
                            }
                            placeholder="Required to cancel…"
                          />
                        </td>
                        <td className="py-2">
                          <button
                            className="rounded-lg border px-3 py-2 disabled:opacity-50"
                            disabled={busy}
                            onClick={() => cancelReservation(r.id)}
                          >
                            Cancel
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
