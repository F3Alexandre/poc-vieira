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
