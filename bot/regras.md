# Regras do bot de hardgoods (decididas pelo Pedro)

Cada regra nasce de uma resposta do Pedro. O bot lê este arquivo toda vez; quando uma regra cobre o caso, ele aplica
e diz qual regra usou — senão, PERGUNTA. Formato: `R<n> · <quando> → <o que fazer>  (origem, data)`.

## Respostas do fornecedor
- R1 · Item "out of stock", "discontinued" ou "cannot currently be ordered" na resposta → tirar a linha do PB (e do PO, se já existir)  (Syndicate, 08/10)
- R2 · Código da resposta difere só no final de um código do PB da mesma loja (ex.: 7121-06-2218 × 7121-06-2216) → PERGUNTAR se é o mesmo item  (Syndicate, 08/10)
- R3 · O pedido de cliente (ex.: Love's Flower Shop) vai junto com a loja dele (WPB), em arquivo separado  (Syndicate, 08/10)

## Invoices
- R4 · Custo do PO e da caixa = preço da fatura + frete rateado pelo valor da linha  (Syndicate, 09/10)
- R5 · Soma das linhas lidas ≠ subtotal da fatura → PARAR e avisar (nada é gravado)  (Syndicate, 09/10)
- R6 · Item que não veio (enviado 0 / back order) → deixar como veio: reduzir PO e caixa ao que chegou; back order não fica anotado  (Giftwares, 09/10)
- R7 · Venda: abaixo de 38% → custo ÷ 0,62 (unidade termina em ,99; cliente de caixa arredonda o centavo para cima). 37,9% é tolerância  (09/10)
- R8 · Venda com preço da caixa no lugar da unidade (margem > 75%) → corrigir para a regra R7  (Syndicate, 09/10)
- R9 · Cliente (não-loja) → venda = custo ÷ 0,62 por caixa  (Love's, 09/10)
- R10 · Item na fatura sem PO e com preço 0 (amostra) → não entra no sistema, só avisar  (Giftwares FORM502, 09/10)
- R11 · Caixa no Inventory Entry: editar sempre pela tela de packing do Flexymax (mantém o customer); nunca pelo Edit Box do fullpotos  (09/10)

## Sempre perguntar (até virar regra)
- Substituição de item, item novo, preço com diferença acima de 5%, unidades por caixa diferentes do PO, item na fatura sem PO com preço > 0.
