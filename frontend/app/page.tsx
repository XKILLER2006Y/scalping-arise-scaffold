"use client";
import { useState } from "react";
import { api } from "../lib/api";
import { Chart } from "../components/Chart";

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
      const candles = c1?.candles || [];
      if (candles.length === 0) throw new Error("No candles returned from market data");

      const analysis: any = await api.analysis(candles.slice(-120));
      const feat: any = await api.features(candles.slice(-220), "1m");
      const featData = feat?.features || {};
      const feats = { ...featData, volatility: feat?.volatility, rel_volume: featData.rel_volume };
      const closePx = candles[candles.length - 1].close;
      const ev: any = await api.evaluate(analysis, feats, closePx);
      const sig: any = await api.decide(ev?.evaluations || [], feats);
      const pl: any = await api.plan(sig, closePx, featData.atr14);
      
      let exec: any = { status: "skipped" };
      if (pl?.feasible && sig?.action && sig.action !== "NO_TRADE") {
        exec = await api.execute({
          action: sig.action,
          direction: sig.direction,
          entry_price: pl.entry,
          stop_loss: pl.stop,
          take_profit_1: pl.take_profit,
          position_size: pl.lots,
          ...pl
        });
      }
      const port: any = await api.portfolio();
      setOut((o: any) => ({
        ...o,
        steps: { candles: c1?.meta, analysis, features: feat, evaluations: ev, signal: sig, plan: pl, execution: exec, portfolio: port },
        fullCandles: candles,
        signals: [sig]
      }));
    } catch (e: any) { setOut((o: any) => ({ ...o, steps: { error: String(e) } })); }
    setBusy("");
  }
  async function fullPipeline() {
    setBusy("pipe");
    try {
      const c1: any = await api.candles("1m", 250);
      const candles = c1?.candles || [];
      if (candles.length === 0) throw new Error("No candles returned from market data");

      const trace: any = await api.trace(candles, candles.slice(-120), candles.slice(-80));
      const bt: any = await api.backtest(candles.slice(-300));
      const rel: any = await api.reliability();
      setOut((o: any) => ({
        ...o,
        pipeline: { trace, backtest: bt, reliability: rel },
        fullCandles: candles,
        signals: trace?.signal ? [trace.signal] : []
      }));
    } catch (e: any) { setOut((o: any) => ({ ...o, pipeline: { error: String(e) } })); }
    setBusy("");
  }
  const B = (k: string, label: string, fn: () => Promise<any>) => (
    <button onClick={() => run(k, fn)} disabled={!!busy} style={{ marginRight: 6, marginBottom: 6 }}>
      {busy === k ? "Loading…" : label}
    </button>
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
      {B("portfolio", "Paper Portfolio", api.portfolio)}
      <button onClick={stepByStep} disabled={!!busy}>{busy === "steps" ? "Running steps…" : "Step-by-step (P2→P7+Exec)"}</button>{" "}
      <button onClick={fullPipeline} disabled={!!busy}>{busy === "pipe" ? "Running…" : "Full trace + backtest"}</button>
    </div>
    
    {(out.fullCandles && out.fullCandles.length > 0) && (
      <div style={{ marginTop: 24, marginBottom: 24 }}>
        <h3>Interactive Chart</h3>
        <Chart candles={out.fullCandles} signals={out.signals || []} features={out.steps?.features} />
      </div>
    )}

    <div style={{ marginTop: 12 }}>
      <Card title="Status">{["health", "mdHealth", "sysHealth", "news", "rel", "fwd", "portfolio"].map(k => out[k] ? <Pre key={k} data={{ [k]: out[k] }} /> : null)}</Card>
      <Card title="Step-by-step P2→P7+Exec">{out.steps ? <Pre data={out.steps} /> : <span style={{ color: "#777" }}>Run step-by-step.</span>}</Card>
      <Card title="Trace + backtest + reliability">{out.pipeline ? <Pre data={out.pipeline} /> : <span style={{ color: "#777" }}>Run full trace.</span>}</Card>
    </div>
  </main>);
}
