"""
Tools (ferramentas) que o agente pode invocar durante a conversa.

Cada tool tem: nome, descrição (para o LLM), parâmetros, e função de execução.
"""

import os
import logging
from typing import Dict, Any, Optional, List

from src.knowledge.search import KnowledgeBaseSearch, SearchQuery
from src.knowledge.manifest import get_feature_manifest, get_feature_summary_text
from src.knowledge.schema import init_db

logger = logging.getLogger(__name__)


# === Definição das tools (para o LLM) ===

TOOL_DEFINITIONS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Busca na base de conhecimento central. Use filtros de metadados "
            "para reduzir o universo antes da busca textual. Se resultado "
            "insuficiente, relaxe filtros e reformule com sinônimos do glossário."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Texto livre para busca (termos específicos, não frases longas)"
                },
                "feature": {
                    "type": "string",
                    "description": "Filtro por feature (ex: devolucao_produtos)"
                },
                "domain": {
                    "type": "string",
                    "description": "Filtro por domínio (ex: pos_venda, financeiro)"
                },
                "chunk_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tipos a buscar (ex: ['regra_negocio', 'fluxo_usuario'])"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags para filtrar"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Quantidade de resultados (default: 10)"
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "get_feature_manifest",
        "description": (
            "Lista todas as features na base de conhecimento com estatísticas: "
            "quantidade de chunks, tipos disponíveis, nível de confiança, última atualização. "
            "Use no início da conversa para verificar o que existe na base."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "save_working_memory",
        "description": (
            "Salva o estado atual da especificação em arquivo para persistência. "
            "Use quando o contexto está ficando grande ou antes de gerar o card."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "generate_card",
        "description": (
            "Gera o card completo em Markdown no template padronizado. "
            "O card é salvo em data/output/cards/. "
            "Se o usuário pedir para gerar mesmo com campos faltando, use force_generate=true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "generate_children": {
                    "type": "boolean",
                    "description": "Se True, gera também os cards filhos"
                },
                "force_generate": {
                    "type": "boolean",
                    "description": "Se True, gera o card mesmo com campos obrigatórios faltando"
                }
            },
            "required": []
        }
    },
]


# === Executor de tools ===

class ToolExecutor:
    """Executa as tools do agente e retorna resultados."""

    def __init__(self, db_path: str, output_dir: str):
        self.search = KnowledgeBaseSearch(db_path)
        self.db_path = db_path
        self.output_dir = output_dir

    async def execute(
        self,
        tool_name: str,
        params: Dict[str, Any],
        working_memory,  # WorkingMemory instance
    ) -> Dict[str, Any]:
        """Executa uma tool e retorna o resultado.

        Args:
            tool_name: Nome da tool a executar.
            params: Parâmetros da tool.
            working_memory: Estado atual do Working Memory (para generate_card e save).

        Returns:
            Dict com resultado da execução.
        """
        if tool_name == "search_knowledge_base":
            return self._search(params, working_memory)
        elif tool_name == "get_feature_manifest":
            return self._manifest()
        elif tool_name == "save_working_memory":
            return self._save_memory(working_memory)
        elif tool_name == "generate_card":
            return self._generate_card(params, working_memory)
        else:
            return {"error": f"Tool desconhecida: {tool_name}"}

    def _search(self, params: Dict, working_memory) -> Dict:
        """Executa busca na base de conhecimento."""
        query = SearchQuery(
            text=params.get("text", ""),
            feature=params.get("feature"),
            domain=params.get("domain"),
            chunk_types=params.get("chunk_types"),
            tags=params.get("tags"),
            top_k=params.get("top_k", 10),
        )

        results = self.search.search(query)

        # Registrar referências no Working Memory
        for r in results:
            ref = {
                "chunk_id": r.chunk_id,
                "title": r.title,
                "chunk_type": r.chunk_type,
                "confidence": r.confidence,
                "date": r.created_at[:10] if r.created_at else "",
            }
            # Evitar duplicatas (knowledge_refs pode conter strings ou dicts)
            existing_ids = set()
            for kr in working_memory.knowledge_refs:
                if isinstance(kr, dict):
                    existing_ids.add(kr.get("chunk_id", ""))
                # strings não têm chunk_id, ignorar na dedup
            if r.chunk_id not in existing_ids:
                working_memory.knowledge_refs.append(ref)

        return {
            "total_results": len(results),
            "chunks": [
                {
                    "id": r.chunk_id,
                    "title": r.title,
                    "content": r.content,
                    "chunk_type": r.chunk_type,
                    "confidence": r.confidence,
                    "tags": r.tags,
                    "source_type": r.source_type,
                    "participants": r.participants,
                    "related_features": r.related_features,
                }
                for r in results
            ],
        }

    def _manifest(self) -> Dict:
        """Retorna manifesto de features."""
        conn = init_db(self.db_path)
        manifest = get_feature_manifest(conn)
        summary = get_feature_summary_text(conn)
        conn.close()

        return {
            "features": manifest,
            "summary_text": summary,
        }

    def _save_memory(self, working_memory) -> Dict:
        """Salva Working Memory em arquivo."""
        os.makedirs(self.output_dir, exist_ok=True)
        filepath = os.path.join(self.output_dir, "working_memory.json")
        working_memory.save_to_file(filepath)

        return {
            "status": "saved",
            "filepath": filepath,
            "filled_fields": working_memory.get_filled_count()[0],
            "total_fields": working_memory.get_filled_count()[1],
        }

    def _generate_card(self, params: Dict, working_memory) -> Dict:
        """Gera card(s) Markdown.

        Suporta:
        - force_generate=True para gerar mesmo com campos faltando
        - user_confirmed=True como sinal de que o usuário aceitou gerar incompleto
        """
        from src.agent.card_generator import generate_card_markdown

        force = params.get("force_generate", False) or params.get("user_confirmed", False)

        # Verificar se está pronto (pular se force)
        missing = working_memory.get_missing_fields()
        if missing and not force:
            return {
                "status": "incomplete",
                "missing_fields": missing,
                "message": f"Campos obrigatórios faltando: {', '.join(missing)}. "
                           f"Use force_generate=true para gerar mesmo assim.",
            }

        filepath = generate_card_markdown(working_memory, self.output_dir)

        result = {
            "status": "success",
            "filepath": filepath,
            "observations_count": len(working_memory.observations),
            "child_cards_count": len(working_memory.child_cards),
        }

        if missing:
            result["warning"] = f"Gerado com campos faltando: {', '.join(missing)}"

        return result

    def close(self):
        self.search.close()
