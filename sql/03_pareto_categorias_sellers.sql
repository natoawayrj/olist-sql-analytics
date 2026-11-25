-- Analise de Pareto (80/20) por categoria de produto e por seller + tendencia mensal MoM
-- Usa CTEs e Window Functions (DENSE_RANK, ROW_NUMBER, SUM OVER, LAG)

-- @query: pareto_categorias
WITH receita_categoria AS (
    SELECT
        categoria_raw,
        COUNT(DISTINCT order_id) AS qtd_pedidos,
        COUNT(*) AS qtd_itens,
        ROUND(SUM(receita_item), 2) AS receita_total,
        ROUND(AVG(receita_item), 2) AS preco_medio_item,
        ROUND(AVG(frete_item), 2) AS frete_medio_item
    FROM vw_itens_entregues
    GROUP BY categoria_raw
),
curva_pareto AS (
    SELECT
        categoria_raw,
        qtd_pedidos,
        qtd_itens,
        receita_total,
        preco_medio_item,
        frete_medio_item,
        DENSE_RANK() OVER (ORDER BY receita_total DESC) AS ranking_receita,
        ROUND(
            receita_total * 100.0 / SUM(receita_total) OVER (),
            2
        ) AS pct_receita,
        ROUND(
            SUM(receita_total) OVER (
                ORDER BY receita_total DESC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) * 100.0 / SUM(receita_total) OVER (),
            2
        ) AS pct_receita_acumulada
    FROM receita_categoria
)
SELECT
    ranking_receita,
    categoria_raw,
    qtd_pedidos,
    qtd_itens,
    receita_total,
    preco_medio_item,
    frete_medio_item,
    pct_receita,
    pct_receita_acumulada
FROM curva_pareto
ORDER BY ranking_receita;

-- @query: pareto_sellers_resumo
WITH receita_sellers AS (
    SELECT
        seller_id,
        seller_state,
        COUNT(DISTINCT order_id) AS qtd_pedidos,
        ROUND(SUM(receita_item), 2) AS receita_total
    FROM vw_itens_entregues
    GROUP BY seller_id, seller_state
),
curva_sellers AS (
    SELECT
        seller_id,
        seller_state,
        qtd_pedidos,
        receita_total,
        ROW_NUMBER() OVER (ORDER BY receita_total DESC, seller_id) AS rank_seller,
        COUNT(*) OVER () AS total_sellers,
        SUM(receita_total) OVER () AS receita_global,
        SUM(receita_total) OVER (
            ORDER BY receita_total DESC, seller_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) * 100.0 / SUM(receita_total) OVER () AS pct_acumulada
    FROM receita_sellers
)
SELECT
    MAX(total_sellers) AS total_sellers_ativos,
    COUNT(CASE WHEN pct_acumulada <= 80.0 THEN 1 END) AS sellers_ate_80pct_receita,
    ROUND(
        COUNT(CASE WHEN pct_acumulada <= 80.0 THEN 1 END) * 100.0 / MAX(total_sellers),
        1
    ) AS pct_sellers_concentram_80pct,
    ROUND(MAX(receita_global), 2) AS receita_total_itens,
    ROUND(
        SUM(CASE WHEN rank_seller <= CAST(total_sellers * 0.20 AS INTEGER) THEN receita_total ELSE 0.0 END)
        * 100.0 / MAX(receita_global),
        1
    ) AS pct_receita_nos_top_20pct_sellers
FROM curva_sellers;

-- @query: tendencia_mensal_top_categorias
WITH top_categorias AS (
    SELECT
        categoria_raw,
        SUM(receita_item) AS receita_global,
        DENSE_RANK() OVER (ORDER BY SUM(receita_item) DESC) AS rk
    FROM vw_itens_entregues
    GROUP BY categoria_raw
),
mensal AS (
    SELECT
        i.categoria_raw,
        i.safra_compra,
        COUNT(DISTINCT i.order_id) AS qtd_pedidos,
        ROUND(SUM(i.receita_item), 2) AS receita_mensal
    FROM vw_itens_entregues i
    INNER JOIN top_categorias t
        ON i.categoria_raw = t.categoria_raw
    WHERE t.rk <= 10
      AND i.safra_compra BETWEEN '2017-01' AND '2018-08'
    GROUP BY i.categoria_raw, i.safra_compra
)
SELECT
    categoria_raw,
    safra_compra,
    qtd_pedidos,
    receita_mensal,
    LAG(receita_mensal) OVER (
        PARTITION BY categoria_raw
        ORDER BY safra_compra
    ) AS receita_mes_anterior,
    ROUND(
        (receita_mensal - LAG(receita_mensal) OVER (PARTITION BY categoria_raw ORDER BY safra_compra))
        * 100.0 / NULLIF(LAG(receita_mensal) OVER (PARTITION BY categoria_raw ORDER BY safra_compra), 0),
        1
    ) AS variacao_mom_pct
FROM mensal
ORDER BY categoria_raw, safra_compra;
