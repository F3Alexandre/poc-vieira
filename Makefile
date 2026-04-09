.PHONY: setup seed ingest test agent demo validate clean reset all

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
	@PYTHONIOENCODING=utf-8 $(PYTHON) tests/test_knowledge_base.py
	@echo ""
	@echo "--- Testes do pipeline de ingestão (Etapa 3) ---"
	@PYTHONIOENCODING=utf-8 $(PYTHON) tests/test_ingestion.py
	@echo ""
	@echo "--- Testes do agente (Etapa 4) ---"
	@PYTHONIOENCODING=utf-8 $(PYTHON) tests/test_agent.py
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
	@PYTHONIOENCODING=utf-8 $(PYTHON) scripts/validate_all.py

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
