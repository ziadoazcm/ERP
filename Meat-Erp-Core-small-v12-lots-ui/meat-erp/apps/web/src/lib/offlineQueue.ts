export type OfflineActionType = "receiving" | "breakdown" | "sale";

export type OfflineQueuedAction = {
  local_id: string; // unique in browser
  client_txn_id: string;
  action_type: OfflineActionType;
  payload: Record<string, any>;
  created_at: string; // ISO
};

const KEY_QUEUE = "meat_erp_offline_queue_v1";
const KEY_CLIENT_ID = "meat_erp_client_id_v1";

function safeJsonParse<T>(s: string | null, fallback: T): T {
  if (!s) return fallback;
  try {
    return JSON.parse(s) as T;
  } catch {
    return fallback;
  }
}

export function getClientId(): string {
  if (typeof window === "undefined") return "server";
  const existing = window.localStorage.getItem(KEY_CLIENT_ID);
  if (existing) return existing;

  const id = (globalThis.crypto?.randomUUID?.() ?? `client-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  window.localStorage.setItem(KEY_CLIENT_ID, id);
  return id;
}

export function listLocalQueue(): OfflineQueuedAction[] {
  if (typeof window === "undefined") return [];
  return safeJsonParse<OfflineQueuedAction[]>(window.localStorage.getItem(KEY_QUEUE), []);
}

function saveLocalQueue(rows: OfflineQueuedAction[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY_QUEUE, JSON.stringify(rows));
}

export function enqueueLocalAction(action_type: OfflineActionType, payload: Record<string, any>, client_txn_id?: string): OfflineQueuedAction {
  const txn = client_txn_id || (globalThis.crypto?.randomUUID?.() ?? `txn-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const row: OfflineQueuedAction = {
    local_id: globalThis.crypto?.randomUUID?.() ?? `local-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    client_txn_id: txn,
    action_type,
    payload,
    created_at: new Date().toISOString(),
  };
  const cur = listLocalQueue();
  cur.push(row);
  saveLocalQueue(cur);
  return row;
}

export function removeLocalActions(local_ids: string[]) {
  const set = new Set(local_ids);
  const cur = listLocalQueue().filter((r) => !set.has(r.local_id));
  saveLocalQueue(cur);
}

export function clearLocalQueue() {
  saveLocalQueue([]);
}

export function groupByTxn(rows: OfflineQueuedAction[]): Record<string, OfflineQueuedAction[]> {
  const out: Record<string, OfflineQueuedAction[]> = {};
  for (const r of rows) {
    (out[r.client_txn_id] ||= []).push(r);
  }
  return out;
}
