"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";

type AtRiskRow = {
  lot_id: number;
  lot_code: string;
  item_name: string;
  state: string;
  location_name: string | null;
  ready_at: string | null;
  expires_at: string | null;
  flags: string[];
  days_to_ready: number | null;
  days_to_expiry: number | null;
  available_qty_kg: number;
  reserved_qty_kg: number;
  sellable_qty_kg: number;
};

type StockRow = {
  lot_id: number;
  lot_code: string;
  item_name: string;
  state: string;
  location_name: string | null;
  received_at: string | null;
  ready_at: string | null;
  expires_at: string | null;
  available_qty_kg: number;
  reserved_qty_kg: number;
  sellable_qty_kg: number;
};

function fmtKg(x: number) {
  const n = Number.isFinite(x) ? x : 0;
  return n.toFixed(3);
}

export default function ReportsPage() {
  const [tab, setTab] = useState<"at_risk" | "stock">("at_risk");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [q, setQ] = useState("");

  // At-risk controls
  const [days, setDays] = useState("7");
  const [includeQuarantined, setIncludeQuarantined] = useState(true);
  const [atRiskRows, setAtRiskRows] = useState<AtRiskRow[]>([]);

  // Stock controls
  const [includeZero, setIncludeZero] = useState(false);
  const [stockRows, setStockRows] = useState<StockRow[]>([]);

  async function loadAtRisk() {
    setBusy(true);
    setError("");
    try {
      const d = Math.max(1, Number(days) || 7);
      const res = await apiGet<{ rows: AtRiskRow[] }>(
        `/reports/at-risk?days=${encodeURIComponent(d)}&include_quarantined=${includeQuarantined ? "true" : "false"}`
      );
      setAtRiskRows(res.rows || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadStock() {
    setBusy(true);
    setError("");
    try {
      const res = await apiGet<{ rows: StockRow[] }>(
        `/reports/stock?include_zero=${includeZero ? "true" : "false"}`
      );
      setStockRows(res.rows || []);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // load active tab on mount
    if (tab === "at_risk") loadAtRisk();
    else loadStock();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const qLower = q.trim().toLowerCase();

  const filteredAtRisk = useMemo(() => {
    if (!qLower) return atRiskRows;
    return atRiskRows.filter((r) =>
      r.lot_code.toLowerCase().includes(qLower) || r.item_name.toLowerCase().includes(qLower)
    );
  }, [atRiskRows, qLower]);

  const filteredStock = useMemo(() => {
    if (!qLower) return stockRows;
    return stockRows.filter((r) =>
      r.lot_code.toLowerCase().includes(qLower) || r.item_name.toLowerCase().includes(qLower)
    );
  }, [stockRows, qLower]);

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Reporting</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <div className="mt-6 rounded-xl border p-4">
          <div className="flex flex-col sm:flex-row gap-3 sm:items-end sm:justify-between">
            <div className="flex gap-2">
              <button
                className={`rounded-lg border px-3 py-2 text-sm ${tab === "at_risk" ? "bg-black text-white" : "bg-white"}`}
                onClick={() => setTab("at_risk")}
                disabled={busy}
              >
                At-risk Inventory
              </button>
              <button
                className={`rounded-lg border px-3 py-2 text-sm ${tab === "stock" ? "bg-black text-white" : "bg-white"}`}
                onClick={() => setTab("stock")}
                disabled={busy}
              >
                Stock by Lot
              </button>
            </div>

            <div className="w-full sm:w-80">
              <label className="text-sm font-medium">Search</label>
              <input
                className="mt-1 w-full border rounded-lg p-2"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="lot code or item…"
              />
            </div>
          </div>

          {tab === "at_risk" ? (
            <div className="mt-4">
              <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
                <div>
                  <label className="text-sm font-medium">Days window</label>
                  <input
                    className="mt-1 w-32 border rounded-lg p-2"
                    value={days}
                    onChange={(e) => setDays(e.target.value)}
                    inputMode="numeric"
                  />
                </div>
                <div className="flex items-center gap-2 sm:pb-2">
                  <input
                    id="inclQ"
                    type="checkbox"
                    checked={includeQuarantined}
                    onChange={(e) => setIncludeQuarantined(e.target.checked)}
                  />
                  <label htmlFor="inclQ" className="text-sm">
                    Include quarantined
                  </label>
                </div>
                <button
                  className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                  onClick={loadAtRisk}
                  disabled={busy}
                >
                  {busy ? "Loading…" : "Refresh"}
                </button>
              </div>

              <div className="mt-4 overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left">
                    <tr className="border-b">
                      <th className="py-2 pr-3">Lot</th>
                      <th className="py-2 pr-3">Item</th>
                      <th className="py-2 pr-3">State</th>
                      <th className="py-2 pr-3">Flags</th>
                      <th className="py-2 pr-3">Avail</th>
                      <th className="py-2 pr-3">Resv</th>
                      <th className="py-2 pr-3">Sellable</th>
                      <th className="py-2 pr-3">ready_at</th>
                      <th className="py-2 pr-3">expires_at</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredAtRisk.length === 0 ? (
                      <tr>
                        <td className="py-3 text-gray-600" colSpan={9}>
                          No rows.
                        </td>
                      </tr>
                    ) : (
                      filteredAtRisk.map((r) => (
                        <tr key={r.lot_id} className="border-b">
                          <td className="py-2 pr-3 font-mono">{r.lot_code}</td>
                          <td className="py-2 pr-3">{r.item_name}</td>
                          <td className="py-2 pr-3">{r.state}</td>
                          <td className="py-2 pr-3">
                            <div className="flex flex-wrap gap-1">
                              {r.flags.map((f) => (
                                <span key={f} className="text-xs border rounded px-2 py-0.5">
                                  {f}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.available_qty_kg)}</td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.reserved_qty_kg)}</td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.sellable_qty_kg)}</td>
                          <td className="py-2 pr-3 text-xs text-gray-700">
                            {r.ready_at ? new Date(r.ready_at).toLocaleString() : "—"}
                          </td>
                          <td className="py-2 pr-3 text-xs text-gray-700">
                            {r.expires_at ? new Date(r.expires_at).toLocaleString() : "—"}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
                <div className="flex items-center gap-2 sm:pb-2">
                  <input
                    id="incl0"
                    type="checkbox"
                    checked={includeZero}
                    onChange={(e) => setIncludeZero(e.target.checked)}
                  />
                  <label htmlFor="incl0" className="text-sm">
                    Include zero-qty
                  </label>
                </div>
                <button
                  className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                  onClick={loadStock}
                  disabled={busy}
                >
                  {busy ? "Loading…" : "Refresh"}
                </button>
              </div>

              <div className="mt-4 overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-left">
                    <tr className="border-b">
                      <th className="py-2 pr-3">Lot</th>
                      <th className="py-2 pr-3">Item</th>
                      <th className="py-2 pr-3">State</th>
                      <th className="py-2 pr-3">Location</th>
                      <th className="py-2 pr-3">Avail</th>
                      <th className="py-2 pr-3">Resv</th>
                      <th className="py-2 pr-3">Sellable</th>
                      <th className="py-2 pr-3">ready_at</th>
                      <th className="py-2 pr-3">expires_at</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStock.length === 0 ? (
                      <tr>
                        <td className="py-3 text-gray-600" colSpan={9}>
                          No rows.
                        </td>
                      </tr>
                    ) : (
                      filteredStock.map((r) => (
                        <tr key={r.lot_id} className="border-b">
                          <td className="py-2 pr-3 font-mono">{r.lot_code}</td>
                          <td className="py-2 pr-3">{r.item_name}</td>
                          <td className="py-2 pr-3">{r.state}</td>
                          <td className="py-2 pr-3">{r.location_name ?? "—"}</td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.available_qty_kg)}</td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.reserved_qty_kg)}</td>
                          <td className="py-2 pr-3 font-mono">{fmtKg(r.sellable_qty_kg)}</td>
                          <td className="py-2 pr-3 text-xs text-gray-700">
                            {r.ready_at ? new Date(r.ready_at).toLocaleString() : "—"}
                          </td>
                          <td className="py-2 pr-3 text-xs text-gray-700">
                            {r.expires_at ? new Date(r.expires_at).toLocaleString() : "—"}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
