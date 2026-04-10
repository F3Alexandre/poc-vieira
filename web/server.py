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

# Carregar .env se existir (override=True para sobrescrever vars vazias do ambiente)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass

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
    """Redireciona para /static/index.html onde os caminhos relativos resolvem."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


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
