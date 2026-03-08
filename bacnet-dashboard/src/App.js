import { useState, useEffect, useRef, useCallback } from "react";

// ─── Simulated WebSocket data (mirrors real COV notifications) ───────────────
// Replace SIMULATED_MODE = false and point WS_URL to your FastAPI server
const SIMULATED_MODE = false;
const WS_URL = "ws://localhost:8000/ws";

const INITIAL_STATE = {
  "analog-input,0":      { label: "T Indoor",   value: 21.2,  unit: "°C",  type: "analog",  low: 15, high: 35,  notifications: 0, subscribed: true },
  "analog-input,1":      { label: "T Water",    value: 44.8,  unit: "°C",  type: "analog",  low: 5,  high: 60,  notifications: 0, subscribed: true },
  "analog-input,2":      { label: "T Outdoor",  value: 28.3,  unit: "°C",  type: "analog",  low: -10,high: 45,  notifications: 0, subscribed: true },
  "analog-value,0":      { label: "T Set",      value: 22.0,  unit: "°C",  type: "analog",  low: 10, high: 40,  notifications: 0, subscribed: true },
  "analog-value,1":      { label: "Setpoint 1", value: 20.0,  unit: "°C",  type: "analog",  low: null, high: null, notifications: 0, subscribed: true },
  "analog-value,2":      { label: "Setpoint 2", value: 18.0,  unit: "°C",  type: "analog",  low: null, high: null, notifications: 0, subscribed: true },
  "analog-value,3":      { label: "Setpoint 3", value: 19.5,  unit: "°C",  type: "analog",  low: null, high: null, notifications: 0, subscribed: true },
  "binary-value,0":      { label: "Heater",     value: true,  unit: "",    type: "binary",  low: null, high: null, notifications: 0, subscribed: true },
  "binary-value,1":      { label: "Chiller",    value: false, unit: "",    type: "binary",  low: null, high: null, notifications: 0, subscribed: true },
  "multi-state-value,0": { label: "State",      value: 2,     unit: "",    type: "multistate", low: null, high: null, notifications: 0, subscribed: true },
  "multi-state-value,1": { label: "Vent Level", value: 3,     unit: "",    type: "multistate", low: null, high: null, notifications: 0, subscribed: true },
};

const MODE_LABELS = { 1: "STANDBY", 2: "COOLING", 3: "HEATING", 4: "VENT", 5: "AUTO" };
const VENT_LABELS = { 1: "OFF", 2: "LOW", 3: "MED", 4: "HIGH" };

// ─── Utilities ────────────────────────────────────────────────────────────────
function formatValue(obj) {
  if (obj.type === "binary") return obj.value ? "ACTIVE" : "OFF";
  if (obj.type === "multistate") {
    if (obj.label === "State")      return MODE_LABELS[obj.value] || obj.value;
    if (obj.label === "Vent Level") return VENT_LABELS[obj.value] || obj.value;
    return obj.value;
  }
  return typeof obj.value === "number" ? obj.value.toFixed(1) : obj.value;
}

function getAlarmState(obj) {
  if (obj.type !== "analog" || obj.value === null) return "ok";
  if (obj.high !== null && obj.value > obj.high) return "high";
  if (obj.low  !== null && obj.value < obj.low)  return "low";
  return "ok";
}

function useSimulator(setPoints, setLog, setConnected) {
  useEffect(() => {
    if (!SIMULATED_MODE) return;
    setConnected(true);

    const interval = setInterval(() => {
      const keys = Object.keys(INITIAL_STATE);
      const key  = keys[Math.floor(Math.random() * keys.length)];
      const obj  = INITIAL_STATE[key];

      let newVal;
      if (obj.type === "analog") {
        const center = typeof obj.value === "number" ? obj.value : 20;
        newVal = +(center + (Math.random() - 0.5) * 4).toFixed(1);
      } else if (obj.type === "binary") {
        newVal = Math.random() > 0.7 ? !obj.value : obj.value;
      } else {
        const max = obj.label === "Vent Level" ? 4 : 5;
        newVal = Math.floor(Math.random() * max) + 1;
      }

      const ts = new Date().toLocaleTimeString();
      setPoints(prev => {
        const updated = {
          ...prev,
          [key]: {
            ...prev[key],
            value: newVal,
            notifications: (prev[key]?.notifications || 0) + 1,
            lastChange: ts,
            prevValue: prev[key]?.value,
          }
        };
        return updated;
      });

      setLog(prev => [{
        ts,
        label: INITIAL_STATE[key].label,
        key,
        value: newVal,
        unit: obj.unit,
      }, ...prev].slice(0, 40));

    }, 1500 + Math.random() * 1000);

    return () => clearInterval(interval);
  }, []);
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ active }) {
  return (
    <span style={{
      display: "inline-block", width: 8, height: 8, borderRadius: "50%",
      background: active ? "#00ff88" : "#ff3b3b",
      boxShadow: active ? "0 0 6px #00ff88" : "0 0 6px #ff3b3b",
      marginRight: 6,
    }} />
  );
}

function GaugeBar({ value, low, high, type }) {
  if (type !== "analog" || value === null) return null;
  const min  = low  !== null ? low  - 5  : 0;
  const max  = high !== null ? high + 5  : 100;
  const pct  = Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
  const alarm = getAlarmState({ value, low, high, type });
  const color = alarm !== "ok" ? "#ffb700" : "#00c896";
  return (
    <div style={{ marginTop: 6, height: 4, background: "#1a1a2e", borderRadius: 2, overflow: "hidden" }}>
      <div style={{
        height: "100%", width: `${pct}%`,
        background: color,
        borderRadius: 2,
        transition: "width 0.6s ease",
        boxShadow: `0 0 8px ${color}88`,
      }} />
    </div>
  );
}

function PointCard({ id, obj, flash }) {
  const alarm = getAlarmState(obj);
  const isOn  = obj.type === "binary" && obj.value;
  const delta = obj.prevValue !== undefined && obj.type === "analog"
    ? (obj.value - obj.prevValue).toFixed(1)
    : null;

  const borderColor = alarm !== "ok" ? "#ffb700"
    : obj.type === "binary" && obj.value ? "#00ff88"
    : "#1e2240";

  return (
    <div style={{
      background: flash ? "#0d1f3c" : "#0b0f2a",
      border: `1px solid ${borderColor}`,
      borderRadius: 12,
      padding: "16px 20px",
      transition: "all 0.3s ease",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Glow effect on alarm */}
      {alarm !== "ok" && (
        <div style={{
          position: "absolute", inset: 0,
          background: "radial-gradient(ellipse at center, #ffb70008, transparent 70%)",
          pointerEvents: "none",
        }} />
      )}

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 11, color: "#4a5080", fontFamily: "monospace", letterSpacing: 1 }}>
            {id}
          </div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#c8d0ff", marginTop: 2 }}>
            {obj.label}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {alarm !== "ok" && (
            <span style={{
              fontSize: 10, padding: "2px 6px", borderRadius: 4,
              background: "#ffb70022", color: "#ffb700",
              fontWeight: 700, letterSpacing: 1,
            }}>
              {alarm.toUpperCase()}
            </span>
          )}
          <StatusDot active={obj.subscribed} />
        </div>
      </div>

      {/* Value */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{
          fontSize: obj.type === "analog" ? 28 : 22,
          fontWeight: 800,
          fontFamily: "monospace",
          color: alarm !== "ok" ? "#ffb700"
            : obj.type === "binary" && isOn ? "#00ff88"
            : obj.type === "binary" ? "#ff6b6b"
            : "#e8ecff",
          transition: "color 0.3s",
          letterSpacing: -1,
        }}>
          {formatValue(obj)}
        </span>
        {obj.unit && (
          <span style={{ fontSize: 13, color: "#4a5080", fontFamily: "monospace" }}>
            {obj.unit}
          </span>
        )}
        {delta !== null && Math.abs(delta) > 0 && (
          <span style={{
            fontSize: 11, marginLeft: 4,
            color: delta > 0 ? "#ffb700" : "#00c8ff",
            fontFamily: "monospace",
          }}>
            {delta > 0 ? `↑+${delta}` : `↓${delta}`}
          </span>
        )}
      </div>

      <GaugeBar value={obj.value} low={obj.low} high={obj.high} type={obj.type} />

      {/* Footer */}
      <div style={{
        display: "flex", justifyContent: "space-between",
        marginTop: 8, fontSize: 10, color: "#2e3460", fontFamily: "monospace",
      }}>
        <span>{obj.notifications} notifs</span>
        {obj.lastChange && <span>{obj.lastChange}</span>}
      </div>
    </div>
  );
}

function EventLog({ log }) {
  return (
    <div style={{
      background: "#060916", border: "1px solid #1a1f40",
      borderRadius: 12, overflow: "hidden",
    }}>
      <div style={{
        padding: "12px 20px", borderBottom: "1px solid #1a1f40",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{ color: "#00ff88", fontSize: 10 }}>●</span>
        <span style={{ color: "#4a5080", fontSize: 12, fontWeight: 700, letterSpacing: 2, fontFamily: "monospace" }}>
          LIVE EVENT LOG
        </span>
      </div>
      <div style={{ maxHeight: 320, overflowY: "auto", padding: "8px 0" }}>
        {log.length === 0 && (
          <div style={{ padding: "20px", color: "#2e3460", fontFamily: "monospace", fontSize: 12, textAlign: "center" }}>
            Waiting for COV notifications...
          </div>
        )}
        {log.map((entry, i) => (
          <div key={i} style={{
            display: "flex", gap: 12, padding: "6px 20px",
            borderLeft: i === 0 ? "2px solid #00c896" : "2px solid transparent",
            background: i === 0 ? "#0d1f1a" : "transparent",
            transition: "all 0.3s",
          }}>
            <span style={{ color: "#2e3460", fontFamily: "monospace", fontSize: 11, minWidth: 70 }}>
              {entry.ts}
            </span>
            <span style={{ color: "#c8d0ff", fontFamily: "monospace", fontSize: 11, minWidth: 90 }}>
              {entry.label}
            </span>
            <span style={{
              color: "#00c896", fontFamily: "monospace", fontSize: 11, fontWeight: 700,
            }}>
              → {typeof entry.value === "number" ? entry.value.toFixed(1) : String(entry.value)} {entry.unit}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConnectionBadge({ connected, mode }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "6px 14px", borderRadius: 20,
      background: connected ? "#00ff8811" : "#ff3b3b11",
      border: `1px solid ${connected ? "#00ff8833" : "#ff3b3b33"}`,
    }}>
      <StatusDot active={connected} />
      <span style={{
        fontSize: 11, fontFamily: "monospace", fontWeight: 700,
        color: connected ? "#00ff88" : "#ff3b3b", letterSpacing: 1,
      }}>
        {mode === "sim" ? "SIMULATED" : connected ? "CONNECTED" : "DISCONNECTED"}
      </span>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function BACnetDashboard() {
  const [points, setPoints]       = useState(() => {
    const init = {};
    Object.entries(INITIAL_STATE).forEach(([k, v]) => {
      init[k] = { ...v, notifications: 0, lastChange: null };
    });
    return init;
  });
  const [log, setLog]             = useState([]);
  const [connected, setConnected] = useState(false);
  const [flashSet, setFlashSet]   = useState(new Set());
  const [totalNotifs, setTotal]   = useState(0);
  const [uptime, setUptime]       = useState(0);
  const wsRef = useRef(null);

  // Flash animation on update
  useEffect(() => {
    const changed = Object.keys(points).filter(k => points[k].lastChange);
    if (changed.length === 0) return;
    const latest = changed.sort((a, b) =>
      (points[b].notifications || 0) - (points[a].notifications || 0)
    )[0];
    setFlashSet(prev => new Set([...prev, latest]));
    const t = setTimeout(() => setFlashSet(prev => {
      const s = new Set(prev); s.delete(latest); return s;
    }), 600);
    return () => clearTimeout(t);
  }, [points]);

  // Total notification counter
  useEffect(() => {
    setTotal(Object.values(points).reduce((s, p) => s + (p.notifications || 0), 0));
  }, [points]);

  // Uptime counter
  useEffect(() => {
    const t = setInterval(() => setUptime(u => u + 1), 1000);
    return () => clearInterval(t);
  }, []);

  // Simulator
  useSimulator(setPoints, setLog, setConnected);

  // Real WebSocket (active when SIMULATED_MODE = false)
  // WITH this — adds auto-reconnect every 2 seconds
  useEffect(() => {
    if (SIMULATED_MODE) return;

    let ws = null;
    let reconnectTimer = null;
    let destroyed = false;

    function connect() {
      if (destroyed) return;

      ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected");
        setConnected(true);
      };

      ws.onclose = () => {
        console.log("WebSocket closed — retrying in 2s...");
        setConnected(false);
        if (!destroyed) {
          reconnectTimer = setTimeout(connect, 2000);
        }
      };

      ws.onerror = (e) => {
        console.warn("WebSocket error:", e);
        ws.close();
      };

      ws.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const ts = new Date().toLocaleTimeString();
        setPoints(prev => ({
          ...prev,
          [data.object_id]: {
            ...prev[data.object_id],
            value: data.value,
            notifications: (prev[data.object_id]?.notifications || 0) + 1,
            lastChange: ts,
            prevValue: prev[data.object_id]?.value,
          }
        }));
        setLog(prev => [{
          ts, label: data.label, key: data.object_id,
          value: data.value, unit: data.unit
        }, ...prev].slice(0, 40));
      };
    }

    connect();   // first attempt

    return () => {
      destroyed = true;
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  const uptimeStr = `${String(Math.floor(uptime/3600)).padStart(2,"0")}:${String(Math.floor((uptime%3600)/60)).padStart(2,"0")}:${String(uptime%60).padStart(2,"0")}`;
  const alarmCount = Object.values(points).filter(p => getAlarmState(p) !== "ok").length;

  return (
    <div style={{
      minHeight: "100vh",
      background: "#04060f",
      backgroundImage: "radial-gradient(ellipse at 20% 20%, #0a1628 0%, transparent 50%), radial-gradient(ellipse at 80% 80%, #080d1e 0%, transparent 50%)",
      fontFamily: "'Segoe UI', sans-serif",
      color: "#e8ecff",
      padding: "24px",
    }}>

      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 4 }}>
              <div style={{
                width: 36, height: 36, borderRadius: 8,
                background: "linear-gradient(135deg, #0044ff22, #00c89622)",
                border: "1px solid #0044ff44",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 18,
              }}>⬡</div>
              <div>
                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: -0.5, color: "#e8ecff" }}>
                  BACnet Monitor
                </div>
                <div style={{ fontSize: 11, color: "#4a5080", fontFamily: "monospace", letterSpacing: 2 }}>
                  ROOMCONTROLLER.SIMULATOR · DEVICE:3506259
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            {/* Stats */}
            {[
              { label: "NOTIFICATIONS", value: totalNotifs },
              { label: "ACTIVE SUBS", value: `${Object.values(points).filter(p=>p.subscribed).length}/11` },
              { label: "ALARMS", value: alarmCount, alert: alarmCount > 0 },
              { label: "UPTIME", value: uptimeStr },
            ].map(s => (
              <div key={s.label} style={{
                padding: "8px 14px", background: "#080c20",
                border: `1px solid ${s.alert ? "#ffb70044" : "#1a1f40"}`,
                borderRadius: 8, textAlign: "center",
              }}>
                <div style={{ fontSize: 16, fontWeight: 800, fontFamily: "monospace", color: s.alert ? "#ffb700" : "#e8ecff" }}>
                  {s.value}
                </div>
                <div style={{ fontSize: 9, color: "#2e3460", letterSpacing: 1.5, marginTop: 1 }}>{s.label}</div>
              </div>
            ))}
            <ConnectionBadge connected={connected} mode={SIMULATED_MODE ? "sim" : "ws"} />
          </div>
        </div>

        {/* Divider */}
        <div style={{ height: 1, background: "linear-gradient(90deg, #0044ff22, #00c89622, transparent)", marginTop: 20 }} />
      </div>

      {/* Section: Temperatures */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: "#2e3460", letterSpacing: 3, fontFamily: "monospace", marginBottom: 12 }}>
          ── TEMPERATURE SENSORS
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {["analog-input,0","analog-input,1","analog-input,2","analog-value,0"].map(k => (
            <PointCard key={k} id={k} obj={points[k]} flash={flashSet.has(k)} />
          ))}
        </div>
      </div>

      {/* Section: Setpoints */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: "#2e3460", letterSpacing: 3, fontFamily: "monospace", marginBottom: 12 }}>
          ── SETPOINTS
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {["analog-value,1","analog-value,2","analog-value,3"].map(k => (
            <PointCard key={k} id={k} obj={points[k]} flash={flashSet.has(k)} />
          ))}
        </div>
      </div>

      {/* Section: States */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 10, color: "#2e3460", letterSpacing: 3, fontFamily: "monospace", marginBottom: 12 }}>
          ── EQUIPMENT STATE
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
          {["binary-value,0","binary-value,1","multi-state-value,0","multi-state-value,1"].map(k => (
            <PointCard key={k} id={k} obj={points[k]} flash={flashSet.has(k)} />
          ))}
        </div>
      </div>

      {/* Event Log */}
      <EventLog log={log} />

      {/* Footer */}
      <div style={{
        marginTop: 20, display: "flex", justifyContent: "space-between",
        fontSize: 10, color: "#1e2240", fontFamily: "monospace", letterSpacing: 1,
      }}>
        <span>BACnet/IP · COV EVENT-DRIVEN · ZERO POLLING</span>
        <span>bacpypes3 · FastAPI · React</span>
      </div>
    </div>
  );
}
