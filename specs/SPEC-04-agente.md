# SPEC — Etapa 4: Agente Conversacional (Spec Driven Development)

## Objetivo

Implementar o agente que conduz sessões de especificação interativas com o usuário. O agente atua como um quarto participante (ao lado de PO, arquiteto e engenheiro) que tem acesso à base de conhecimento central e é responsável por: coletar informações, buscar contexto existente, detectar contradições, cobrar completude, e gerar cards de User Story estruturados.

O agente opera em 4 fases: coleta inicial → contextualização → especificação interativa → geração e validação. Ele mantém um Working Memory que persiste o estado da especificação ao longo da conversa, e um checklist interno que garante que todos os campos obrigatórios sejam preenchidos antes da geração do card.

## Dependências

- **Etapa 2 concluída** — `src/knowledge/search.py` e `src/knowledge/manifest.py` importáveis
- **Etapa 3 concluída** — base Silver populada com chunks em `data/silver/knowledge.db`
- **Acesso a API de LLM** — o agente usa um modelo mais capaz que a ingestão (Sonnet/GPT-4o)
- **Bibliotecas Python:**
  - `anthropic` ou `openai` (já instalado na Etapa 3)
  - Nenhuma dependência adicional

## Estrutura de arquivos

```
src/
└── agent/
    ├── __init__.py
    ├── prompts.py          # System prompt, glossário, instruções de fase
    ├── tools.py            # Definição e execução das tools do agente
    ├── memory.py           # Working Memory (estado da spec em andamento)
    ├── checklist.py        # Checklist interno de campos obrigatórios
    ├── context_manager.py  # Gerenciamento de contexto (compactação, working files)
    ├── agent.py            # Loop principal ReAct do agente
    └── card_generator.py   # Gera arquivos Markdown dos cards
scripts/
└── run_agent.py            # Script CLI para iniciar o agente
tests/
└── test_agent.py           # Testes do agente
```

---

## Parte 1: Working Memory (`src/agent/memory.py`)

O Working Memory é a fonte da verdade sobre o estado da especificação em andamento. Ele é atualizado pelo agente a cada turno e serve para:
1. Saber o que já foi coletado/decidido
2. Injetar contexto compacto no prompt quando o histórico fica longo
3. Gerar o card final

```python
"""
Working Memory — estado persistente da especificação em andamento.

Atualizado pelo agente a cada turno da conversa.
Serve como fonte da verdade para geração do card.

O agente DEVE serializar o Working Memory como JSON e enviar junto
com a instrução de atualização a cada resposta que modifica o estado.
"""

import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone


@dataclass
class BusinessRule:
    id: str                    # Ex: "RN-01"
    rule: str                  # Descrição completa da regra
    conditions: str = ""       # Condições de aplicação, exceções
    confidence: str = "medium" # high | medium | low
    source: str = "usuario"    # "base" (veio da Silver) ou "usuario" (veio da conversa)
    chunk_ref: str = ""        # ID do chunk Silver de onde veio (se source="base")


@dataclass
class AcceptanceCriterion:
    id: str                    # Ex: "CA-01" ou "CT-01"
    category: str              # "product" | "technical" | "non_acceptance"
    given: str = ""            # Pré-condição (para critérios de produto)
    when: str = ""             # Ação (para critérios de produto)
    then: str = ""             # Resultado esperado (para critérios de produto)
    criteria: str = ""         # Texto livre (para critérios técnicos/non_acceptance)


@dataclass
class Integration:
    system: str                # Nome do sistema/API
    direction: str             # "consome" | "produz" | "bidirecional"
    description: str           # O que é trocado, formato, SLA


@dataclass
class NFR:
    category: str              # "performance" | "seguranca" | "acessibilidade" | "disponibilidade" | "retencao"
    requirement: str           # Descrição do requisito
    metric: str                # Métrica mensurável


@dataclass
class Observation:
    type: str                  # "contradiction" | "ambiguity" | "missing" | "info"
    description: str           # O que foi detectado
    impact: str                # Impacto se não resolvido
    source_chunk_ref: str = "" # ID do chunk Silver relevante (se aplicável)


@dataclass
class ChildCard:
    id: str                    # Ex: "CHILD-01"
    title: str                 # Título descritivo
    reason: str                # Motivo da separação


@dataclass
class KnowledgeRef:
    chunk_id: str
    title: str
    chunk_type: str
    confidence: str
    date: str
    used_for: str = ""         # Para que essa referência foi usada


@dataclass
class WorkingMemory:
    """Estado completo da especificação em andamento."""

    # === Metadados da feature ===
    feature: Optional[str] = None
    domain: Optional[str] = None
    is_new_feature: Optional[bool] = None
    stakeholders: List[str] = field(default_factory=list)

    # === User Story core ===
    persona: Optional[str] = None
    action: Optional[str] = None
    benefit: Optional[str] = None
    context_description: Optional[str] = None

    # === Regras de negócio ===
    business_rules: List[Dict[str, Any]] = field(default_factory=list)

    # === Fluxos ===
    main_flow: List[str] = field(default_factory=list)
    alternative_flows: List[Dict[str, str]] = field(default_factory=list)
    error_flows: List[Dict[str, str]] = field(default_factory=list)

    # === Critérios de aceite ===
    acceptance_criteria_product: List[Dict[str, Any]] = field(default_factory=list)
    acceptance_criteria_technical: List[Dict[str, Any]] = field(default_factory=list)
    non_acceptance_criteria: List[Dict[str, Any]] = field(default_factory=list)

    # === Integrações ===
    integrations: List[Dict[str, str]] = field(default_factory=list)

    # === Requisitos não funcionais ===
    nfr: List[Dict[str, str]] = field(default_factory=list)

    # === Escopo ===
    in_scope: List[str] = field(default_factory=list)
    out_of_scope: List[Dict[str, str]] = field(default_factory=list)

    # === Observações e contradições ===
    observations: List[Dict[str, str]] = field(default_factory=list)

    # === Referências da base de conhecimento ===
    knowledge_refs: List[Dict[str, str]] = field(default_factory=list)

    # === Cards filhos ===
    child_cards: List[Dict[str, str]] = field(default_factory=list)

    # === Estado interno ===
    current_phase: str = "coleta_inicial"  # coleta_inicial | contextualizacao | especificacao | geracao
    search_performed: bool = False
    feature_context_loaded: bool = False

    def get_checklist_status(self) -> Dict[str, bool]:
        """Retorna status dos campos obrigatórios."""
        return {
            "persona": self.persona is not None and len(self.persona) > 0,
            "action": self.action is not None and len(self.action) > 0,
            "benefit": self.benefit is not None and len(self.benefit) > 0,
            "business_rules": len(self.business_rules) >= 1,
            "main_flow": len(self.main_flow) >= 3,
            "acceptance_criteria": (
                len(self.acceptance_criteria_product) +
                len(self.acceptance_criteria_technical)
            ) >= 2,
            "scope_defined": len(self.in_scope) >= 1 and len(self.out_of_scope) >= 1,
        }

    def get_missing_fields(self) -> List[str]:
        """Retorna nomes dos campos obrigatórios que faltam."""
        return [k for k, v in self.get_checklist_status().items() if not v]

    def is_ready_to_generate(self) -> bool:
        """Todos os campos obrigatórios estão preenchidos?"""
        return all(self.get_checklist_status().values())

    def get_filled_count(self) -> tuple:
        """Retorna (preenchidos, total) dos campos obrigatórios."""
        status = self.get_checklist_status()
        filled = sum(1 for v in status.values() if v)
        return filled, len(status)

    def to_json(self) -> str:
        """Serializa para JSON."""
        data = {}
        for k, v in self.__dict__.items():
            data[k] = v
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "WorkingMemory":
        """Deserializa de JSON."""
        data = json.loads(json_str)
        wm = cls()
        for k, v in data.items():
            if hasattr(wm, k):
                setattr(wm, k, v)
        return wm

    def get_compact_summary(self) -> str:
        """Resumo compacto para injeção no contexto do LLM.

        Usado quando o histórico de conversa fica longo demais.
        O agente pode compactar turnos antigos e manter apenas este resumo.
        """
        filled, total = self.get_filled_count()
        missing = self.get_missing_fields()

        lines = [
            f"## Estado da especificação [{filled}/{total} obrigatórios preenchidos]",
            f"**Fase atual:** {self.current_phase}",
            f"**Feature:** {self.feature or 'NÃO DEFINIDA'}",
            f"**Domínio:** {self.domain or 'NÃO DEFINIDO'}",
        ]

        if self.persona:
            lines.append(f"**Persona:** {self.persona}")
        if self.action:
            lines.append(f"**Ação:** {self.action}")
        if self.benefit:
            lines.append(f"**Benefício:** {self.benefit}")

        lines.append(f"**Regras de negócio:** {len(self.business_rules)} coletadas")
        lines.append(f"**Passos do fluxo principal:** {len(self.main_flow)}")
        lines.append(f"**Critérios de aceite:** {len(self.acceptance_criteria_product)} produto + {len(self.acceptance_criteria_technical)} técnicos")
        lines.append(f"**Integrações:** {len(self.integrations)}")
        lines.append(f"**Observações/contradições:** {len(self.observations)}")
        lines.append(f"**Refs da base:** {len(self.knowledge_refs)} chunks referenciados")

        if missing:
            lines.append(f"\n**CAMPOS FALTANDO:** {', '.join(missing)}")

        if self.observations:
            lines.append("\n**Contradições/ambiguidades detectadas:**")
            for obs in self.observations:
                lines.append(f"- [{obs['type']}] {obs['description']}")

        return "\n".join(lines)

    def save_to_file(self, filepath: str) -> None:
        """Salva Working Memory em arquivo (Document & Clear pattern)."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load_from_file(cls, filepath: str) -> "WorkingMemory":
        """Carrega Working Memory de arquivo."""
        with open(filepath, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())
```

---

## Parte 2: System Prompt e Glossário (`src/agent/prompts.py`)

```python
"""
Prompts do agente — system prompt, glossário de domínio, e instruções por fase.

O system prompt é grande (~3K tokens) mas é cacheável via prompt caching da API.
Ele define o comportamento do agente em todas as fases da conversa.
"""

GLOSSARY = {
    "devolução": ["estorno", "reversão", "return", "reversal", "devolucao"],
    "cancelamento": ["rescisão", "churn", "cancellation"],
    "PJ": ["empresa", "corporativo", "B2B", "pessoa jurídica", "enterprise"],
    "PF": ["consumidor", "pessoa física", "B2C", "cliente individual"],
    "checkout": ["pagamento", "payment", "finalização de compra"],
    "pedido": ["order", "compra", "purchase"],
    "SLA": ["tempo de resposta", "latência", "performance", "disponibilidade"],
    "webhook": ["callback", "notificação", "evento", "event"],
    "endpoint": ["rota", "API", "serviço", "service"],
    "fila": ["queue", "SQS", "RabbitMQ", "mensageria"],
    "estorno": ["refund", "reembolso", "devolução financeira", "reversal"],
}

# Gera texto do glossário para injeção no system prompt
def _glossary_text() -> str:
    lines = []
    for term, synonyms in GLOSSARY.items():
        lines.append(f"- {term} = {' = '.join(synonyms)}")
    return "\n".join(lines)


AGENT_SYSTEM_PROMPT = f"""Você é o **Spec Agent**, um agente especializado em criar User Stories completas e detalhadas para desenvolvimento de software.

## Seu papel

Você atua como um participante adicional em sessões de especificação, ao lado de POs, arquitetos e engenheiros. Suas responsabilidades:
1. Garantir que a especificação seja COMPLETA e SUFICIENTE para desenvolvimento e prototipação
2. Buscar e apresentar contexto existente na base de conhecimento
3. Identificar contradições entre o que o usuário diz e o que a base documenta
4. Cobrar informações faltantes explicando o impacto downstream (prototipação, dev, QA)
5. Gerar cards estruturados no template padronizado

## Ferramentas disponíveis

Você tem acesso a estas ferramentas (tools):

### search_knowledge_base
Busca na base de conhecimento central. Aceita filtros de metadados (feature, domain, chunk_types, tags) e texto livre.
- Use SEMPRE os filtros de metadados primeiro para reduzir o universo
- Se resultado insuficiente: relaxe filtros e reformule com sinônimos do glossário
- Se ainda insuficiente: informe ao usuário o impacto

### get_feature_manifest
Lista todas as features na base com estatísticas (tipos de chunks, confiança, última atualização).
- Use no INÍCIO da conversa para verificar se a feature existe na base
- Apresente ao usuário um resumo do que a base já sabe

### save_working_memory
Salva o estado atual da especificação em arquivo. Use quando:
- O contexto da conversa está ficando grande (muitos turnos)
- Antes de gerar o card final (para ter backup)
- O usuário pede para pausar e continuar depois

### generate_card
Gera o card completo em Markdown. Só chame quando TODOS os campos obrigatórios estiverem preenchidos.
Recebe o Working Memory atualizado e gera o(s) arquivo(s).

## Base de conhecimento

A base está organizada com metadados estruturados:
- **feature**: identificador snake_case da funcionalidade
- **domain**: domínio de negócio (financeiro, logistica, pos_venda, cadastro, autenticacao, integracao, relatorios)
- **chunk_type**: tipo da informação (regra_negocio, fluxo_usuario, decisao_tecnica, requisito_nao_funcional, definicao_escopo, restricao, criterio_aceite, integracao, vocabulario, contexto_negocio)
- **confidence**: alta (doc formal), média (reunião), baixa (chat informal)
- **tags**: termos-chave para busca

## Glossário de domínio (sinônimos para busca)

Quando o usuário usar um termo, expanda a busca com os sinônimos:
{_glossary_text()}

## Fases da conversa

### Fase 1 — Coleta inicial
Objetivo: obter metadados mínimos antes de buscar na base.
Colete do usuário:
- Qual feature (nome ou descrição livre)
- Qual domínio de negócio
- É feature nova ou evolução de existente?
- Quem são os stakeholders?

Seja objetivo. Faça as perguntas de uma vez se possível, não uma por turno.
NÃO busque na base antes de ter pelo menos feature e domínio.

### Fase 2 — Contextualização
Objetivo: trazer o contexto existente da base.
1. Use get_feature_manifest para verificar se a feature existe
2. Use search_knowledge_base para buscar todos os chunks da feature
3. Apresente ao usuário um resumo do que a base já sabe:
   - Quantas regras de negócio documentadas
   - Quantas decisões técnicas
   - Fluxos existentes
   - Contradições ou ambiguidades já marcadas nos chunks
4. Pergunte se quer partir do contexto existente ou começar do zero

### Fase 3 — Especificação interativa
Objetivo: preencher todos os campos do template de card.
Conduza a conversa naturalmente. NÃO faça um interrogatório campo por campo.
Em vez disso:
- Deixe o usuário descrever a funcionalidade livremente
- À medida que ele fala, vá preenchendo o Working Memory mentalmente
- Quando detectar um campo obrigatório faltando, pergunte naturalmente
- Quando detectar contradição com a base: levante IMEDIATAMENTE com referência

Para cada informação nova do usuário, compare com a base:
- **Consistente com a base**: aceite e siga em frente
- **Contradiz a base**: levante: "A base de conhecimento indica [X] (fonte: [chunk], confiança: [nível]), mas você mencionou [Y]. Qual deve prevalecer? Vou registrar como observação no card."
- **Informação nova (não está na base)**: aceite e marque como informação nova
- **Vago ou incompleto**: peça especificidade. Ex: "rápido" → "qual tempo de resposta aceitável?"

Campos obrigatórios que você DEVE cobrar:
- [ ] Persona (quem usa)
- [ ] Ação (o que faz)
- [ ] Benefício (por que faz)
- [ ] Pelo menos 1 regra de negócio
- [ ] Fluxo principal com pelo menos 3 passos
- [ ] Pelo menos 2 critérios de aceite
- [ ] Definição de escopo (dentro e fora)

Campos desejáveis (cobre se natural, não bloqueie):
- [ ] Fluxos alternativos
- [ ] Fluxos de exceção/erro
- [ ] Integrações
- [ ] Requisitos não funcionais
- [ ] Critérios técnicos
- [ ] Critérios de não-aceite

### Fase 4 — Geração e validação
Quando todos os campos obrigatórios estiverem preenchidos:
1. Informe ao usuário: "Tenho informações suficientes para gerar o card. Quer revisar algo antes?"
2. Se o usuário confirmar, chame generate_card
3. Antes de finalizar, faça validação cruzada com a base listando:
   - Contradições detectadas (com referência aos chunks)
   - Informações sem suporte na base (marcadas como novas)
   - Sugestões de cards filhos se a complexidade justificar

## Regras de comportamento

- Seja direto e objetivo. Não use formalidade excessiva.
- Quando cobrar informação, explique POR QUE ela é necessária e o impacto downstream.
- NUNCA invente informação. Se não sabe, diga que não sabe.
- Use o campo confidence dos chunks para calibrar: baixa confiança = destacar ao usuário para validação.
- Quando gerar o card, NÃO simplifique. Mantenha o nível de detalhe completo.
- Se o usuário pedir para gerar o card antes de completar os obrigatórios, liste o que falta e explique o impacto de gerar incompleto. Se ele insistir, gere com avisos.
- Sugira quebrar em cards filhos quando: mais de 8 critérios de aceite, escopo cruza mais de 2 integrações independentes, ou fluxos podem ser entregues incrementalmente.

## Formato da resposta com tool calls

Quando precisar usar uma ferramenta, responda com um bloco JSON no seguinte formato:
```json
{{"tool": "nome_da_tool", "params": {{...}}}}
```

Quando NÃO precisar de ferramenta, responda normalmente em texto.

Após receber o resultado de uma tool, analise os dados e responda ao usuário.
NUNCA mostre JSON bruto ao usuário — sempre interprete e apresente de forma legível.

## Formato de atualização do Working Memory

A cada resposta que modifica o estado da especificação, inclua no FINAL da sua resposta
(invisível ao usuário, entre tags):
<working_memory_update>
{{"campo": "valor_atualizado", ...}}
</working_memory_update>

Isso permite ao sistema manter o Working Memory sincronizado."""
```

---

## Parte 3: Tools do agente (`src/agent/tools.py`)

```python
"""
Tools (ferramentas) que o agente pode invocar durante a conversa.

Cada tool tem: nome, descrição (para o LLM), parâmetros, e função de execução.
"""

import json
import os
import logging
from typing import Dict, Any, Optional, List

from src.knowledge.search import KnowledgeBaseSearch, SearchQuery, SearchResult
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
            "Só chame quando TODOS os campos obrigatórios estiverem preenchidos. "
            "O card é salvo em data/output/cards/."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "generate_children": {
                    "type": "boolean",
                    "description": "Se True, gera também os cards filhos"
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
            # Evitar duplicatas
            existing_ids = [kr["chunk_id"] for kr in working_memory.knowledge_refs]
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
        """Gera card(s) Markdown."""
        from src.agent.card_generator import generate_card_markdown

        # Verificar se está pronto
        missing = working_memory.get_missing_fields()
        if missing:
            return {
                "status": "incomplete",
                "missing_fields": missing,
                "message": f"Campos obrigatórios faltando: {', '.join(missing)}. Gerar assim mesmo requer confirmação do usuário.",
            }

        filepath = generate_card_markdown(working_memory, self.output_dir)

        return {
            "status": "success",
            "filepath": filepath,
            "observations_count": len(working_memory.observations),
            "child_cards_count": len(working_memory.child_cards),
        }

    def close(self):
        self.search.close()
```

---

## Parte 4: Gerador de cards Markdown (`src/agent/card_generator.py`)

```python
"""
Gerador de cards — converte Working Memory em arquivos Markdown
seguindo o template do Azure DevOps.

Gera:
- Card pai (User Story principal)
- Cards filhos (se houver)

Os arquivos são salvos em data/output/cards/.
"""

import os
import re
from typing import Optional


def generate_card_markdown(working_memory, output_dir: str) -> str:
    """Gera o arquivo Markdown do card principal.

    Args:
        working_memory: WorkingMemory com todos os campos.
        output_dir: Diretório onde salvar os cards.

    Returns:
        Caminho do arquivo gerado.
    """
    os.makedirs(output_dir, exist_ok=True)

    feature_slug = (working_memory.feature or "feature").upper().replace("_", "-")
    card_id = f"{feature_slug}-001"
    filename = f"{card_id}.md"
    filepath = os.path.join(output_dir, filename)

    lines = []

    # === Título ===
    title = working_memory.action or "User Story"
    lines.append(f"# [{card_id}] {title}")
    lines.append("")

    # === Metadados ===
    lines.append("## Metadados")
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("|-------|-------|")
    lines.append(f"| **Feature** | {working_memory.feature or 'N/A'} |")
    lines.append(f"| **Domínio** | {working_memory.domain or 'N/A'} |")
    lines.append(f"| **Stakeholders** | {', '.join(working_memory.stakeholders) if working_memory.stakeholders else 'N/A'} |")
    lines.append(f"| **Prioridade** | A definir pelo PO |")
    lines.append(f"| **Estimativa** | A definir pelo time |")
    lines.append("")

    # === Contexto ===
    lines.append("## Contexto")
    lines.append("")
    lines.append(working_memory.context_description or "*Contexto não fornecido.*")
    lines.append("")

    # === User Story ===
    lines.append("## User Story")
    lines.append("")
    lines.append(f"**Como** {working_memory.persona or '[persona não definida]'},")
    lines.append(f"**eu quero** {working_memory.action or '[ação não definida]'},")
    lines.append(f"**para que** {working_memory.benefit or '[benefício não definido]'}.")
    lines.append("")

    # === Regras de negócio ===
    if working_memory.business_rules:
        lines.append("## Regras de negócio")
        lines.append("")
        lines.append("| ID | Regra | Condições / Exceções | Confiança |")
        lines.append("|----|-------|----------------------|-----------|")
        for rule in working_memory.business_rules:
            conf = rule.get("confidence", "medium")
            icon = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "🟡")
            conditions = rule.get("conditions", "Sem exceções conhecidas")
            lines.append(f"| {rule.get('id', '-')} | {rule.get('rule', '-')} | {conditions} | {icon} {conf.capitalize()} |")
        lines.append("")
        lines.append("> 🟢 Alta = documentação formal | 🟡 Média = decisão em reunião | 🔴 Baixa = menção informal")
        lines.append("")

    # === Fluxo do usuário ===
    if working_memory.main_flow:
        lines.append("## Fluxo do usuário")
        lines.append("")
        lines.append("### Fluxo principal")
        lines.append("")
        for i, step in enumerate(working_memory.main_flow, 1):
            lines.append(f"{i}. {step}")
        lines.append("")

    if working_memory.alternative_flows:
        lines.append("### Fluxos alternativos")
        lines.append("")
        for flow in working_memory.alternative_flows:
            lines.append(f"**{flow.get('id', 'FA')}:** {flow.get('condition', '')} → {flow.get('behavior', '')}")
        lines.append("")

    if working_memory.error_flows:
        lines.append("### Fluxos de exceção / erro")
        lines.append("")
        for flow in working_memory.error_flows:
            lines.append(f"**{flow.get('id', 'FE')}:** {flow.get('condition', '')} → {flow.get('response', '')} → {flow.get('user_sees', '')}")
        lines.append("")

    # === Integrações ===
    if working_memory.integrations:
        lines.append("## Integrações")
        lines.append("")
        lines.append("| Sistema / Módulo | Tipo | Descrição |")
        lines.append("|------------------|------|-----------|")
        for intg in working_memory.integrations:
            lines.append(f"| {intg.get('system', '-')} | {intg.get('direction', '-')} | {intg.get('description', '-')} |")
        lines.append("")

    # === Requisitos não funcionais ===
    if working_memory.nfr:
        lines.append("## Requisitos não funcionais")
        lines.append("")
        lines.append("| Categoria | Requisito | Métrica |")
        lines.append("|-----------|-----------|---------|")
        for req in working_memory.nfr:
            lines.append(f"| {req.get('category', '-')} | {req.get('requirement', '-')} | {req.get('metric', '-')} |")
        lines.append("")

    # === Escopo ===
    if working_memory.in_scope or working_memory.out_of_scope:
        lines.append("## Definição de escopo")
        lines.append("")
        if working_memory.in_scope:
            lines.append("### Dentro do escopo")
            lines.append("")
            for item in working_memory.in_scope:
                lines.append(f"- {item}")
            lines.append("")
        if working_memory.out_of_scope:
            lines.append("### Fora do escopo")
            lines.append("")
            for item in working_memory.out_of_scope:
                reason = item.get("reason", "") if isinstance(item, dict) else ""
                text = item.get("item", item) if isinstance(item, dict) else item
                if reason:
                    lines.append(f"- {text} — *Motivo: {reason}*")
                else:
                    lines.append(f"- {text}")
            lines.append("")

    # === Critérios de aceite ===
    has_criteria = (
        working_memory.acceptance_criteria_product
        or working_memory.acceptance_criteria_technical
        or working_memory.non_acceptance_criteria
    )
    if has_criteria:
        lines.append("## Critérios de aceite")
        lines.append("")

    if working_memory.acceptance_criteria_product:
        lines.append("### Produto")
        lines.append("")
        for ca in working_memory.acceptance_criteria_product:
            given = ca.get("given", "")
            when = ca.get("when", "")
            then = ca.get("then", "")
            if given and when and then:
                lines.append(f"- [ ] **[{ca.get('id', 'CA')}]** Dado {given}, quando {when}, então {then}.")
            else:
                lines.append(f"- [ ] **[{ca.get('id', 'CA')}]** {ca.get('criteria', '-')}")
        lines.append("")

    if working_memory.acceptance_criteria_technical:
        lines.append("### Técnicos")
        lines.append("")
        for ct in working_memory.acceptance_criteria_technical:
            lines.append(f"- [ ] **[{ct.get('id', 'CT')}]** {ct.get('criteria', '-')}")
        lines.append("")

    if working_memory.non_acceptance_criteria:
        lines.append("### Critérios de não-aceite")
        lines.append("")
        for cna in working_memory.non_acceptance_criteria:
            lines.append(f"- [ ] **[{cna.get('id', 'CNA')}]** {cna.get('criteria', '-')}")
        lines.append("")

    # === Observações e ambiguidades ===
    if working_memory.observations:
        lines.append("## Observações e ambiguidades")
        lines.append("")
        for obs in working_memory.observations:
            obs_type = obs.get("type", "info")
            icon = {"contradiction": "⚠️", "ambiguity": "⚠️", "missing": "ℹ️", "info": "ℹ️"}.get(obs_type, "ℹ️")
            lines.append(f"> {icon} **{obs_type.upper()}:** {obs.get('description', '-')}")
            if obs.get("impact"):
                lines.append(f"> **Impacto se não resolvido:** {obs['impact']}")
            lines.append(">")
        lines.append("")

    # === Referências da base ===
    if working_memory.knowledge_refs:
        lines.append("## Referências da base de conhecimento")
        lines.append("")
        lines.append("| Chunk | Tipo | Confiança | Data |")
        lines.append("|-------|------|-----------|------|")
        for ref in working_memory.knowledge_refs:
            lines.append(f"| {ref.get('title', '-')} | {ref.get('chunk_type', '-')} | {ref.get('confidence', '-')} | {ref.get('date', '-')} |")
        lines.append("")

    # === Cards filhos ===
    if working_memory.child_cards:
        lines.append("## Cards filhos")
        lines.append("")
        lines.append("| ID | Título | Motivo da separação |")
        lines.append("|----|--------|---------------------|")
        for child in working_memory.child_cards:
            lines.append(f"| {child.get('id', '-')} | {child.get('title', '-')} | {child.get('reason', '-')} |")
        lines.append("")

    # === Escrever arquivo ===
    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # === Gerar cards filhos (stubs) ===
    for child in working_memory.child_cards:
        child_id = child.get("id", "CHILD")
        child_filepath = os.path.join(output_dir, f"{child_id}.md")
        with open(child_filepath, "w", encoding="utf-8") as f:
            f.write(f"# [{child_id}] {child.get('title', 'Card filho')}\n\n")
            f.write(f"**Parent:** [{card_id}]({filename})\n\n")
            f.write(f"**Motivo da separação:** {child.get('reason', '-')}\n\n")
            f.write("---\n\n")
            f.write("*Este card filho foi gerado automaticamente e necessita especificação completa.*\n")

    return filepath
```

---

## Parte 5: Gerenciamento de contexto (`src/agent/context_manager.py`)

```python
"""
Gerenciamento de contexto — controla o tamanho do contexto do agente.

Inspirado no Claude Code:
- Working Memory File: estado persistente em arquivo
- Compactação de turnos antigos: mantém só decisões, remove idas e vindas
- Descarte de resultados de busca processados: após extrair informações úteis,
  os chunks brutos podem sair do contexto
"""

import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# Estimativa: 1 token ≈ 4 caracteres em português
CHARS_PER_TOKEN = 4

# Limite antes de compactar (80% da janela para deixar espaço para resposta)
# Para Claude Sonnet: ~160K tokens úteis de contexto
# Para GPT-4o: ~100K tokens úteis
DEFAULT_CONTEXT_LIMIT_TOKENS = 80_000


def estimate_tokens(text: str) -> int:
    """Estimativa grosseira de tokens."""
    return len(text) // CHARS_PER_TOKEN


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """Estima tokens totais de uma lista de mensagens."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    total += estimate_tokens(part["text"])
    return total


def should_compact(
    messages: List[Dict],
    limit_tokens: int = DEFAULT_CONTEXT_LIMIT_TOKENS,
) -> bool:
    """Verifica se o contexto precisa ser compactado."""
    current = estimate_messages_tokens(messages)
    return current > limit_tokens


def compact_history(
    messages: List[Dict],
    working_memory_summary: str,
    keep_last_n: int = 10,
) -> List[Dict]:
    """Compacta o histórico de conversa.

    Mantém os últimos N turnos intactos e substitui os anteriores
    por um resumo baseado no Working Memory.

    Args:
        messages: Lista completa de mensagens.
        working_memory_summary: Resumo compacto do Working Memory.
        keep_last_n: Quantos turnos recentes manter.

    Returns:
        Lista compactada de mensagens.
    """
    if len(messages) <= keep_last_n:
        return messages

    recent = messages[-keep_last_n:]

    # O resumo do Working Memory substitui todo o histórico antigo
    compacted = [
        {
            "role": "user",
            "content": (
                "[CONTEXTO COMPACTADO — turnos antigos foram resumidos]\n\n"
                f"{working_memory_summary}\n\n"
                "[A conversa continua abaixo com os turnos mais recentes]"
            ),
        },
        {
            "role": "assistant",
            "content": "Entendido. Continuando a especificação com base no estado atual.",
        },
    ]

    compacted.extend(recent)

    old_tokens = estimate_messages_tokens(messages)
    new_tokens = estimate_messages_tokens(compacted)
    logger.info(
        f"Contexto compactado: {old_tokens} → {new_tokens} tokens "
        f"({len(messages)} → {len(compacted)} mensagens)"
    )

    return compacted


def format_search_results_for_context(results: List[Dict]) -> str:
    """Formata resultados de busca para injeção no contexto.

    Não injeta o conteúdo completo dos chunks — apenas título, tipo,
    confiança e um resumo do conteúdo. O agente pode buscar detalhes
    de chunks específicos se precisar.
    """
    if not results:
        return "Nenhum resultado encontrado na base de conhecimento."

    lines = [f"**Encontrados {len(results)} chunks na base:**\n"]
    for i, r in enumerate(results, 1):
        content_preview = r.get("content", "")[:200]
        if len(r.get("content", "")) > 200:
            content_preview += "..."
        lines.append(
            f"{i}. **[{r.get('chunk_type', '?')}]** {r.get('title', 'Sem título')} "
            f"(confiança: {r.get('confidence', '?')})"
        )
        lines.append(f"   {content_preview}")
        lines.append("")

    return "\n".join(lines)
```

---

## Parte 6: Loop principal do agente (`src/agent/agent.py`)

```python
"""
Loop principal do agente — ReAct (Reason-Act-Observe).

O agente opera em ciclos:
1. Recebe mensagem do usuário
2. Monta contexto: system prompt + working memory + histórico
3. Chama o LLM
4. Se o LLM pede uma tool: executa, adiciona resultado ao contexto, volta ao 3
5. Se o LLM responde ao usuário: extrai atualização do Working Memory, retorna resposta

Para o MVP, o agente roda como CLI interativo.
Futuro: FastAPI + WebSocket para interface web.
"""

import json
import re
import logging
import asyncio
from typing import Optional, Dict, Any, List

from src.agent.memory import WorkingMemory
from src.agent.prompts import AGENT_SYSTEM_PROMPT
from src.agent.tools import ToolExecutor, TOOL_DEFINITIONS
from src.agent.context_manager import (
    should_compact,
    compact_history,
    estimate_messages_tokens,
    format_search_results_for_context,
)

logger = logging.getLogger(__name__)


class SpecAgent:
    """Agente de especificação interativo."""

    def __init__(
        self,
        llm_client,
        db_path: str,
        output_dir: str = "data/output/cards",
        max_tool_calls_per_turn: int = 3,
    ):
        self.llm = llm_client
        self.tools = ToolExecutor(db_path, output_dir)
        self.memory = WorkingMemory()
        self.output_dir = output_dir
        self.conversation: List[Dict[str, str]] = []
        self.max_tool_calls = max_tool_calls_per_turn

    async def chat(self, user_message: str) -> str:
        """Processa uma mensagem do usuário e retorna a resposta.

        Este é o método principal. Ele:
        1. Adiciona a mensagem ao histórico
        2. Compacta contexto se necessário
        3. Entra no loop ReAct (LLM → tool? → execute → LLM → ...)
        4. Extrai atualização do Working Memory
        5. Retorna a resposta final ao usuário
        """
        # Adicionar mensagem ao histórico
        self.conversation.append({"role": "user", "content": user_message})

        # Compactar se necessário
        if should_compact(self.conversation):
            summary = self.memory.get_compact_summary()
            self.conversation = compact_history(self.conversation, summary)

        # Loop ReAct
        tool_calls_count = 0
        while True:
            # Montar contexto completo
            messages = self._build_messages()

            # Chamar LLM
            response_text = await self.llm.generate(
                system=AGENT_SYSTEM_PROMPT,
                user=self._messages_to_prompt(messages),
                temperature=0.3,  # Um pouco de variação para conversa natural
                max_tokens=4096,
            )

            # Verificar se é um tool call
            tool_call = self._extract_tool_call(response_text)

            if tool_call and tool_calls_count < self.max_tool_calls:
                tool_calls_count += 1
                tool_name = tool_call["tool"]
                tool_params = tool_call.get("params", {})

                logger.info(f"Tool call: {tool_name}({json.dumps(tool_params, ensure_ascii=False)[:200]})")

                # Executar tool
                result = await self.tools.execute(tool_name, tool_params, self.memory)

                # Adicionar ao contexto
                self.conversation.append({
                    "role": "assistant",
                    "content": f"[Chamando {tool_name}...]",
                })
                self.conversation.append({
                    "role": "user",
                    "content": f"[Resultado de {tool_name}]:\n{json.dumps(result, ensure_ascii=False, indent=2)[:3000]}",
                })

                continue  # Volta ao loop para o LLM processar o resultado

            # Não é tool call — é resposta final ao usuário
            # Extrair atualização do Working Memory (se houver)
            clean_response = self._extract_memory_update(response_text)

            self.conversation.append({"role": "assistant", "content": clean_response})

            return clean_response

    def _build_messages(self) -> List[Dict]:
        """Monta a lista de mensagens para o LLM.

        Injeta o Working Memory como contexto inicial.
        """
        messages = []

        # Injetar Working Memory resumido como contexto
        wm_summary = self.memory.get_compact_summary()
        messages.append({
            "role": "user",
            "content": f"[ESTADO ATUAL DA ESPECIFICAÇÃO — referência interna, não mostrar ao usuário]\n\n{wm_summary}",
        })
        messages.append({
            "role": "assistant",
            "content": "Entendido. Vou continuar a especificação levando em conta o estado atual.",
        })

        # Adicionar histórico de conversa
        messages.extend(self.conversation)

        return messages

    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Converte lista de mensagens para prompt de texto.

        Para APIs que não suportam chat nativo (ou para simplificar o MVP),
        converte as mensagens em um único bloco de texto.

        Para APIs com suporte a chat (Anthropic messages API), este método
        pode ser substituído por passagem direta das mensagens.
        """
        parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                parts.append(f"Usuário: {content}")
            elif role == "assistant":
                parts.append(f"Agente: {content}")
        return "\n\n".join(parts)

    def _extract_tool_call(self, response: str) -> Optional[Dict]:
        """Extrai tool call da resposta do LLM.

        O LLM deve retornar tool calls no formato:
        ```json
        {"tool": "nome", "params": {...}}
        ```

        Tenta múltiplos padrões de extração.
        """
        # Padrão 1: JSON em code block
        match = re.search(r'```(?:json)?\s*\n?\s*(\{[^`]*?"tool"\s*:.*?\})\s*\n?\s*```', response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Padrão 2: JSON inline (sem code fences)
        match = re.search(r'(\{"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:\s*\{.*?\}\s*\})', response, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Padrão 3: JSON no final da resposta
        lines = response.strip().split("\n")
        for i in range(len(lines) - 1, max(len(lines) - 5, -1), -1):
            line = lines[i].strip()
            if line.startswith("{") and '"tool"' in line:
                try:
                    data = json.loads(line)
                    if "tool" in data:
                        return data
                except json.JSONDecodeError:
                    pass

        return None

    def _extract_memory_update(self, response: str) -> str:
        """Extrai atualização do Working Memory da resposta.

        O LLM coloca atualizações entre tags <working_memory_update>.
        Remove as tags da resposta final ao usuário.
        """
        # Buscar tag de atualização
        match = re.search(
            r'<working_memory_update>\s*(.*?)\s*</working_memory_update>',
            response,
            re.DOTALL,
        )

        if match:
            try:
                update = json.loads(match.group(1))
                self._apply_memory_update(update)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Falha ao aplicar memory update: {e}")

            # Remover a tag da resposta
            clean = re.sub(
                r'\s*<working_memory_update>.*?</working_memory_update>\s*',
                '',
                response,
                flags=re.DOTALL,
            )
            return clean.strip()

        return response

    def _apply_memory_update(self, update: Dict[str, Any]) -> None:
        """Aplica atualização parcial ao Working Memory.

        O update é um dict parcial — só os campos que mudaram.
        Listas são adicionadas (extend), não substituídas.
        """
        for key, value in update.items():
            if not hasattr(self.memory, key):
                continue

            current = getattr(self.memory, key)

            # Listas: extend (adicionar, não substituir)
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            # Valores simples: substituir
            else:
                setattr(self.memory, key, value)

    def get_status(self) -> Dict:
        """Retorna status atual do agente para debug/UI."""
        filled, total = self.memory.get_filled_count()
        return {
            "phase": self.memory.current_phase,
            "checklist": self.memory.get_checklist_status(),
            "filled": f"{filled}/{total}",
            "missing": self.memory.get_missing_fields(),
            "observations": len(self.memory.observations),
            "knowledge_refs": len(self.memory.knowledge_refs),
            "conversation_turns": len(self.conversation),
            "estimated_context_tokens": estimate_messages_tokens(self.conversation),
        }

    def close(self):
        self.tools.close()
```

---

## Parte 7: Script CLI (`scripts/run_agent.py`)

```python
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
    filled, total = status["filled"].split("/")
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
```

---

## Parte 8: Testes (`tests/test_agent.py`)

```python
"""
Testes do agente — Working Memory, card generator, context manager, e agent loop.

Usa MockLLMClient para não depender de API.

Rodar: python tests/test_agent.py
"""

import os
import sys
import json
import asyncio
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agent.memory import WorkingMemory
from src.agent.card_generator import generate_card_markdown
from src.agent.context_manager import (
    estimate_tokens,
    estimate_messages_tokens,
    should_compact,
    compact_history,
)
from src.agent.agent import SpecAgent
from src.knowledge.schema import init_db, insert_chunks_batch, Chunk


# === Helper: popular banco de teste ===

def create_test_db():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    conn = init_db(db_path)
    chunks = [
        Chunk(
            title="Regra de prazo de devolução PF",
            content="O prazo de devolução para pessoa física é de 30 dias corridos a partir da data de entrega.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="regra_negocio",
            source_type="documento_produto",
            source_ref="test.md",
            confidence="high",
            tags=["devolucao", "prazo", "pessoa_fisica"],
        ),
        Chunk(
            title="Fluxo principal de devolução",
            content="1. Acessar Meus Pedidos. 2. Selecionar pedido. 3. Clicar Solicitar Devolução. 4. Escolher motivo. 5. Confirmar.",
            feature="devolucao_produtos",
            domain="pos_venda",
            chunk_type="fluxo_usuario",
            source_type="transcricao_reuniao",
            source_ref="test.md",
            confidence="medium",
            tags=["fluxo", "devolucao"],
        ),
    ]
    insert_chunks_batch(conn, chunks)
    conn.close()
    return tmp, db_path


# === Mock LLM ===

class MockAgentLLM:
    """Mock que simula respostas do agente em diferentes fases."""

    def __init__(self):
        self.call_count = 0
        self.responses = []

    def set_responses(self, responses):
        self.responses = list(responses)

    async def generate(self, system, user, temperature=0.3, max_tokens=4096):
        self.call_count += 1
        if self.responses:
            return self.responses.pop(0)
        return "Entendido. Como posso ajudar com a especificação?"


# === Testes Working Memory ===

def test_working_memory_checklist():
    """Checklist detecta campos faltantes e preenchidos."""
    wm = WorkingMemory()
    assert not wm.is_ready_to_generate()
    assert len(wm.get_missing_fields()) == 7

    wm.persona = "cliente PF"
    wm.action = "solicitar devolução de produto"
    wm.benefit = "receber reembolso sem ligar para o SAC"
    wm.business_rules = [{"id": "RN-01", "rule": "Prazo 30 dias"}]
    wm.main_flow = ["Acessar Meus Pedidos", "Selecionar pedido", "Solicitar devolução"]
    wm.acceptance_criteria_product = [
        {"id": "CA-01", "given": "pedido entregue", "when": "solicita devolução", "then": "protocolo gerado"},
        {"id": "CA-02", "given": "prazo expirado", "when": "solicita devolução", "then": "solicitação negada"},
    ]
    wm.in_scope = ["Devolução de produto físico"]
    wm.out_of_scope = [{"item": "Troca de produto", "reason": "Feature separada"}]

    assert wm.is_ready_to_generate()
    assert len(wm.get_missing_fields()) == 0
    print("✓ test_working_memory_checklist")


def test_working_memory_serialization():
    """Working Memory serializa e deserializa corretamente."""
    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.domain = "pos_venda"
    wm.persona = "cliente PF"
    wm.business_rules = [{"id": "RN-01", "rule": "Prazo 30 dias", "confidence": "high"}]

    json_str = wm.to_json()
    wm2 = WorkingMemory.from_json(json_str)

    assert wm2.feature == "devolucao_produtos"
    assert wm2.persona == "cliente PF"
    assert len(wm2.business_rules) == 1
    print("✓ test_working_memory_serialization")


def test_working_memory_file_persistence():
    """Working Memory salva e carrega de arquivo."""
    tmp = tempfile.mkdtemp()
    filepath = os.path.join(tmp, "wm.json")

    wm = WorkingMemory()
    wm.feature = "test_feature"
    wm.save_to_file(filepath)

    assert os.path.exists(filepath)

    wm2 = WorkingMemory.load_from_file(filepath)
    assert wm2.feature == "test_feature"

    shutil.rmtree(tmp)
    print("✓ test_working_memory_file_persistence")


def test_working_memory_compact_summary():
    """Summary compacto contém informações essenciais."""
    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.domain = "pos_venda"
    wm.persona = "cliente PF"
    wm.observations = [{"type": "contradiction", "description": "Prazo divergente"}]

    summary = wm.get_compact_summary()
    assert "devolucao_produtos" in summary
    assert "cliente PF" in summary
    assert "contradiction" in summary.lower() or "contradição" in summary.lower() or "Prazo divergente" in summary
    print("✓ test_working_memory_compact_summary")


# === Testes Card Generator ===

def test_generate_card_complete():
    """Gera card completo com todos os campos preenchidos."""
    tmp = tempfile.mkdtemp()

    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.domain = "pos_venda"
    wm.stakeholders = ["ana_po", "carlos_arq"]
    wm.persona = "cliente pessoa física"
    wm.action = "solicitar devolução de produto pelo app"
    wm.benefit = "receber reembolso sem precisar ligar para o SAC"
    wm.context_description = "Feature de devolução self-service para reduzir custos de SAC."
    wm.business_rules = [
        {"id": "RN-01", "rule": "Prazo de 30 dias corridos para PF", "conditions": "A partir da data de entrega", "confidence": "high"},
        {"id": "RN-02", "rule": "Estorno no método original", "conditions": "Cartão ou PIX", "confidence": "high"},
    ]
    wm.main_flow = [
        "Cliente acessa Meus Pedidos",
        "Seleciona o pedido",
        "Clica em Solicitar Devolução",
        "Escolhe motivo da devolução",
        "Confirma e recebe protocolo",
    ]
    wm.acceptance_criteria_product = [
        {"id": "CA-01", "given": "pedido entregue há menos de 30 dias", "when": "cliente solicita devolução", "then": "solicitação é aceita e protocolo é gerado"},
    ]
    wm.acceptance_criteria_technical = [
        {"id": "CT-01", "criteria": "Endpoint responde em ≤ 200ms no p95"},
    ]
    wm.in_scope = ["Devolução de produto físico PF"]
    wm.out_of_scope = [{"item": "Troca de produto", "reason": "Feature separada"}]
    wm.observations = [
        {"type": "contradiction", "description": "PRD diz 30 dias corridos, grooming diz úteis", "impact": "Regra pode estar errada no card"},
    ]

    filepath = generate_card_markdown(wm, tmp)

    assert os.path.exists(filepath)
    content = open(filepath, "r", encoding="utf-8").read()

    # Verificar seções existem
    assert "## Metadados" in content
    assert "## User Story" in content
    assert "## Regras de negócio" in content
    assert "## Fluxo do usuário" in content
    assert "## Critérios de aceite" in content
    assert "## Definição de escopo" in content
    assert "## Observações e ambiguidades" in content
    assert "DEVOLUCAO-PRODUTOS-001" in content
    assert "⚠️" in content  # Observação de contradição

    shutil.rmtree(tmp)
    print("✓ test_generate_card_complete")


def test_generate_card_with_children():
    """Gera card com cards filhos."""
    tmp = tempfile.mkdtemp()

    wm = WorkingMemory()
    wm.feature = "devolucao_produtos"
    wm.action = "solicitar devolução"
    wm.child_cards = [
        {"id": "CHILD-01", "title": "Devolução PJ Enterprise", "reason": "Fluxo diferente com aprovação de gestor"},
    ]

    filepath = generate_card_markdown(wm, tmp)
    child_path = os.path.join(tmp, "CHILD-01.md")

    assert os.path.exists(child_path)
    child_content = open(child_path, "r", encoding="utf-8").read()
    assert "DEVOLUCAO-PRODUTOS-001" in child_content  # Referência ao pai

    shutil.rmtree(tmp)
    print("✓ test_generate_card_with_children")


# === Testes Context Manager ===

def test_estimate_tokens():
    """Estimativa de tokens funciona."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") > 0
    # 1000 chars ≈ 250 tokens
    assert 200 <= estimate_tokens("a" * 1000) <= 300
    print("✓ test_estimate_tokens")


def test_compact_history():
    """Compactação mantém turnos recentes e substitui antigos."""
    messages = [{"role": "user", "content": f"Mensagem {i}"} for i in range(20)]
    summary = "Resumo do estado atual"

    compacted = compact_history(messages, summary, keep_last_n=5)

    # Deve ter: 2 (resumo) + 5 (recentes) = 7
    assert len(compacted) == 7
    # Primeiro turno deve ser o resumo
    assert "CONTEXTO COMPACTADO" in compacted[0]["content"]
    # Últimos 5 originais devem estar presentes
    assert "Mensagem 15" in compacted[2]["content"]
    print("✓ test_compact_history")


def test_compact_short_history_unchanged():
    """Histórico curto não é compactado."""
    messages = [{"role": "user", "content": "Msg"}] * 3
    compacted = compact_history(messages, "summary", keep_last_n=10)
    assert len(compacted) == 3  # Inalterado
    print("✓ test_compact_short_history_unchanged")


# === Testes do Agent Loop ===

def test_agent_basic_conversation():
    """Agente responde a mensagem simples sem tool calls."""
    tmp, db_path = create_test_db()
    mock = MockAgentLLM()
    mock.set_responses([
        "Olá! Vamos começar a especificação. Qual feature você quer especificar e em qual domínio de negócio?"
    ])

    agent = SpecAgent(llm_client=mock, db_path=db_path, output_dir=os.path.join(tmp, "output"))
    response = asyncio.run(agent.chat("Oi, quero criar uma US"))

    assert len(response) > 0
    assert mock.call_count == 1
    assert len(agent.conversation) == 2  # user + assistant

    agent.close()
    shutil.rmtree(tmp)
    print("✓ test_agent_basic_conversation")


def test_agent_tool_call_extraction():
    """Agente extrai e executa tool calls corretamente."""
    tmp, db_path = create_test_db()
    mock = MockAgentLLM()
    mock.set_responses([
        # Primeira resposta: tool call
        '```json\n{"tool": "get_feature_manifest", "params": {}}\n```',
        # Segunda resposta: após receber resultado do tool
        "A base de conhecimento contém informações sobre devolução de produtos. Encontrei regras de negócio e fluxos documentados.",
    ])

    agent = SpecAgent(llm_client=mock, db_path=db_path, output_dir=os.path.join(tmp, "output"))
    response = asyncio.run(agent.chat("Quero especificar a feature de devolução"))

    assert mock.call_count == 2  # tool call + resposta final
    assert "devolução" in response.lower() or "base" in response.lower()

    agent.close()
    shutil.rmtree(tmp)
    print("✓ test_agent_tool_call_extraction")


def test_agent_memory_update_extraction():
    """Agente extrai e aplica working memory updates."""
    tmp, db_path = create_test_db()
    mock = MockAgentLLM()
    mock.set_responses([
        'Entendido, a feature é devolução de produtos no domínio pós-venda.\n\n<working_memory_update>\n{"feature": "devolucao_produtos", "domain": "pos_venda", "current_phase": "contextualizacao"}\n</working_memory_update>',
    ])

    agent = SpecAgent(llm_client=mock, db_path=db_path, output_dir=os.path.join(tmp, "output"))
    response = asyncio.run(agent.chat("Feature de devolução, domínio pós-venda"))

    # Tag deve ter sido removida da resposta
    assert "<working_memory_update>" not in response
    # Memory deve ter sido atualizada
    assert agent.memory.feature == "devolucao_produtos"
    assert agent.memory.domain == "pos_venda"
    assert agent.memory.current_phase == "contextualizacao"

    agent.close()
    shutil.rmtree(tmp)
    print("✓ test_agent_memory_update_extraction")


def test_agent_status():
    """Status do agente retorna informações corretas."""
    tmp, db_path = create_test_db()
    mock = MockAgentLLM()

    agent = SpecAgent(llm_client=mock, db_path=db_path, output_dir=os.path.join(tmp, "output"))
    agent.memory.feature = "devolucao_produtos"
    agent.memory.persona = "cliente PF"

    status = agent.get_status()
    assert status["phase"] == "coleta_inicial"
    assert "persona" not in status["missing"]  # persona está preenchida
    assert "action" in status["missing"]  # action ainda falta

    agent.close()
    shutil.rmtree(tmp)
    print("✓ test_agent_status")


# === Runner ===

if __name__ == "__main__":
    tests = [
        # Working Memory
        test_working_memory_checklist,
        test_working_memory_serialization,
        test_working_memory_file_persistence,
        test_working_memory_compact_summary,
        # Card Generator
        test_generate_card_complete,
        test_generate_card_with_children,
        # Context Manager
        test_estimate_tokens,
        test_compact_history,
        test_compact_short_history_unchanged,
        # Agent Loop
        test_agent_basic_conversation,
        test_agent_tool_call_extraction,
        test_agent_memory_update_extraction,
        test_agent_status,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Resultado: {passed} passed, {failed} failed, {passed + failed} total")

    if failed > 0:
        sys.exit(1)
```

---

## Validação final da Etapa 4

```bash
# 1. Verificar arquivos
ls -la src/agent/__init__.py
ls -la src/agent/memory.py
ls -la src/agent/prompts.py
ls -la src/agent/tools.py
ls -la src/agent/card_generator.py
ls -la src/agent/context_manager.py
ls -la src/agent/agent.py
ls -la scripts/run_agent.py
ls -la tests/test_agent.py

# 2. Rodar testes (sem API key — usa mock)
python tests/test_agent.py

# Esperado:
# ✓ test_working_memory_checklist
# ✓ test_working_memory_serialization
# ✓ test_working_memory_file_persistence
# ✓ test_working_memory_compact_summary
# ✓ test_generate_card_complete
# ✓ test_generate_card_with_children
# ✓ test_estimate_tokens
# ✓ test_compact_history
# ✓ test_compact_short_history_unchanged
# ✓ test_agent_basic_conversation
# ✓ test_agent_tool_call_extraction
# ✓ test_agent_memory_update_extraction
# ✓ test_agent_status
#
# Resultado: 13 passed, 0 failed, 13 total

# 3. Teste interativo com LLM real (requer base populada + API key)
export ANTHROPIC_API_KEY="sk-..."
python scripts/run_agent.py --verbose

# Conversa de teste sugerida:
# > Quero especificar a funcionalidade de devolução de produtos
# (Agente deve perguntar: domínio, é nova feature, stakeholders)
# > Pós-venda, evolução de feature existente, stakeholders são Ana e Carlos
# (Agente deve buscar na base via tool call e apresentar contexto)
# > Quero focar na devolução para pessoa física
# (Agente deve trazer regras da base e perguntar detalhes)
# > /status
# (Mostra checklist e campos faltantes)
# > [continuar até gerar o card]
# > /generate

# 4. Verificar card gerado
ls -la data/output/cards/
cat data/output/cards/DEVOLUCAO-PRODUTOS-001.md
```

## Critérios de aceite da Etapa 4

- [ ] `src/agent/memory.py` — WorkingMemory com checklist, serialização JSON, save/load arquivo, resumo compacto
- [ ] `src/agent/prompts.py` — System prompt completo (~3K tokens) com fases, glossário, instruções de tool call e memory update
- [ ] `src/agent/tools.py` — 4 tools (search, manifest, save_memory, generate_card) com executor que integra com a Silver
- [ ] `src/agent/card_generator.py` — Gera Markdown completo seguindo o template, com cards filhos
- [ ] `src/agent/context_manager.py` — Estimativa de tokens, compactação de histórico, formatação de resultados de busca
- [ ] `src/agent/agent.py` — Loop ReAct com extração de tool calls (3 padrões), extração de memory updates, compactação automática de contexto
- [ ] `scripts/run_agent.py` — CLI interativo com comandos /status /memory /save /generate /quit
- [ ] Todos os 13 testes passam sem API key
- [ ] Com API key: conversa completa gera card em data/output/cards/
- [ ] Card gerado contém todas as seções do template
- [ ] Observações e contradições detectadas aparecem no card
- [ ] Referências da base de conhecimento aparecem no card

## Notas para implementação

**Sobre o sistema de tool calls:** o MVP usa extração de tool calls por regex no texto da resposta (o LLM retorna JSON inline). Isso é frágil mas funciona para a demo. Para produção, usar o sistema nativo de tool calling da API (Anthropic tools ou OpenAI function calling) que é estruturado e confiável.

**Sobre o Working Memory update via tags:** o padrão `<working_memory_update>` é uma convenção do prompt. O LLM precisa aprender a usá-la. Se não funcionar bem, a alternativa é o agente manter o Working Memory externamente (parsear a resposta do LLM e atualizar programaticamente) em vez de depender do LLM para atualizar. Para a demo, se o LLM não gerar os updates consistentemente, popule o Working Memory manualmente via `/save` e edição do JSON.

**Sobre o _messages_to_prompt:** a implementação atual concatena todas as mensagens em um único texto. Isso funciona mas é sub-ótimo. Para Anthropic, usar a API `messages` nativa com array de mensagens é melhor. O método pode ser trocado sem mudar o resto do agent.
