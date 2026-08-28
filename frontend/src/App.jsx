import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { TrendingUp, TrendingDown, Bot, UserCheck, Sliders, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import * as api from "./api";

export default function TradingDashboard() {
  const [status, setStatus] = useState(null);
  const [aggressiveness, setAggressiveness] = useState(30);
  const [zoneLabel, setZoneLabel] = useState("Conservador");
  const [zone, setZone] = useState("conservative");
  const [mode, setModeState] = useState("asesor");
  
  const [recommendations, setRecommendations] = useState([]);
  const [orders, setOrders] = useState([]);
  const [pnlData, setPnlData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cycleLoading, setCycleLoading] = useState(false);

  // Fetch initial data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, recsRes, ordersRes, pnlRes] = await Promise.all([
        api.getStatus(),
        api.getRecommendations(),
        api.getOrders(),
        api.getPnl()
      ]);
      
      setStatus(statusRes);
      setAggressiveness(statusRes.aggressiveness);
      setZone(statusRes.zone);
      setZoneLabel(statusRes.zone_label);
      setModeState(statusRes.mode);
      
      setRecommendations(recsRes.recommendations || []);
      setOrders(ordersRes.orders || []);
      
      // Map P&L data for the chart
      const chartData = (pnlRes.snapshots || []).reverse().map(snap => ({
        t: new Date(snap.snapshot_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        value: snap.equity
      }));
      // Provide fallback data if empty
      setPnlData(chartData.length > 0 ? chartData : [{t: "10:00", value: 100000}]);
      
    } catch (err) {
      console.error("Failed to fetch data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Refresh every 5 seconds
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleAggressivenessChange = async (e) => {
    const val = Number(e.target.value);
    setAggressiveness(val);
    try {
      const res = await api.setAggressiveness(val);
      setZone(res.zone);
      setZoneLabel(res.zone_label);
    } catch (err) {
      console.error(err);
    }
  };

  const handleModeChange = async (newMode) => {
    try {
      await api.setMode(newMode);
      setModeState(newMode);
      fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleTriggerCycle = async () => {
    setCycleLoading(true);
    try {
      await api.triggerCycle();
      await fetchData();
    } catch (err) {
      console.error(err);
    } finally {
      setCycleLoading(false);
    }
  };

  const handleApprove = async (recId) => {
    try {
      await api.approveRecommendation(recId);
      await fetchData();
    } catch (err) {
      console.error(err);
    }
  };

  if (loading && !status) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center">
        <RefreshCw className="animate-spin text-slate-500" size={32} />
      </div>
    );
  }

  const zoneStyles = {
    conservative: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    moderate: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    aggressive: "text-rose-400 border-rose-500/30 bg-rose-500/10",
  };

  const currentPnl = pnlData.length > 1 
    ? pnlData[pnlData.length - 1].value - pnlData[0].value
    : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
      <div className="max-w-5xl mx-auto space-y-6">
        
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold flex items-center gap-3">
              SILVERCAWN Trading Agent
              {!status?.mcp_connected && (
                <span className="text-xs font-mono bg-rose-500/10 text-rose-400 px-2 py-0.5 rounded border border-rose-500/30">
                  MCP Disconnected
                </span>
              )}
            </h1>
            <p className="text-slate-400 text-sm mt-1">Cuenta paper · $100,000 balance inicial</p>
          </div>
          
          <div className="flex items-center gap-4">
            <button
              onClick={handleTriggerCycle}
              disabled={cycleLoading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm bg-slate-800 hover:bg-slate-700 text-slate-300 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={16} className={cycleLoading ? "animate-spin" : ""} />
              Forzar Ciclo
            </button>
            
            <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1">
              <button
                onClick={() => handleModeChange("asesor")}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                  mode === "asesor" ? "bg-blue-600 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <UserCheck size={16} /> Asesor
              </button>
              <button
                onClick={() => handleModeChange("autonomo")}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm transition-colors ${
                  mode === "autonomo" ? "bg-rose-600 text-white" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Bot size={16} /> Autónomo
                {status?.autonomous_running && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse ml-1"></span>}
              </button>
            </div>
          </div>
        </div>

        {/* Top Widgets Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          
          {/* Aggressiveness Widget */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Sliders size={16} /> Agresividad de Estrategia
              </div>
              <span className={`text-sm font-mono px-3 py-1 rounded border ${zoneStyles[zone]}`}>
                {aggressiveness}% · {zoneLabel}
              </span>
            </div>
            
            <input
              type="range"
              min="0"
              max="100"
              value={aggressiveness}
              onChange={handleAggressivenessChange}
              className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer"
              style={{ accentColor: "#3b82f6" }}
            />
            <div className="flex justify-between text-xs text-slate-500 mt-2 font-mono">
              <span>0% (Conservador)</span>
              <span>100% (Agresivo)</span>
            </div>
          </div>

          {/* P&L Chart Widget */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm text-slate-400">Equity (Paper)</h2>
              <div className={`flex items-center gap-1 text-sm font-mono ${currentPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                {currentPnl >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
                {currentPnl >= 0 ? "+" : ""}
                ${Math.abs(currentPnl).toFixed(2)}
              </div>
            </div>
            <div style={{ width: "100%", height: 120 }}>
              <ResponsiveContainer>
                <LineChart data={pnlData}>
                  <XAxis dataKey="t" hide />
                  <YAxis domain={["auto", "auto"]} hide />
                  <Tooltip 
                    contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px", fontSize: "12px" }}
                    itemStyle={{ color: "#e2e8f0" }}
                  />
                  <Line type="monotone" dataKey="value" stroke={currentPnl >= 0 ? "#10b981" : "#f43f5e"} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Content Tabs area (Recomendaciones y Órdenes) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Recomendaciones (Advisor Mode) */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-[500px]">
            <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
              <h2 className="text-sm font-medium text-slate-300">Recomendaciones Pendientes</h2>
              <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded">Modo Asesor</span>
            </div>
            <div className="p-4 overflow-y-auto flex-1 space-y-4">
              {recommendations.filter(r => r.status === "pending").length === 0 ? (
                <div className="text-center text-slate-500 text-sm mt-10">
                  No hay recomendaciones pendientes.<br/>
                  Usa "Forzar Ciclo" para que el agente analice el mercado.
                </div>
              ) : (
                recommendations.filter(r => r.status === "pending").map((rec) => (
                  <div key={rec.id} className="bg-slate-950 border border-slate-800 rounded-lg p-4">
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          <span className="font-mono text-blue-400 font-semibold">{rec.symbol || "UNKNOWN"}</span>
                          <span className="text-xs bg-slate-800 px-2 py-0.5 rounded text-slate-300">{rec.strategy}</span>
                        </div>
                        <p className="text-sm text-slate-200 mt-2">{rec.action}</p>
                      </div>
                    </div>
                    
                    {rec.llm_reasoning && (
                      <div className="mt-3 text-xs text-slate-400 bg-slate-900 p-3 rounded-md border border-slate-800/50">
                        <span className="text-slate-500 uppercase tracking-wider text-[10px] block mb-1">Reasoning</span>
                        {rec.llm_reasoning.substring(0, 150)}...
                      </div>
                    )}
                    
                    <div className="mt-4 flex justify-end gap-2">
                      <button 
                        onClick={() => handleApprove(rec.id)}
                        className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs px-3 py-1.5 rounded transition-colors"
                      >
                        <CheckCircle2 size={14} /> Aprobar y Ejecutar
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Historial de Órdenes */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl flex flex-col h-[500px]">
            <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
              <h2 className="text-sm font-medium text-slate-300">Historial de Ejecución</h2>
            </div>
            <div className="p-0 overflow-y-auto flex-1">
              {orders.length === 0 ? (
                <div className="text-center text-slate-500 text-sm mt-14">
                  No hay órdenes ejecutadas.
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-slate-800 text-xs text-slate-500 uppercase tracking-wider">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Símbolo</th>
                      <th className="px-4 py-3 text-left font-medium">Estrategia</th>
                      <th className="px-4 py-3 text-left font-medium">Estado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {orders.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-3 font-mono text-slate-300">{o.symbol}</td>
                        <td className="px-4 py-3 text-slate-400 truncate max-w-[150px]">{o.order_type}</td>
                        <td className="px-4 py-3">
                          <span
                            className={`text-[11px] font-medium px-2 py-1 rounded-full ${
                              o.status === "submitted" || o.status === "filled" 
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" 
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                            }`}
                          >
                            {o.status.toUpperCase()}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
