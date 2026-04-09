# SPEC — Etapa 1: Dados Simulados (Camada Bronze)

## Objetivo

Criar 5 documentos simulados que representam fontes reais de informação sobre a feature fictícia de **"Devolução de Produtos"** de um e-commerce. Esses dados serão processados pelo pipeline de ingestão (Etapa 3) e populam a base de conhecimento Silver (Etapa 2).

Os dados devem ser **realistas o suficiente** para demonstrar:
- Regras de negócio com exceções condicionais
- Decisões técnicas concretas
- Ambiguidades não resolvidas
- Contradições entre fontes diferentes
- Diferentes níveis de formalidade (documento formal vs chat informal)
- Vocabulário variado (mesma coisa descrita com termos diferentes em fontes diferentes)

## Dependências

Nenhuma. Esta é a primeira etapa do projeto.

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

> **Nota sobre source_type:** o pipeline de ingestão (Etapa 3) infere o `source_type` pelo diretório:
> - `calls/` → `transcricao_reuniao`
> - `docs/` → `documento_produto` (ou `documento_cliente` se "cliente" ou "enterprise" no nome do arquivo)
> - `chats/` → `chat`

## Critérios de qualidade dos dados

### Obrigatório em TODOS os arquivos
- Texto em português brasileiro
- Entre 400-800 palavras por arquivo
- Deve conter informação que será classificada em pelo menos 2 `chunk_types` diferentes
- Deve mencionar a feature como "devolução de produtos" ou variações (estorno, reversão, return)
- Deve mencionar pelo menos uma integração com outro sistema

### Obrigatório no CONJUNTO dos arquivos
- 3 contradições intencionais entre documentos (C-01, C-02, C-03)
- 2 ambiguidades não resolvidas (A-01, A-02)
- Variação de vocabulário entre fontes (V-01)
- Cobertura dos seguintes `chunk_types` (a classificação será feita na Etapa 3, mas os dados devem conter informação para cada tipo):
  - `regra_negocio` (mínimo 5 regras distribuídas nos docs)
  - `fluxo_usuario` (mínimo 1 fluxo principal completo)
  - `decisao_tecnica` (mínimo 3 decisões)
  - `requisito_nao_funcional` (mínimo 2 com métricas)
  - `definicao_escopo` (o que está dentro e fora)
  - `restricao` (mínimo 1 limitação)
  - `criterio_aceite` (mínimo 1 condição de aceite explícita)
  - `integracao` (mínimo 2 integrações)
  - `vocabulario` (mínimo 1 correção/definição de termo)
  - `contexto_negocio` (motivação e background)

### Sistemas referenciados (usar estes nomes em todos os docs)
- **Gateway XPay** — gateway de pagamento para estornos
- **LogiTrack** — sistema de logística reversa (coleta, etiqueta, rastreio)
- **Zendesk** — SAC, abertura de tickets
- **SAP (ERP TechCorp)** — integração via webhook com o ERP do cliente enterprise
- **Kafka** — eventos para analytics/dados

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
- API de estorno será integrada com o Gateway XPay
- Carlos sugere usar mensageria assíncrona para o processo de estorno (não bloquear o usuário)

Fluxo discutido informalmente:
- Cliente acessa "Meus Pedidos" → seleciona o pedido → clica "Solicitar Devolução" → escolhe motivo → confirma → recebe protocolo

**Ambiguidade A-01 (NÃO resolvida):**
- Devolução parcial (devolver 1 item de um pedido com 3 itens) — Ana diz "precisamos ver isso com o financeiro", Carlos diz "tecnicamente é possível mas complica o estorno", Pedro diz "vamos deixar pra v2". **NÃO HOUVE DECISÃO FINAL.**

Escopo mencionado:
- Ana diz que troca de produto é outra feature, não entra aqui
- Pedro pergunta sobre devolução de produto digital, Ana diz "por enquanto só produto físico"

Requisito não funcional mencionado vagamente:
- Ana diz "precisa ser rápido, o cliente não pode ficar esperando"
- Carlos diz "vou ver o SLA do Gateway XPay"

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

**Tom e estilo:**
A transcrição deve parecer real. Usar linguagem informal brasileira:
- "Beleza, então fica assim..."
- "Peraí, mas e se..."
- "Tipo, o cliente vai lá e..."
- "Aí a gente faz o estorno, né"
- Uma pessoa interrompendo outra ocasionalmente
- Carlos usando termos mais técnicos que Ana
- Pedro fazendo perguntas práticas de implementação

**Palavras:** 500-700

---

## Arquivo 2: PRD (Documento de Produto)

**Caminho:** `data/bronze/docs/prd-devolucao-v2.md`

**Contexto simulado:** Documento formal de requisitos de produto, escrito pela PO após a reunião de grooming. Mais estruturado, linguagem formal, incorpora as decisões do grooming.

**Conteúdo obrigatório:**

Seções do documento:
1. **Visão geral** — por que essa feature existe, impacto no negócio (20% das reclamações no SAC são sobre devolução, NPS caiu 15 pontos por causa de processo manual)
2. **Personas** — Cliente PF (comprador individual), Cliente PJ (empresa com contrato), Operador de Suporte (atendente do SAC)
3. **Regras de negócio** — formalizadas em lista numerada:
   - RN-01: Prazo de 30 dias corridos para PF a partir da data de entrega
   - RN-02: Prazo conforme contrato para PJ enterprise
   - RN-03: Produto em embalagem original e sem uso (exceto defeito)
   - RN-04: Estorno no método de pagamento original
   - RN-05: Limite de 3 devoluções por cliente PF por mês (**REGRA NOVA** — não mencionada no grooming)
   - RN-06: Pedidos acima de R$ 5.000 necessitam aprovação do gestor de operações
   - RN-07: Motivos aceitos: arrependimento, produto diferente do anunciado, defeito, danificado no transporte. Cada motivo tem tratamento diferente (arrependimento: frete por conta do cliente; defeito: frete por conta da empresa)
   - RN-08: Estorno do valor integral do produto. Frete original NÃO é estornado exceto em caso de defeito ou erro da empresa
4. **Requisitos não funcionais**:
   - Performance: endpoint de criação de devolução deve responder em até 200ms (p95)
   - Disponibilidade: 99.9% uptime
   - Estorno deve ser processado em até 5 dias úteis após recebimento no CD
   - Segurança: autenticação via OAuth 2.0, dados de pagamento não trafegam pelo backend
5. **Integrações**:
   - Gateway XPay — API de estorno
   - LogiTrack — logística reversa, agendamento de coleta
   - Zendesk — atualização de tickets automática quando devolução é por defeito
6. **Fora do escopo**:
   - Troca de produto (feature separada)
   - Devolução de produto digital
   - Devolução parcial de pedido (decidido para v2)

**CONTRADIÇÃO C-01:** No grooming, a devolução parcial ficou **sem decisão final** (A-01). No PRD, a Ana colocou como **"decidido para v2"**. Essa divergência é intencional — o agente deve detectar que no grooming o assunto ficou em aberto mas no PRD aparece como decisão tomada.

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
- Pedro pergunta: "e se o cara abriu a caixa mas não usou? tipo, eletrônico que tirou o lacre?" — Ana responde: "aberto sem uso aceita sim, desde que com todos os acessórios"
- Carlos menciona que precisa de idempotência no endpoint de estorno para evitar estorno duplicado
- Pedro menciona informalmente: "seria legal ter uma tela de acompanhamento do status da devolução, tipo rastreio de entrega invertido"
- Ana compartilha que o time de dados pediu eventos de devolução no Kafka para analytics

**CONTRADIÇÃO C-02:** Ana menciona que "o prazo de devolução para PF pode ser estendido para 45 dias em campanhas promocionais". Isso NÃO está no PRD (que fala apenas 30 dias fixo). O agente deve detectar essa inconsistência.

**Vocabulário V-01:** Pedro usa o termo "reversal" e "return request". Carlos corrige: "Aqui a gente chama de 'estorno', o 'reversal' é o termo da API do Gateway XPay. No nosso domínio é estorno mesmo." Informação classificável como `vocabulario`.

**Tom e estilo:**
Mensagens curtas, informais, com emoji ocasional, abreviações ("vc", "blz", "tbm"), respostas rápidas em sequência. Alguém mandando "👍" como confirmação. Algumas mensagens irrelevantes (bom dia, risadas) para simular ruído real.

**Formato:**

```markdown
# Thread: #proj-devolucao
**Canal:** #proj-devolucao
**Data:** 2026-04-03

---

**[09:15] Pedro:** [mensagem]

**[09:18] Ana:** [mensagem]

**[09:22] Carlos:** [mensagem]

[... 15-20 mensagens incluindo ruído]
```

**Palavras:** 400-600

---

## Arquivo 4: Documento de Requisitos do Cliente Enterprise

**Caminho:** `data/bronze/docs/requisitos-cliente-enterprise.md`

**Contexto simulado:** Documento formal enviado por um cliente enterprise (TechCorp Ltda) com requisitos específicos para o módulo de devolução no contrato deles.

**Conteúdo obrigatório:**

Requisitos do cliente:
- Prazo de devolução: 90 dias corridos (diferente dos 30 dias padrão PF) conforme contrato ENT-2026-0042
- Toda devolução de item acima de R$ 5.000 precisa de aprovação do gestor de compras antes de ser processada. Até R$ 5.000, qualquer funcionário autorizado pode solicitar
- Integração via webhook com o ERP do cliente (SAP) para notificação de status. Endpoint: POST para o ERP com payload contendo order_id, return_id, items, status, timestamp
- Relatório mensal de devoluções em formato CSV enviado por email até o 5º dia útil do mês seguinte. Campos: data solicitação, produto, motivo, valor estornado, status, tempo de processamento
- SLA específico: devolução deve ser processada (estorno iniciado) em até 48 horas após aprovação
- Necessidade de campo customizado "Centro de Custo" na solicitação de devolução
- Devolução parcial é OBRIGATÓRIA para esse cliente (eles compram em lote e frequentemente devolvem itens específicos)

**CONTRADIÇÃO C-03:** O PRD e o grooming tratam devolução parcial como fora de escopo / v2. O cliente enterprise **EXIGE** devolução parcial. O agente deve levantar essa contradição.

**Formato:** Documento formal com cabeçalho do cliente, seções numeradas, linguagem contratual.

```markdown
# Requisitos de Devolução — TechCorp Ltda
**Contrato:** ENT-2026-0042
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

**Contexto simulado:** Ata de reunião técnica entre arquiteto, devs e QA, focada em decisões de implementação. Tom semi-formal (é uma ata estruturada, mais organizada que o grooming, mas ainda conversacional).

**Participantes:** Carlos (Arquiteto), Pedro (Dev Backend), Julia (Dev Frontend), Marina (QA)

**Conteúdo obrigatório:**

Decisões técnicas registradas:
- Endpoint principal: `POST /api/v1/returns` — cria solicitação de devolução
- Endpoints auxiliares:
  - `GET /api/v1/returns/{id}` — consulta status
  - `GET /api/v1/returns?order_id={id}` — lista devoluções de um pedido
  - `PATCH /api/v1/returns/{id}/cancel` — cancela solicitação (antes do envio)
- State machine da devolução: `requested` → `approved` → `shipping_label_sent` → `in_transit` → `received` → `inspecting` → `refunded` (ou `rejected`). Para PJ acima de R$5.000: `requested` → `pending_approval` → `approved` → ...
- Comunicação com LogiTrack (logística reversa) via fila SQS: publicar evento `return.approved` para agendar coleta
- Comunicação com Gateway XPay para estorno: chamada HTTP síncrona com retry exponencial (max 3 tentativas) e fallback para fila de reprocessamento
- Idempotência no endpoint de estorno via `idempotency_key` gerado no momento da criação da devolução
- Frontend: Julia propõe componente reutilizável de timeline para mostrar status da devolução (similar ao rastreio)
- Observabilidade: logs estruturados com `correlation_id` em todas as chamadas, métricas de latência do estorno no Datadog, alerta se taxa de falha de estorno > 5%

Critério de aceite (Marina QA):
- "Preciso que o estorno nunca seja processado em duplicidade. Se o sistema falhar no meio, o retry não pode estornar duas vezes." Carlos confirma que a idempotência resolve isso.

Restrição técnica:
- Rate limit do Gateway XPay: 100 requisições por minuto. Carlos calcula que em Black Friday podemos ter picos de 500 devoluções/hora, então precisamos de throttling no nosso lado.

**Ambiguidade A-02:**
- Como lidar com estorno quando o gateway está fora do ar por mais de 24h? Carlos sugere "dead letter queue + alerta para operações", Pedro sugere "retry infinito com backoff". **Decisão adiada para próxima reunião.**

**Formato:**

```markdown
# Refinamento Técnico — Devolução de Produtos
**Data:** 2026-04-05
**Participantes:** Carlos (Arquiteto), Pedro (Dev Backend), Julia (Dev Frontend), Marina (QA)
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

## Critérios de aceite (QA)
[...]

## Pendências
[...]
```

**Tom e estilo:**
Mais técnico que o grooming. Termos como "state machine", "idempotency key", "exponential backoff", "SQS consumer". Mas ainda conversacional em partes — Carlos liderando decisões, Pedro questionando, Julia propondo UX, Marina focando em testabilidade.

**Palavras:** 500-700

---

## Mapa de contradições, ambiguidades e vocabulário (referência para testes)

Este mapa NÃO é um documento bronze. É uma referência para validar se o pipeline e o agente detectam corretamente.

| ID | Tipo | Fonte A | Fonte B | Descrição |
|----|------|---------|---------|-----------|
| C-01 | Contradição | Grooming (sem decisão) | PRD (decidido v2) | Devolução parcial: no grooming ficou em aberto, no PRD aparece como "decidido para v2" |
| C-02 | Contradição | PRD (30 dias PF fixo) | Chat (45 dias em promoção) | Prazo PF: PRD diz 30 dias, chat menciona extensão para 45 dias em campanhas |
| C-03 | Contradição | PRD/Grooming (parcial fora de escopo) | Cliente enterprise (parcial obrigatório) | Devolução parcial fora de escopo vs exigência contratual do cliente enterprise |
| A-01 | Ambiguidade | Grooming | — | Devolução parcial sem decisão final (3 opiniões diferentes, nenhuma conclusão) |
| A-02 | Ambiguidade | Refinamento técnico | — | Gateway fora do ar >24h: dead letter queue vs retry infinito, decisão adiada |
| V-01 | Vocabulário | Chat (reversal, return request) | PRD/Grooming (estorno, devolução) | Mesmos conceitos com termos diferentes entre fontes. Carlos corrige no chat. |

## Cobertura de chunk_types (referência para testes)

| chunk_type | Onde aparece | Quantidade mínima |
|---|---|---|
| `regra_negocio` | Grooming (prazo PF, prazo PJ, produto usado, defeito, estorno por método), PRD (RN-01 a RN-08), Chat (produto aberto sem uso), Enterprise (aprovação gestor, parcial obrigatória) | 8+ |
| `fluxo_usuario` | Grooming (fluxo principal), Chat (tela acompanhamento) | 2 |
| `decisao_tecnica` | Grooming (API Gateway XPay, mensageria), Refinamento (API design, state machine, SQS, idempotência, timeline frontend) | 5+ |
| `requisito_nao_funcional` | PRD (200ms p95, 99.9%, estorno 5 dias), Enterprise (SLA 48h, relatório mensal) | 4+ |
| `definicao_escopo` | PRD (dentro/fora do escopo) | 1 |
| `restricao` | Chat (rate limit 100 req/min), Refinamento (throttling Black Friday) | 2 |
| `criterio_aceite` | Refinamento (Marina: sem estorno duplicado) | 1 |
| `integracao` | PRD (XPay, LogiTrack, Zendesk), Chat (Kafka), Enterprise (SAP webhook), Refinamento (SQS, Datadog) | 5+ |
| `vocabulario` | Chat (reversal → estorno) | 1 |
| `contexto_negocio` | PRD (20% reclamações SAC, NPS -15) | 1 |

## Alinhamento com glossário do agente (SPEC-04)

Os documentos devem usar termos variados que exercitem o glossário de sinônimos do agente:

| Termo canônico | Variações que devem aparecer nos docs |
|---|---|
| devolução | "estorno" (PRD), "return" (chat), "devolver o dinheiro" (grooming) |
| PJ | "empresa" (grooming), "enterprise" (PRD/enterprise), "corporativo" (enterprise) |
| PF | "pessoa física" (grooming), "consumidor" (PRD), "cliente individual" (PRD) |
| fila | "SQS" (refinamento), "mensageria" (grooming), "queue" (chat) |
| endpoint | "API" (grooming), "rota" (informal no chat) |

---

## Validação

### Script de verificação de existência e tamanho

```bash
#!/bin/bash
echo "=== Validação Etapa 1 ==="

expected_files=(
  "data/bronze/calls/grooming-devolucao-2026-04-01.md"
  "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md"
  "data/bronze/docs/prd-devolucao-v2.md"
  "data/bronze/docs/requisitos-cliente-enterprise.md"
  "data/bronze/chats/slack-devolucao-2026-04-03.md"
)

all_ok=true
for f in "${expected_files[@]}"; do
  if [ -f "$f" ]; then
    words=$(wc -w < "$f")
    echo "✅ $f ($words palavras)"
    if [ "$words" -lt 400 ]; then
      echo "   ⚠️ AVISO: menos de 400 palavras"
      all_ok=false
    fi
    if [ "$words" -gt 800 ]; then
      echo "   ⚠️ AVISO: mais de 800 palavras"
      all_ok=false
    fi
  else
    echo "❌ $f — NÃO ENCONTRADO"
    all_ok=false
  fi
done

echo ""
if $all_ok; then
  echo "✅ Todos os arquivos presentes e dentro do tamanho"
else
  echo "❌ Problemas encontrados"
fi
```

### Script de verificação de conteúdo

```bash
#!/bin/bash
echo "=== Verificação de conteúdo ==="

# Devolução/estorno deve aparecer em todos
echo "Verificando termos-chave..."
for f in data/bronze/**/*.md; do
  if ! grep -qi "devolu\|estorno\|return" "$f"; then
    echo "⚠️ $f não menciona devolução/estorno/return"
  fi
done

# Contradição C-02: "45 dias" ou "promoção" no chat
echo ""
echo "Verificando contradições..."
if grep -qi "45 dias\|campanha\|promoção\|promocional" data/bronze/chats/slack-devolucao-2026-04-03.md; then
  echo "✅ C-02: prazo promocional presente no chat"
else
  echo "❌ C-02: chat não contém menção a prazo promocional"
fi

# Contradição C-03: "parcial" no doc do cliente
if grep -qi "parcial" data/bronze/docs/requisitos-cliente-enterprise.md; then
  echo "✅ C-03: devolução parcial presente no doc enterprise"
else
  echo "❌ C-03: doc enterprise não menciona devolução parcial"
fi

# Contradição C-01: "v2" no PRD e ambiguidade no grooming
if grep -qi "v2\|segunda fase\|próxima versão" data/bronze/docs/prd-devolucao-v2.md; then
  echo "✅ C-01: parcial como v2 presente no PRD"
else
  echo "❌ C-01: PRD não menciona parcial como v2"
fi

# Vocabulário V-01: termos em inglês no chat
echo ""
echo "Verificando vocabulário..."
if grep -qi "reversal\|return request" data/bronze/chats/slack-devolucao-2026-04-03.md; then
  echo "✅ V-01: termos em inglês presentes no chat"
else
  echo "❌ V-01: chat não contém termos em inglês"
fi

# Sinônimos variados
echo ""
echo "Verificando sinônimos entre docs..."
sinonimos=0
for termo in "estorno" "reembolso" "reversal" "devolução do valor"; do
  if grep -rqi "$termo" data/bronze/; then
    echo "  ✅ '$termo' encontrado"
    ((sinonimos++))
  fi
done
if [ "$sinonimos" -ge 3 ]; then
  echo "✅ Pelo menos 3 variações de vocabulário"
else
  echo "❌ Poucos sinônimos ($sinonimos encontrados)"
fi

# Gateway XPay em pelo menos 3 docs
echo ""
echo "Verificando integrações..."
xpay_count=$(grep -rli "Gateway XPay\|XPay" data/bronze/ | wc -l)
echo "  Gateway XPay mencionado em $xpay_count arquivos"
if [ "$xpay_count" -ge 3 ]; then
  echo "✅ Gateway XPay presente em 3+ docs"
else
  echo "⚠️ Gateway XPay em poucos docs"
fi

# Contrato ENT-2026-0042
if grep -qi "ENT-2026-0042" data/bronze/docs/requisitos-cliente-enterprise.md; then
  echo "✅ Contrato ENT-2026-0042 presente"
else
  echo "❌ Contrato ENT-2026-0042 não encontrado"
fi

echo ""
echo "Verificação concluída."
```

## Definição de pronto (DoD)

- [ ] 5 arquivos .md criados nos caminhos corretos
- [ ] Cada arquivo tem entre 400-800 palavras
- [ ] Contradição C-01 presente: parcial sem decisão (grooming) vs decidido v2 (PRD)
- [ ] Contradição C-02 presente: prazo 30 dias (PRD) vs 45 dias em promoção (chat)
- [ ] Contradição C-03 presente: parcial fora de escopo (PRD/grooming) vs obrigatória (enterprise)
- [ ] Ambiguidade A-01 presente: parcial sem conclusão no grooming
- [ ] Ambiguidade A-02 presente: gateway fora do ar, decisão adiada no refinamento
- [ ] Vocabulário V-01 presente: reversal/return request no chat, estorno/devolução nos demais
- [ ] Pelo menos 5 regras de negócio distribuídas nos documentos
- [ ] Pelo menos 1 fluxo de usuário completo (mínimo 5 passos)
- [ ] Pelo menos 3 decisões técnicas concretas
- [ ] Pelo menos 2 requisitos não funcionais com métricas (200ms p95, 99.9%, etc.)
- [ ] Pelo menos 2 integrações mencionadas (Gateway XPay, LogiTrack, etc.)
- [ ] Pelo menos 1 critério de aceite explícito (Marina QA no refinamento)
- [ ] Pelo menos 1 informação classificável como `vocabulario`
- [ ] Pelo menos 1 informação classificável como `contexto_negocio`
- [ ] Gateway de pagamento é "Gateway XPay" em todos os docs
- [ ] Contrato enterprise é "ENT-2026-0042"
- [ ] Formatos distintos: transcrição informal, PRD formal, chat, documento de cliente, ata técnica
- [ ] Todos os arquivos são UTF-8 válidos e parseáveis como markdown
- [ ] Scripts de validação passam sem erros
