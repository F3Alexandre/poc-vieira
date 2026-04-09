# SPEC — Etapa 1: Dados Simulados (Camada Bronze)

## Objetivo

Criar 5 documentos simulados que representam fontes reais de informação sobre uma feature fictícia de **"Devolução de Produtos"** de um e-commerce. Esses dados serão processados pelo pipeline de ingestão (Etapa 4) e populam a base de conhecimento Silver.

Os dados devem ser **realistas o suficiente** para demonstrar:
- Regras de negócio com exceções condicionais
- Decisões técnicas concretas
- Ambiguidades não resolvidas
- Contradições entre fontes diferentes
- Diferentes níveis de formalidade (documento formal vs chat informal)
- Vocabulário variado (mesma coisa descrita com termos diferentes em fontes diferentes)

## Estrutura de diretórios

```
data/
└── bronze/
    ├── calls/
    │   ├── grooming-devolucao-2026-04-01.md
    │   └── refinamento-tecnico-devolucao-2026-04-05.md
    ├── docs/
    │   ├── prd-devolucao-v2.md
    │   └── requisitos-cliente-enterprise.md
    └── chats/
        └── slack-devolucao-2026-04-03.md
```

## Critérios de qualidade dos dados

### Obrigatório em TODOS os arquivos
- Texto em português brasileiro
- Entre 400-800 palavras por arquivo
- Deve conter informação que será classificada em pelo menos 2 `chunk_types` diferentes
- Deve mencionar a feature como "devolução de produtos" ou variações (estorno, reversão, return)
- Deve mencionar pelo menos uma integração com outro sistema

### Obrigatório no CONJUNTO dos arquivos
- Pelo menos 1 contradição entre documentos (o grooming diz uma coisa, o chat diz outra)
- Pelo menos 1 ambiguidade não resolvida (mencionada mas sem decisão final)
- Pelo menos 1 informação que aparece com termos diferentes em fontes diferentes
- Cobertura dos seguintes chunk_types (a classificação será feita na Etapa 4, mas os dados devem conter informação para cada tipo):
  - `regra_negocio` (mínimo 5 regras distribuídas nos docs)
  - `fluxo_usuario` (mínimo 1 fluxo principal completo)
  - `decisao_tecnica` (mínimo 3 decisões)
  - `requisito_nao_funcional` (mínimo 2)
  - `definicao_escopo` (o que está dentro e fora)
  - `restricao` (mínimo 1 limitação)
  - `integracao` (mínimo 2 integrações)
  - `contexto_negocio` (motivação e background)

---

## Arquivo 1: Transcrição de Grooming

**Caminho:** `data/bronze/calls/grooming-devolucao-2026-04-01.md`

**Contexto simulado:** Reunião de grooming de produto onde PO, arquiteto e dev discutem a feature de devolução pela primeira vez. Tom informal, decisões tomadas verbalmente, algumas coisas ficam em aberto.

**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev Backend)

**Conteúdo obrigatório — o texto deve conter estas informações entrelaçadas na conversa:**

Regras de negócio discutidas:
- Prazo de devolução para pessoa física: 30 dias corridos a partir da data de entrega
- Prazo de devolução para PJ com contrato enterprise: conforme contrato (pode ser 60 ou 90 dias)
- Produto deve estar na embalagem original e sem sinais de uso
- Para defeito de fabricação, o prazo segue a garantia legal (90 dias)
- Devolução gera estorno no mesmo método de pagamento original
- Estorno para cartão de crédito: até 2 faturas para aparecer
- Estorno para PIX: até 24 horas úteis

Decisão técnica:
- API de estorno será integrada com o gateway de pagamento (Gateway XPay)
- Carlos sugere usar mensageria assíncrona para o processo de estorno (não bloquear o usuário)

Fluxo discutido informalmente:
- Cliente acessa "Meus Pedidos" → seleciona o pedido → clica "Solicitar Devolução" → escolhe motivo → confirma → recebe protocolo

Ambiguidade NÃO resolvida:
- Devolução parcial (devolver 1 item de um pedido com 3 itens) — Ana diz "precisamos ver isso com o financeiro", Carlos diz "tecnicamente é possível mas complica o estorno", Pedro diz "vamos deixar pra v2". NÃO HOUVE DECISÃO FINAL.

Escopo mencionado:
- Ana diz que troca de produto é outra feature, não entra aqui
- Pedro pergunta sobre devolução de produto digital, Ana diz "por enquanto só produto físico"

Requisito não funcional mencionado vagamente:
- Ana diz "precisa ser rápido, o cliente não pode ficar esperando"
- Carlos diz "vou ver o SLA do gateway"

**Formato do arquivo:**

```markdown
# Grooming — Devolução de Produtos
**Data:** 2026-04-01
**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev Backend)
**Duração:** 45 min

---

**Ana:** [fala]

**Carlos:** [fala]

**Pedro:** [fala]

[... continuar em formato de transcrição de reunião, tom informal,
com interrupções naturais, concordâncias, discordâncias, e os
momentos onde algo fica sem decisão]
```

**Palavras:** 500-700

---

## Arquivo 2: PRD (Documento de Produto)

**Caminho:** `data/bronze/docs/prd-devolucao-v2.md`

**Contexto simulado:** Documento formal de requisitos de produto, escrito pela PO após a reunião de grooming. Mais estruturado, linguagem formal, mas incorpora as decisões do grooming.

**Conteúdo obrigatório:**

Seções do documento:
1. **Visão geral** — por que essa feature existe, impacto no negócio (20% das reclamações no SAC são sobre devolução, NPS caiu 15 pontos por causa de processo manual)
2. **Personas** — Cliente PF (comprador individual), Cliente PJ (empresa com contrato), Operador de Suporte (atendente do SAC)
3. **Regras de negócio** — formalizadas em lista numerada:
   - RN-01: Prazo de 30 dias corridos para PF a partir da data de entrega
   - RN-02: Prazo conforme contrato para PJ enterprise
   - RN-03: Produto em embalagem original e sem uso (exceto defeito)
   - RN-04: Estorno no método de pagamento original
   - RN-05: Limite de 3 devoluções por cliente PF por mês (ESTA REGRA NÃO FOI MENCIONADA NO GROOMING — é nova)
   - RN-06: Pedidos acima de R$ 5.000 necessitam aprovação do gestor de operações
4. **Requisitos não funcionais**:
   - Performance: endpoint de criação de devolução deve responder em até 200ms (p95)
   - Disponibilidade: 99.9% uptime
   - Segurança: autenticação via OAuth 2.0, dados de pagamento não trafegam pelo nosso backend
5. **Integrações**:
   - Gateway XPay — API de estorno
   - Sistema de Logística Reversa (LogiTrack) — agendamento de coleta
   - SAC (Zendesk) — atualização de tickets
6. **Fora do escopo**:
   - Troca de produto (feature separada)
   - Devolução de produto digital
   - Devolução parcial de pedido (decidido para v2)

**CONTRADIÇÃO INTENCIONAL com o grooming:** No grooming, a devolução parcial ficou sem decisão final. No PRD, a Ana colocou como "decidido para v2". Essa divergência é intencional — o agente deve detectar que no grooming o assunto ficou em aberto mas no PRD aparece como decisão tomada.

**Formato:** Markdown estruturado com headers, listas numeradas, tabela de integrações.

**Palavras:** 600-800

---

## Arquivo 3: Mensagens de Chat

**Caminho:** `data/bronze/chats/slack-devolucao-2026-04-03.md`

**Contexto simulado:** Thread no Slack entre os participantes, 2 dias após o grooming. Conversas curtas, informais, com informações técnicas importantes misturadas com conversa casual.

**Conteúdo obrigatório:**

Informações técnicas importantes que devem aparecer nas mensagens:
- Pedro descobre que o endpoint de estorno do Gateway XPay tem rate limit de 100 req/min
- Pedro pergunta: "e se o produto já foi usado mas tem defeito?" — Ana responde: "produto usado não aceita devolução, EXCETO se for defeito de fabricação comprovado"
- Carlos menciona que precisa de idempotência no endpoint de estorno para evitar estorno duplicado
- Alguém (Pedro) menciona informalmente: "seria legal ter uma tela de acompanhamento do status da devolução, tipo rastreio de entrega invertido"
- Ana compartilha que o time de dados pediu eventos de devolução no Kafka para analytics

**CONTRADIÇÃO INTENCIONAL com o PRD:** No chat, Ana menciona que "o prazo de devolução para PF pode ser estendido para 45 dias em campanhas promocionais". Isso NÃO está no PRD (que fala apenas 30 dias). O agente deve detectar essa inconsistência.

**Informação com vocabulário diferente:** No chat, Pedro chama o estorno de "reversal" e a devolução de "return request". O agente (via glossário) deve conseguir mapear esses termos.

**Formato:**

```markdown
# Thread: #proj-devolucao
**Canal:** #proj-devolucao
**Data:** 2026-04-03

---

**[09:15] Pedro:** [mensagem]

**[09:18] Ana:** [mensagem]

**[09:22] Carlos:** [mensagem]

[... continuar com 15-20 mensagens, incluindo algumas que são
irrelevantes (bom dia, risadas, emojis) para simular ruído real]
```

**Palavras:** 400-600

---

## Arquivo 4: Documento de Requisitos do Cliente Enterprise

**Caminho:** `data/bronze/docs/requisitos-cliente-enterprise.md`

**Contexto simulado:** Documento formal enviado por um cliente enterprise (TechCorp Ltda) com requisitos específicos para o módulo de devolução no contrato deles.

**Conteúdo obrigatório:**

Requisitos do cliente:
- Prazo de devolução: 90 dias corridos (diferente dos 30 dias padrão PF)
- Toda devolução precisa de aprovação prévia do gestor de compras do cliente antes de ser processada
- Integração com ERP do cliente (SAP) via webhook para notificação de status da devolução
- Relatório mensal de devoluções com: quantidade, valor total estornado, motivos, tempo médio de processamento
- SLA específico: devolução deve ser processada (estorno iniciado) em até 48 horas após aprovação
- Necessidade de campo customizado "Centro de Custo" na solicitação de devolução
- Devolução parcial é OBRIGATÓRIA para esse cliente (eles compram em lote e frequentemente devolvem itens específicos)

**CONTRADIÇÃO INTENCIONAL:** O PRD e o grooming tratam devolução parcial como fora de escopo / v2. O cliente enterprise EXIGE devolução parcial. O agente deve levantar essa contradição.

**Formato:** Documento formal com cabeçalho do cliente, seções numeradas, linguagem contratual.

```markdown
# Requisitos de Devolução — TechCorp Ltda
**Contrato:** ENT-2026-0847
**Data:** 2026-03-28
**Versão:** 1.0
**Responsável:** Maria Silva (Gerente de Compras, TechCorp)

## 1. Introdução
[...]

## 2. Requisitos funcionais
[...]

## 3. Requisitos de integração
[...]

## 4. SLAs
[...]
```

**Palavras:** 400-600

---

## Arquivo 5: Ata de Refinamento Técnico

**Caminho:** `data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md`

**Contexto simulado:** Ata de reunião técnica entre arquiteto e devs, focada em decisões de implementação. Tom semi-formal (é uma ata, não transcrição).

**Participantes:** Carlos (Arquiteto), Pedro (Dev Backend), Julia (Dev Frontend)

**Conteúdo obrigatório:**

Decisões técnicas registradas:
- Endpoint principal: `POST /api/v1/returns` — cria solicitação de devolução
- Endpoints auxiliares:
  - `GET /api/v1/returns/{id}` — consulta status
  - `GET /api/v1/returns?order_id={id}` — lista devoluções de um pedido
  - `PATCH /api/v1/returns/{id}/cancel` — cancela solicitação (antes do envio)
- State machine da devolução com estados: `requested` → `approved` → `shipping_label_sent` → `in_transit` → `received` → `inspecting` → `refunded` (ou `rejected`)
- Comunicação com LogiTrack (logística reversa) via fila SQS: publicar evento `return.approved` para agendar coleta
- Comunicação com Gateway XPay para estorno: chamada HTTP síncrona com retry exponencial (max 3 tentativas) e fallback para fila de reprocessamento
- Idempotência no endpoint de estorno via idempotency_key gerado no momento da criação da devolução
- Frontend: Julia propõe componente reutilizável de timeline para mostrar status da devolução (similar ao rastreio)
- Observabilidade: logs estruturados com correlation_id em todas as chamadas, métricas de latência do estorno no Datadog, alerta se taxa de falha de estorno > 5%

Dúvida técnica pendente:
- Como lidar com estorno quando o gateway está fora do ar por mais de 24h? Carlos sugere "dead letter queue + alerta para operações", Pedro sugere "retry infinito com backoff". Decisão adiada para próxima reunião.

Restrição técnica identificada:
- Rate limit do Gateway XPay: 100 requisições por minuto. Carlos calcula que em Black Friday podemos ter picos de 500 devoluções/hora, então precisamos de throttling no nosso lado.

**Formato:**

```markdown
# Refinamento Técnico — Devolução de Produtos
**Data:** 2026-04-05
**Participantes:** Carlos (Arquiteto), Pedro (Dev Backend), Julia (Dev Frontend)
**Duração:** 1h30

## Decisões

### 1. API Design
[...]

### 2. State Machine
[...]

### 3. Integrações
[...]

### 4. Observabilidade
[...]

## Pendências
[...]
```

**Palavras:** 500-700

---

## Mapa de contradições e ambiguidades (referência para testes)

Este mapa é para uso interno durante testes. O agente deve ser capaz de detectar essas inconsistências:

| ID | Tipo | Fonte A | Fonte B | Descrição |
|----|------|---------|---------|-----------|
| C-01 | Contradição | Grooming (sem decisão) | PRD (decidido v2) | Devolução parcial: no grooming ficou em aberto, no PRD aparece como "decidido para v2" |
| C-02 | Contradição | PRD (30 dias PF fixo) | Chat (45 dias em promoção) | Prazo PF: PRD diz 30 dias, chat menciona extensão para 45 dias em campanhas |
| C-03 | Contradição | PRD/Grooming (parcial fora de escopo) | Cliente enterprise (parcial obrigatório) | Devolução parcial fora de escopo vs exigência contratual do cliente enterprise |
| A-01 | Ambiguidade | Grooming | — | Devolução parcial sem decisão final (3 opiniões diferentes, nenhuma conclusão) |
| A-02 | Ambiguidade | Refinamento técnico | — | Gateway fora do ar >24h: dead letter queue vs retry infinito, decisão adiada |
| V-01 | Vocabulário | Chat (reversal, return request) | PRD/Grooming (estorno, devolução) | Mesmos conceitos com termos diferentes entre fontes |

## Validação

Após criar os arquivos, execute:

```bash
# Verificar que todos os arquivos existem
expected_files=(
  "data/bronze/calls/grooming-devolucao-2026-04-01.md"
  "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md"
  "data/bronze/docs/prd-devolucao-v2.md"
  "data/bronze/docs/requisitos-cliente-enterprise.md"
  "data/bronze/chats/slack-devolucao-2026-04-03.md"
)

all_ok=true
for f in "${expected_files[@]}"; do
  if [ ! -f "$f" ]; then
    echo "FALTANDO: $f"
    all_ok=false
  else
    words=$(wc -w < "$f")
    echo "OK: $f ($words palavras)"
    if [ "$words" -lt 300 ]; then
      echo "  AVISO: arquivo muito curto (mínimo 400 palavras esperado)"
    fi
  fi
done

if $all_ok; then
  echo ""
  echo "=== Todos os arquivos bronze criados ==="
else
  echo ""
  echo "=== ERRO: arquivos faltando ==="
  exit 1
fi
```

```bash
# Verificar conteúdo mínimo (busca por termos-chave que devem existir)
echo "Verificando termos-chave nos documentos..."

# Devolução/estorno deve aparecer em todos
for f in data/bronze/**/*.md; do
  if ! grep -qi "devolu" "$f" && ! grep -qi "estorno" "$f" && ! grep -qi "return" "$f"; then
    echo "AVISO: $f não menciona devolução/estorno/return"
  fi
done

# Contradição C-02: "45 dias" ou "promoção" deve aparecer no chat
if ! grep -qi "45 dias\|campanha\|promoção\|promocional" data/bronze/chats/slack-devolucao-2026-04-03.md; then
  echo "AVISO: chat não contém a contradição C-02 (prazo promocional)"
fi

# Contradição C-03: "parcial" deve aparecer no doc do cliente
if ! grep -qi "parcial" data/bronze/docs/requisitos-cliente-enterprise.md; then
  echo "AVISO: doc do cliente não menciona devolução parcial"
fi

# Vocabulário V-01: termos em inglês devem aparecer no chat
if ! grep -qi "reversal\|return request" data/bronze/chats/slack-devolucao-2026-04-03.md; then
  echo "AVISO: chat não contém termos em inglês (reversal/return request)"
fi

echo "Verificação concluída."
```

## Definição de pronto (DoD)

- [ ] 5 arquivos .md criados nos caminhos corretos
- [ ] Cada arquivo tem entre 400-800 palavras
- [ ] Contradições C-01, C-02, C-03 estão presentes nos documentos
- [ ] Ambiguidades A-01, A-02 estão presentes nos documentos
- [ ] Variação de vocabulário V-01 está presente
- [ ] Pelo menos 5 regras de negócio distribuídas nos documentos
- [ ] Pelo menos 1 fluxo de usuário completo (mínimo 5 passos)
- [ ] Pelo menos 3 decisões técnicas concretas
- [ ] Pelo menos 2 integrações mencionadas
- [ ] Pelo menos 2 requisitos não funcionais com métricas
- [ ] Scripts de validação passam sem erros
