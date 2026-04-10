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

# Carregar .env se existir (override=True para sobrescrever vars vazias do ambiente)
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser(description="Spec Agent — Servidor Web")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Porta (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Auto-reload em mudanças")
    args = parser.parse_args()

    # Verificar base Silver
    db_path = os.environ.get("SILVER_DB", "data/silver/knowledge.db")
    if not os.path.exists(db_path):
        print(f"Base Silver não encontrada: {db_path}")
        print("   Execute: make all")
        sys.exit(1)

    print(f"Iniciando Spec Agent Web em http://{args.host}:{args.port}")
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
