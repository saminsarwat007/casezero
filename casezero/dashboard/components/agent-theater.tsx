"use client";

import { useEffect, useState } from "react";
import { accessToken, isRehearsal, streamUrl } from "@/lib/api";

const agents = ["Intake", "Classifier", "Verifier", "Resolver", "Communicator", "Supervisor"];
const rehearsalCalls: Array<[string, string, string]> = [
  ["00:20.02", "intake", "firewall.scan → clean"],
  ["00:21.03", "classifier", "rule pack v3 → High / 5 WD"],
  ["00:22.04", "verifier", "core-banking.verify_claim → PASS"],
  ["00:23.05", "resolver", "kernel ticket → REVERSAL"],
  ["00:24.06", "communicator", "lint_outbound → 6/6 passed"],
];

export function AgentTheater() {
  const [active, setActive] = useState(2);
  const [calls, setCalls] = useState(rehearsalCalls);
  const [mode, setMode] = useState("REHEARSAL");
  useEffect(() => {
    if (isRehearsal()) {
      const timer = window.setInterval(() => setActive((value) => (value + 1) % agents.length), 1400);
      return () => window.clearInterval(timer);
    }
    const controller = new AbortController();
    async function subscribe() {
      const token = await accessToken();
      if (!token) return;
      const response = await fetch(streamUrl(), {
        headers: { Authorization: `Bearer ${token}` },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) return;
      setMode("LIVE SSE");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (!controller.signal.aborted) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const packets = buffer.split("\n\n");
        buffer = packets.pop() ?? "";
        for (const packet of packets) {
          const line = packet.split("\n").find((item) => item.startsWith("data:"));
          if (!line) continue;
          try {
            const event = JSON.parse(line.slice(5)) as { actor?: string; type?: string; payload?: Record<string, unknown> };
            const actor = (event.actor ?? "kernel").replace("agent:", "");
            const index = agents.findIndex((name) => name.toLowerCase() === actor);
            if (index >= 0) setActive(index);
            const detail = event.payload?.tool ? `${String(event.payload.tool)} → ${event.type}` : event.type ?? "event";
            const row: [string, string, string] = [
              new Date().toLocaleTimeString("en-MY", { hour12: false }),
              actor,
              detail,
            ];
            setCalls((current) => [row, ...current].slice(0, 5));
          } catch {}
        }
      }
    }
    void subscribe();
    return () => controller.abort();
  }, []);
  return (
    <div className="theater" aria-label="Agent observability theater">
      <div className="theater-grid" />
      <div className="theater-inner">
        <div className="agent-map">
          {agents.map((agent, index) => (
            <div className={`agent-node ${index === active ? "active" : ""}`} key={agent}>
              <p className="eyebrow mono" style={{ color: "#97a59b" }}>AGENT 0{index + 1}</p>
              <strong>{agent}</strong>
              <div className="mono" style={{ color: "#97a59b", fontSize: 9, marginTop: 7 }}>{index === active ? "EXECUTING" : "READY"}</div>
            </div>
          ))}
        </div>
        <aside className="ticker" aria-label="Recent tool calls">
          <p className="eyebrow mono" style={{ color: "#97a59b" }}>{mode} / tool register</p>
          {calls.map(([at, agent, call], index) => <div className="ticker-item" key={`${agent}-${call}-${index}`}><strong className="mono">{at} / {agent}</strong>{call}</div>)}
        </aside>
      </div>
    </div>
  );
}
