// Use Vercel Environment Variable if available, otherwise default to local backend
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const getStatus = () => fetch(`${API_BASE}/status`).then(r => r.json());

export const getAggressiveness = () => fetch(`${API_BASE}/aggressiveness`).then(r => r.json());

export const setAggressiveness = (value) => 
  fetch(`${API_BASE}/aggressiveness`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value })
  }).then(r => r.json());

export const setMode = (mode) => 
  fetch(`${API_BASE}/mode`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode })
  }).then(r => r.json());

export const getRecommendations = (status = null) => {
  const url = status ? `${API_BASE}/recommendations?status=${status}` : `${API_BASE}/recommendations`;
  return fetch(url).then(r => r.json());
};

export const approveRecommendation = (recId) => 
  fetch(`${API_BASE}/recommendations/${recId}/approve`, {
    method: "POST",
  }).then(r => r.json());

export const triggerCycle = () => 
  fetch(`${API_BASE}/cycle`, { method: "POST" }).then(r => r.json());

export const getOrders = () => fetch(`${API_BASE}/orders`).then(r => r.json());

export const getPnl = () => fetch(`${API_BASE}/pnl`).then(r => r.json());
