# SPEC — Etapa 5: Integração End-to-End e Script de Demo

## Objetivo

Integrar todas as etapas anteriores (1-4) em um fluxo único executável, com scripts de setup, validação automática, e um roteiro de demo para a apresentação. Esta etapa garante que tudo funciona junto e prepara a execução da demo de sexta-feira.

**Esta etapa NÃO inclui a aplicação web.** O agente roda via CLI (scripts/run_agent.py). A aplicação web com interface de chat é a Etapa 6 (spec separada).

## Dependências

- **Etapas 1-4 concluídas e testadas individualmente**
- **API key do LLM configurada** (ANTHROPIC_API_KEY ou OPENAI_API_KEY)

## Estrutura de arquivos

```
knowledge-base-mvp/
├── scripts/
│   ├── setup.sh                # Setup completo do projeto (deps + estrutura)
│   ├── seed_bronze.py          # (Etapa 1) Cria dados simulados
│   ├── run_ingestion.py        # (Etapa 3) Pipeline de ingestão
│   ├── run_agent.py            # (Etapa 4) Agente CLI
│   ├── validate_all.py         # Validação completa de todas as etapas
│   └── demo.py                 # Script de demo automatizada (conversa pré-definida)
├── requirements.txt            # Dependências Python
├── .env.example                # Template de variáveis de ambiente
├── README.md                   # Documentação do projeto
└── Makefile                    # Atalhos para comandos comuns
```

---

## Parte 1: requirements.txt

```text
# LLM Clients (instalar um dos dois)
anthropic>=0.40.0
# openai>=1.50.0

# Nenhuma outra dependência externa.
# O projeto usa apenas stdlib do Python:
# - sqlite3 (FTS5)
# - json, uuid, hashlib, dataclasses
# - asyncio, argparse, logging
# - os, sys, re, time, tempfile
```

---

## Parte 2: Variáveis de ambiente (`.env.example`)

```bash
# === LLM Provider ===
# Escolha UM provider e configure a API key correspondente

# Opção A: Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...
LLM_PROVIDER=anthropic
LLM_MODEL_INGESTION=claude-haiku-4-5-20251001
LLM_MODEL_AGENT=claude-sonnet-4-6

# Opção B: OpenAI
# OPENAI_API_KEY=sk-...
# LLM_PROVIDER=openai
# LLM_MODEL_INGESTION=gpt-4o-mini
# LLM_MODEL_AGENT=gpt-4o

# Opção C: Azure OpenAI
# AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
# LLM_PROVIDER=azure_openai
# LLM_MODEL_INGESTION=gpt-4o-mini
# LLM_MODEL_AGENT=gpt-4o

# === Paths ===
BRONZE_DIR=data/bronze
SILVER_DB=data/silver/knowledge.db
OUTPUT_DIR=data/output/cards
```

---

## Parte 3: Script de setup (`scripts/setup.sh`)

```bash
#!/bin/bash
set -e

echo "================================================"
echo "  SETUP — Knowledge Base MVP"
echo "================================================"
echo ""

# 1. Verificar Python
PYTHON=$(command -v python3 || command -v python)
if [ -z "$PYTHON" ]; then
    echo "❌ Python 3 não encontrado. Instale Python 3.11+."
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PY_VERSION encontrado ($PYTHON)"

# 2. Verificar FTS5
$PYTHON -c "
import sqlite3
conn = sqlite3.connect(':memory:')
conn.execute('CREATE VIRTUAL TABLE t USING fts5(c)')
conn.close()
print('✓ SQLite FTS5 disponível')
" || { echo "❌ FTS5 não disponível. Atualize o SQLite."; exit 1; }

# 3. Instalar dependências
echo ""
echo ">>> Instalando dependências..."
$PYTHON -m pip install -r requirements.txt --quiet
echo "✓ Dependências instaladas"

# 4. Verificar API key
if [ -f .env ]; then
    source .env
fi

if [ -z "$ANTHROPIC_API_KEY" ] && [ -z "$OPENAI_API_KEY" ] && [ -z "$AZURE_OPENAI_API_KEY" ]; then
    echo ""
    echo "⚠️  Nenhuma API key configurada."
    echo "   Copie .env.example para .env e configure sua key."
    echo "   Os testes com mock funcionam sem key."
fi

# 5. Criar estrutura de diretórios
echo ""
echo ">>> Criando estrutura de diretórios..."
mkdir -p data/bronze/calls
mkdir -p data/bronze/docs
mkdir -p data/bronze/chats
mkdir -p data/silver
mkdir -p data/output/cards
mkdir -p src/ingestion
mkdir -p src/knowledge
mkdir -p src/agent
mkdir -p tests
mkdir -p scripts

# Criar __init__.py se não existem
touch src/__init__.py
touch src/ingestion/__init__.py
touch src/knowledge/__init__.py
touch src/agent/__init__.py
touch tests/__init__.py

echo "✓ Estrutura criada"

# 6. Verificar que os módulos importam
echo ""
echo ">>> Verificando imports..."
$PYTHON -c "
import sys
sys.path.insert(0, '.')
errors = []
try:
    from src.knowledge.schema import init_db, Chunk, CHUNK_TYPES
except ImportError as e:
    errors.append(f'knowledge.schema: {e}')
try:
    from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
except ImportError as e:
    errors.append(f'knowledge.search: {e}')
try:
    from src.knowledge.manifest import get_feature_manifest
except ImportError as e:
    errors.append(f'knowledge.manifest: {e}')
try:
    from src.ingestion.extractor import extract_text
except ImportError as e:
    errors.append(f'ingestion.extractor: {e}')
try:
    from src.ingestion.chunker import chunk_and_classify
except ImportError as e:
    errors.append(f'ingestion.chunker: {e}')
try:
    from src.ingestion.pipeline import run_ingestion
except ImportError as e:
    errors.append(f'ingestion.pipeline: {e}')
try:
    from src.agent.memory import WorkingMemory
except ImportError as e:
    errors.append(f'agent.memory: {e}')
try:
    from src.agent.agent import SpecAgent
except ImportError as e:
    errors.append(f'agent.agent: {e}')

if errors:
    print('❌ Erros de import:')
    for e in errors:
        print(f'   {e}')
    sys.exit(1)
else:
    print('✓ Todos os módulos importam corretamente')
"

echo ""
echo "================================================"
echo "  SETUP COMPLETO"
echo "================================================"
echo ""
echo "Próximos passos:"
echo "  1. Configure .env com sua API key"
echo "  2. make seed      — gera dados bronze simulados"
echo "  3. make ingest    — roda pipeline de ingestão"
echo "  4. make test      — roda todos os testes"
echo "  5. make agent     — inicia o agente CLI"
echo "  6. make demo      — roda demo automatizada"
echo ""
```

---

## Parte 4: Makefile

```makefile
.PHONY: setup seed ingest test agent demo validate clean

# Detectar python
PYTHON := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)

# Carregar .env se existir
ifneq (,$(wildcard .env))
    include .env
    export
endif

## Setup completo do projeto
setup:
	@chmod +x scripts/setup.sh
	@bash scripts/setup.sh

## Gera dados bronze simulados (Etapa 1)
seed:
	@echo ">>> Gerando dados bronze..."
	@$(PYTHON) scripts/seed_bronze.py

## Roda pipeline de ingestão (Etapa 3)
ingest:
	@echo ">>> Rodando ingestão Bronze → Silver..."
	@$(PYTHON) scripts/run_ingestion.py --verbose

## Roda TODOS os testes (sem API key)
test:
	@echo ">>> Rodando testes..."
	@echo ""
	@echo "--- Testes da base de conhecimento (Etapa 2) ---"
	@$(PYTHON) tests/test_knowledge_base.py
	@echo ""
	@echo "--- Testes do pipeline de ingestão (Etapa 3) ---"
	@$(PYTHON) tests/test_ingestion.py
	@echo ""
	@echo "--- Testes do agente (Etapa 4) ---"
	@$(PYTHON) tests/test_agent.py
	@echo ""
	@echo "=== TODOS OS TESTES PASSARAM ==="

## Inicia o agente CLI interativo (Etapa 4)
agent:
	@$(PYTHON) scripts/run_agent.py

## Roda demo automatizada (Etapa 5)
demo:
	@$(PYTHON) scripts/demo.py

## Validação completa de todas as etapas
validate:
	@$(PYTHON) scripts/validate_all.py

## Limpa dados gerados (mantém bronze)
clean:
	@echo ">>> Limpando dados gerados..."
	@rm -f data/silver/knowledge.db
	@rm -rf data/output/cards/*
	@echo "✓ Limpo. Dados bronze mantidos."

## Reset completo (limpa tudo incluindo bronze)
reset:
	@echo ">>> Reset completo..."
	@rm -rf data/
	@echo "✓ Tudo removido. Execute 'make setup && make seed' para recomeçar."

## Pipeline completo: seed → ingest → validate
all: seed ingest validate
	@echo ""
	@echo "=== Pipeline completo executado com sucesso ==="
	@echo "Execute 'make agent' para iniciar o agente."
```

---

## Parte 5: Script de validação completa (`scripts/validate_all.py`)

```python
#!/usr/bin/env python3
"""
Validação completa — verifica que todas as etapas estão funcionais.

Verifica:
1. Dados bronze existem e têm conteúdo
2. Base Silver está populada e FTS5 funciona
3. Busca retorna resultados relevantes
4. Manifesto de features está correto
5. Working Memory funciona
6. Card generator produz output válido

Rodar: python scripts/validate_all.py
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(description: str, condition: bool, detail: str = ""):
    """Helper de validação."""
    if condition:
        print(f"  ✓ {description}")
    else:
        print(f"  ✗ {description}")
        if detail:
            print(f"    → {detail}")
    return condition


def validate_bronze():
    """Valida Etapa 1 — dados bronze."""
    print("\n=== ETAPA 1: Dados Bronze ===")
    ok = True

    expected = [
        "data/bronze/calls/grooming-devolucao-2026-04-01.md",
        "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md",
        "data/bronze/docs/prd-devolucao-v2.md",
        "data/bronze/docs/requisitos-cliente-enterprise.md",
        "data/bronze/chats/slack-devolucao-2026-04-03.md",
    ]

    for filepath in expected:
        exists = os.path.exists(filepath)
        if exists:
            with open(filepath, "r", encoding="utf-8") as f:
                words = len(f.read().split())
            ok &= check(f"{os.path.basename(filepath)} ({words} palavras)", words >= 200, f"Muito curto: {words} palavras")
        else:
            ok &= check(f"{os.path.basename(filepath)}", False, "Arquivo não encontrado")

    return ok


def validate_silver():
    """Valida Etapa 2+3 — base Silver populada."""
    print("\n=== ETAPA 2+3: Base Silver ===")
    ok = True

    db_path = "data/silver/knowledge.db"
    ok &= check("Banco existe", os.path.exists(db_path), f"{db_path} não encontrado")

    if not os.path.exists(db_path):
        return False

    from src.knowledge.schema import init_db, get_db_stats
    from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
    from src.knowledge.manifest import get_feature_manifest

    conn = init_db(db_path)
    stats = get_db_stats(conn)

    ok &= check(
        f"Chunks na base: {stats['total_chunks']}",
        stats["total_chunks"] >= 10,
        f"Esperado >= 10 chunks, tem {stats['total_chunks']}"
    )

    ok &= check(
        f"Chunks ativos: {stats['active_chunks']}",
        stats["active_chunks"] >= 10,
        ""
    )

    type_count = len(stats.get("chunks_by_type", {}))
    ok &= check(
        f"Tipos de chunk: {type_count} tipos diferentes",
        type_count >= 3,
        f"Esperado >= 3 tipos, tem {type_count}"
    )

    # Testar FTS5
    try:
        cursor = conn.execute("""
            SELECT COUNT(*) FROM chunks c
            JOIN chunks_fts fts ON c.id = fts.id
            WHERE chunks_fts MATCH 'devolução OR devolucao'
        """)
        fts_count = cursor.fetchone()[0]
        ok &= check(f"FTS5 funciona: {fts_count} resultados para 'devolução'", fts_count > 0)
    except Exception as e:
        ok &= check("FTS5 funciona", False, str(e))

    # Testar busca com filtros
    search = KnowledgeBaseSearch(db_path)
    results = search.search(SearchQuery(
        text="prazo devolução",
        feature="devolucao_produtos",
        top_k=5,
    ))
    ok &= check(
        f"Busca 'prazo devolução': {len(results)} resultados",
        len(results) > 0,
    )

    # Testar manifesto
    manifest = get_feature_manifest(conn)
    ok &= check(
        f"Manifesto: {len(manifest)} features",
        len(manifest) >= 1,
    )

    features = [m["feature"] for m in manifest]
    ok &= check(
        "Feature 'devolucao_produtos' no manifesto",
        "devolucao_produtos" in features,
        f"Features encontradas: {features}"
    )

    search.close()
    conn.close()
    return ok


def validate_agent_components():
    """Valida Etapa 4 — componentes do agente."""
    print("\n=== ETAPA 4: Componentes do Agente ===")
    ok = True

    # Working Memory
    from src.agent.memory import WorkingMemory

    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.persona = "cliente PF"
    wm.action = "solicitar devolução"
    wm.benefit = "receber reembolso"
    wm.business_rules = [{"id": "RN-01", "rule": "Prazo 30 dias"}]
    wm.main_flow = ["Passo 1", "Passo 2", "Passo 3"]
    wm.acceptance_criteria_product = [
        {"id": "CA-01", "given": "x", "when": "y", "then": "z"},
        {"id": "CA-02", "given": "a", "when": "b", "then": "c"},
    ]
    wm.in_scope = ["item 1"]
    wm.out_of_scope = [{"item": "item 2", "reason": "fase 2"}]

    ok &= check("WorkingMemory.is_ready_to_generate()", wm.is_ready_to_generate())

    json_str = wm.to_json()
    wm2 = WorkingMemory.from_json(json_str)
    ok &= check("WorkingMemory serializa/deserializa", wm2.feature == "devolucao_produtos")

    summary = wm.get_compact_summary()
    ok &= check("WorkingMemory.get_compact_summary()", len(summary) > 50)

    # Card Generator
    import tempfile
    from src.agent.card_generator import generate_card_markdown

    tmp = tempfile.mkdtemp()
    filepath = generate_card_markdown(wm, tmp)
    ok &= check("Card gerado", os.path.exists(filepath))

    content = open(filepath, "r", encoding="utf-8").read()
    ok &= check("Card tem seção Metadados", "## Metadados" in content)
    ok &= check("Card tem seção User Story", "## User Story" in content)
    ok &= check("Card tem seção Regras", "## Regras de negócio" in content)
    ok &= check("Card tem seção Fluxo", "## Fluxo do usuário" in content)
    ok &= check("Card tem seção Critérios", "## Critérios de aceite" in content)
    ok &= check("Card tem seção Escopo", "## Definição de escopo" in content)

    import shutil
    shutil.rmtree(tmp)

    return ok


def main():
    print("=" * 60)
    print("  VALIDAÇÃO COMPLETA — Knowledge Base MVP")
    print("=" * 60)

    results = {}
    results["bronze"] = validate_bronze()
    results["silver"] = validate_silver()
    results["agent"] = validate_agent_components()

    # Resumo
    print("\n" + "=" * 60)
    print("  RESUMO")
    print("=" * 60)

    all_ok = True
    for etapa, ok in results.items():
        status = "✓ OK" if ok else "✗ FALHAS"
        print(f"  {etapa}: {status}")
        all_ok &= ok

    print()
    if all_ok:
        print("  ✅ TODAS AS VALIDAÇÕES PASSARAM")
        print("  O sistema está pronto para a demo.")
        print()
        print("  Execute: make agent")
        print("  Ou:      make demo")
    else:
        print("  ❌ EXISTEM FALHAS")
        print("  Corrija os problemas acima antes de prosseguir.")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## Parte 6: Script de demo automatizada (`scripts/demo.py`)

Este script simula uma conversa completa com o agente, mostrando o fluxo end-to-end sem interação manual. Útil para demonstrações ao vivo onde digitar pode ser lento ou arriscado.

```python
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
```

---

## Parte 7: README.md

```markdown
# Knowledge Base MVP — Base de Conhecimento Central + Spec Agent

Sistema que ingere documentação de produto (reuniões, PRDs, chats, documentos de clientes),
cria uma base de conhecimento estruturada, e usa um agente conversacional para gerar
User Stories completas a partir dessa base.

## Quick Start

```bash
# 1. Setup
cp .env.example .env
# Edite .env com sua API key

# 2. Instalar e validar
make setup

# 3. Pipeline completo: seed → ingest → validate
make all

# 4. Iniciar o agente
make agent

# 5. Ou rodar demo automatizada
make demo
```

## Arquitetura

```
Bronze (dados brutos)
  ↓ Pipeline de Ingestão (LLM classifica e segmenta)
Silver (SQLite + FTS5, chunks com metadados ricos)
  ↓ Busca (filtro metadados + FTS5)
Agente (conversa com usuário, busca na base, detecta contradições)
  ↓ Geração
Cards Markdown (template Azure DevOps)
```

## Comandos

| Comando | Descrição |
|---------|-----------|
| `make setup` | Instala dependências e valida ambiente |
| `make seed` | Gera dados simulados na Bronze |
| `make ingest` | Roda pipeline de ingestão (Bronze → Silver) |
| `make test` | Roda todos os testes (sem API key) |
| `make agent` | Inicia agente CLI interativo |
| `make demo` | Demo automatizada completa |
| `make validate` | Validação de todas as etapas |
| `make clean` | Limpa Silver e output (mantém Bronze) |
| `make reset` | Remove tudo (incluindo Bronze) |

## Comandos do Agente (modo CLI)

| Comando | Descrição |
|---------|-----------|
| `/status` | Mostra checklist e estado atual |
| `/memory` | Mostra Working Memory resumido |
| `/save` | Salva estado em arquivo |
| `/generate` | Força geração do card |
| `/quit` | Encerra |

## Estrutura do Projeto

```
├── data/
│   ├── bronze/          # Dados brutos (transcrições, docs, chats)
│   ├── silver/          # Base de conhecimento (SQLite + FTS5)
│   └── output/cards/    # Cards gerados (Markdown)
├── src/
│   ├── knowledge/       # Schema, busca, manifesto
│   ├── ingestion/       # Pipeline Bronze → Silver
│   └── agent/           # Agente conversacional
├── tests/               # Testes (rodam sem API key)
├── scripts/             # Scripts de execução
├── Makefile             # Atalhos
└── requirements.txt     # Dependências
```

## Testes

```bash
# Todos os testes (sem API key — usa mocks)
make test

# Testes individuais
python tests/test_knowledge_base.py    # 19 testes (Schema + Busca + Manifesto)
python tests/test_ingestion.py         # 19 testes (Extração + Chunking + Pipeline)
python tests/test_agent.py             # 13 testes (Memory + Cards + Agent Loop)
```
```

---

## Validação final da Etapa 5

```bash
# 1. Verificar que todos os arquivos existem
ls -la requirements.txt
ls -la .env.example
ls -la README.md
ls -la Makefile
ls -la scripts/setup.sh
ls -la scripts/validate_all.py
ls -la scripts/demo.py

# 2. Rodar setup
make setup

# 3. Rodar pipeline completo
make all

# 4. Rodar demo (com API key)
make demo

# OU demo step-by-step (para apresentação)
python scripts/demo.py --step-by-step
```

## Critérios de aceite da Etapa 5

- [ ] `requirements.txt` lista apenas anthropic (e opcionalmente openai)
- [ ] `.env.example` documenta todas as variáveis necessárias para os 3 providers
- [ ] `scripts/setup.sh` verifica Python, FTS5, instala deps, cria diretórios, valida imports
- [ ] `Makefile` tem targets: setup, seed, ingest, test, agent, demo, validate, clean, reset, all
- [ ] `scripts/validate_all.py` testa Bronze (5 arquivos), Silver (chunks + FTS5 + busca + manifesto), Agent (memory + card generator)
- [ ] `scripts/demo.py` executa roteiro de 7 passos com saída formatada, timing por step, e verificação de cards gerados
- [ ] `README.md` documenta quick start, arquitetura, comandos, estrutura
- [ ] `make test` roda os 51 testes (19 + 19 + 13) sem API key
- [ ] `make all` executa seed → ingest → validate sem erros
- [ ] `make demo` gera pelo menos 1 card em data/output/cards/
- [ ] Demo step-by-step funciona com pausa entre mensagens
