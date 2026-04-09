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
