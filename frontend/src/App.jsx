import { useState, useEffect, useCallback } from "react";
import { 
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer 
} from "recharts";
import { 
  TrendingUp, TrendingDown, Bot, UserCheck, Sliders, 
  RefreshCw, CheckCircle2, ShieldAlert, Activity, ArrowRight
} from "lucide-react";
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
  const [fng, setFng] = useState({ value: 50, label: "Neutral" });
  
  const [loading, setLoading] = useState(true);
  const [cycleLoading, setCycleLoading] = useState(false);

  // Fetch initial data
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, recsRes, ordersRes, pnlRes, fngRes] = await Promise.all([
        api.getStatus(),
        api.getRecommendations(),
        api.getOrders(),
        api.getPnl(),
        fetch("https://api.alternative.me/fng/").then(r => r.json()).catch(() => null)
      ]);
      
      setStatus(statusRes);
      setAggressiveness(statusRes.aggressiveness);
      setZone(statusRes.zone);
      setZoneLabel(statusRes.zone_label);
      setModeState(statusRes.mode);
      
      setRecommendations(recsRes.recommendations || []);
      setOrders(ordersRes.orders || []);
      
      if (fngRes && fngRes.data && fngRes.data.length > 0) {
        setFng({
          value: parseInt(fngRes.data[0].value, 10),
          label: fngRes.data[0].value_classification
        });
      }
      
      // Map P&L data for the chart
      const chartData = (pnlRes.snapshots || []).reverse().map(snap => ({
        t: new Date(snap.snapshot_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        value: snap.equity
      }));
      setPnlData(chartData.length > 0 ? chartData : [{t: "10:00", value: 100000}]);
      
    } catch (err) {
      console.error("Failed to fetch data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
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
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center gap-4 text-indigo-400">
        <RefreshCw className="animate-spin" size={40} />
        <p className="font-mono text-sm uppercase tracking-widest">Inicializando Sistemas...</p>
      </div>
    );
  }

  const zoneColors = {
    conservative: { text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30", hex: "#34d399" },
    moderate: { text: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30", hex: "#fbbf24" },
    aggressive: { text: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/30", hex: "#fb7185" },
  };

  const currentPnl = pnlData.length > 1 
    ? pnlData[pnlData.length - 1].value - pnlData[0].value
    : 0;

  // Render Fear and Greed Color
  const getFngColor = (val) => {
    if (val <= 25) return "#ef4444"; // red
    if (val <= 45) return "#f97316"; // orange
    if (val <= 55) return "#eab308"; // yellow
    if (val <= 75) return "#84cc16"; // light green
    return "#22c55e"; // green
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans relative overflow-hidden">
      
      {/* Background Animated Blobs */}
      <div className="absolute top-0 -left-4 w-72 h-72 bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 animate-blob pointer-events-none"></div>
      <div className="absolute top-0 -right-4 w-72 h-72 bg-emerald-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 animate-blob animation-delay-2000 pointer-events-none"></div>
      <div className="absolute -bottom-8 left-20 w-72 h-72 bg-rose-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 animate-blob animation-delay-4000 pointer-events-none"></div>

      <div className="relative max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
        
        {/* Header */}
        <header className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 glass-panel rounded-2xl p-4">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
              <Activity className="text-white" size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                SILVERCAWN OPS
              </h1>
              <div className="flex items-center gap-3 text-sm mt-1">
                <span className="text-slate-400 flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-blue-500"></div> Paper Trading
                </span>
                {!status?.mcp_connected && (
                  <span className="text-xs font-mono bg-rose-500/10 text-rose-400 px-2 py-0.5 rounded-full border border-rose-500/30 flex items-center gap-1">
                    <ShieldAlert size={12} /> MCP Error
                  </span>
                )}
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <button
              onClick={handleTriggerCycle}
              disabled={cycleLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 transition-all disabled:opacity-50 font-medium"
            >
              <RefreshCw size={16} className={cycleLoading ? "animate-spin" : ""} />
              Forzar Análisis
            </button>
            
            <div className="flex items-center gap-1 bg-slate-900/80 border border-slate-800 rounded-lg p-1">
              <button
                onClick={() => handleModeChange("asesor")}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm transition-all font-medium ${
                  mode === "asesor" ? "bg-blue-600 text-white shadow-lg shadow-blue-500/20" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <UserCheck size={16} /> Asesor
              </button>
              <button
                onClick={() => handleModeChange("autonomo")}
                className={`flex items-center gap-2 px-4 py-1.5 rounded-md text-sm transition-all font-medium ${
                  mode === "autonomo" ? "bg-rose-600 text-white shadow-lg shadow-rose-500/20" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Bot size={16} /> Autónomo
                {status?.autonomous_running && <span className="w-2 h-2 rounded-full bg-emerald-300 animate-pulse ml-1 shadow-[0_0_8px_rgba(52,211,153,0.8)]"></span>}
              </button>
            </div>
          </div>
        </header>

        {/* Middle Section: Widgets */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Main Chart (Spans 8 cols) */}
          <div className="lg:col-span-8 glass-panel rounded-2xl p-6 flex flex-col">
            <div className="flex items-end justify-between mb-6">
              <div>
                <h2 className="text-sm font-medium text-slate-400 mb-1">Equidad Total (Paper)</h2>
                <div className="text-3xl font-bold tracking-tight">${pnlData[pnlData.length - 1]?.value.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) || "100,000.00"}</div>
              </div>
              <div className={`flex items-center gap-1.5 font-mono text-lg ${currentPnl >= 0 ? "text-emerald-400" : "text-rose-400"} bg-slate-900/50 px-3 py-1.5 rounded-lg border border-slate-800`}>
                {currentPnl >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />}
                {currentPnl >= 0 ? "+" : "-"}${Math.abs(currentPnl).toFixed(2)}
              </div>
            </div>
            
            <div className="flex-1 w-full min-h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={pnlData}>
                  <defs>
                    <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={currentPnl >= 0 ? "#10b981" : "#f43f5e"} stopOpacity={0.3}/>
                      <stop offset="95%" stopColor={currentPnl >= 0 ? "#10b981" : "#f43f5e"} stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="t" hide />
                  <YAxis domain={["auto", "auto"]} hide />
                  <Tooltip 
                    contentStyle={{ background: "rgba(15, 23, 42, 0.9)", border: "1px solid #1e293b", borderRadius: "8px", backdropFilter: "blur(4px)" }}
                    itemStyle={{ color: "#f8fafc", fontWeight: 500 }}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="value" 
                    stroke={currentPnl >= 0 ? "#10b981" : "#f43f5e"} 
                    strokeWidth={3}
                    fillOpacity={1} 
                    fill="url(#colorPnl)" 
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Right Column: F&G and Aggressiveness (Spans 4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            
            {/* Fear & Greed Index */}
            <div className="glass-panel rounded-2xl p-6 flex flex-col justify-center relative overflow-hidden group">
              <h2 className="text-sm font-medium text-slate-400 mb-6 flex items-center gap-2">
                Market Sentiment
              </h2>
              
              <div className="flex items-center justify-between">
                <div className="relative">
                  <svg width="120" height="120" viewBox="0 0 120 120" className="transform -rotate-90">
                    {/* Background circle */}
                    <circle cx="60" cy="60" r="50" fill="none" stroke="#1e293b" strokeWidth="12" />
                    {/* Value circle */}
                    <circle 
                      cx="60" cy="60" r="50" fill="none" 
                      stroke={getFngColor(fng.value)} 
                      strokeWidth="12"
                      strokeDasharray={`${(fng.value / 100) * 314} 314`}
                      className="transition-all duration-1000 ease-out"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-3xl font-bold">{fng.value}</span>
                  </div>
                </div>
                
                <div className="flex flex-col items-end text-right">
                  <span className="text-xs text-slate-500 uppercase tracking-wider font-semibold mb-1">Index</span>
                  <span className="text-lg font-medium" style={{color: getFngColor(fng.value)}}>{fng.label}</span>
                  <span className="text-xs text-slate-400 mt-2 max-w-[120px]">Impulsado por CNN / alternative.me</span>
                </div>
              </div>
            </div>

            {/* Aggressiveness Control */}
            <div className="glass-panel rounded-2xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2 text-sm text-slate-400 font-medium">
                  <Sliders size={16} /> Perfil de Riesgo
                </div>
                <span className={`text-xs font-mono font-bold px-2 py-1 rounded-md border ${zoneColors[zone].bg} ${zoneColors[zone].border} ${zoneColors[zone].text}`}>
                  {aggressiveness}% · {zoneLabel}
                </span>
              </div>
              
              <div className="relative pt-2 pb-4">
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={aggressiveness}
                  onChange={handleAggressivenessChange}
                  className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer outline-none relative z-10"
                  style={{ accentColor: zoneColors[zone].hex }}
                />
                
                {/* Visual markers */}
                <div className="absolute top-2 left-0 w-full h-1.5 rounded-lg flex pointer-events-none z-0 overflow-hidden opacity-50">
                  <div className="h-full bg-emerald-500" style={{width: '35%'}}></div>
                  <div className="h-full bg-amber-500" style={{width: '30%'}}></div>
                  <div className="h-full bg-rose-500" style={{width: '35%'}}></div>
                </div>

                <div className="flex justify-between text-[10px] text-slate-500 mt-3 font-mono uppercase font-semibold">
                  <span>Safe</span>
                  <span>Degen</span>
                </div>
              </div>
            </div>

          </div>
        </div>

        {/* Bottom Section: Lists */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          
          {/* Advisor Recommendations */}
          <div className="glass-panel rounded-2xl flex flex-col h-[400px]">
            <div className="p-5 border-b border-slate-800/50 flex justify-between items-center bg-slate-900/30">
              <h2 className="text-sm font-semibold text-slate-300">Action Center (Asesor)</h2>
              <span className="text-xs bg-slate-800 text-slate-400 px-2 py-1 rounded-md font-mono">{recommendations.filter(r => r.status === "pending").length} Pending</span>
            </div>
            <div className="p-4 overflow-y-auto flex-1 space-y-3 custom-scrollbar">
              {recommendations.filter(r => r.status === "pending").length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm">
                  <CheckCircle2 size={32} className="text-slate-700 mb-3" />
                  <p>All caught up.</p>
                  <p className="text-xs text-slate-600 mt-1">Waiting for next analysis cycle.</p>
                </div>
              ) : (
                recommendations.filter(r => r.status === "pending").map((rec) => (
                  <div key={rec.id} className="bg-slate-900/50 border border-slate-800/50 rounded-xl p-4 hover:border-slate-700 transition-colors">
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-3">
                        <div className="bg-slate-800 rounded-lg p-2 flex items-center justify-center font-mono font-bold text-blue-400 border border-slate-700 shadow-inner">
                          {rec.symbol || "UNK"}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-slate-200">{rec.action}</p>
                            <span className="text-[10px] uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-2 py-0.5 rounded-full">{rec.strategy}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    
                    {rec.llm_reasoning && (
                      <div className="mt-3 text-xs text-slate-400 bg-slate-950/50 p-3 rounded-lg border border-slate-800/50 leading-relaxed italic">
                        "{rec.llm_reasoning.substring(0, 180)}{rec.llm_reasoning.length > 180 ? '...' : ''}"
                      </div>
                    )}
                    
                    <div className="mt-4 flex justify-end">
                      <button 
                        onClick={() => handleApprove(rec.id)}
                        className="flex items-center gap-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/30 text-xs px-4 py-2 rounded-lg transition-all font-medium"
                      >
                        Aprobar Orden <ArrowRight size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Execution History */}
          <div className="glass-panel rounded-2xl flex flex-col h-[400px]">
            <div className="p-5 border-b border-slate-800/50 bg-slate-900/30">
              <h2 className="text-sm font-semibold text-slate-300">Terminal Log</h2>
            </div>
            <div className="p-0 overflow-y-auto flex-1 custom-scrollbar">
              {orders.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 text-sm">
                  <Activity size={32} className="text-slate-700 mb-3" />
                  <p>No trade executions yet.</p>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-900/80 backdrop-blur-md border-b border-slate-800/50 text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                    <tr>
                      <th className="px-5 py-3 text-left">Asset</th>
                      <th className="px-5 py-3 text-left">Strategy</th>
                      <th className="px-5 py-3 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/30">
                    {orders.map((o) => (
                      <tr key={o.id} className="hover:bg-slate-800/20 transition-colors group">
                        <td className="px-5 py-3 font-mono font-medium text-slate-300">{o.symbol}</td>
                        <td className="px-5 py-3 text-slate-400 text-xs truncate max-w-[150px]">{o.order_type}</td>
                        <td className="px-5 py-3 text-right">
                          <span
                            className={`text-[10px] font-semibold tracking-wider px-2.5 py-1 rounded-full shadow-sm ${
                              o.status === "submitted" || o.status === "filled" 
                                ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 group-hover:bg-emerald-500/20" 
                                : "bg-rose-500/10 text-rose-400 border border-rose-500/20 group-hover:bg-rose-500/20"
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
