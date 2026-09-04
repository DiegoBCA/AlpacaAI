# SIGMA IA — Autonomous Options Trading Agent 🦅

**SIGMA IA** is an elite, fully autonomous AI trading agent built specifically for the **LabLab.ai × Alpaca (2026)** Hackathon. 

Powered by **NVIDIA AI** (DeepSeek V4 Pro) and the **Model Context Protocol (MCP)**, SIGMA IA constantly monitors the market, parses massive option chains, evaluates market sentiment, and executes risk-managed option strategies directly into an Alpaca Paper Trading account.

---

## 🌟 Hackathon Highlights

- **🧠 NVIDIA AI Inference:** Utilizes `deepseek-v4-pro-0813` via NVIDIA's API to analyze complex market data and JSON option chains with deep reasoning.
- **🔌 Alpaca MCP Server Integration:** Dynamically loads 35+ Alpaca trading and market data tools through the official `alpacahq/alpaca-mcp-server` over a native `stdio` transport.
- **🛡️ Dynamic Risk Gates Engine:** A strict backend safety layer that intercepts AI tool calls. Risk tolerance is controlled via a slider (Conservative ➔ Moderate ➔ Aggressive ➔ Degen), which strictly dictates what instruments (ETFs vs Naked Puts) and maximum exposures the AI is allowed to trade.
- **📈 Premium Ops Dashboard:** A stunning, glassmorphism-inspired React dashboard featuring live P&L charts, an integrated CNN *Fear & Greed* gauge, and a real-time Terminal Log to monitor the AI's "brain" and executions.
- **🤖 Autonomous Loop:** Operates in a 60-second cycle evaluating time, calendar, account equity, positions, and live option data before firing logic chains.

---

## 🚀 Instalación y Ejecución

### Prerrequisitos
- Python 3.11+
- Node.js 20+ y npm
- `uv` (Requerido para instanciar el MCP server de forma fluida)

### 1. Variables de Entorno
Copia el archivo de ejemplo y configura tus llaves:
```bash
cp .env.example .env
```
Edita `.env` y añade tus credenciales de [Alpaca Paper](https://app.alpaca.markets/paper/dashboard/overview) y [NVIDIA AI](https://build.nvidia.com). 
*Nota: Asegúrate de tener las Opciones habilitadas en el dashboard de Alpaca.*

### 2. Backend (FastAPI + SQLite)
Abre una terminal y ejecuta:
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```
La API estará disponible en `http://localhost:8000`.

### 3. Frontend (React + Tailwind v4)
Abre otra terminal y ejecuta:
```bash
cd frontend
nvm use 20  # Opcional, asegurar node v20
npm install
npm run dev
```
El dashboard Ops Center estará disponible en `http://localhost:5173`.

---

## 🏗️ Arquitectura del Sistema

1. **Frontend:** React + Vite + Tailwind CSS v4 + Recharts + Lucide Icons. Diseñado con micro-animaciones y paletas HSL premium.
2. **Backend API:** FastAPI (endpoints de control asíncrono).
3. **Database:** SQLite async (`aiosqlite`) con schema relacional para logs, razonamientos del LLM (Recommendation Engine) y eventos de bloqueo de riesgos.
4. **LLM Engine:** Cliente OpenAI-compatible apuntando a NVIDIA NIM.
5. **Trading Execution:** Cliente MCP nativo que instancia el `alpaca-mcp-server` oficial usando `uvx` como subproceso.

---

## 🧪 Testing

El backend incluye pruebas unitarias para el motor de agresividad (funciones puras) y los risk gates, además de pruebas de integración con el MCP server.

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

> **Built with 💻 & ☕ for the Alpaca Hackathon 2026.**
