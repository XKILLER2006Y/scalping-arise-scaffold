"use client";
import { useState } from "react";
import { api } from "../lib/api";

function Card({ title, children }: any) {
  return (<div style={{ border: "1px solid #222", borderRadius: 8, padding: 12, marginBottom: 12, background: "#11141c" }}>
    <h3 style={{ margin: "0 0 8px" }}>{title}</h3>{children}</div>);
}
function Pre({ data }: any) {
  return (<pre style={{ whiteSpace: "pre-wrap", fontSize: 12, maxHeight: 260, overflow: "auto" }}>{JSON.stringify(data, null, 2)}</pre>);
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
  async function fullPipeline() {
    setBusy("pipe");
    try {
      const c1: any = await api.candles("1m", 250);
      const candles = c1.candles;
      const trace: any = await api.trace(candles, candles.slice(-120), candles.slice(-80));
      const bt: any = await api.backtest(candles.slice(-300));
      setOut((o: any) => ({ ...o, pipeline: { trace, backtest: bt } }));
    } catch (e: any) { setOut((o: any) => ({ ...o, pipeline: { error: String(e) } })); }
    setBusy("");
  }
  return (<main style={{ padding: 20, maxWidth: 1100, margin: "0 auto", fontFamily: "monospace" }}>
    <h1>Scalping Arise — full scaffold (Phases 1-10)</h1>
    <p style={{ color: "#9aa" }}>Backend: {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"} · XAU/USD SPOT vs GC=F FUTURES_PROXY preserved · Analysis only, not financial advice.</p>
    <div>
      <button onClick={() => run("health", api.health)} disabled={!!busy}>Health</button>{" "}
      <button onClick={() => run("mdHealth", api.mdHealth)} disabled={!!busy}>Market-data health</button>{" "}
      <button onClick={() => run("sysHealth", api.sysHealth)} disabled={!!busy}>System health</button>{" "}
      <button onClick={fullPipeline} disabled={!!busy}>{busy === "pipe" ? "Running…" : "Run full pipeline (candles→trace→backtest)"}</button>
    </div>
    <div style={{ marginTop: 12 }}>
      <Card title="Health / System">{out.health ? <Pre data={out.health} /> : null}{out.mdHealth ? <Pre data={out.mdHealth} /> : null}{out.sysHealth ? <Pre data={out.sysHealth} /> : null}</Card>
      <Card title="Pipeline: trace + backtest">{out.pipeline ? <Pre data={out.pipeline} /> : <span style={{ color: "#777" }}>Click full pipeline above.</span>}</Card>
    </div>
  </main>);
}
