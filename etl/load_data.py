"""
Olist 数据集 ETL:把 data/raw/ 下的原始 CSV 清洗后导入 MySQL。

用法:
    1. 先建表:   mysql -u root -p < ../sql/schema.sql
    2. 装依赖:   pip install -r ../requirements.txt
    3. 配密码:   cp .env.example .env,再把真实密码填进 .env
    4. 导入:     python load_data.py

说明:
    - 导入前会先清空目标表(TRUNCATE),所以脚本可重复执行、幂等。
    - 原始数据存在少量重复主键(如 order_reviews 的 review_id),
      导入前按主键去重,这也是数据清洗的一部分。
"""
import os
import sys

import pandas as pd
from sqlalchemy import text

# 让脚本能 import 同目录的 config.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import get_engine

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(PROJECT_ROOT, "data", "raw")

# 原始 CSV 文件名 -> 目标表名
TABLES = {
    "olist_customers_dataset.csv": "customers",
    "olist_sellers_dataset.csv": "sellers",
    "olist_products_dataset.csv": "products",
    "product_category_name_translation.csv": "product_category_translation",
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    # geolocation 约 100 万行,非核心分析,默认跳过;需要时取消下面注释
    # "olist_geolocation_dataset.csv": "geolocation",
}

# 各表的主键列(用于导入前去重)
PRIMARY_KEYS = {
    "customers": ["customer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id"],
    "product_category_translation": ["product_category_name"],
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["review_id"],
}

# 各表里需要转成 datetime 的列
DATE_COLS = {
    "orders": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "order_items": ["shipping_limit_date"],
    "order_reviews": ["review_creation_date", "review_answer_timestamp"],
}

# 各表里需要转成数值的列
NUMERIC_COLS = {
    "products": [
        "product_name_length",
        "product_description_length",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ],
    "order_items": ["price", "freight_value"],
    "order_payments": ["payment_installments", "payment_value"],
    "order_reviews": ["review_score"],
}

# 原始 CSV 里拼写错误的列名 -> 规范列名(products 表)
RENAME_MAP = {
    "product_name_lenght": "product_name_length",
    "product_description_lenght": "product_description_length",
}


def load_table(engine, csv_name, table_name):
    path = os.path.join(RAW_DIR, csv_name)
    if not os.path.exists(path):
        print(f"  [跳过] 找不到 {path}")
        return

    # 先全部按字符串读,避免 pandas 类型推断出错
    df = pd.read_csv(path, dtype=str)
    df = df.rename(columns=RENAME_MAP)

    # 按主键去重(原始数据有少量重复,如 order_reviews 的 review_id)
    pk = PRIMARY_KEYS.get(table_name)
    if pk:
        before = len(df)
        df = df.drop_duplicates(subset=pk, keep="first")
        if len(df) < before:
            print(f"    [去重] 去掉 {before - len(df)} 行重复记录")

    # 日期列转 datetime,非法值转 NaT
    for col in DATE_COLS.get(table_name, []):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # 数值列转数字
    for col in NUMERIC_COLS.get(table_name, []):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # 清空目标表,保证脚本可重复执行
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE TABLE `{table_name}`"))

    print(f"  导入 {csv_name} -> {table_name}: {len(df):,} 行")
    df.to_sql(table_name, engine, if_exists="append", index=False, chunksize=10000)


def main():
    engine = get_engine()
    print("开始导入...")
    for csv_name, table_name in TABLES.items():
        try:
            load_table(engine, csv_name, table_name)
        except Exception as e:
            print(f"  [失败] {table_name}: {e}")
    print("完成。可用 `mysql -u root -p olist` 查看。")


if __name__ == "__main__":
    main()
