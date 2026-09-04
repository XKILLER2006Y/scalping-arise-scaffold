const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
async function j<T = any>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
export const api = {
  health: () => j("/api/v1/health"),
  mdHealth: () => j("/api/v1/market-data/health"),
  candles: (tf = "1m", limit = 250) => j(`/api/v1/market-data/candles?symbol=XAU/USD&timeframe=${tf}&limit=${limit}`),
  analysis: (candles: any[]) => j("/api/v1/market-analysis", { method: "POST", body: JSON.stringify({ symbol: "XAU/USD", candles }) }),
  features: (candles: any[], tf = "1m") => j(`/api/v1/technical-features?timeframe=${tf}`, { method: "POST", body: JSON.stringify({ symbol: "XAU/USD", candles }) }),
  featuresMtf: (byTf: any) => j("/api/v1/technical-features/mtf", { method: "POST", body: JSON.stringify({ symbol: "XAU/USD", candles_by_timeframe: byTf }) }),
  evaluate: (analysis: any, features: any, close: number) => j("/api/v1/strategy/evaluate", { method: "POST", body: JSON.stringify({ analysis, features, close }) }),
  decide: (evaluations: any[], features: any) => j("/api/v1/signals/decide", { method: "POST", body: JSON.stringify({ evaluations, features }) }),
  plan: (signal: any, entry: number, atr: number) => j("/api/v1/trade-plan", { method: "POST", body: JSON.stringify({ signal, entry, atr, equity: 10000, risk_pct: 1.0, spread: 0.3 }) }),
  trace: (c1: any[], c5: any[], c15: any[]) => j("/api/v1/system/trace", { method: "POST", body: JSON.stringify({ symbol: "XAU/USD", candles_1m: c1, candles_5m: c5, candles_15m: c15 }) }),
  reliability: () => j("/api/v1/system/reliability"),
  forward: () => j("/api/v1/system/forward?limit=20"),
  news: () => j("/api/v1/intelligence/news-check"),
  backtest: (candles: any[]) => j("/api/v1/backtest/run", { method: "POST", body: JSON.stringify({ candles, equity: 10000, risk_pct: 1.0 }) }),
  sysHealth: () => j("/api/v1/system/health"),
  portfolio: () => j("/api/v1/execution/portfolio"),
  execute: (plan: any) => j("/api/v1/execution/trade", { method: "POST", body: JSON.stringify(plan) }),
};
