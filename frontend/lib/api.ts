const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
async function j<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
// Minimum effective dose: only what the signal page calls.
export const api = {
  signal: (symbol = "XAU/USD", limit = 250) => j(`/api/v1/signal?symbol=${symbol}&limit=${limit}`),
  sysHealth: () => j("/api/v1/system/health"),
  reliability: () => j("/api/v1/system/reliability"),
  paperStatus: () => j("/api/v1/paper/status"),
  divergence: () => j("/api/v1/paper/divergence?backtest_expectancy_r=0.5"),
  auditLog: () => j("/api/v1/system/audit-log?lines=15"),
};
