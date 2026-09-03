"use client";
import { useEffect, useState } from "react";
export default function Page() {
  const [b, setB] = useState("..."); const [m, setM] = useState("..."); const [t, setT] = useState("...");
  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${base}/api/v1/health`).then(r=>r.json()).then(j=>setB(JSON.stringify(j))).catch(e=>setB("ERR:"+e));
    fetch(`${base}/api/v1/market-data/health`).then(r=>r.json()).then(j=>setM(JSON.stringify(j))).catch(e=>setM("ERR:"+e));
    fetch(`${base}/api/v1/technical-features/health`).then(r=>r.json()).then(j=>setT(JSON.stringify(j))).catch(e=>setT("ERR:"+e));
  }, []);
  return (<main style={{padding:24,fontFamily:"monospace"}}><h1>Scalping Arise — scaffold</h1><p>Backend: {b}</p><p>MarketData: {m}</p><p>TechFeatures: {t}</p><p>Phase 4 extension: PLANNED, not implemented.</p></main>);
}
