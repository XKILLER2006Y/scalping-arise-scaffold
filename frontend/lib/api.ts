const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
async function j<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
export const api = {
  health: () => j("/api/v1/health"),
  // One call: past + live XAU/USD in, BUY/SELL/NO_TRADE out.
  signal: (symbol = "XAU/USD", limit = 250) => j(`/api/v1/signal?symbol=${symbol}&limit=${limit}`),
  // Proof the signals are worth reading: backtest + full validation audit.
  backtest: (candles: any[]) => j("/api/v1/backtest/run", { method: "POST", body: JSON.stringify({ candles, equity: 10000, risk_pct: 1.0 }) }),
  audit: (candles: any[]) => j("/api/v1/validation/full-audit", { method: "POST", body: JSON.stringify({ candles, folds: 2 }) }),
  candles: (tf = "1m", limit = 250) => j(`/api/v1/market-data/candles?symbol=XAU/USD&timeframe=${tf}&limit=${limit}`),
  sysHealth: () => j("/api/v1/system/health"),
  reliability: () => j("/api/v1/system/reliability"),
  forward: () => j("/api/v1/system/forward?limit=20"),
};
