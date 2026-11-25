-- Analise de retencao e recompra por cliente unico (customer_unique_id)
-- Usa CTEs e Window Functions (ROW_NUMBER, LAG, FIRST_VALUE)

-- @query: resumo_recompra_clientes
WITH pedidos_entregues AS (
    SELECT
        order_id,
        customer_unique_id,
        order_purchase_timestamp,
        receita_itens
    FROM vw_pedidos_consolidados
    WHERE order_status = 'delivered'
),
sequencia_pedidos AS (
    SELECT
        customer_unique_id,
        order_id,
        order_purchase_timestamp,
        receita_itens,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id
            ORDER BY order_purchase_timestamp, order_id
        ) AS ordem_compra,
        LAG(order_purchase_timestamp) OVER (
            PARTITION BY customer_unique_id
            ORDER BY order_purchase_timestamp, order_id
        ) AS compra_anterior,
        COUNT(*) OVER (
            PARTITION BY customer_unique_id
        ) AS total_pedidos_cliente
    FROM pedidos_entregues
),
metricas_cliente AS (
    SELECT
        customer_unique_id,
        MAX(total_pedidos_cliente) AS total_pedidos,
        ROUND(SUM(receita_itens), 2) AS gmv_cliente,
        MAX(
            CASE
                WHEN ordem_compra = 2
                THEN ROUND(julianday(order_purchase_timestamp) - julianday(compra_anterior), 2)
            END
        ) AS dias_ate_segunda_compra
    FROM sequencia_pedidos
    GROUP BY customer_unique_id
)
SELECT
    COUNT(*) AS clientes_unicos,
    SUM(CASE WHEN total_pedidos = 1 THEN 1 ELSE 0 END) AS clientes_compra_unica,
    SUM(CASE WHEN total_pedidos >= 2 THEN 1 ELSE 0 END) AS clientes_recompra,
    ROUND(
        SUM(CASE WHEN total_pedidos >= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) AS pct_recompra,
    SUM(
        CASE WHEN total_pedidos >= 2 AND dias_ate_segunda_compra >= 1.0 THEN 1 ELSE 0 END
    ) AS clientes_recompra_dias_distintos,
    ROUND(
        SUM(CASE WHEN total_pedidos >= 2 AND dias_ate_segunda_compra >= 1.0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
        2
    ) AS pct_recompra_dias_distintos,
    ROUND(
        AVG(CASE WHEN dias_ate_segunda_compra >= 1.0 THEN dias_ate_segunda_compra END),
        1
    ) AS media_dias_ate_2a_compra,
    ROUND(SUM(gmv_cliente), 2) AS gmv_total_entregue
FROM metricas_cliente;

-- @query: coorte_mensal_retencao
WITH pedidos_janela AS (
    SELECT
        customer_unique_id,
        order_purchase_timestamp,
        safra_compra
    FROM vw_pedidos_consolidados
    WHERE order_status = 'delivered'
      AND safra_compra BETWEEN '2017-01' AND '2018-08'
),
primeira_compra AS (
    SELECT
        customer_unique_id,
        MIN(safra_compra) AS safra_inicial
    FROM pedidos_janela
    GROUP BY customer_unique_id
),
atividade_coorte AS (
    SELECT
        p.safra_inicial,
        j.customer_unique_id,
        (
            (CAST(substr(j.safra_compra, 1, 4) AS INTEGER) - CAST(substr(p.safra_inicial, 1, 4) AS INTEGER)) * 12
            + (CAST(substr(j.safra_compra, 6, 2) AS INTEGER) - CAST(substr(p.safra_inicial, 6, 2) AS INTEGER))
        ) AS mes_indice
    FROM pedidos_janela j
    INNER JOIN primeira_compra p
        ON j.customer_unique_id = p.customer_unique_id
),
agregado_coorte AS (
    SELECT
        safra_inicial,
        mes_indice,
        COUNT(DISTINCT customer_unique_id) AS clientes_ativos
    FROM atividade_coorte
    WHERE mes_indice BETWEEN 0 AND 12
    GROUP BY safra_inicial, mes_indice
)
SELECT
    safra_inicial,
    mes_indice,
    clientes_ativos,
    FIRST_VALUE(clientes_ativos) OVER (
        PARTITION BY safra_inicial
        ORDER BY mes_indice
    ) AS tamanho_coorte,
    ROUND(
        clientes_ativos * 100.0 / FIRST_VALUE(clientes_ativos) OVER (
            PARTITION BY safra_inicial
            ORDER BY mes_indice
        ),
        2
    ) AS pct_retencao
FROM agregado_coorte
ORDER BY safra_inicial, mes_indice;
