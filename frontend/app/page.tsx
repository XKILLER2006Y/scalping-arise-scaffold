"use client";
import { useState } from "react";
import { api } from "../lib/api";

function Card({ title, children }: any) {
  return (<div style={{ border: "1px solid #222", borderRadius: 8, padding: 12, marginBottom: 12, background: "#11141c" }}>
    <h3 style={{ margin: "0 0 8px" }}>{title}</h3>{children}</div>);
}
function Pre({ data }: any) {
  return (<pre style={{ whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 300, overflow: "auto" }}>{JSON.stringify(data, null, 2)}</pre>);
}
export default function Page() {
  const [out, setOut] = useState<any>({});
  const [busy, setBusy] = useState("");
  async function run(key: string, fn: () => Promise<any>) {
    setBusy(key);
    try {
      const v = await fn();
      setOut((o: any) => ({ ...o, [key]: v }));
    }
    catch (e: any) { setOut((o: any) => ({ ...o, [key]: { error: String(e) } })); }
    setBusy("");
  }
  async function stepByStep() {
    setBusy("steps");
    try {
      const c1: any = await api.candles("1m", 250);
      const candles = c1.candles;
      const analysis: any = await api.analysis(candles.slice(-120));
      const feat: any = await api.features(candles.slice(-220), "1m");
      const feats = { ...feat.features, volatility: feat.volatility, rel_volume: feat.features.rel_volume };
      const ev: any = await api.evaluate(analysis, feats, candles[candles.length - 1].close);
      const sig: any = await api.decide(ev.evaluations, feats);
      const pl: any = await api.plan(sig, candles[candles.length - 1].close, feat.features.atr14);
      setOut((o: any) => ({ ...o, steps: { candles: c1.meta, analysis, features: feat, evaluations: ev, signal: sig, plan: pl } }));
    } catch (e: any) { setOut((o: any) => ({ ...o, steps: { error: String(e) } })); }
    setBusy("");
  }
  async function fullPipeline() {
    setBusy("pipe");
    try {
      const c1: any = await api.candles("1m", 250);
      const candles = c1.candles;
      const trace: any = await api.trace(candles, candles.slice(-120), candles.slice(-80));
      const bt: any = await api.backtest(candles.slice(-300));
      const rel: any = await api.reliability();
      setOut((o: any) => ({ ...o, pipeline: { trace, backtest: bt, reliability: rel } }));
    } catch (e: any) { setOut((o: any) => ({ ...o, pipeline: { error: String(e) } })); }
    setBusy("");
  }
  const B = (k: string, label: string, fn: () => Promise<any>) => (
    <button onClick={() => run(k, fn)} disabled={!!busy} style={{ marginRight: 6, marginBottom: 6 }}>{label}</button>
  );
  return (<main style={{ padding: 20, maxWidth: 1100, margin: "0 auto", fontFamily: "monospace" }}>
    <h1>Scalping Arise — full project (Phases 1-10)</h1>
    <p style={{ color: "#9aa" }}>XAU/USD SPOT vs GC=F FUTURES_PROXY preserved · Analysis only, not financial advice.</p>
    <div>
      {B("health", "Health", api.health)}
      {B("mdHealth", "Market-data", api.mdHealth)}
      {B("sysHealth", "System", api.sysHealth)}
      {B("news", "News check", api.news)}
      {B("rel", "Reliability", api.reliability)}
      {B("fwd", "Forward log", api.forward)}
      <button onClick={stepByStep} disabled={!!busy}>Step-by-step (P2→P7)</button>{" "}
      <button onClick={fullPipeline} disabled={!!busy}>{busy === "pipe" ? "Running…" : "Full trace + backtest"}</button>
    </div>
    <div style={{ marginTop: 12 }}>
      <Card title="Status">{["health", "mdHealth", "sysHealth", "news", "rel", "fwd"].map(k => out[k] ? <Pre key={k} data={{ [k]: out[k] }} /> : null)}</Card>
      <Card title="Step-by-step P2→P7">{out.steps ? <Pre data={out.steps} /> : <span style={{ color: "#777" }}>Run step-by-step.</span>}</Card>
      <Card title="Trace + backtest + reliability">{out.pipeline ? <Pre data={out.pipeline} /> : <span style={{ color: "#777" }}>Run full trace.</span>}</Card>
    </div>
  </main>);
}
