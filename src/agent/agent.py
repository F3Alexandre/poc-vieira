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
