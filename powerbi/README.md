# Power BI 看板搭建指南

---

## 1. 连接 MySQL

1. 打开 Power BI Desktop → 主页 → **获取数据 → 更多 → 数据库 → MySQL 数据库**
2. 服务器填 `127.0.0.1`,数据库填 `olist`
3. 选 **DirectQuery** 或 **导入**(数据量不大,建议"导入",交互更快)
4. 输入 root 账号密码,勾选 8 张表(geolocation 可选,不必导入)

## 2. 建立表关系(星型模型)

进入"模型视图",按下面的主外键建立关系(方向/基数让 Power BI 自动识别即可):

| 表 | 键 | 关联表 | 键 |
| --- | --- | --- | --- |
| orders | customer_id | customers | customer_id |
| order_items | order_id | orders | order_id |
| order_items | product_id | products | product_id |
| order_items | seller_id | sellers | seller_id |
| order_payments | order_id | orders | order_id |
| order_reviews | order_id | orders | order_id |
| products | product_category_name | product_category_translation | product_category_name |

> 事实表:`orders`、`order_items`、`order_payments`、`order_reviews`
> 维度表:`customers`、`products`、`sellers`、`product_category_translation`

## 3. 建议的看板页面结构

- **页 1 · 销售总览**:月度 GMV 折线 + 订单量柱状、KPI 卡片(总 GMV、总订单、客单价)
- **页 2 · 客户分析**:复购率、各州订单分布(地图或条形图)
- **页 3 · 物流时效**:各州平均送达天数(条形图,降序)、准时率
- **页 4 · 评价与品类**:评分分布(环形图)、品类销售额 Top10(条形图)、分期 vs 客单价

## 4. DAX 度量值(核心公式)

在"新建度量值"里逐个添加:

```dax
-- 成交总额(GMV)
GMV = SUM('order_items'[price])

-- 订单量(去重)
订单量 = DISTINCTCOUNT('orders'[order_id])

-- 客单价
客单价 = DIVIDE([GMV], [订单量])

-- 复购率
复购率 =
VAR RepeatCust =
    COUNTROWS(
        FILTER(
            VALUES('orders'[customer_id]),
            CALCULATE(DISTINCTCOUNT('orders'[order_id])) > 1
        )
    )
VAR TotalCust = DISTINCTCOUNT('orders'[customer_id])
RETURN DIVIDE(RepeatCust, TotalCust)

-- 平均评分
平均评分 = AVERAGE('order_reviews'[review_score])
```

## 5. 计算列(用于物流时效)

在 `orders` 表新建计算列:

```dax
送达天数 = DATEDIFF('orders'[order_purchase_timestamp], 'orders'[order_delivered_customer_date], DAY)
```

然后度量值:

```dax
平均送达天数 = AVERAGE('orders'[送达天数])
```

## 6. 提交到 GitHub 的内容

- 本 README(连接 + DAX)
- `powerbi/screenshots/` 下的看板截图(每页一张)
- 可选:导出的 `.pbit`(Power BI 模板文件,不含数据,更适合版本管理)代替 `.pbix`
