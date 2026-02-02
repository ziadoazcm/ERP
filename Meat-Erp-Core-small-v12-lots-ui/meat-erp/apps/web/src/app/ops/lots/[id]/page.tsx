"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { apiGet } from "@/lib/api";

type LotDetail = {
  id: number;
  lot_code: string;
  state: string;
  item_id: number;
  item_name: string;
  supplier_id: number | null;
  supplier_name: string | null;
  location_id: number | null;
  location_name: string | null;
  received_at: string;
  aging_started_at?: string | null;
  ready_at?: string | null;
  released_at?: string | null;
  expires_at?: string | null;
  quantities: {
    received_qty_kg: number;
    available_qty_kg: number;
    reserved_qty_kg: number;
    sellable_qty_kg: number;
  };
  movements: Array<{
    id: number;
    move_type: string;
    quantity_kg: number;
    moved_at: string;
    from_location_name: string | null;
    to_location_name: string | null;
  }>;
  events: Array<{
    id: number;
    event_type: string;
    notes: string | null;
    performed_by: number;
    performed_at: string;
  }>;
  reservations: Array<{
    id: number;
    customer_name: string;
    quantity_kg: number;
    reserved_at: string;
  }>;
  sales: Array<{
    sale_id: number;
    sold_at: string;
    customer_name: string | null;
    quantity_kg: number;
  }>;
  genealogy: {
    as_input: Array<{
      production_order_id: number;
      process_type: string;
      is_rework: boolean;
      started_at: string | null;
      outputs: Array<{ lot_id: number; lot_code: string; quantity_kg: number }>;
    }>;
    as_output: Array<{
      production_order_id: number;
      process_type: string;
      is_rework: boolean;
      started_at: string | null;
      inputs: Array<{ lot_id: number; lot_code: string; quantity_kg: number }>;
    }>;
  };
};

export default function LotDetailPage({ params }: { params: { id: string } }) {
  const lotId = Number(params.id);
  const [data, setData] = useState<LotDetail | null>(null);
  const [tab, setTab] = useState<"movements" | "events" | "reservations" | "sales" | "genealogy">("movements");
  const [error, setError] = useState("");

  async function load() {
    const d = await apiGet<LotDetail>(`/lots/${lotId}`);
    setData(d);
  }

  useEffect(() => {
    if (!Number.isFinite(lotId)) return;
    load().catch((e) => setError(String(e)));
  }, [lotId]);

  const headerRows = useMemo(() => {
    if (!data) return [];
    return [
      { k: "State", v: data.state },
      { k: "Item", v: data.item_name },
      { k: "Supplier", v: data.supplier_name ?? "—" },
      { k: "Location", v: data.location_name ?? "—" },
      { k: "Received at", v: new Date(data.received_at).toLocaleString() },
      { k: "Aging started", v: data.aging_started_at ? new Date(data.aging_started_at).toLocaleString() : "—" },
      { k: "Ready at", v: data.ready_at ? new Date(data.ready_at).toLocaleString() : "—" },
      { k: "Released at", v: data.released_at ? new Date(data.released_at).toLocaleString() : "—" },
      { k: "Expires at", v: data.expires_at ? new Date(data.expires_at).toLocaleString() : "—" },
    ];
  }, [data]);

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-5xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">
            Lot Detail <span className="font-mono">#{Number.isFinite(lotId) ? lotId : "?"}</span>
          </h1>
          <div className="flex gap-3 text-sm">
            <Link className="underline" href="/ops/lots">Lots</Link>
            <Link className="underline" href="/">Ops Index</Link>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        {!data ? (
          <div className="mt-6 text-sm text-gray-600">Loading…</div>
        ) : (
          <>
            <div className="mt-6 rounded-xl border p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-lg">{data.lot_code}</div>
                  <div className="text-sm text-gray-600">{data.item_name}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-600">Sellable</div>
                  <div className="font-mono text-lg">{data.quantities.sellable_qty_kg.toFixed(3)} kg</div>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-gray-600">Received</div>
                  <div className="font-mono">{data.quantities.received_qty_kg.toFixed(3)} kg</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-gray-600">Available</div>
                  <div className="font-mono">{data.quantities.available_qty_kg.toFixed(3)} kg</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-gray-600">Reserved</div>
                  <div className="font-mono">{data.quantities.reserved_qty_kg.toFixed(3)} kg</div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-gray-600">Sellable</div>
                  <div className="font-mono">{data.quantities.sellable_qty_kg.toFixed(3)} kg</div>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {headerRows.map((r) => (
                  <div key={r.k} className="text-sm">
                    <div className="text-xs text-gray-600">{r.k}</div>
                    <div className="mt-0.5">{r.v}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-6 flex flex-wrap gap-2">
              {(
                [
                  ["movements", "Movements"],
                  ["events", "Lot Events"],
                  ["reservations", "Reservations"],
                  ["sales", "Sales"],
                  ["genealogy", "Genealogy"],
                ] as const
              ).map(([k, label]) => (
                <button
                  key={k}
                  className={`rounded-lg border px-3 py-2 text-sm ${tab === k ? "bg-gray-100" : "bg-white"}`}
                  onClick={() => setTab(k)}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-3 rounded-xl border p-4">
              {tab === "movements" && (
                <div className="space-y-2">
                  {data.movements.length === 0 ? (
                    <div className="text-sm text-gray-600">No movements.</div>
                  ) : (
                    data.movements.map((m) => (
                      <div key={m.id} className="rounded-lg border p-3">
                        <div className="flex justify-between gap-3">
                          <div className="font-mono text-sm">{m.move_type}</div>
                          <div className="font-mono text-sm">{m.quantity_kg.toFixed(3)} kg</div>
                        </div>
                        <div className="text-xs text-gray-600 mt-1">
                          {new Date(m.moved_at).toLocaleString()} — {m.from_location_name ?? "—"} → {m.to_location_name ?? "—"}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {tab === "events" && (
                <div className="space-y-2">
                  {data.events.length === 0 ? (
                    <div className="text-sm text-gray-600">No events.</div>
                  ) : (
                    data.events.map((e) => (
                      <div key={e.id} className="rounded-lg border p-3">
                        <div className="flex justify-between gap-3">
                          <div className="font-medium">{e.event_type}</div>
                          <div className="text-xs text-gray-600">{new Date(e.performed_at).toLocaleString()}</div>
                        </div>
                        {e.notes ? <div className="text-sm mt-2 whitespace-pre-wrap">{e.notes}</div> : null}
                        <div className="text-xs text-gray-600 mt-2">performed_by: {e.performed_by}</div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {tab === "reservations" && (
                <div className="space-y-2">
                  {data.reservations.length === 0 ? (
                    <div className="text-sm text-gray-600">No reservations.</div>
                  ) : (
                    data.reservations.map((r) => (
                      <div key={r.id} className="rounded-lg border p-3">
                        <div className="flex justify-between gap-3">
                          <div className="font-medium">{r.customer_name}</div>
                          <div className="font-mono">{r.quantity_kg.toFixed(3)} kg</div>
                        </div>
                        <div className="text-xs text-gray-600 mt-1">{new Date(r.reserved_at).toLocaleString()}</div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {tab === "sales" && (
                <div className="space-y-2">
                  {data.sales.length === 0 ? (
                    <div className="text-sm text-gray-600">No sales.</div>
                  ) : (
                    data.sales.map((s) => (
                      <div key={`${s.sale_id}-${s.sold_at}`} className="rounded-lg border p-3">
                        <div className="flex justify-between gap-3">
                          <div className="font-medium">Sale #{s.sale_id}</div>
                          <div className="font-mono">{s.quantity_kg.toFixed(3)} kg</div>
                        </div>
                        <div className="text-xs text-gray-600 mt-1">
                          {new Date(s.sold_at).toLocaleString()} — {s.customer_name ?? "Retail"}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {tab === "genealogy" && (
                <div className="space-y-4">
                  <div>
                    <div className="font-medium">Used as input</div>
                    <div className="space-y-2 mt-2">
                      {data.genealogy.as_input.length === 0 ? (
                        <div className="text-sm text-gray-600">No production orders consuming this lot.</div>
                      ) : (
                        data.genealogy.as_input.map((po) => (
                          <div key={po.production_order_id} className="rounded-lg border p-3">
                            <div className="flex justify-between gap-3">
                              <div>
                                <div className="font-medium">{po.process_type} #{po.production_order_id}</div>
                                <div className="text-xs text-gray-600">is_rework: {String(po.is_rework)}</div>
                              </div>
                              <div className="text-xs text-gray-600">
                                {po.started_at ? new Date(po.started_at).toLocaleString() : "—"}
                              </div>
                            </div>
                            <div className="mt-2 text-sm">
                              Outputs:
                              <ul className="list-disc ml-5 mt-1">
                                {po.outputs.map((o) => (
                                  <li key={o.lot_id}>
                                    <Link className="underline font-mono" href={`/ops/lots/${o.lot_id}`}>{o.lot_code}</Link> — {o.quantity_kg.toFixed(3)} kg
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="font-medium">Created as output</div>
                    <div className="space-y-2 mt-2">
                      {data.genealogy.as_output.length === 0 ? (
                        <div className="text-sm text-gray-600">No production orders produced this lot.</div>
                      ) : (
                        data.genealogy.as_output.map((po) => (
                          <div key={po.production_order_id} className="rounded-lg border p-3">
                            <div className="flex justify-between gap-3">
                              <div>
                                <div className="font-medium">{po.process_type} #{po.production_order_id}</div>
                                <div className="text-xs text-gray-600">is_rework: {String(po.is_rework)}</div>
                              </div>
                              <div className="text-xs text-gray-600">
                                {po.started_at ? new Date(po.started_at).toLocaleString() : "—"}
                              </div>
                            </div>
                            <div className="mt-2 text-sm">
                              Inputs:
                              <ul className="list-disc ml-5 mt-1">
                                {po.inputs.map((i) => (
                                  <li key={i.lot_id}>
                                    <Link className="underline font-mono" href={`/ops/lots/${i.lot_id}`}>{i.lot_code}</Link> — {i.quantity_kg.toFixed(3)} kg
                                  </li>
                                ))}
                              </ul>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
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
