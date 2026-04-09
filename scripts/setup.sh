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
