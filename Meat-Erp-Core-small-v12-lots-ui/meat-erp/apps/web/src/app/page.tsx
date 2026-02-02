"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listLocalQueue } from "@/lib/offlineQueue";

export default function Home() {
  const [offlineCount, setOfflineCount] = useState<number>(0);

  useEffect(() => {
    // initial load
    setOfflineCount(listLocalQueue().length);

    // keep in sync across tabs/windows
    const onStorage = (e: StorageEvent) => {
      if (e.key && e.key.includes("meat_erp_offline_queue")) {
        setOfflineCount(listLocalQueue().length);
      }
    };
    window.addEventListener("storage", onStorage);

    // best-effort refresh when returning to tab
    const onFocus = () => setOfflineCount(listLocalQueue().length);
    window.addEventListener("focus", onFocus);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const tiles = [
    { href: "/ops/lots", title: "Lots", desc: "Browse lots, movements, events, genealogy" },
    { href: "/ops/receiving", title: "Receiving", desc: "Create lot from scale weight (offline allowed)" },
    { href: "/ops/breakdown", title: "Breakdown", desc: "1 input → many outputs (offline allowed)" },
    { href: "/ops/rework", title: "Rework / Regrade", desc: "Consume lot → new lot (traceable)" },
    { href: "/ops/reservations", title: "Reservations", desc: "Soft allocation for restaurants" },
    { href: "/ops/sales", title: "Sales", desc: "Sell by lot (offline allowed)" },
    { href: "/ops/aging", title: "Aging", desc: "Start aging + supervisor release (online only)" },
    { href: "/ops/qa", title: "QA", desc: "Checks + quarantine (online only)" },
    { href: "/ops/mixing", title: "Mixing", desc: "Sausage/burger mixing (online only)" },
    { href: "/ops/offline", title: "Offline Sync", desc: "Queue + apply + conflicts (Policy B)", badge: offlineCount > 0 ? `Offline queue: ${offlineCount}` : null },
    { href: "/ops/recall", title: "Recall", desc: "Forward/back trace + customers" },
    { href: "/ops/reports", title: "Reporting", desc: "At-risk inventory + stock by lot" },
  ];

  return (
    <main className="min-h-screen p-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-2xl font-semibold">Meat ERP v2.5</h1>
        <p className="text-sm text-gray-600 mt-1">Ops Console</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
          {tiles.map((t) => (
            <Link key={t.href} href={t.href} className="rounded-xl border p-4 hover:bg-gray-50">
              <div className="flex items-start justify-between gap-3">
                <div className="font-medium">{t.title}</div>
                {t.badge ? (
                  <div className="text-xs rounded-full border px-2 py-1 whitespace-nowrap">
                    {t.badge}
                  </div>
                ) : null}
              </div>
              <div className="text-sm text-gray-600 mt-1">{t.desc}</div>
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
