# SPEC — Etapa 6: Aplicação Web (Interface de Chat)

## Objetivo

Criar uma interface web de chat que conecta ao agente de especificação (Etapa 4). A interface permite que o usuário converse com o Spec Agent pelo navegador, visualize o status do checklist em tempo real, e faça download dos cards gerados.

**Prioridade:** SECUNDÁRIA em relação às Etapas 1-5. O agente funciona via CLI sem esta etapa. A aplicação web é um upgrade de experiência para a demo.

**Abordagem:** aplicação simples com backend Python (FastAPI + WebSocket) e frontend leve (HTML/CSS/JS vanilla ou React mínimo). Zero dependências pesadas de frontend — nada de build steps complexos.

## Dependências

- **Etapas 1-5 concluídas** — o agente funciona via CLI
- **Bibliotecas Python adicionais:**
  - `fastapi` — framework web
  - `uvicorn` — servidor ASGI
  - `websockets` — suporte a WebSocket no FastAPI

```bash
pip install fastapi uvicorn[standard] websockets
```

## Estrutura de arquivos

```
web/
├── server.py                # Backend FastAPI (API REST + WebSocket)
├── static/
│   ├── index.html           # Página principal (chat)
│   ├── style.css            # Estilos
│   └── app.js               # Lógica do frontend (WebSocket + UI)
scripts/
└── run_web.py               # Script para iniciar o servidor web
```

---

## Parte 1: Backend (`web/server.py`)

O backend expõe:
- **WebSocket `/ws/chat`** — canal bidirecional para conversa com o agente
- **GET `/api/status`** — retorna status atual do checklist (polling para sidebar)
- **GET `/api/cards`** — lista cards gerados
- **GET `/api/cards/{filename}`** — download de um card específico
- **GET `/`** — serve o frontend estático

```python
"""
Backend web — FastAPI com WebSocket para chat em tempo real.

O WebSocket mantém uma sessão de agente por conexão.
Cada conexão cria uma instância nova do SpecAgent.

Uso:
    python scripts/run_web.py
    # Abre http://localhost:8000
"""

import os
import sys
import json
import asyncio
import logging
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.agent import SpecAgent
from src.ingestion.llm_client import create_llm_client

logger = logging.getLogger(__name__)

# === Config ===

DB_PATH = os.environ.get("SILVER_DB", "data/silver/knowledge.db")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "data/output/cards")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")
LLM_MODEL = os.environ.get("LLM_MODEL_AGENT")

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o",
    "azure_openai": "gpt-4o",
}

# === App ===

app = FastAPI(title="Spec Agent", version="1.0.0")

# Servir arquivos estáticos
WEB_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

# Armazenar sessões ativas (WebSocket → SpecAgent)
active_sessions: dict = {}


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve a página principal."""
    html_path = WEB_DIR / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/status")
async def get_status(session_id: Optional[str] = None):
    """Retorna status do checklist do agente."""
    if session_id and session_id in active_sessions:
        agent = active_sessions[session_id]
        return JSONResponse(agent.get_status())
    return JSONResponse({"error": "Nenhuma sessão ativa"}, status_code=404)


@app.get("/api/cards")
async def list_cards():
    """Lista cards gerados."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cards = []
    for f in sorted(Path(OUTPUT_DIR).glob("*.md")):
        cards.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "url": f"/api/cards/{f.name}",
        })
    return JSONResponse({"cards": cards})


@app.get("/api/cards/{filename}")
async def get_card(filename: str):
    """Download de um card específico."""
    filepath = Path(OUTPUT_DIR) / filename
    if not filepath.exists() or not filepath.suffix == ".md":
        return JSONResponse({"error": "Card não encontrado"}, status_code=404)
    return FileResponse(filepath, media_type="text/markdown", filename=filename)


@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """WebSocket para chat em tempo real com o agente.

    Protocolo:
    - Cliente envia: {"type": "message", "content": "texto do usuário"}
    - Cliente envia: {"type": "command", "command": "/status"}
    - Servidor envia: {"type": "response", "content": "resposta do agente"}
    - Servidor envia: {"type": "status", "data": {...checklist...}}
    - Servidor envia: {"type": "card_generated", "data": {"filepath": "..."}}
    - Servidor envia: {"type": "error", "content": "mensagem de erro"}
    - Servidor envia: {"type": "thinking", "content": "Buscando na base..."} (feedback de progresso)
    """
    await ws.accept()
    session_id = str(id(ws))

    # Criar agente para esta sessão
    try:
        model = LLM_MODEL or DEFAULT_MODELS.get(LLM_PROVIDER)
        llm_client = create_llm_client(provider=LLM_PROVIDER, model=model)
        agent = SpecAgent(
            llm_client=llm_client,
            db_path=DB_PATH,
            output_dir=OUTPUT_DIR,
        )
        active_sessions[session_id] = agent
    except Exception as e:
        await ws.send_json({"type": "error", "content": f"Erro ao criar agente: {e}"})
        await ws.close()
        return

    # Mensagem de boas-vindas
    await ws.send_json({
        "type": "response",
        "content": (
            "Olá! Sou o **Spec Agent** — vou te ajudar a criar User Stories completas.\n\n"
            "Me diga qual feature quer especificar, o domínio de negócio, "
            "e se é feature nova ou evolução de existente."
        ),
    })
    await ws.send_json({"type": "status", "data": agent.get_status()})

    # Loop de mensagens
    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {"type": "message", "content": raw}

            msg_type = data.get("type", "message")

            if msg_type == "command":
                await _handle_command(ws, agent, data.get("command", ""))
                continue

            if msg_type == "message":
                content = data.get("content", "").strip()
                if not content:
                    continue

                # Feedback de thinking
                await ws.send_json({"type": "thinking", "content": "Processando..."})

                try:
                    response = await agent.chat(content)
                    await ws.send_json({"type": "response", "content": response})
                except Exception as e:
                    logger.error(f"Erro no agente: {e}", exc_info=True)
                    await ws.send_json({"type": "error", "content": f"Erro: {str(e)}"})

                # Sempre enviar status atualizado após cada mensagem
                await ws.send_json({"type": "status", "data": agent.get_status()})

                # Verificar se card foi gerado
                cards_dir = Path(OUTPUT_DIR)
                if cards_dir.exists():
                    cards = list(cards_dir.glob("*.md"))
                    if cards:
                        latest = max(cards, key=lambda f: f.stat().st_mtime)
                        await ws.send_json({
                            "type": "card_generated",
                            "data": {
                                "filename": latest.name,
                                "url": f"/api/cards/{latest.name}",
                            },
                        })

    except WebSocketDisconnect:
        logger.info(f"Sessão {session_id} desconectada")
    finally:
        if session_id in active_sessions:
            active_sessions[session_id].close()
            del active_sessions[session_id]


async def _handle_command(ws: WebSocket, agent: SpecAgent, command: str):
    """Processa comandos especiais (/status, /memory, /save, /generate)."""
    cmd = command.strip().lower()

    if cmd == "/status":
        await ws.send_json({"type": "status", "data": agent.get_status()})

    elif cmd == "/memory":
        summary = agent.memory.get_compact_summary()
        await ws.send_json({"type": "response", "content": f"```\n{summary}\n```"})

    elif cmd == "/save":
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        agent.memory.save_to_file(os.path.join(OUTPUT_DIR, "working_memory.json"))
        await ws.send_json({"type": "response", "content": "Working Memory salvo."})

    elif cmd == "/generate":
        response = await agent.chat("Gere o card agora com as informações que temos, mesmo que esteja incompleto.")
        await ws.send_json({"type": "response", "content": response})
        await ws.send_json({"type": "status", "data": agent.get_status()})

    else:
        await ws.send_json({"type": "error", "content": f"Comando desconhecido: {command}"})
```

---

## Parte 2: Frontend — HTML (`web/static/index.html`)

A interface tem 3 áreas: chat principal (centro), sidebar de status/checklist (direita), e header com info do projeto.

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spec Agent — Gerador de User Stories</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="layout">
        <!-- Header -->
        <header class="header">
            <div class="header-left">
                <h1>Spec Agent</h1>
                <span class="subtitle">Gerador Interativo de User Stories</span>
            </div>
            <div class="header-right">
                <span id="connection-status" class="status-badge disconnected">Desconectado</span>
            </div>
        </header>

        <!-- Main content -->
        <div class="main">
            <!-- Chat area -->
            <div class="chat-container">
                <div id="chat-messages" class="chat-messages">
                    <!-- Mensagens são inseridas aqui via JS -->
                </div>

                <div class="chat-input-area">
                    <textarea
                        id="chat-input"
                        placeholder="Descreva a funcionalidade que quer especificar..."
                        rows="2"
                    ></textarea>
                    <button id="send-btn" onclick="sendMessage()">Enviar</button>
                </div>

                <div class="chat-commands">
                    <button class="cmd-btn" onclick="sendCommand('/status')">/status</button>
                    <button class="cmd-btn" onclick="sendCommand('/memory')">/memory</button>
                    <button class="cmd-btn" onclick="sendCommand('/save')">/save</button>
                    <button class="cmd-btn" onclick="sendCommand('/generate')">/generate</button>
                </div>
            </div>

            <!-- Sidebar -->
            <aside class="sidebar">
                <!-- Checklist -->
                <div class="sidebar-section">
                    <h3>Checklist</h3>
                    <div id="checklist">
                        <div class="check-item" data-field="persona">
                            <span class="check-icon">○</span> Persona
                        </div>
                        <div class="check-item" data-field="action">
                            <span class="check-icon">○</span> Ação
                        </div>
                        <div class="check-item" data-field="benefit">
                            <span class="check-icon">○</span> Benefício
                        </div>
                        <div class="check-item" data-field="business_rules">
                            <span class="check-icon">○</span> Regras de negócio
                        </div>
                        <div class="check-item" data-field="main_flow">
                            <span class="check-icon">○</span> Fluxo principal
                        </div>
                        <div class="check-item" data-field="acceptance_criteria">
                            <span class="check-icon">○</span> Critérios de aceite
                        </div>
                        <div class="check-item" data-field="scope_defined">
                            <span class="check-icon">○</span> Escopo definido
                        </div>
                    </div>
                    <div id="checklist-progress" class="progress-bar">
                        <div id="progress-fill" class="progress-fill" style="width: 0%"></div>
                    </div>
                    <p id="checklist-label" class="progress-label">0/7 obrigatórios</p>
                </div>

                <!-- Info da sessão -->
                <div class="sidebar-section">
                    <h3>Sessão</h3>
                    <div id="session-info">
                        <p><strong>Fase:</strong> <span id="phase">coleta_inicial</span></p>
                        <p><strong>Contexto:</strong> <span id="context-tokens">0</span> tokens</p>
                        <p><strong>Refs base:</strong> <span id="knowledge-refs">0</span></p>
                        <p><strong>Contradições:</strong> <span id="observations">0</span></p>
                    </div>
                </div>

                <!-- Cards gerados -->
                <div class="sidebar-section">
                    <h3>Cards gerados</h3>
                    <div id="cards-list">
                        <p class="empty-state">Nenhum card gerado ainda.</p>
                    </div>
                </div>
            </aside>
        </div>
    </div>

    <script src="/static/app.js"></script>
</body>
</html>
```

---

## Parte 3: Frontend — CSS (`web/static/style.css`)

```css
/* === Reset e variáveis === */
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg-primary: #ffffff;
    --bg-secondary: #f5f5f0;
    --bg-tertiary: #eae8e0;
    --text-primary: #1a1a1a;
    --text-secondary: #6b6b6b;
    --accent: #c96442;
    --accent-light: #f0ddd4;
    --success: #2d8a4e;
    --success-light: #d4edda;
    --warning: #c08a30;
    --border: #d4d2ca;
    --radius: 8px;
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    --font-mono: "SF Mono", "Fira Code", monospace;
}

body {
    font-family: var(--font);
    background: var(--bg-secondary);
    color: var(--text-primary);
    height: 100vh;
    overflow: hidden;
}

/* === Layout === */
.layout {
    display: flex;
    flex-direction: column;
    height: 100vh;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 24px;
    background: var(--bg-primary);
    border-bottom: 1px solid var(--border);
}

.header h1 { font-size: 18px; font-weight: 600; }
.header .subtitle { font-size: 13px; color: var(--text-secondary); margin-left: 12px; }

.status-badge {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 12px;
    font-weight: 500;
}
.status-badge.connected { background: var(--success-light); color: var(--success); }
.status-badge.disconnected { background: var(--bg-tertiary); color: var(--text-secondary); }

.main {
    display: flex;
    flex: 1;
    overflow: hidden;
}

/* === Chat === */
.chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--bg-primary);
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.message {
    max-width: 85%;
    padding: 12px 16px;
    border-radius: var(--radius);
    line-height: 1.6;
    font-size: 14px;
    white-space: pre-wrap;
    word-wrap: break-word;
}

.message.user {
    align-self: flex-end;
    background: var(--accent);
    color: white;
    border-bottom-right-radius: 2px;
}

.message.agent {
    align-self: flex-start;
    background: var(--bg-secondary);
    color: var(--text-primary);
    border-bottom-left-radius: 2px;
}

.message.thinking {
    align-self: flex-start;
    background: transparent;
    color: var(--text-secondary);
    font-style: italic;
    padding: 4px 16px;
    font-size: 13px;
}

.message.error {
    align-self: flex-start;
    background: #fef2f2;
    color: #991b1b;
    border-left: 3px solid #dc2626;
}

/* === Input area === */
.chat-input-area {
    display: flex;
    gap: 8px;
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-primary);
}

.chat-input-area textarea {
    flex: 1;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-family: var(--font);
    font-size: 14px;
    resize: none;
    outline: none;
    line-height: 1.5;
}

.chat-input-area textarea:focus { border-color: var(--accent); }

.chat-input-area button {
    padding: 10px 20px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--radius);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
}

.chat-input-area button:hover { opacity: 0.9; }
.chat-input-area button:disabled { opacity: 0.5; cursor: not-allowed; }

.chat-commands {
    display: flex;
    gap: 6px;
    padding: 6px 20px 12px;
}

.cmd-btn {
    padding: 4px 10px;
    background: var(--bg-secondary);
    border: 1px solid var(--border);
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 12px;
    cursor: pointer;
    color: var(--text-secondary);
}

.cmd-btn:hover { background: var(--bg-tertiary); color: var(--text-primary); }

/* === Sidebar === */
.sidebar {
    width: 280px;
    background: var(--bg-primary);
    border-left: 1px solid var(--border);
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.sidebar-section h3 {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-secondary);
    margin-bottom: 10px;
}

/* === Checklist === */
.check-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    font-size: 13px;
    color: var(--text-secondary);
    transition: color 0.2s;
}

.check-item.done { color: var(--success); }
.check-item.done .check-icon { color: var(--success); }
.check-icon { font-size: 14px; }

.progress-bar {
    height: 6px;
    background: var(--bg-tertiary);
    border-radius: 3px;
    margin-top: 10px;
    overflow: hidden;
}

.progress-fill {
    height: 100%;
    background: var(--success);
    border-radius: 3px;
    transition: width 0.3s ease;
}

.progress-label {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 4px;
}

/* === Session info === */
#session-info p {
    font-size: 13px;
    margin-bottom: 4px;
}

/* === Cards list === */
#cards-list .empty-state {
    font-size: 13px;
    color: var(--text-secondary);
    font-style: italic;
}

.card-link {
    display: block;
    padding: 8px 10px;
    background: var(--bg-secondary);
    border-radius: var(--radius);
    text-decoration: none;
    color: var(--text-primary);
    font-size: 13px;
    margin-bottom: 6px;
}

.card-link:hover { background: var(--bg-tertiary); }

/* === Responsive === */
@media (max-width: 768px) {
    .sidebar { display: none; }
}
```

---

## Parte 4: Frontend — JavaScript (`web/static/app.js`)

```javascript
/**
 * Spec Agent — Frontend
 *
 * Gerencia a conexão WebSocket, renderiza mensagens,
 * e atualiza o sidebar de status em tempo real.
 */

let ws = null;
let isConnected = false;

// === WebSocket ===

function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/chat`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        isConnected = true;
        updateConnectionStatus(true);
        console.log('WebSocket conectado');
    };

    ws.onclose = () => {
        isConnected = false;
        updateConnectionStatus(false);
        console.log('WebSocket desconectado. Reconectando em 3s...');
        setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
        console.error('WebSocket erro:', err);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };
}

function handleServerMessage(data) {
    switch (data.type) {
        case 'response':
            removeThinking();
            addMessage('agent', data.content);
            break;

        case 'thinking':
            showThinking(data.content);
            break;

        case 'status':
            updateStatus(data.data);
            break;

        case 'card_generated':
            addCardToSidebar(data.data);
            break;

        case 'error':
            removeThinking();
            addMessage('error', data.content);
            break;

        default:
            console.warn('Tipo de mensagem desconhecido:', data.type);
    }
}

// === Enviar mensagens ===

function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text || !isConnected) return;

    addMessage('user', text);
    ws.send(JSON.stringify({ type: 'message', content: text }));
    input.value = '';
    input.style.height = 'auto';
    document.getElementById('send-btn').disabled = true;
    setTimeout(() => { document.getElementById('send-btn').disabled = false; }, 1000);
}

function sendCommand(cmd) {
    if (!isConnected) return;
    ws.send(JSON.stringify({ type: 'command', command: cmd }));
}

// === Renderizar mensagens ===

function addMessage(type, content) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `message ${type}`;

    // Renderização básica de markdown
    div.innerHTML = renderBasicMarkdown(content);

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function showThinking(text) {
    removeThinking();
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'message thinking';
    div.id = 'thinking-indicator';
    div.textContent = text || 'Processando...';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function removeThinking() {
    const el = document.getElementById('thinking-indicator');
    if (el) el.remove();
}

function renderBasicMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

// === Atualizar sidebar ===

function updateStatus(status) {
    // Checklist
    if (status.checklist) {
        const items = document.querySelectorAll('.check-item');
        let filled = 0;
        let total = items.length;

        items.forEach(item => {
            const field = item.dataset.field;
            const done = status.checklist[field] || false;
            item.classList.toggle('done', done);
            item.querySelector('.check-icon').textContent = done ? '●' : '○';
            if (done) filled++;
        });

        // Progress bar
        const pct = (filled / total) * 100;
        document.getElementById('progress-fill').style.width = `${pct}%`;
        document.getElementById('checklist-label').textContent = `${filled}/${total} obrigatórios`;
    }

    // Session info
    if (status.phase) {
        document.getElementById('phase').textContent = status.phase;
    }
    if (status.estimated_context_tokens !== undefined) {
        document.getElementById('context-tokens').textContent =
            Math.round(status.estimated_context_tokens).toLocaleString();
    }
    if (status.knowledge_refs !== undefined) {
        document.getElementById('knowledge-refs').textContent = status.knowledge_refs;
    }
    if (status.observations !== undefined) {
        document.getElementById('observations').textContent = status.observations;
    }
}

function updateConnectionStatus(connected) {
    const el = document.getElementById('connection-status');
    el.textContent = connected ? 'Conectado' : 'Desconectado';
    el.className = `status-badge ${connected ? 'connected' : 'disconnected'}`;
}

function addCardToSidebar(data) {
    const container = document.getElementById('cards-list');
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    // Evitar duplicatas
    if (container.querySelector(`[data-filename="${data.filename}"]`)) return;

    const link = document.createElement('a');
    link.className = 'card-link';
    link.href = data.url;
    link.target = '_blank';
    link.dataset.filename = data.filename;
    link.textContent = data.filename;
    container.appendChild(link);
}

// === Event listeners ===

document.getElementById('chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-resize textarea
document.getElementById('chat-input').addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

// === Inicializar ===

connect();
```

---

## Parte 5: Script de inicialização (`scripts/run_web.py`)

```python
#!/usr/bin/env python3
"""
Inicia o servidor web do Spec Agent.

Uso:
    python scripts/run_web.py
    python scripts/run_web.py --port 3000
    python scripts/run_web.py --host 0.0.0.0 --port 8080
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Spec Agent — Servidor Web")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload em mudanças")
    args = parser.parse_args()

    # Verificar base Silver
    db_path = os.environ.get("SILVER_DB", "data/silver/knowledge.db")
    if not os.path.exists(db_path):
        print(f"❌ Base Silver não encontrada: {db_path}")
        print("   Execute: make all")
        sys.exit(1)

    print(f"🌐 Iniciando Spec Agent Web em http://{args.host}:{args.port}")
    print(f"   Base: {db_path}")
    print(f"   LLM: {os.environ.get('LLM_PROVIDER', 'anthropic')}")
    print()

    import uvicorn
    uvicorn.run(
        "web.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
```

---

## Parte 6: Atualização do Makefile (adicionar target web)

Adicionar ao Makefile da Etapa 5:

```makefile
## Inicia o servidor web
web:
	@$(PYTHON) scripts/run_web.py

## Inicia o servidor web com auto-reload (dev)
web-dev:
	@$(PYTHON) scripts/run_web.py --reload
```

## Atualização do requirements.txt

Adicionar:

```text
# Web (Etapa 6)
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
websockets>=12.0
```

---

## Validação da Etapa 6

```bash
# 1. Instalar deps adicionais
pip install fastapi uvicorn[standard] websockets

# 2. Verificar arquivos
ls -la web/server.py
ls -la web/static/index.html
ls -la web/static/style.css
ls -la web/static/app.js
ls -la scripts/run_web.py

# 3. Iniciar servidor (requer base Silver populada + API key)
make web

# 4. Abrir no navegador
# http://localhost:8000

# 5. Testar:
#    - Conexão WebSocket (badge "Conectado" no header)
#    - Enviar mensagem e receber resposta
#    - Checklist atualiza no sidebar
#    - Comandos /status /memory /save /generate funcionam
#    - Card gerado aparece no sidebar com link de download
```

## Critérios de aceite da Etapa 6

- [ ] `web/server.py` — FastAPI com WebSocket `/ws/chat`, endpoints REST para status/cards, serve frontend estático
- [ ] `web/static/index.html` — layout com chat (centro) e sidebar (direita) com checklist
- [ ] `web/static/style.css` — design limpo, responsivo, sem dependências externas
- [ ] `web/static/app.js` — WebSocket com reconexão, renderização de mensagens, atualização de checklist em tempo real
- [ ] `scripts/run_web.py` — inicializa servidor com validação de base Silver
- [ ] WebSocket conecta e mantém sessão com agente
- [ ] Mensagens do usuário são enviadas e respostas do agente renderizadas
- [ ] Checklist sidebar atualiza em tempo real após cada mensagem
- [ ] Cards gerados aparecem no sidebar com link de download
- [ ] Comandos /status /memory /save /generate funcionam via botões
- [ ] Interface funciona em Chrome, Firefox e Safari
- [ ] Servidor roda em localhost sem configuração adicional além da API key
