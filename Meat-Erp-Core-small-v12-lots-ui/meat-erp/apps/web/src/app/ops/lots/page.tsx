"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  current_location_id: number | null;
  received_at: string;
  ready_at?: string | null;
  expires_at?: string | null;
  received_qty_kg: number;
  available_qty_kg: number;
  reserved_qty_kg: number;
  sellable_qty_kg: number;
};

type LocationRow = { id: number; name: string };

export default function LotsPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [locations, setLocations] = useState<LocationRow[]>([]);
  const [error, setError] = useState("");

  const [q, setQ] = useState("");
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [locFilter, setLocFilter] = useState<string>("all");
  const [includeZero, setIncludeZero] = useState(false);

  async function refresh() {
    const [l, locs] = await Promise.all([
      apiGet<LotRow[]>("/lots?limit=1500"),
      apiGet<LocationRow[]>("/lookups/locations"),
    ]);
    setLots(l);
    setLocations(locs);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  const locationName = useMemo(() => {
    const m: Record<number, string> = {};
    for (const x of locations) m[x.id] = x.name;
    return m;
  }, [locations]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return lots
      .filter((l) => {
        if (!includeZero && l.available_qty_kg <= 0.0005 && l.received_qty_kg <= 0.0005) return false;
        return true;
      })
      .filter((l) => {
        if (!qq) return true;
        return l.lot_code.toLowerCase().includes(qq) || l.item_name.toLowerCase().includes(qq);
      })
      .filter((l) => (stateFilter === "all" ? true : l.state === stateFilter))
      .filter((l) => {
        if (locFilter === "all") return true;
        const id = Number(locFilter);
        return (l.current_location_id ?? -1) === id;
      });
  }, [lots, q, stateFilter, locFilter, includeZero]);

  const distinctStates = useMemo(() => {
    const s = new Set<string>();
    for (const l of lots) s.add(l.state);
    return Array.from(s).sort();
  }, [lots]);

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Lots</h1>
          <Link className="text-sm underline" href="/">Ops Index</Link>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <label className="text-sm font-medium">Search</label>
            <input
              className="mt-1 w-full border rounded-lg p-2"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="lot code or item…"
            />
          </div>

          <div>
            <label className="text-sm font-medium">State</label>
            <select
              className="mt-1 w-full border rounded-lg p-2"
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
            >
              <option value="all">All</option>
              {distinctStates.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium">Location</label>
            <select
              className="mt-1 w-full border rounded-lg p-2"
              value={locFilter}
              onChange={(e) => setLocFilter(e.target.value)}
            >
              <option value="all">All</option>
              {locations.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>

          <div className="md:col-span-4 flex items-center gap-2">
            <input
              id="includeZero"
              type="checkbox"
              checked={includeZero}
              onChange={(e) => setIncludeZero(e.target.checked)}
            />
            <label htmlFor="includeZero" className="text-sm">
              Include zero-qty lots
            </label>
            <button className="ml-auto text-sm underline" onClick={() => refresh().catch((e) => setError(String(e)))}>
              Refresh
            </button>
          </div>
        </div>

        <div className="mt-6 overflow-auto rounded-xl border">
          <table className="min-w-[980px] w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-3">Lot</th>
                <th className="text-left p-3">Item</th>
                <th className="text-left p-3">State</th>
                <th className="text-left p-3">Location</th>
                <th className="text-right p-3">Received</th>
                <th className="text-right p-3">Available</th>
                <th className="text-right p-3">Reserved</th>
                <th className="text-right p-3">Sellable</th>
                <th className="text-left p-3">Ready</th>
                <th className="text-left p-3">Expires</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => (
                <tr key={l.id} className="border-t">
                  <td className="p-3 font-mono">
                    <Link className="underline" href={`/ops/lots/${l.id}`}>
                      {l.lot_code}
                    </Link>
                  </td>
                  <td className="p-3">{l.item_name}</td>
                  <td className="p-3">{l.state}</td>
                  <td className="p-3">{l.current_location_id ? (locationName[l.current_location_id] ?? `#${l.current_location_id}`) : "—"}</td>
                  <td className="p-3 text-right font-mono">{l.received_qty_kg.toFixed(3)}</td>
                  <td className="p-3 text-right font-mono">{l.available_qty_kg.toFixed(3)}</td>
                  <td className="p-3 text-right font-mono">{l.reserved_qty_kg.toFixed(3)}</td>
                  <td className="p-3 text-right font-mono">{l.sellable_qty_kg.toFixed(3)}</td>
                  <td className="p-3 text-xs">{l.ready_at ? new Date(l.ready_at).toLocaleString() : "—"}</td>
                  <td className="p-3 text-xs">{l.expires_at ? new Date(l.expires_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
              {filtered.length === 0 ? (
                <tr>
                  <td className="p-6 text-gray-600" colSpan={10}>
                    No lots match your filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  );
}
