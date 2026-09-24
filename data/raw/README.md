# 原始数据放这里

本目录**不提交 CSV**(体积大,已在 `.gitignore` 里排除)。请自行下载数据集后,把下面 9 个文件放进本目录:

```
olist_customers_dataset.csv
olist_sellers_dataset.csv
olist_products_dataset.csv
olist_orders_dataset.csv
olist_order_items_dataset.csv
olist_order_payments_dataset.csv
olist_order_reviews_dataset.csv
olist_geolocation_dataset.csv          # 可选,约 100 万行,默认不导入
product_category_name_translation.csv
```

## 下载地址

- 官方 Kaggle:<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce>
- GitHub 镜像:<https://github.com/HNguyennt/Brazilian-E-Commerce-Public-Dataset-by-Olist>

下载 `brazilian-ecommerce` 压缩包解压即可,文件名与上表一致。

## 然后

```bash
mysql -u root -p < sql/schema.sql   # 建库建表
python etl/load_data.py             # 清洗并导入
python analysis/run_analysis.py     # 跑分析并出图
```

> 若本目录为空,`python etl/load_data.py` 会对每张表提示「找不到」并跳过——这是预期行为,不是报错。
