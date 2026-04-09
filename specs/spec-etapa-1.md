# SPEC — Etapa 1: Dados Simulados (Camada Bronze)

## Objetivo

Criar 5 documentos simulados mas realistas que representam as fontes de dados típicas de um time de produto/engenharia discutindo uma feature. Esses dados serão processados pelo pipeline de ingestão (Etapa 4) e formarão a base de conhecimento do MVP.

## Feature escolhida: Devolução de Produtos

E-commerce B2B/B2C. A feature de devolução foi escolhida porque tem:
- Regras de negócio com exceções condicionais (PF vs PJ, prazos diferentes)
- Integrações com múltiplos sistemas (gateway pagamento, logística, SAC)
- Decisões técnicas relevantes (state machine, mensageria, idempotência)
- Ambiguidades não resolvidas (devolução parcial)
- Requisitos não funcionais mensuráveis (SLA, rate limit)
- Fluxos de exceção ricos (produto usado, prazo expirado, defeito)

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

## Regras para os dados simulados

1. **Realismo:** os documentos devem parecer reais. Transcrições com falas naturais (interrupções, correções, "tipo", "aí", "né"). Documentos formais com linguagem de PRD. Chat com informalidade de Slack.
2. **Redundância intencional:** a mesma regra de negócio (ex: prazo de 30 dias para PF) deve aparecer em pelo menos 2 documentos diferentes, com redações ligeiramente diferentes. Isso testa a capacidade do pipeline de identificar a mesma informação em fontes distintas.
3. **Contradição intencional:** pelo menos 1 contradição entre documentos. Ex: o grooming diz "prazo de 30 dias corridos", o PRD diz "30 dias úteis". Isso testa a capacidade do agente de detectar contradições.
4. **Ambiguidade intencional:** pelo menos 1 ponto ambíguo não resolvido. Ex: devolução parcial (devolver 1 item de um pedido com 3) — mencionada mas sem decisão final.
5. **Tamanho:** cada documento deve ter entre 300-800 palavras. Grande o suficiente para gerar 3-6 chunks cada, pequeno o suficiente para o LLM processar em uma chamada.
6. **Vocabulário variado:** usar sinônimos propositalmente. Um doc diz "estorno", outro diz "reembolso", outro diz "devolução do valor". Isso testa o glossário de sinônimos do agente.

---

## Documento 1: Transcrição de Grooming

**Arquivo:** `data/bronze/calls/grooming-devolucao-2026-04-01.md`
**source_type:** `transcricao_reuniao`
**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev)

### Conteúdo esperado

O documento deve ser uma transcrição de reunião de grooming com o seguinte formato:

```
# Grooming — Devolução de Produtos
**Data:** 2026-04-01
**Participantes:** Ana (PO), Carlos (Arquiteto), Pedro (Dev)

---

**Ana:** [fala da Ana]

**Carlos:** [fala do Carlos]

**Pedro:** [fala do Pedro]
```

### Informações que DEVEM estar presentes neste documento

Cada item abaixo é uma unidade de informação que o pipeline de ingestão deve extrair como chunk:

**Regra de negócio — Prazo PF (chunk_type: regra_negocio)**
Ana explica que o prazo de devolução para pessoa física é de 30 dias corridos a partir da data de entrega. Menciona que pelo CDC são 7 dias de arrependimento, mas comercialmente oferecem 30. Pedro pergunta se é corrido ou útil, Ana confirma que é corrido.

**Regra de negócio — Prazo PJ (chunk_type: regra_negocio)**
Ana explica que para PJ com contrato enterprise o prazo depende do contrato, podendo ser 60 ou 90 dias. Carlos pergunta como o sistema sabe qual prazo aplicar, Ana diz que vem do cadastro do cliente no CRM.

**Regra de negócio — Produto usado (chunk_type: regra_negocio)**
Pedro pergunta sobre produto usado. Ana responde que produto com sinais de uso não aceita devolução, EXCETO em caso de defeito de fabricação. Carlos sugere que a verificação seja feita pelo time de logística no recebimento.

**Decisão técnica — API de estorno (chunk_type: decisao_tecnica)**
Carlos propõe integração com a API de estorno do gateway de pagamento (PaymentGateway v3). Menciona que o endpoint é assíncrono — o estorno é solicitado e confirmado via webhook. Pedro pergunta sobre idempotência, Carlos diz que vão tratar.

**Fluxo do usuário — Fluxo principal (chunk_type: fluxo_usuario)**
Ana descreve o fluxo: cliente acessa "Meus Pedidos", seleciona o pedido, clica em "Solicitar Devolução", seleciona o motivo, confirma. Sistema gera etiqueta de envio reverso. Após recebimento no CD, estorno é processado.

**Ambiguidade — Devolução parcial (chunk_type: regra_negocio)**
Pedro levanta: "E se o cara comprou 3 itens e quer devolver só 1?". Ana diz que precisa pensar melhor, porque o frete reverso é por pedido e não por item. Carlos sugere cobrar frete proporcional. Não chegam a uma decisão. Ana diz que vai alinhar com o financeiro.

**Requisito informal — Performance (chunk_type: requisito_nao_funcional)**
Ana menciona: "Isso precisa ser rápido, o cliente não pode ficar esperando. Aquela tela de devolução tem que carregar rapidinho." Sem métrica específica.

### Tom e estilo

A transcrição deve parecer real. Usar linguagem informal brasileira:
- "Beleza, então fica assim..."
- "Peraí, mas e se..."
- "Tipo, o cliente vai lá e..."
- "Aí a gente faz o estorno, né"
- Uma pessoa interrompendo outra ocasionalmente
- Carlos usando termos mais técnicos que Ana
- Pedro fazendo perguntas práticas de implementação

---

## Documento 2: PRD Formal

**Arquivo:** `data/bronze/docs/prd-devolucao-v2.md`
**source_type:** `documento_produto`

### Conteúdo esperado

Documento formal com headers markdown, linguagem de PRD:

```
# PRD — Devolução de Produtos v2
**Autor:** Ana Silva (Product Owner)
**Última atualização:** 2026-03-28
**Status:** Em refinamento

## 1. Visão geral
[...]

## 2. Personas
[...]

## 3. Regras de negócio
[...]
```

### Informações que DEVEM estar presentes

**Contexto de negócio (chunk_type: contexto_negocio)**
Taxa atual de devolução é 4.2%. Benchmark do mercado é 3.5%. Feature visa melhorar a experiência de devolução para reduzir NPS negativo associado a devoluções (atualmente score 2.1/5 no fluxo de devolução).

**Personas (chunk_type: contexto_negocio)**
Três personas: Cliente PF (comprador individual), Cliente PJ (comprador corporativo com contrato), Operador de Suporte (atende chamados de devolução).

**Regra de negócio — Prazo PF (chunk_type: regra_negocio)**
CONTRADIÇÃO INTENCIONAL: aqui o PRD diz "30 dias úteis" (no grooming, Ana disse "30 dias corridos"). Essa contradição é deliberada para testar a detecção pelo agente.

**Regra de negócio — Prazo PJ (chunk_type: regra_negocio)**
Consistente com o grooming: prazo conforme contrato, default 30 dias se não especificado.

**Regra de negócio — Motivos de devolução (chunk_type: regra_negocio)**
Lista de motivos aceitos: arrependimento, produto diferente do anunciado, defeito de fabricação, produto danificado no transporte. Cada motivo tem tratamento diferente (arrependimento: frete por conta do cliente; defeito: frete por conta da empresa).

**Regra de negócio — Valor do estorno (chunk_type: regra_negocio)**
Estorno do valor integral do produto. Frete de envio original NÃO é estornado exceto em caso de defeito ou erro da empresa. Frete reverso: gratuito para defeito, cobrado para arrependimento (descontado do estorno).

**Requisitos não funcionais (chunk_type: requisito_nao_funcional)**
SLA: página de devolução deve carregar em até 200ms (p95). Disponibilidade: 99.9%. Estorno deve ser processado em até 5 dias úteis após recebimento do produto no CD.

**Integrações (chunk_type: integracao)**
Gateway de pagamento (PaymentGateway v3) para estornos. Sistema de logística reversa (LogiReverse API) para geração de etiqueta e rastreamento. CRM para consulta de dados do contrato PJ. SAC para abertura automática de ticket quando devolução é por defeito.

**Escopo (chunk_type: definicao_escopo)**
DENTRO: devolução de produtos físicos comprados no e-commerce. FORA: troca de produto (feature separada), devolução de serviços digitais, devolução de marketplace (responsabilidade do seller).

---

## Documento 3: Chat de Alinhamento

**Arquivo:** `data/bronze/chats/slack-devolucao-2026-04-03.md`
**source_type:** `chat`

### Conteúdo esperado

```
# Canal: #squad-checkout — Devolução de Produtos
**Data:** 2026-04-03

---

**[09:14] Pedro:** Galera, sobre a devolução...
**[09:15] Ana:** Fala
**[09:16] Pedro:** [mensagem]
```

### Informações que DEVEM estar presentes

**Edge case — Produto usado (chunk_type: regra_negocio)**
Pedro pergunta: "E se o cara abriu a caixa mas não usou? Tipo, eletrônico que tirou o lacre". Ana responde: "Aberto sem uso aceita devolução sim, desde que com todos os acessórios. Usado não, exceto defeito." Informação complementa o grooming.

**Decisão técnica — Rate limit (chunk_type: decisao_tecnica)**
Carlos compartilha: "Pessoal, confirmei com o time do gateway — o endpoint de estorno tem rate limit de 100 requests por minuto. Precisamos implementar uma fila." Pedro responde: "Beleza, vou usar SQS pra isso."

**Ideia informal — Tela de acompanhamento (chunk_type: fluxo_usuario)**
Ana menciona: "Ah, acho importante ter uma tela onde o cliente acompanha o status da devolução. Tipo, 'solicitada', 'produto enviado', 'produto recebido', 'estorno processado'." Carlos: "Sim, é o tracking. Faz sentido."

**Vocabulário (chunk_type: vocabulario)**
Pedro usa o termo "reversal" e Carlos corrige: "Aqui a gente chama de 'estorno', o 'reversal' é o termo da API do gateway. No nosso domínio é estorno mesmo."

### Tom e estilo

Mensagens curtas, informais, com emoji ocasional, abreviações ("vc", "blz", "tbm"), respostas rápidas em sequência. Alguém mandando "👍" como confirmação.

---

## Documento 4: Requisitos do Cliente Enterprise

**Arquivo:** `data/bronze/docs/requisitos-cliente-enterprise.md`
**source_type:** `documento_cliente`

### Conteúdo esperado

```
# Requisitos de Devolução — Cliente Enterprise (TechCorp)
**Contrato:** ENT-2026-0042
**Contato:** Mariana Souza (Gestora de Compras)
**Data:** 2026-03-15

## Requisitos específicos
[...]
```

### Informações que DEVEM estar presentes

**Regra de negócio — Prazo especial PJ (chunk_type: regra_negocio)**
TechCorp tem prazo de 90 dias para devolução conforme contrato enterprise. Diferente do padrão PJ.

**Regra de negócio — Aprovação por gestor (chunk_type: regra_negocio)**
Toda devolução de item acima de R$ 5.000 precisa de aprovação do gestor de compras antes de ser processada. Para itens até R$ 5.000, qualquer funcionário autorizado pode solicitar.

**Integração — Webhook ERP (chunk_type: integracao)**
TechCorp exige integração via webhook com seu ERP (SAP) para notificação de devoluções. Endpoint fornecido: POST https://erp.techcorp.com/api/v1/returns/notify. Payload esperado com campos: order_id, return_id, items, status, timestamp.

**Requisito — Relatório mensal (chunk_type: requisito_nao_funcional)**
Relatório mensal de devoluções em formato CSV enviado por email até o 5º dia útil do mês seguinte. Campos: data solicitação, produto, motivo, valor estornado, status, tempo de processamento.

### Tom e estilo

Linguagem formal de documento contratual/requisito de cliente. Objetivo, sem informalidade. Pode ter formato de lista de requisitos numerados (REQ-001, REQ-002, etc.).

---

## Documento 5: Ata de Refinamento Técnico

**Arquivo:** `data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md`
**source_type:** `transcricao_reuniao`
**Participantes:** Carlos (Arquiteto), Pedro (Dev), Lucas (Dev Backend), Marina (QA)

### Conteúdo esperado

```
# Refinamento Técnico — Devolução de Produtos
**Data:** 2026-04-05
**Participantes:** Carlos (Arquiteto), Pedro (Dev), Lucas (Dev Backend), Marina (QA)

## Decisões

### 1. API Design
[...]

### 2. State Machine
[...]
```

### Informações que DEVEM estar presentes

**Decisão técnica — API (chunk_type: decisao_tecnica)**
Endpoint: POST /api/v1/returns. Request body com campos: order_id, items (array de product_id + quantity + reason), customer_notes. Response: return_id, status, estimated_refund_date.

**Decisão técnica — State machine (chunk_type: decisao_tecnica)**
Estados da devolução: requested → approved → label_generated → shipped → received → inspected → refunded (ou rejected). Transições: requested→approved é automática para PF com prazo válido. Para PJ acima de R$5.000, requested→pending_approval→approved.

**Decisão técnica — Mensageria (chunk_type: decisao_tecnica)**
Usar SQS para comunicação assíncrona com: sistema de logística (geração de etiqueta), gateway de pagamento (solicitação de estorno), CRM (atualização de status), ERP do cliente enterprise (webhook).

**Decisão técnica — Idempotência (chunk_type: decisao_tecnica)**
Endpoint de estorno deve ser idempotente. Usar idempotency_key baseado em return_id + attempt_number. Se o gateway já processou o estorno para aquele return_id, retorna sucesso sem reprocessar.

**Restrição técnica — Rate limit (chunk_type: restricao)**
Gateway permite 100 requests/minuto para estorno. Queue consumer deve respeitar esse limite. Implementar exponential backoff em caso de 429.

**Ambiguidade — Devolução parcial (chunk_type: decisao_tecnica)**
Carlos retoma a discussão. Proposta: permitir devolução parcial, cada item gera um "return_item" dentro do return. Estorno é proporcional ao valor do item. Frete reverso: se devolução parcial por arrependimento, frete é cobrado integralmente (não proporcional). DECISÃO: implementar devolução parcial no MVP. Pedro discorda, acha que complica demais. Carlos prevalece. Marina levanta preocupação sobre testes.

**Critério de aceite — QA (chunk_type: criterio_aceite)**
Marina define: "Preciso que o estorno nunca seja processado em duplicidade. Se o sistema falhar no meio, o retry não pode estornar duas vezes." Carlos confirma que a idempotência resolve isso.

### Tom e estilo

Mais técnico que o grooming. Termos como "state machine", "idempotency key", "exponential backoff", "SQS consumer". Mas ainda conversacional — é uma reunião, não um documento. Carlos liderando as decisões técnicas, Pedro questionando, Marina focando em testabilidade.

---

## Mapa de contradições e ambiguidades (referência para testes)

Este mapa NÃO é um documento bronze. É uma referência para validar se o pipeline e o agente detectam corretamente:

| ID | Tipo | Descrição | Docs envolvidos |
|----|------|-----------|-----------------|
| C-01 | Contradição | Prazo PF: "30 dias corridos" (grooming) vs "30 dias úteis" (PRD) | grooming + PRD |
| A-01 | Ambiguidade | Devolução parcial: mencionada no grooming sem decisão, decidida no refinamento técnico mas com discordância | grooming + refinamento |
| A-02 | Ambiguidade | Performance: "tem que ser rápido" (grooming, sem métrica) vs "200ms p95" (PRD, com métrica) — não é contradição, mas o grooming está vago | grooming + PRD |
| R-01 | Redundância | Regra de prazo PJ: consistente entre grooming e PRD | grooming + PRD |
| R-02 | Redundância | Produto usado: mencionado no grooming e expandido no chat | grooming + chat |
| R-03 | Redundância | Rate limit do gateway: mencionado no chat e no refinamento técnico | chat + refinamento |

## Critérios de aceite desta etapa

- [ ] 5 arquivos .md criados nos diretórios corretos
- [ ] Cada arquivo tem entre 300-800 palavras
- [ ] Pelo menos 1 contradição intencional entre documentos (prazo corrido vs útil)
- [ ] Pelo menos 1 ambiguidade não resolvida (devolução parcial no grooming)
- [ ] Pelo menos 3 sinônimos diferentes usados entre documentos (estorno/reembolso/reversão)
- [ ] Informações redundantes entre pelo menos 2 pares de documentos
- [ ] Formatos distintos: transcrição informal, PRD formal, chat, documento de cliente, ata técnica
- [ ] Todos os arquivos são UTF-8 válidos e parseáveis como markdown

## Comando de validação

```bash
#!/bin/bash
echo "=== Validação Etapa 1 ==="

# Verificar existência dos arquivos
files=(
  "data/bronze/calls/grooming-devolucao-2026-04-01.md"
  "data/bronze/calls/refinamento-tecnico-devolucao-2026-04-05.md"
  "data/bronze/docs/prd-devolucao-v2.md"
  "data/bronze/docs/requisitos-cliente-enterprise.md"
  "data/bronze/chats/slack-devolucao-2026-04-03.md"
)

all_ok=true
for f in "${files[@]}"; do
  if [ -f "$f" ]; then
    words=$(wc -w < "$f")
    echo "✅ $f ($words palavras)"
    if [ "$words" -lt 300 ]; then
      echo "   ⚠️ AVISO: menos de 300 palavras"
    fi
    if [ "$words" -gt 800 ]; then
      echo "   ⚠️ AVISO: mais de 800 palavras"
    fi
  else
    echo "❌ $f — NÃO ENCONTRADO"
    all_ok=false
  fi
done

# Verificar encoding UTF-8
echo ""
echo "Verificando encoding..."
for f in "${files[@]}"; do
  if [ -f "$f" ]; then
    if file "$f" | grep -q "UTF-8\|ASCII"; then
      echo "✅ $f — encoding OK"
    else
      echo "❌ $f — encoding inválido"
      all_ok=false
    fi
  fi
done

# Verificar contradição (prazo corrido vs útil)
echo ""
echo "Verificando contradição intencional..."
if grep -ql "corridos" data/bronze/calls/grooming-devolucao-2026-04-01.md && \
   grep -ql "úteis" data/bronze/docs/prd-devolucao-v2.md; then
  echo "✅ Contradição 'corridos vs úteis' presente"
else
  echo "❌ Contradição intencional não encontrada"
  all_ok=false
fi

# Verificar sinônimos
echo ""
echo "Verificando uso de sinônimos..."
sinonimos_encontrados=0
for termo in "estorno" "reembolso" "reversal"; do
  if grep -rql "$termo" data/bronze/; then
    echo "  ✅ Termo '$termo' encontrado"
    ((sinonimos_encontrados++))
  fi
done
if [ "$sinonimos_encontrados" -ge 2 ]; then
  echo "✅ Pelo menos 2 sinônimos distintos encontrados"
else
  echo "❌ Poucos sinônimos — adicionar variações"
  all_ok=false
fi

echo ""
if $all_ok; then
  echo "🎉 Etapa 1 APROVADA"
else
  echo "🚨 Etapa 1 tem problemas — corrigir antes de prosseguir"
fi
```
