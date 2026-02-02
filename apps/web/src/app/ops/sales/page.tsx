export default function SalesPlaceholder() {
  return (
    <main className="min-h-screen p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-baseline justify-between">
          <h1 className="text-xl font-semibold">Sales</h1>
          <a className="text-sm underline" href="/">Ops Index</a>
        </div>

        <div className="mt-6 rounded-xl border p-4">
          <div className="font-medium">Sales UI is paused</div>
          <div className="text-sm text-gray-600 mt-1">
            Sales backend is implemented and hard-gated (released + ready_at + reservations + availability). The UI will be added later.
          </div>
          <div className="text-sm mt-3">
            If you created sales while offline, use <a className="underline" href="/ops/offline">Offline Sync</a> to push/apply and review conflicts.
          </div>
        </div>
      </div>
    </main>
  );
}
