"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";

type LotRow = {
  id: number;
  lot_code: string;
  state: string;
  item_name: string;
  received_at?: string;
};

type QACheckRequest = {
  lot_id: number;
  check_type: string;
  mode: "full" | "partial";
  passed?: boolean | null;
  pass_qty_kg?: string | null;
  fail_qty_kg?: string | null;
  notes?: string | null;
  performed_by: number;
};

type QACheckResponse = {
  qa_check_id: number;
  quarantined: boolean;
  lot_event_id?: number | null;
};

type QACheckRow = {
  id: number;
  check_type: string;
  passed: boolean;
  notes: string | null;
  performed_at: string;
};

type LotEventRow = {
  id: number;
  event_type: string;
  reason: string | null;
  performed_by: number;
  performed_at: string;
};

export default function QAPage() {
  const [lots, setLots] = useState<LotRow[]>([]);
  const [quarantinedLots, setQuarantinedLots] = useState<LotRow[]>([]);

  const [search, setSearch] = useState("");
  const [lotId, setLotId] = useState<number | "">("");

  const [checkType, setCheckType] = useState("visual");
  const [mode, setMode] = useState<"full" | "partial">("full");
  const [passed, setPassed] = useState(true);
  const [passKg, setPassKg] = useState("");
  const [failKg, setFailKg] = useState("");
  const [notes, setNotes] = useState("");
  const [performedBy, setPerformedBy] = useState("1");

  const [history, setHistory] = useState<QACheckRow[]>([]);
  const [events, setEvents] = useState<LotEventRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<QACheckResponse | null>(null);

  async function refreshLots() {
    const [rows, qrows] = await Promise.all([
      apiGet<any[]>("/lots?limit=700"),
      apiGet<any[]>("/lots/quarantined?limit=300"),
    ]);

    setLots(
      rows.map((r) => ({
        id: r.id,
        lot_code: r.lot_code,
        state: r.state,
        item_name: r.item_name,
        received_at: r.received_at,
      }))
    );

    setQuarantinedLots(
      qrows.map((r) => ({
        id: r.id,
        lot_code: r.lot_code,
        state: r.state,
        item_name: r.item_name,
        received_at: r.received_at,
      }))
    );
  }

  useEffect(() => {
    refreshLots().catch((e) => setError(String(e)));
  }, []);

  const filteredLots = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return lots;
    return lots.filter(
      (l) =>
        l.lot_code.toLowerCase().includes(q) ||
        l.item_name.toLowerCase().includes(q) ||
        l.state.toLowerCase().includes(q)
    );
  }, [lots, search]);

  const selectedLot = useMemo(
    () => lots.find((l) => l.id === lotId) || quarantinedLots.find((l) => l.id === lotId) || null,
    [lots, quarantinedLots, lotId]
  );

  async function loadHistory(id: number) {
    setLoadingHistory(true);
    try {
      const rows = await apiGet<QACheckRow[]>(`/qa/checks/by-lot/${id}`);
      setHistory(rows);
    } finally {
      setLoadingHistory(false);
    }
  }

  async function loadEvents(id: number) {
    setLoadingEvents(true);
    try {
      const rows = await apiGet<LotEventRow[]>(`/lots/${id}/events?limit=200`);
      setEvents(rows);
    } finally {
      setLoadingEvents(false);
    }
  }

  useEffect(() => {
    setHistory([]);
    setEvents([]);
    setResult(null);
    setError("");
    if (typeof lotId === "number") {
      loadHistory(lotId).catch((e) => setError(String(e)));
      loadEvents(lotId).catch((e) => setError(String(e)));
    }
  }, [lotId]);

  async function submit() {
    setError("");
    setResult(null);

    if (typeof lotId !== "number") {
      setError("Select a lot.");
      return;
    }
    if (checkType.trim().length < 2) {
      setError("Enter a check type.");
      return;
    }

    if (mode === "partial") {
      if (!passKg && !failKg) {
        setError("Partial mode requires pass qty and/or fail qty.");
        return;
      }
    }

    setBusy(true);
    try {
      const payload: any = {
        lot_id: lotId,
        check_type: checkType.trim(),
        notes: notes.trim() ? notes.trim() : null,
        performed_by: Number(performedBy),
        mode,
      };

      if (mode === "full") {
        payload.passed = passed;
      } else {
        payload.pass_qty_kg = Number(passKg) || 0;
        payload.fail_qty_kg = Number(failKg) || 0;
      }

      const resp = await apiPost<QACheckResponse>("/qa/checks", payload);
      setResult(resp);
      setNotes("");
      setPassKg("");
      setFailKg("");

      await refreshLots();
      await loadHistory(lotId);
      await loadEvents(lotId);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const isQuarantined = selectedLot?.state === "quarantined";

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">QA</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
          {/* Left: Quarantined list */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">Quarantined Lots</div>
            <div className="text-sm text-gray-600 mt-1">Quick view for safety holds</div>
            <div className="mt-3 space-y-2 max-h-[520px] overflow-auto">
              {quarantinedLots.length === 0 ? (
                <div className="text-sm text-gray-600">None.</div>
              ) : (
                quarantinedLots.map((l) => (
                  <button
                    key={l.id}
                    className="w-full text-left rounded-lg border p-2 hover:bg-gray-50"
                    onClick={() => setLotId(l.id)}
                    type="button"
                  >
                    <div className="font-mono text-sm">{l.lot_code}</div>
                    <div className="text-xs text-gray-600">{l.item_name}</div>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Middle: QA entry */}
          <div className="rounded-xl border p-4">
            <div className="font-medium">QA Check Entry</div>
            <div className="text-sm text-gray-600 mt-1">Fail → quarantines the lot</div>

            <div className="mt-4 space-y-3">
              <div>
                <label className="text-sm font-medium">Search lots</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="lot code / item / state…"
                />
              </div>

              <div>
                <label className="text-sm font-medium">Lot</label>
                <select
                  className="mt-1 w-full border rounded-lg p-2"
                  value={lotId}
                  onChange={(e) => setLotId(e.target.value ? Number(e.target.value) : "")}
                >
                  <option value="">Select a lot…</option>
                  {filteredLots.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.lot_code} — {l.item_name} — {l.state}
                    </option>
                  ))}
                </select>
              </div>

              {selectedLot && (
                <div className={`rounded-xl border p-3 ${isQuarantined ? "bg-red-50 border-red-300" : "bg-gray-50"}`}>
                  <div className="text-sm font-medium">Status</div>
                  <div className="mt-1 text-sm">
                    <span className="font-mono">{selectedLot.lot_code}</span> — {selectedLot.item_name}
                  </div>
                  <div className="text-sm">
                    State:{" "}
                    <span className={`font-medium ${isQuarantined ? "text-red-700" : ""}`}>
                      {selectedLot.state}
                    </span>
                  </div>
                  {isQuarantined && (
                    <div className="text-xs text-red-800 mt-1">
                      Quarantined lots cannot be released or sold.
                    </div>
                  )}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2">
                  <label className="text-sm font-medium">Check Type</label>
                  <input
                    className="mt-1 w-full border rounded-lg p-2"
                    value={checkType}
                    onChange={(e) => setCheckType(e.target.value)}
                    placeholder="visual / temp / micro…"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">Performed By</label>
                  <input
                    className="mt-1 w-full border rounded-lg p-2"
                    value={performedBy}
                    onChange={(e) => setPerformedBy(e.target.value)}
                    inputMode="numeric"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium">Mode</label>
                <select className="mt-1 w-full border rounded-lg p-2" value={mode} onChange={(e) => setMode(e.target.value as any)}>
                  <option value="full">Full (pass/fail)</option>
                  <option value="partial">Partial (split pass + fail)</option>
                </select>
              </div>

              {mode === "full" && (
                <div>
                  <label className="text-sm font-medium">Result</label>
                  <select
                    className="mt-1 w-full border rounded-lg p-2"
                    value={passed ? "pass" : "fail"}
                    onChange={(e) => setPassed(e.target.value === "pass")}
                  >
                    <option value="pass">Pass</option>
                    <option value="fail">Fail (quarantine)</option>
                  </select>
                </div>
              )}

              {mode === "partial" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-sm font-medium">Pass (kg)</label>
                    <input className="mt-1 w-full border rounded-lg p-2" value={passKg} onChange={(e) => setPassKg(e.target.value)} inputMode="decimal" />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Fail (kg)</label>
                    <input className="mt-1 w-full border rounded-lg p-2" value={failKg} onChange={(e) => setFailKg(e.target.value)} inputMode="decimal" />
                  </div>
                </div>
              )}

              <div>
                <label className="text-sm font-medium">Notes</label>
                <input
                  className="mt-1 w-full border rounded-lg p-2"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="optional"
                />
              </div>

              <button
                className={`w-full rounded-lg p-2 text-white disabled:opacity-50 ${
                  mode === "partial" ? "bg-blue-600" : passed ? "bg-black" : "bg-red-600"
                }`}
                disabled={busy || typeof lotId !== "number" || checkType.trim().length < 2}
                onClick={submit}
              >
                {busy
                  ? "Saving…"
                  : mode === "partial"
                  ? "Submit Partial Split"
                  : passed
                  ? "Submit QA Pass"
                  : "Submit QA Fail (Quarantine)"}
              </button>

              {result && (
                <div className="rounded-xl border border-green-300 bg-green-50 p-3 text-sm text-green-900">
                  <div className="font-medium">Saved</div>
                  <div>qa_check_id: {result.qa_check_id}</div>
                  <div>quarantined: {String(result.quarantined)}</div>
                  {result.lot_event_id ? <div>lot_event_id: {result.lot_event_id}</div> : null}
                </div>
              )}

              {error && (
                <div className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 whitespace-pre-wrap">
                  {error}
                </div>
              )}
            </div>
          </div>

          <div className="space-y-4">
            {/* QA history */}
            <div className="rounded-xl border p-4">
              <div className="font-medium">QA History</div>
              <div className="text-sm text-gray-600 mt-1">Checks for selected lot</div>

              <div className="mt-3 space-y-2 max-h-[260px] overflow-auto">
                {typeof lotId !== "number" ? (
                  <div className="text-sm text-gray-600">Select a lot to view history.</div>
                ) : loadingHistory ? (
                  <div className="text-sm text-gray-600">Loading…</div>
                ) : history.length === 0 ? (
                  <div className="text-sm text-gray-600">No checks yet.</div>
                ) : (
                  history.map((h) => (
                    <div key={h.id} className="rounded-lg border p-2">
                      <div className="flex justify-between gap-2">
                        <div className="text-sm font-medium">{h.check_type}</div>
                        <div className={`text-xs font-medium ${h.passed ? "text-green-700" : "text-red-700"}`}>
                          {h.passed ? "PASS" : "FAIL"}
                        </div>
                      </div>
                      <div className="text-xs text-gray-600 mt-1">{new Date(h.performed_at).toLocaleString()}</div>
                      {h.notes ? <div className="text-sm mt-1">{h.notes}</div> : null}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Lot events */}
            <div className="rounded-xl border p-4">
              <div className="font-medium">Lot Events</div>
              <div className="text-sm text-gray-600 mt-1">Audit trail for selected lot</div>

              <div className="mt-3 space-y-2 max-h-[260px] overflow-auto">
                {typeof lotId !== "number" ? (
                  <div className="text-sm text-gray-600">Select a lot to view events.</div>
                ) : loadingEvents ? (
                  <div className="text-sm text-gray-600">Loading…</div>
                ) : events.length === 0 ? (
                  <div className="text-sm text-gray-600">No events yet.</div>
                ) : (
                  events.map((e) => (
                    <div key={e.id} className="rounded-lg border p-2">
                      <div className="flex justify-between gap-2">
                        <div className="text-sm font-medium">{e.event_type}</div>
                        <div className="text-xs text-gray-600">{new Date(e.performed_at).toLocaleString()}</div>
                      </div>
                      <div className="text-xs text-gray-600 mt-1">performed_by: {e.performed_by}</div>
                      {e.reason ? <div className="text-sm mt-1">{e.reason}</div> : null}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
