-- Camada analitica no SQLite: views consolidadas sem fan-out (duplicacao de pedidos)
-- Distingue customer_id (chave do pedido) de customer_unique_id (cliente unico real)

DROP VIEW IF EXISTS vw_pedidos_consolidados;
DROP VIEW IF EXISTS vw_itens_entregues;

CREATE VIEW vw_pedidos_consolidados AS
WITH itens_por_pedido AS (
    SELECT
        order_id,
        COUNT(*) AS qtd_itens,
        COUNT(DISTINCT seller_id) AS qtd_sellers,
        ROUND(SUM(price), 2) AS receita_itens,
        ROUND(SUM(freight_value), 2) AS valor_frete
    FROM order_items
    GROUP BY order_id
),
pagamentos_por_pedido AS (
    SELECT
        order_id,
        ROUND(SUM(payment_value), 2) AS valor_total_pago,
        MAX(payment_installments) AS max_parcelas,
        COUNT(*) AS qtd_meios_pagamento
    FROM order_payments
    GROUP BY order_id
),
avaliacoes_por_pedido AS (
    SELECT
        order_id,
        ROUND(AVG(review_score), 2) AS nota_media_pedido,
        COUNT(*) AS qtd_avaliacoes
    FROM order_reviews
    GROUP BY order_id
),
base_prazos AS (
    SELECT
        o.order_id,
        o.customer_id,
        c.customer_unique_id,
        c.customer_city,
        c.customer_state,
        o.order_status,
        o.order_purchase_timestamp,
        strftime('%Y-%m', o.order_purchase_timestamp) AS safra_compra,
        o.order_delivered_customer_date,
        o.order_estimated_delivery_date,
        CASE
            WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
            THEN CAST(
                julianday(date(o.order_delivered_customer_date))
                - julianday(date(o.order_estimated_delivery_date))
                AS INTEGER
            )
            ELSE NULL
        END AS atraso_dias,
        CASE
            WHEN o.order_delivered_customer_date IS NOT NULL
            THEN ROUND(
                julianday(o.order_delivered_customer_date)
                - julianday(o.order_purchase_timestamp),
                1
            )
            ELSE NULL
        END AS tempo_entrega_dias,
        COALESCE(i.qtd_itens, 0) AS qtd_itens,
        COALESCE(i.qtd_sellers, 0) AS qtd_sellers,
        COALESCE(i.receita_itens, 0.0) AS receita_itens,
        COALESCE(i.valor_frete, 0.0) AS valor_frete,
        COALESCE(p.valor_total_pago, 0.0) AS valor_total_pago,
        COALESCE(p.max_parcelas, 0) AS max_parcelas,
        a.nota_media_pedido,
        CASE
            WHEN a.nota_media_pedido IS NOT NULL AND a.nota_media_pedido <= 2.0 THEN 1
            WHEN a.nota_media_pedido IS NOT NULL THEN 0
            ELSE NULL
        END AS eh_detrator
    FROM orders o
    INNER JOIN customers c
        ON o.customer_id = c.customer_id
    LEFT JOIN itens_por_pedido i
        ON o.order_id = i.order_id
    LEFT JOIN pagamentos_por_pedido p
        ON o.order_id = p.order_id
    LEFT JOIN avaliacoes_por_pedido a
        ON o.order_id = a.order_id
)
SELECT
    *,
    CASE
        WHEN atraso_dias IS NULL THEN 'Sem entrega registrada'
        WHEN atraso_dias < 0 THEN 'Antecipado'
        WHEN atraso_dias = 0 THEN 'No prazo'
        WHEN atraso_dias BETWEEN 1 AND 3 THEN 'Atraso 1-3 dias'
        WHEN atraso_dias BETWEEN 4 AND 7 THEN 'Atraso 4-7 dias'
        ELSE 'Atraso > 7 dias'
    END AS faixa_sla,
    CASE
        WHEN atraso_dias IS NULL THEN 99
        WHEN atraso_dias < 0 THEN 1
        WHEN atraso_dias = 0 THEN 2
        WHEN atraso_dias BETWEEN 1 AND 3 THEN 3
        WHEN atraso_dias BETWEEN 4 AND 7 THEN 4
        ELSE 5
    END AS ordem_faixa_sla
FROM base_prazos;

CREATE VIEW vw_itens_entregues AS
SELECT
    oi.order_id,
    oi.order_item_id,
    o.order_purchase_timestamp,
    strftime('%Y-%m', o.order_purchase_timestamp) AS safra_compra,
    c.customer_unique_id,
    c.customer_state,
    oi.seller_id,
    s.seller_state,
    oi.product_id,
    COALESCE(NULLIF(TRIM(pr.product_category_name), ''), 'sem_categoria') AS categoria_raw,
    COALESCE(ct.product_category_name_english, 'uncategorized') AS categoria_en,
    oi.price AS receita_item,
    oi.freight_value AS frete_item
FROM order_items oi
INNER JOIN orders o
    ON oi.order_id = o.order_id
INNER JOIN customers c
    ON o.customer_id = c.customer_id
LEFT JOIN sellers s
    ON oi.seller_id = s.seller_id
LEFT JOIN products pr
    ON oi.product_id = pr.product_id
LEFT JOIN category_translation ct
    ON pr.product_category_name = ct.product_category_name
WHERE o.order_status = 'delivered';
