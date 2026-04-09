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
PYTHONIOENCODING=utf-8 python tests/test_knowledge_base.py    # 19 testes (Schema + Busca + Manifesto)
PYTHONIOENCODING=utf-8 python tests/test_ingestion.py         # 19 testes (Extração + Chunking + Pipeline)
PYTHONIOENCODING=utf-8 python tests/test_agent.py             # 13 testes (Memory + Cards + Agent Loop)
```