"use client";
import { useState } from "react";
import { api } from "../lib/api";

function Card({ title, children }: any) {
  return (<div style={{ border: "1px solid #222", borderRadius: 8, padding: 12, marginBottom: 12, background: "#11141c" }}>
    <h3 style={{ margin: "0 0 8px" }}>{title}</h3>{children}</div>);
}
function Pre({ data }: any) {
  return (<pre style={{ whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 320, overflow: "auto" }}>{JSON.stringify(data, null, 2)}</pre>);
}
const COLORS: any = { BUY: "#1db954", SELL: "#e5484d", NO_TRADE: "#888" };
export default function Page() {
  const [sig, setSig] = useState<any>(null);
  const [hist, setHist] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [extra, setExtra] = useState<any>({});
  async function getSignal() {
    setBusy(true);
    try {
      const s: any = await api.signal();
      setSig(s);
      setHist((h) => [{ t: new Date().toLocaleTimeString(), action: s.signal?.action, conf: s.signal?.confidence, px: s.trade_plan?.entry }, ...h].slice(0, 20));
    } catch (e: any) { setSig({ error: String(e) }); }
    setBusy(false);
  }
  async function run(key: string, fn: () => Promise<any>) {
    try {
      const v = await fn();
      setExtra((o: any) => ({ ...o, [key]: v }));
    }
    catch (e: any) { setExtra((o: any) => ({ ...o, [key]: { error: String(e) } })); }
  }
  const action = sig?.signal?.action || "—";
  return (<main style={{ padding: 20, maxWidth: 900, margin: "0 auto", fontFamily: "monospace" }}>
    <h1>XAU/USD Signal Bot</h1>
    <p style={{ color: "#9aa" }}>Past + live market data in — BUY / SELL / NO_TRADE out. Signals only, no execution. Not financial advice.</p>
    <button onClick={getSignal} disabled={busy} style={{ fontSize: 18, padding: "10px 24px" }}>
      {busy ? "Analysing…" : "Get Signal"}
    </button>{" "}
    <button onClick={() => run("health", api.sysHealth)}>System</button>{" "}
    <button onClick={() => run("rel", api.reliability)}>Reliability</button>
    {sig && !sig.error && (
      <div style={{ border: `3px solid ${COLORS[action] || "#888"}`, borderRadius: 12, padding: 16, margin: "16px 0", background: "#11141c" }}>
        <div style={{ fontSize: 42, fontWeight: "bold", color: COLORS[action] || "#fff" }}>{action}</div>
        <div>Confidence {sig.signal?.confidence} · Quality {sig.signal?.quality} · {sig.signal?.strategy || "no setup"}</div>
        <div>Entry {sig.trade_plan?.entry} · SL {sig.trade_plan?.stop} · TP {sig.trade_plan?.take_profit} · RR {sig.trade_plan?.rr}</div>
        <div style={{ color: "#9aa" }}>{(sig.signal?.reasons || []).join(" · ")}</div>
        <div style={{ color: "#666", fontSize: 12 }}>Session {sig.market?.session} · Regime {sig.market?.regime} · Vol {sig.features_mtf?.timeframes?.["1m"]?.volatility} · {sig.latency_ms}ms</div>
      </div>
    )}
    {sig?.error && <Card title="Error"><Pre data={sig} /></Card>}
    <Card title="Signal history (this session)">{hist.length ? <Pre data={hist} /> : <span style={{ color: "#777" }}>No signals yet.</span>}</Card>
    {extra.health || extra.rel ? <Card title="System"><Pre data={extra} /></Card> : null}
  </main>);
}
