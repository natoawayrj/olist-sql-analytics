-- Impacto do prazo de entrega (SLA) na avaliacao do cliente e ranking por UF
-- Usa CTEs e Window Functions (SUM OVER, RANK OVER, AVG OVER, LAG)

-- @query: sla_faixas_avaliacao
WITH pedidos_avaliados AS (
    SELECT
        faixa_sla,
        ordem_faixa_sla,
        nota_media_pedido,
        eh_detrator,
        tempo_entrega_dias,
        receita_itens
    FROM vw_pedidos_consolidados
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
      AND nota_media_pedido IS NOT NULL
)
SELECT
    ordem_faixa_sla,
    faixa_sla,
    COUNT(*) AS qtd_pedidos,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_volume,
    ROUND(AVG(nota_media_pedido), 2) AS nota_media,
    ROUND(AVG(CASE WHEN eh_detrator = 1 THEN 100.0 ELSE 0.0 END), 1) AS pct_detratores_nota_1_2,
    ROUND(AVG(CASE WHEN nota_media_pedido >= 4.5 THEN 100.0 ELSE 0.0 END), 1) AS pct_promotores_nota_5,
    ROUND(AVG(tempo_entrega_dias), 1) AS tempo_medio_entrega_dias,
    ROUND(SUM(receita_itens), 2) AS gmv_faixa
FROM pedidos_avaliados
GROUP BY ordem_faixa_sla, faixa_sla
ORDER BY ordem_faixa_sla;

-- @query: sla_por_uf
WITH metricas_uf AS (
    SELECT
        customer_state AS uf,
        COUNT(*) AS qtd_pedidos,
        ROUND(
            AVG(CASE WHEN atraso_dias > 0 THEN 100.0 ELSE 0.0 END),
            1
        ) AS pct_atraso,
        ROUND(AVG(nota_media_pedido), 2) AS nota_media,
        ROUND(AVG(CASE WHEN eh_detrator = 1 THEN 100.0 ELSE 0.0 END), 1) AS pct_detratores,
        ROUND(AVG(tempo_entrega_dias), 1) AS tempo_medio_entrega_dias,
        ROUND(AVG(valor_frete), 2) AS frete_medio,
        ROUND(SUM(receita_itens), 2) AS receita_itens
    FROM vw_pedidos_consolidados
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
      AND nota_media_pedido IS NOT NULL
    GROUP BY customer_state
)
SELECT
    uf,
    qtd_pedidos,
    pct_atraso,
    nota_media,
    pct_detratores,
    tempo_medio_entrega_dias,
    frete_medio,
    receita_itens,
    RANK() OVER (ORDER BY pct_atraso DESC) AS rank_atraso,
    ROUND(
        SUM(qtd_pedidos * nota_media) OVER () * 1.0 / SUM(qtd_pedidos) OVER (),
        2
    ) AS media_nacional_nota,
    ROUND(
        SUM(qtd_pedidos * pct_atraso) OVER () * 1.0 / SUM(qtd_pedidos) OVER (),
        1
    ) AS media_nacional_atraso
FROM metricas_uf
ORDER BY pct_atraso DESC, qtd_pedidos DESC;

-- @query: serie_mensal_sla
WITH mensal AS (
    SELECT
        safra_compra,
        COUNT(*) AS qtd_pedidos,
        ROUND(SUM(receita_itens), 2) AS receita_itens,
        ROUND(AVG(CASE WHEN atraso_dias > 0 THEN 100.0 ELSE 0.0 END), 1) AS pct_atraso,
        ROUND(AVG(nota_media_pedido), 2) AS nota_media,
        ROUND(AVG(tempo_entrega_dias), 1) AS tempo_medio_entrega_dias
    FROM vw_pedidos_consolidados
    WHERE order_status = 'delivered'
      AND order_delivered_customer_date IS NOT NULL
      AND nota_media_pedido IS NOT NULL
      AND safra_compra BETWEEN '2017-01' AND '2018-08'
    GROUP BY safra_compra
)
SELECT
    safra_compra,
    qtd_pedidos,
    receita_itens,
    pct_atraso,
    nota_media,
    tempo_medio_entrega_dias,
    LAG(pct_atraso) OVER (ORDER BY safra_compra) AS pct_atraso_mes_anterior
FROM mensal
ORDER BY safra_compra;
