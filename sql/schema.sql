-- ============================================================
-- Olist 电商数据集 —— MySQL 建表脚本
-- 运行方式: mysql -u root -p < sql/schema.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS olist
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE olist;

-- 顺序:先删依赖表,再删主表
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS product_category_translation;

-- 客户
CREATE TABLE customers (
    customer_id               VARCHAR(64)  PRIMARY KEY,
    customer_unique_id        VARCHAR(64)  NOT NULL,
    customer_zip_code_prefix  VARCHAR(16),
    customer_city             VARCHAR(128),
    customer_state            VARCHAR(8)
);

-- 卖家
CREATE TABLE sellers (
    seller_id               VARCHAR(64)  PRIMARY KEY,
    seller_zip_code_prefix  VARCHAR(16),
    seller_city             VARCHAR(128),
    seller_state            VARCHAR(8)
);

-- 商品
CREATE TABLE products (
    product_id                  VARCHAR(64)  PRIMARY KEY,
    product_category_name       VARCHAR(128),
    product_name_length         INT,
    product_description_length  INT,
    product_photos_qty          INT,
    product_weight_g            INT,
    product_length_cm           INT,
    product_height_cm           INT,
    product_width_cm            INT
);

-- 商品分类名翻译(葡语 -> 英语)
CREATE TABLE product_category_translation (
    product_category_name          VARCHAR(128) PRIMARY KEY,
    product_category_name_english  VARCHAR(128)
);

-- 订单
CREATE TABLE orders (
    order_id                      VARCHAR(64) PRIMARY KEY,
    customer_id                   VARCHAR(64),
    order_status                  VARCHAR(32),
    order_purchase_timestamp      DATETIME,
    order_approved_at             DATETIME,
    order_delivered_carrier_date  DATETIME,
    order_delivered_customer_date DATETIME,
    order_estimated_delivery_date DATETIME,
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status   (order_status)
);

-- 订单商品项
CREATE TABLE order_items (
    order_id            VARCHAR(64),
    order_item_id       INT,
    product_id          VARCHAR(64),
    seller_id           VARCHAR(64),
    shipping_limit_date DATETIME,
    price               DECIMAL(12,2),
    freight_value       DECIMAL(12,2),
    PRIMARY KEY (order_id, order_item_id),
    KEY idx_items_product (product_id),
    KEY idx_items_seller (seller_id)
);

-- 支付
CREATE TABLE order_payments (
    order_id             VARCHAR(64),
    payment_sequential   INT,
    payment_type         VARCHAR(32),
    payment_installments INT,
    payment_value        DECIMAL(12,2),
    PRIMARY KEY (order_id, payment_sequential)
);

-- 评价
CREATE TABLE order_reviews (
    review_id               VARCHAR(64) PRIMARY KEY,
    order_id                VARCHAR(64),
    review_score            INT,
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    DATETIME,
    review_answer_timestamp DATETIME,
    KEY idx_reviews_order (order_id)
);

-- 地理位置(约 100 万行,非核心分析,默认不导入)
CREATE TABLE geolocation (
    geolocation_zip_code_prefix VARCHAR(16),
    geolocation_lat             DECIMAL(12,8),
    geolocation_lng             DECIMAL(12,8),
    geolocation_city            VARCHAR(128),
    geolocation_state           VARCHAR(8),
    KEY idx_geo_zip (geolocation_zip_code_prefix)
);
