-- ============================================================
-- Olist 电商数据分析 —— 业务分析 SQL
-- 每个查询对应一个业务问题,结果与 analysis/run_analysis.py 一致
-- 运行: mysql -u root -p olist < sql/analysis_queries.sql
--
-- 全局口径:统一限定 order_status='delivered'(已送达)。
-- 多表查询最容易出的错就是漏掉这个过滤,导致各查询口径不一致、总数对不上。
-- ============================================================

-- 必须设置客户端字符集:否则查询 6 里的中文常量 '未分类' 会用客户端默认
-- 字符集(如 Windows 下的 gbk)解析,与列上的 utf8mb4 冲突,
-- 报 "Illegal mix of collations"。
SET NAMES utf8mb4;

-- ------------------------------------------------------------
-- 0. 总览 KPI(以及 GMV 口径的自洽性校验)
-- ------------------------------------------------------------
SELECT
    COUNT(DISTINCT o.order_id) AS orders,
    ROUND(SUM(oi.price), 2)    AS gmv,           -- 商品成交额,不含运费
    ROUND(SUM(oi.freight_value), 2) AS freight
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered';

-- ------------------------------------------------------------
-- 1. 销售总览:月度 GMV 和订单量
-- 业务问题:整体销售趋势如何?有没有增长点/季节性?
-- ------------------------------------------------------------
-- 说明:2016-09 与 2016-12 各只有 1 单,是上线初期的噪声,已用 month >= '2017-01' 剔除
SELECT
    DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS month,
    COUNT(DISTINCT o.order_id)                       AS orders,
    ROUND(SUM(oi.price), 2)                          AS gmv
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.order_status = 'delivered'
GROUP BY month
HAVING month >= '2017-01'
ORDER BY month;

-- ------------------------------------------------------------
-- 2. 复购率:有多少客户下过不止一单
-- 业务问题:客户粘性如何?
-- 【易错点】必须用 customers.customer_unique_id,不能用 orders.customer_id。
--   在 Olist 数据里 customer_id 是「每单唯一」的,按它分组复购率恒为 0.00%;
--   customer_unique_id 才标识同一个自然人。这个坑会让所有客户级分析失效。
-- 结果约 3.00%(注:观察窗口仅约 2 年,这是复购率的下限)
-- ------------------------------------------------------------
WITH customer_orders AS (
    SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_cnt
    FROM orders o
    JOIN customers c ON o.customer_id = c.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY c.customer_unique_id
)
SELECT
    SUM(order_cnt > 1)                            AS repeat_customers,
    COUNT(*)                                      AS total_customers,
    ROUND(SUM(order_cnt > 1) / COUNT(*) * 100, 2) AS repeat_rate_pct
FROM customer_orders;

-- ------------------------------------------------------------
-- 3. 物流时效:各州平均送达天数 + 延迟率
-- 业务问题:哪些地区物流拖后腿?建议优先在哪些地区补仓?
-- 【分析要点】平均天数和延迟率并不一致:
--   AP/AM/AC 平均送达最久但延迟率低(平台承诺期本就长);
--   AL/MA/PI/CE 才是真正频繁违约的州。运营考核应看延迟率。
-- 【样本量】RR/AP/AC/AM 等州样本量 <300,单州结论不可靠,需一并看 n。
-- ------------------------------------------------------------
SELECT
    c.customer_state AS state,
    COUNT(*)         AS n,
    ROUND(AVG(TIMESTAMPDIFF(DAY, o.order_purchase_timestamp,
                            o.order_delivered_customer_date)), 1) AS avg_delivery_days,
    ROUND(SUM(o.order_delivered_customer_date > o.order_estimated_delivery_date)
          / COUNT(*) * 100, 1)                                    AS late_pct
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY c.customer_state
ORDER BY late_pct DESC;

-- ------------------------------------------------------------
-- 4. 评价分布:分订单状态看评分
-- 业务问题:整体满意度如何?差评占多少?
-- 【口径说明】评价是行级数据(一条评价一行)。
--   主导口径应取「已送达」:差评率约 12.8%;
--   若混入未送达订单会得到约 14.6%,会高估商品/履约本身的问题。
--   未送达订单(processing/unavailable 等)差评率高达 70–90%,单独看才是有效信息。
-- 需要 MySQL 8.0(SUM(...) OVER () 窗口函数,5.7 不支持)
-- ------------------------------------------------------------
SELECT
    o.order_status,
    COUNT(*)                                          AS reviews,
    ROUND(AVG(r.review_score), 2)                     AS avg_score,
    ROUND(SUM(r.review_score <= 2) / COUNT(*) * 100, 1) AS negative_pct,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM orders o
JOIN order_reviews r ON o.order_id = r.order_id
GROUP BY o.order_status
ORDER BY reviews DESC;

-- ------------------------------------------------------------
-- 5. 分期与客单价的关系
-- 业务问题:分期是否拉高了客单价?
-- 【易错点 1】order_payments 是「行级」表,一个订单可能有多条支付记录
--   (如 信用卡 + 优惠券,共 2,961 单)。必须先聚合到订单级,
--   否则 COUNT(*) 会把一单算成多单,金额也只是部分值。
-- 【易错点 2】未限定 payment_type 时,1 期档混入了 boleto/debit_card
--   (这两类结构上永远是 1 期),会污染"1 期"的客单价。
-- 【分析要点】结果并非严格单调(7 期低于 6 期,9 期低于 8 期),
--   且这是相关而非因果 —— 是高价订单倾向选择分期,不是分期抬高了客单价。
-- ------------------------------------------------------------
WITH card AS (
    SELECT order_id,
           MAX(payment_installments) AS inst,
           SUM(payment_value)        AS card_value
    FROM order_payments
    WHERE payment_type = 'credit_card'
    GROUP BY order_id
)
SELECT
    card.inst AS payment_installments,
    COUNT(*)                       AS orders,
    ROUND(AVG(card.card_value), 2) AS avg_order_value
FROM card
JOIN orders o ON o.order_id = card.order_id
WHERE o.order_status = 'delivered'
  AND card.inst BETWEEN 1 AND 10
GROUP BY card.inst
ORDER BY card.inst;

-- ------------------------------------------------------------
-- 6. 品类销售额 Top10(带英文分类名)
-- 业务问题:哪些品类贡献最大?选品/投放该聚焦哪?
-- 【易错点】必须 join orders 并过滤 delivered,否则总额会比总 GMV 高约 2.8%,
--   且第 7/8 名排序会发生变化(housewares 与 cool_stuff 互换)。
-- 【口径】COALESCE 兜底,避免未分类商品在结果里显示为 NULL;
--   未分类商品约占营收 1.29%,不影响 Top10 结论。
-- ------------------------------------------------------------
SELECT
    COALESCE(t.product_category_name_english,
             p.product_category_name, '未分类') AS category,
    COUNT(DISTINCT oi.order_id)              AS orders,
    ROUND(SUM(oi.price), 2)                  AS revenue,
    ROUND(AVG(oi.price), 2)                  AS avg_price
FROM order_items oi
JOIN orders o   ON oi.order_id = o.order_id
JOIN products p ON oi.product_id = p.product_id
LEFT JOIN product_category_translation t
       ON p.product_category_name = t.product_category_name
WHERE o.order_status = 'delivered'
GROUP BY category
ORDER BY revenue DESC
LIMIT 10;
