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
        max_tool_calls_per_turn: int = 5,
        on_action=None,
    ):
        self.llm = llm_client
        self.tools = ToolExecutor(db_path, output_dir)
        self.memory = WorkingMemory()
        self.output_dir = output_dir
        self.conversation: List[Dict[str, str]] = []
        self.max_tool_calls = max_tool_calls_per_turn
        self.on_action = on_action  # callback async: on_action(action_type, data)

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
        total_iterations = 0
        max_iterations = self.max_tool_calls + 2  # safety limit
        actions_log = []  # Registro de ações para o frontend

        while total_iterations < max_iterations:
            total_iterations += 1
            # Montar contexto completo
            messages = self._build_messages()

            # Emitir ação de "pensando"
            await self._emit_action("thinking", {"step": tool_calls_count + 1})

            # Chamar LLM
            response_text = await self.llm.generate(
                system=AGENT_SYSTEM_PROMPT,
                user=self._messages_to_prompt(messages),
                temperature=0.3,
                max_tokens=8192,
            )

            # Verificar se é um tool call
            tool_call = self._extract_tool_call(response_text)

            if tool_call and tool_calls_count < self.max_tool_calls:
                tool_calls_count += 1
                tool_name = tool_call["tool"]
                tool_params = tool_call.get("params", {})

                logger.info(f"Tool call: {tool_name}({json.dumps(tool_params, ensure_ascii=False)[:200]})")

                # Emitir ação para o frontend
                action_desc = self._describe_tool_action(tool_name, tool_params)
                actions_log.append(action_desc)
                await self._emit_action("tool_call", {
                    "tool": tool_name,
                    "description": action_desc,
                    "step": tool_calls_count,
                })

                # Executar tool (com tratamento de erro para sempre emitir resultado)
                try:
                    result = await self.tools.execute(tool_name, tool_params, self.memory)
                    tool_status = result.get("status", "ok")
                    # Normalizar status para o frontend
                    is_success = tool_status in ("ok", "success", "saved", "complete")
                    await self._emit_action("tool_result", {
                        "tool": tool_name,
                        "status": "ok" if is_success else "error",
                        "step": tool_calls_count,
                    })
                except Exception as e:
                    logger.error(f"Erro ao executar tool {tool_name}: {e}", exc_info=True)
                    result = {"status": "error", "error": str(e)}
                    await self._emit_action("tool_result", {
                        "tool": tool_name,
                        "status": "error",
                        "step": tool_calls_count,
                    })

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

            elif tool_call and tool_calls_count >= self.max_tool_calls:
                # Limite de tool calls atingido — pedir ao LLM para responder sem tools
                logger.warning(f"Limite de {self.max_tool_calls} tool calls atingido, forçando resposta")
                self.conversation.append({
                    "role": "assistant",
                    "content": "[Tentativa de chamar ferramenta ignorada — limite atingido]",
                })
                self.conversation.append({
                    "role": "user",
                    "content": "[SISTEMA] Limite de ferramentas atingido. Responda ao usuário com as informações que já tem, sem chamar mais ferramentas.",
                })
                continue

            # Não é tool call — é resposta final ao usuário
            # Extrair atualização do Working Memory (se houver)
            clean_response = self._extract_memory_update(response_text)

            self.conversation.append({"role": "assistant", "content": clean_response})

            return clean_response

    async def _emit_action(self, action_type: str, data: dict) -> None:
        """Emite ação de progresso para o frontend (se callback configurado)."""
        if self.on_action:
            try:
                await self.on_action(action_type, data)
            except Exception as e:
                logger.warning(f"Erro ao emitir ação: {e}")

    @staticmethod
    def _describe_tool_action(tool_name: str, params: dict) -> str:
        """Gera descrição legível de uma ação de tool para o frontend."""
        if tool_name == "search_knowledge_base":
            query = params.get("text", params.get("feature", ""))
            return f"Buscando na base: \"{query}\"" if query else "Buscando na base de conhecimento"
        elif tool_name == "generate_card":
            return "Gerando card da User Story"
        elif tool_name == "save_working_memory":
            return "Salvando estado da especificação"
        elif tool_name == "get_feature_context":
            feature = params.get("feature", "")
            return f"Carregando contexto de \"{feature}\"" if feature else "Carregando contexto"
        return f"Executando {tool_name}"

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

        O LLM deve retornar APENAS o JSON (sem code blocks), mas tratamos
        múltiplos formatos como fallback.
        """
        stripped = response.strip()

        # Padrão 0: Resposta INTEIRA é JSON puro (caso ideal após fix do prompt)
        if stripped.startswith("{") and stripped.endswith("}"):
            data = self._try_parse_tool_json(stripped)
            if data:
                logger.info("Tool call extraída: resposta é JSON puro")
                return data

        # Padrão 1: JSON em code block (fallback se LLM ainda usar ```)
        match = re.search(r'```(?:json)?\s*\n?\s*(\{[^`]*?"tool"\s*:.*?\})\s*\n?\s*```', response, re.DOTALL)
        if match:
            data = self._try_parse_tool_json(match.group(1))
            if data:
                logger.info("Tool call extraída: JSON em code block")
                return data

        # Padrão 2: Buscar JSON com balanceamento de chaves (suporta aninhamento)
        tool_pos = response.find('"tool"')
        if tool_pos != -1:
            # Encontrar o { antes do "tool"
            brace_start = response.rfind('{', 0, tool_pos)
            if brace_start != -1:
                extracted = self._extract_balanced_json(response, brace_start)
                if extracted:
                    data = self._try_parse_tool_json(extracted)
                    if data:
                        logger.info("Tool call extraída: JSON embutido com chaves balanceadas")
                        return data

        # Padrão 3: JSON no final da resposta
        lines = stripped.split("\n")
        for i in range(len(lines) - 1, max(len(lines) - 10, -1), -1):
            line = lines[i].strip()
            if line.startswith("{") and '"tool"' in line:
                data = self._try_parse_tool_json(line)
                if data:
                    logger.info("Tool call extraída: JSON no final da resposta")
                    return data

        return None

    @staticmethod
    def _try_parse_tool_json(text: str) -> Optional[Dict]:
        """Tenta parsear texto como JSON de tool call."""
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "tool" in data:
                return data
        except json.JSONDecodeError:
            pass
        return None

    @staticmethod
    def _extract_balanced_json(text: str, start: int) -> Optional[str]:
        """Extrai JSON com chaves balanceadas a partir de uma posição."""
        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape:
                escape = False
                continue

            if ch == '\\' and in_string:
                escape = True
                continue

            if ch == '"' and not escape:
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]

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

    # Mapeamento de nomes comuns/abreviados que o LLM pode usar
    # para os campos reais do WorkingMemory.
    _FIELD_ALIASES = {
        # acceptance_criteria → split em product/technical
        "acceptance_criteria": "acceptance_criteria_product",
        "criterios_aceite": "acceptance_criteria_product",
        "criteria": "acceptance_criteria_product",
        # scope_defined → split em in_scope/out_of_scope
        "scope_defined": "_scope_compound",
        "scope": "_scope_compound",
        "escopo": "_scope_compound",
        # Outros aliases comuns
        "rules": "business_rules",
        "regras": "business_rules",
        "flow": "main_flow",
        "fluxo": "main_flow",
        "fluxo_principal": "main_flow",
        "fluxos_alternativos": "alternative_flows",
        "fluxos_erro": "error_flows",
        "nao_aceite": "non_acceptance_criteria",
        "cards_filhos": "child_cards",
        "observacoes": "observations",
    }

    def _apply_memory_update(self, update: Dict[str, Any]) -> None:
        """Aplica atualização parcial ao Working Memory.

        O update é um dict parcial — só os campos que mudaram.
        Listas são adicionadas (extend), não substituídas.
        Suporta aliases para campos compostos (ex: acceptance_criteria,
        scope_defined) que o LLM pode usar em vez dos nomes internos.
        """
        for key, value in update.items():
            resolved_key = self._FIELD_ALIASES.get(key, key)

            # Tratamento especial: scope_defined é um campo composto
            if resolved_key == "_scope_compound":
                self._apply_scope_update(value)
                continue

            if not hasattr(self.memory, resolved_key):
                logger.warning(
                    f"Campo ignorado no memory update: '{key}' "
                    f"(não existe no WorkingMemory)"
                )
                continue

            current = getattr(self.memory, resolved_key)

            # Listas: extend (adicionar, não substituir)
            if isinstance(current, list) and isinstance(value, list):
                current.extend(value)
            elif isinstance(current, list) and isinstance(value, dict):
                # LLM pode enviar um dict único em vez de lista
                current.append(value)
            # Valores simples: substituir
            else:
                setattr(self.memory, resolved_key, value)

    def _apply_scope_update(self, value: Any) -> None:
        """Trata o campo composto scope_defined, mapeando para in_scope e out_of_scope."""
        if isinstance(value, dict):
            if "in_scope" in value:
                in_s = value["in_scope"]
                if isinstance(in_s, list):
                    self.memory.in_scope.extend(in_s)
                elif isinstance(in_s, str):
                    self.memory.in_scope.append(in_s)
            if "out_of_scope" in value:
                out_s = value["out_of_scope"]
                if isinstance(out_s, list):
                    self.memory.out_of_scope.extend(out_s)
                elif isinstance(out_s, str):
                    self.memory.out_of_scope.append(out_s)
        elif isinstance(value, bool):
            # Ignorar se é apenas um flag booleano
            pass
        else:
            logger.warning(
                f"scope_defined recebeu tipo inesperado: {type(value)}. "
                f"Esperado dict com 'in_scope' e 'out_of_scope'."
            )

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
