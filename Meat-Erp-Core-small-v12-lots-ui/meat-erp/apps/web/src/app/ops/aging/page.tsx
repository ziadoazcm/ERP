"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  ready_at?: string | null;
  aging_started_at?: string | null;
  current_location_id?: number | null;
};

type LocationRow = { id: number; name: string };

export default function AgingPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [locations, setLocations] = useState<LocationRow[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const [lotId, setLotId] = useState<number | "">("");
  const [mode, setMode] = useState<"dry" | "wet">("dry");
  const [days, setDays] = useState("14");
  const [toLocId, setToLocId] = useState<number | "">("");
  const [notes, setNotes] = useState("");

  const [showReadyOnly, setShowReadyOnly] = useState(false);
  const [releaseNotesByLot, setReleaseNotesByLot] = useState<Record<number, string>>({});

  async function refresh() {
    const [l, locs] = await Promise.all([
      apiGet<any[]>("/lots?limit=800"),
      apiGet<LocationRow[]>("/lookups/locations"),
    ]);

    setLots(
      l.map((r) => ({
        id: r.id,
        lot_code: r.lot_code,
        state: r.state,
        item_name: r.item_name,
        ready_at: r.ready_at ?? null,
        aging_started_at: r.aging_started_at ?? null,
        current_location_id: r.current_location_id ?? null,
      }))
    );
    setLocations(locs);
  }

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, []);

  const eligibleToStart = useMemo(
    () => lots.filter((l) => l.state === "received"),
    [lots]
  );

  const agingLots = useMemo(() => {
    const aging = lots.filter((l) => l.state === "aging");
    if (!showReadyOnly) return aging;
    const now = Date.now();
    return aging.filter((l) => l.ready_at && new Date(l.ready_at).getTime() <= now);
  }, [lots, showReadyOnly]);

  async function startAging() {
    setError("");
    if (typeof lotId !== "number") return setError("Select a lot.");
    if (typeof toLocId !== "number") return setError("Select an aging location.");
    if (!(Number(days) > 0)) return setError("Enter days.");

    setBusy(true);
    try {
      await apiPost("/aging/start", {
        lot_id: lotId,
        to_location_id: toLocId,
        days: Number(days),
        mode,
        notes: notes.trim() ? notes.trim() : null,
      });
      setNotes("");
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function releaseLot(id: number) {
    setError("");
    setBusy(true);
    try {
      const note = (releaseNotesByLot[id] ?? "").trim();
      await apiPost(`/aging/${id}/release`, {
        notes: note ? note : null,
      });

      // clear the note after successful release
      setReleaseNotesByLot((prev) => {
        const copy = { ...prev };
        delete copy[id];
        return copy;
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
          <h1 className="text-xl font-semibold">Aging</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          <div className="rounded-xl border p-4">
            <div className="font-medium">Start Aging</div>
            <div className="text-sm text-gray-600 mt-1">
              Move lot to aging location, set state=aging, compute ready_at.
            </div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-sm font-medium">Lot (received only)</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={lotId}
                  onChange={(e) => setLotId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select…</option>
                  {eligibleToStart.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.lot_code} — {l.item_name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="text-sm font-medium">Mode</label>
                  <select
                    className="mt-1 w-full border rounded-lg p-2"
                    value={mode}
                    onChange={(e) => setMode(e.target.value as any)}
                  >
                    <option value="dry">Dry</option>
                    <option value="wet">Wet</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Days</label>
                  <input
                    className="mt-1 w-full border rounded-lg p-2"
                    value={days}
                    onChange={(e) => setDays(e.target.value)}
                    inputMode="numeric"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Aging Location</label>
                  <select
                    className="mt-1 w-full border rounded-lg p-2"
                    value={toLocId}
                    onChange={(e) => setToLocId(e.target.value ? Number(e.target.value) : "")}
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

              <button
                className="w-full rounded-lg bg-black text-white p-2 disabled:opacity-50"
                onClick={startAging}
                disabled={busy}
              >
                {busy ? "Saving…" : "Start Aging"}
              </button>
            </div>
          </div>

          <div className="rounded-xl border p-4">
            <div className="font-medium">Currently Aging</div>
            <div className="text-sm text-gray-600 mt-1">
              Supervisor must release (no auto-release).
            </div>
            <div className="mt-3 flex items-center gap-2">
              <input
                id="readyOnly"
                type="checkbox"
                checked={showReadyOnly}
                onChange={(e) => setShowReadyOnly(e.target.checked)}
              />
              <label htmlFor="readyOnly" className="text-sm">
                Show ready-only
              </label>
            </div>

            <div className="mt-4 space-y-2 max-h-[560px] overflow-auto">
              {agingLots.length === 0 ? (
                <div className="text-sm text-gray-600">No lots currently aging.</div>
              ) : (
                agingLots.map((l) => {
                  const ready = l.ready_at ? new Date(l.ready_at).getTime() : null;
                  const now = Date.now();
                  const isReady = ready !== null && ready <= now;

                  return (
                    <div key={l.id} className="rounded-lg border p-3">
                      <div className="flex justify-between gap-3 items-start">
                        <div>
                          <div className="font-mono text-sm">{l.lot_code}</div>
                          <div className="text-xs text-gray-600">{l.item_name}</div>
                          <div className="text-xs text-gray-600 mt-1">
                            ready_at:{" "}
                            {l.ready_at ? new Date(l.ready_at).toLocaleString() : "—"}
                            {"  "}
                            <span className={isReady ? "text-green-700 font-medium" : "text-gray-600"}>
                              {isReady ? "READY" : "NOT READY"}
                            </span>
                          </div>
                        </div>

                        <button
                          className="rounded-lg bg-black text-white px-3 py-2 text-sm disabled:opacity-50"
                          onClick={() => releaseLot(l.id)}
                          disabled={busy}
                          title="Supervisor release"
                        >
                          Release
                        </button>
                      </div>
                      <div className="mt-2">
                        <label className="text-xs text-gray-600">Release notes</label>
                        <input
                          className="mt-1 w-full border rounded-lg p-2 text-sm"
                          value={releaseNotesByLot[l.id] ?? ""}
                          onChange={(e) =>
                            setReleaseNotesByLot((prev) => ({ ...prev, [l.id]: e.target.value }))
                          }
                          placeholder="Optional…"
                        />
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
