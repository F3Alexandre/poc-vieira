#!/usr/bin/env python3
"""
Demo automatizada — simula uma conversa completa com o agente.

Executa uma sequência pré-definida de mensagens que exercita
o fluxo completo: coleta → busca na base → especificação → geração do card.

Uso:
    python scripts/demo.py
    python scripts/demo.py --step-by-step     # Pausa entre cada mensagem (Enter para continuar)
    python scripts/demo.py --provider openai   # Usa OpenAI em vez de Anthropic
"""

import os
import sys
import asyncio
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent.agent import SpecAgent
from src.ingestion.llm_client import create_llm_client

# === Roteiro da demo ===
# Cada item é uma mensagem do "usuário" simulado.
# O agente responde naturalmente a cada uma.

DEMO_SCRIPT = [
    {
        "label": "1. Início — Usuário quer especificar uma feature",
        "message": (
            "Preciso criar a especificação da funcionalidade de devolução de produtos. "
            "É uma evolução de feature existente, no domínio de pós-venda. "
            "Os stakeholders são Ana (PO) e Carlos (Arquiteto)."
        ),
    },
    {
        "label": "2. Contexto — Usuário pede para buscar na base",
        "message": (
            "Busque na base o que já temos documentado sobre essa feature. "
            "Quero entender o que já foi decidido antes de começar."
        ),
    },
    {
        "label": "3. Persona e ação — Usuário descreve a User Story",
        "message": (
            "A user story é: como cliente pessoa física, eu quero solicitar a devolução "
            "de um produto pelo aplicativo, para que eu receba o reembolso sem precisar "
            "ligar para o SAC. O fluxo é: o cliente acessa Meus Pedidos, seleciona o pedido, "
            "clica em Solicitar Devolução, escolhe o motivo, anexa foto se necessário, "
            "escolhe entre estorno no cartão ou crédito na loja, e confirma. "
            "Depois recebe uma etiqueta de envio por email."
        ),
    },
    {
        "label": "4. Contradição — Usuário menciona prazo diferente da base",
        "message": (
            "O prazo de devolução é de 45 dias úteis a partir da entrega."
        ),
    },
    {
        "label": "5. Escopo — Usuário define o que está dentro e fora",
        "message": (
            "Dentro do escopo: devolução de produto físico para pessoa física, "
            "estorno no cartão ou crédito na loja, geração de etiqueta de envio reverso. "
            "Fora do escopo: troca de produto (é outra feature), devolução parcial "
            "(fica para a versão 2), e devolução de produtos digitais."
        ),
    },
    {
        "label": "6. Critérios — Usuário define critérios de aceite",
        "message": (
            "Critérios de aceite: dado que o pedido foi entregue dentro do prazo, "
            "quando o cliente solicita devolução, então um protocolo é gerado e email "
            "é enviado. Dado que o prazo expirou, quando tenta solicitar, então a "
            "solicitação é negada com mensagem clara. Critério técnico: o endpoint "
            "de criação deve responder em até 200ms no p95."
        ),
    },
    {
        "label": "7. Geração — Solicitar criação do card",
        "message": (
            "Gere o card completo com todas as informações que temos."
        ),
    },
]


def print_separator():
    print("\n" + "─" * 60 + "\n")


async def run_demo(args):
    """Executa a demo."""

    # Setup
    db_path = os.environ.get("SILVER_DB", "data/silver/knowledge.db")
    output_dir = os.environ.get("OUTPUT_DIR", "data/output/cards")

    if not os.path.exists(db_path):
        print("❌ Base Silver não encontrada. Execute: make seed && make ingest")
        sys.exit(1)

    # LLM client
    provider = args.provider or os.environ.get("LLM_PROVIDER", "anthropic")
    model = args.model or os.environ.get("LLM_MODEL_AGENT")

    default_models = {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "azure_openai": "gpt-4o",
    }
    model = model or default_models.get(provider)

    try:
        llm_client = create_llm_client(provider=provider, model=model)
    except Exception as e:
        print(f"❌ Erro ao criar LLM client: {e}")
        sys.exit(1)

    agent = SpecAgent(llm_client=llm_client, db_path=db_path, output_dir=output_dir)

    # Header
    print("=" * 60)
    print("  DEMO — Knowledge Base + Spec Agent")
    print("=" * 60)
    print(f"  LLM: {provider}/{model}")
    print(f"  Base: {db_path}")
    print(f"  Output: {output_dir}")
    print(f"  Passos: {len(DEMO_SCRIPT)}")
    if args.step_by_step:
        print("  Modo: step-by-step (Enter para avançar)")
    print("=" * 60)

    # Executar roteiro
    for i, step in enumerate(DEMO_SCRIPT):
        print_separator()
        print(f"📋 {step['label']}")
        print_separator()

        # Mostrar mensagem do usuário
        print(f"👤 Usuário:")
        print(f"   {step['message']}")
        print()

        # Pausar se step-by-step
        if args.step_by_step:
            input("   [Enter para enviar ao agente...]")
            print()

        # Enviar ao agente
        start = time.time()
        try:
            print(f"🤖 Agente:")
            response = await agent.chat(step["message"])
            elapsed = time.time() - start

            # Indentar resposta
            for line in response.split("\n"):
                print(f"   {line}")
            print()
            print(f"   ⏱ {elapsed:.1f}s")

        except Exception as e:
            print(f"   ❌ Erro: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

        # Mostrar status do checklist
        status = agent.get_status()
        filled = status["filled"]
        missing = status["missing"]
        print(f"   📊 Checklist: {filled} | Fase: {status['phase']}")
        if missing:
            print(f"   📝 Faltando: {', '.join(missing)}")

    # Resultado final
    print_separator()
    print("=" * 60)
    print("  DEMO CONCLUÍDA")
    print("=" * 60)
    print()

    # Verificar cards gerados
    cards = [f for f in os.listdir(output_dir) if f.endswith(".md")] if os.path.exists(output_dir) else []
    if cards:
        print(f"  📄 Cards gerados ({len(cards)}):")
        for card in sorted(cards):
            filepath = os.path.join(output_dir, card)
            size = os.path.getsize(filepath)
            print(f"     {card} ({size} bytes)")
        print()
        print(f"  Para ver o card: cat {os.path.join(output_dir, cards[0])}")
    else:
        print("  ⚠️  Nenhum card gerado. O agente pode não ter completado o fluxo.")
        print("  Tente executar: make agent (modo interativo)")

    print()
    agent.close()


def main():
    parser = argparse.ArgumentParser(description="Demo automatizada do Spec Agent")
    parser.add_argument("--step-by-step", action="store_true", help="Pausar entre cada mensagem")
    parser.add_argument("--provider", default=None, help="LLM provider")
    parser.add_argument("--model", default=None, help="Modelo LLM")
    parser.add_argument("--verbose", action="store_true", help="Log detalhado")
    args = parser.parse_args()

    asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
