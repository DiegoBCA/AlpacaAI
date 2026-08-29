# SILVERCAWN — Autonomous Trading Agent 🦅

Agente de IA autónomo para trading de opciones sobre la API de Alpaca, impulsado por NVIDIA AI y Model Context Protocol (MCP). Creado para el hackathon LabLab.ai × Alpaca (2026).

## Características principales (Fase 1)
- **Motor de Agresividad (0-100%):** Define instrumentos permitidos, estrategias y límites de riesgo (stop-loss, exposición) dinámicamente.
- **Modo Asesor:** Analiza el mercado y recomienda trades. Requiere aprobación humana explícita.
- **Modo Autónomo:** Loop continuo que analiza y ejecuta órdenes automáticamente.
- **Risk Gates (Hard Limits):** Verificaciones de seguridad a nivel de código (exposición, posiciones, instrumentos) que el LLM no puede anular.
- **Integración FastMCP:** Usa el servidor oficial `alpacahq/alpaca-mcp-server` v2 vía transporte `stdio`.
- **Safeguards:** Bloqueado rígidamente para *Paper Trading* únicamente.

---

## 🚀 Instalación y Ejecución

### Prerrequisitos
- Python 3.11+
- Node.js 18+ y npm
- `uv` (opcional pero recomendado para el MCP server)

### 1. Variables de Entorno
Copia el archivo de ejemplo y configura tus llaves:
```bash
cp .env.example .env
```
Edita `.env` y añade tus credenciales de [Alpaca Paper](https://app.alpaca.markets/paper/dashboard/overview) y [NVIDIA AI](https://build.nvidia.com).

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

### 3. Frontend (React + Vite)
Abre otra terminal y ejecuta:
```bash
cd frontend
npm install
npm run dev
```
El dashboard estará disponible en `http://localhost:5173`.

---

## 🧪 Testing

El backend incluye pruebas unitarias para el motor de agresividad (funciones puras) y los risk gates, además de pruebas de integración con el MCP server.

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

---

## 🏗️ Arquitectura (Fase 1)

1. **Frontend:** React + Vite + Tailwind CSS v4 + Recharts.
2. **Backend API:** FastAPI (endpoints de control).
3. **Database:** SQLite async (`aiosqlite`) con schema relacional para logs, recomendaciones y risk events.
4. **LLM Engine:** NVIDIA AI (OpenAI-compatible) con *tool-use loop*.
5. **Trading Execution:** Cliente MCP nativo que instancia el `alpaca-mcp-server` oficial como subproceso.
