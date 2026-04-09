#!/usr/bin/env python3
"""
Script para rodar o agente em modo CLI interativo.

Uso:
    python scripts/run_agent.py
    python scripts/run_agent.py --provider anthropic --model claude-sonnet-4-6
    python scripts/run_agent.py --db-path data/silver/knowledge.db
"""

import os
import sys
import asyncio
import argparse
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.agent import SpecAgent
from src.ingestion.llm_client import create_llm_client


def parse_args():
    parser = argparse.ArgumentParser(description="Spec Agent — Gerador interativo de User Stories")
    parser.add_argument("--db-path", default="data/silver/knowledge.db", help="Base Silver")
    parser.add_argument("--output-dir", default="data/output/cards", help="Diretório de output")
    parser.add_argument("--provider", default="anthropic", choices=["anthropic", "openai", "azure_openai"])
    parser.add_argument("--model", default=None, help="Modelo LLM")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    return parser.parse_args()


def print_status(agent):
    """Exibe status do agente."""
    status = agent.get_status()
    bar_len = int(status["filled"].split("/")[1])
    bar_filled = int(status["filled"].split("/")[0])
    bar = "█" * bar_filled + "░" * (bar_len - bar_filled)
    print(f"\n  [{bar}] {status['filled']} campos obrigatórios | Fase: {status['phase']} | Contexto: ~{status['estimated_context_tokens']} tokens")
    if status["missing"]:
        print(f"  Faltando: {', '.join(status['missing'])}")
    if status["observations"] > 0:
        print(f"  ⚠️  {status['observations']} observações/contradições detectadas")
    print()


async def main():
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")

    # Verificar base Silver
    if not os.path.exists(args.db_path):
        print(f"❌ Base Silver não encontrada: {args.db_path}")
        print("   Execute primeiro: python scripts/run_ingestion.py")
        sys.exit(1)

    # Criar LLM client (modelo mais capaz para o agente)
    default_models = {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "azure_openai": "gpt-4o",
    }
    model = args.model or default_models.get(args.provider, "gpt-4o")

    try:
        llm_client = create_llm_client(provider=args.provider, model=model)
    except (ImportError, ValueError) as e:
        print(f"❌ Erro ao criar LLM client: {e}")
        sys.exit(1)

    # Criar agente
    agent = SpecAgent(
        llm_client=llm_client,
        db_path=args.db_path,
        output_dir=args.output_dir,
    )

    # Header
    print("=" * 60)
    print("  SPEC AGENT — Gerador Interativo de User Stories")
    print("=" * 60)
    print(f"  LLM: {args.provider}/{model}")
    print(f"  Base: {args.db_path}")
    print(f"  Output: {args.output_dir}")
    print()
    print("  Comandos especiais:")
    print("    /status   — mostra checklist e estado atual")
    print("    /memory   — mostra Working Memory completo")
    print("    /save     — salva estado em arquivo")
    print("    /generate — força geração do card (mesmo incompleto)")
    print("    /quit     — encerra")
    print("=" * 60)
    print()

    # Loop interativo
    while True:
        try:
            user_input = input("Você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break

        if not user_input:
            continue

        # Comandos especiais
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/quit":
                print("Encerrando. Até mais!")
                break
            elif cmd == "/status":
                print_status(agent)
                continue
            elif cmd == "/memory":
                print("\n" + agent.memory.get_compact_summary() + "\n")
                continue
            elif cmd == "/save":
                os.makedirs(args.output_dir, exist_ok=True)
                agent.memory.save_to_file(os.path.join(args.output_dir, "working_memory.json"))
                print("✓ Working Memory salvo.\n")
                continue
            elif cmd == "/generate":
                user_input = "Gere o card agora com as informações que temos, mesmo que esteja incompleto."
            else:
                print(f"Comando desconhecido: {cmd}")
                continue

        # Chat com o agente
        try:
            print("\nAgente > ", end="", flush=True)
            response = await agent.chat(user_input)
            print(response)
            print()
        except Exception as e:
            print(f"\n❌ Erro: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            print()

    agent.close()


if __name__ == "__main__":
    asyncio.run(main())
