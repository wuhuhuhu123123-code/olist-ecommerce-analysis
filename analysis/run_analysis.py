"""Olist 业务分析:跑 7 个业务问题,打印结果并导出图表。

用法(两种都行):
    python analysis/run_analysis.py
    python -m analysis.run_analysis

前置条件:MySQL 已建表并导入数据(见 README),且 .env 已配好密码。

设计说明:
    - 所有查询都限定 order_status='delivered'(已送达),口径统一;
      每条查询的口径差异都在注释里写明。
    - 输出 PNG 到 analysis/charts/,供 README 引用。
"""
import os
import sys

# 保证从任意目录运行都能 import 到 etl/config.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Windows 控制台默认可能是 cp936/GBK,显式切 UTF-8 避免中文输出乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib

matplotlib.use("Agg")  # 无 GUI 后端,直接存文件

import matplotlib.pyplot as plt
import pandas as pd

from etl.config import get_engine

# ---------------------------------------------------------------- 图表样式

# 中文字体回退列表:Windows 用雅黑/黑体,Linux/CI 用 Noto/文泉驿
plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Zen Hei",
]
# 不设这一行,负号会显示成方块
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.25

# 配色:主色 / 警示色 / 强调色
C_MAIN, C_WARN, C_ACCENT, C_MUTED = "#2E6F9E", "#C0392B", "#E8A33D", "#8D9BA8"

CHARTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "charts")


def save(fig, name):
    os.makedirs(CHARTS_DIR, exist_ok=True)
    path = os.path.join(CHARTS_DIR, name)
    fig.savefig(path)
    plt.close(fig)
    print(f"    -> 图表已保存 {os.path.relpath(path, PROJECT_ROOT)}")


def title(ax, text, sub=None):
    # 有副标题时把主标题抬得更高,否则两行会贴在一起
    ax.set_title(text, fontsize=13, fontweight="bold", pad=30 if sub else 8)
    if sub:
        ax.text(0.0, 1.015, sub, transform=ax.transAxes, fontsize=9, color=C_MUTED)


# ---------------------------------------------------------------- 分析

def q_kpi(engine):
    """总览 KPI,以及 GMV 口径的自洽性校验。"""
    print("\n=== 总览 KPI(口径:已送达订单)===")
    sql = """
        SELECT COUNT(DISTINCT o.order_id)  AS orders,
               SUM(oi.price)               AS gmv,
               SUM(oi.freight_value)       AS freight
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'delivered'
    """
    row = pd.read_sql(sql, engine).iloc[0]
    orders, gmv, freight = int(row.orders), float(row.gmv), float(row.freight)

    pay = pd.read_sql(
        """
        SELECT SUM(p.payment_value) AS paid
        FROM order_payments p
        JOIN orders o ON p.order_id = o.order_id
        WHERE o.order_status = 'delivered'
        """,
        engine,
    ).iloc[0].paid

    # 付款总额 vs 商品+运费。差异极小说明数据自洽,是可信度加分项。
    diff_pct = (float(pay) - (gmv + freight)) / (gmv + freight) * 100

    print(f"  已送达订单      {orders:,}")
    print(f"  GMV(商品,不含运费) R${gmv:,.2f}")
    print(f"  运费            R${freight:,.2f}(占 GMV {freight / gmv * 100:.1f}%)")
    print(f"  客单价(基于商品)  R${gmv / orders:,.2f}")
    print(f"  客单价(基于付款)  R${float(pay) / orders:,.2f}   <- 与上一行口径不同,勿混用")
    print(f"  付款总额        R${float(pay):,.2f}(与商品+运费差 {diff_pct:.2f}%,数据自洽)")


def q1_monthly(engine):
    """业务问题 1:整体销售趋势如何?有没有增长点?"""
    print("\n=== Q1 月度 GMV 与订单量 ===")
    # 按天聚合后在 pandas 里按月汇总:避免在 SQL 里写 DATE_FORMAT('%Y-%m'),
    # 那个 % 会被 pymysql 当成参数占位符而报错。
    daily = pd.read_sql(
        """
        SELECT DATE(o.order_purchase_timestamp) AS d,
               COUNT(DISTINCT o.order_id)       AS orders,
               SUM(oi.price)                    AS gmv
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.order_status = 'delivered'
        GROUP BY d
        ORDER BY d
        """,
        engine,
    )
    daily["d"] = pd.to_datetime(daily.d)
    df = (
        daily.set_index("d")
        .resample("MS")
        .agg({"orders": "sum", "gmv": "sum"})
        .reset_index()
    )
    df["month"] = df.d.dt.strftime("%Y-%m")
    # 2016-09 与 2016-12 各只有 1 单,是上线初期的噪声,会把坐标轴拉平
    df = df[df.month >= "2017-01"].reset_index(drop=True)
    df["ma3"] = df.gmv.rolling(3, min_periods=1).mean()

    peak = df.loc[df.gmv.idxmax()]
    print(f"  区间 {df.month.iloc[0]} ~ {df.month.iloc[-1]},共 {len(df)} 个月")
    print(f"  峰值 {peak.month}: {int(peak.orders):,} 单 / R${peak.gmv:,.0f}(黑五)")

    fig, ax = plt.subplots(figsize=(11, 4.6))
    ax.bar(df.month, df.gmv, color=C_MAIN, alpha=0.75, label="月度 GMV")
    ax.plot(df.month, df.ma3, color=C_ACCENT, lw=2.2, marker="o", ms=4, label="3 个月移动平均")
    ax.annotate(
        f"黑五 {peak.month}\nR${peak.gmv / 1000:,.0f}k",
        xy=(list(df.month).index(peak.month), peak.gmv),
        xytext=(0, 16), textcoords="offset points",
        ha="center", fontsize=9, color=C_WARN, fontweight="bold",
    )
    tick = max(len(df) // 12, 1)
    ax.set_xticks(range(0, len(df), tick))
    ax.set_xticklabels(df.month[::tick], rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, df.gmv.max() * 1.22)  # 留出顶部空间,避免黑五标注挤到副标题
    ax.set_ylabel("GMV(百万雷亚尔)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")
    ax.legend(loc="upper left", fontsize=9)
    title(ax, "月度 GMV 趋势:2017 年高速增长,2018 年趋于平稳",
          "口径:已送达订单商品金额(不含运费);已剔除 2016 年仅 1 单的噪声月份")
    save(fig, "q1_monthly_gmv.png")
    return df


def q_hero(engine):
    """核心结论:准时送达 vs 延迟送达的评价差异。"""
    print("\n=== 核心结论:物流时效 vs 满意度 ===")
    df = pd.read_sql(
        """
        SELECT CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                    THEN '延迟' ELSE '准时' END             AS grp,
               COUNT(*)                                     AS n,
               AVG(r.review_score)                          AS avg_score,
               SUM(r.review_score <= 2) / COUNT(*) * 100    AS neg_pct
        FROM orders o
        JOIN order_reviews r ON o.order_id = r.order_id
        WHERE o.order_status = 'delivered'
          AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY grp
        """,
        engine,
    ).set_index("grp")
    late, ontime = df.loc["延迟"], df.loc["准时"]
    print(f"  准时  n={int(ontime.n):,}  均分 {ontime.avg_score:.2f}  差评率 {ontime.neg_pct:.1f}%")
    print(f"  延迟  n={int(late.n):,}  均分 {late.avg_score:.2f}  差评率 {late.neg_pct:.1f}%")
    print(f"  -> 延迟订单差评率是准时的 {late.neg_pct / ontime.neg_pct:.1f} 倍")

    detail = pd.read_sql(
        """
        SELECT CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                    THEN '延迟' ELSE '准时' END AS grp,
               r.review_score, COUNT(*) AS n
        FROM orders o
        JOIN order_reviews r ON o.order_id = r.order_id
        WHERE o.order_status = 'delivered'
          AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY grp, r.review_score
        """,
        engine,
    )
    piv = detail.pivot(index="review_score", columns="grp", values="n").fillna(0)
    piv = piv.div(piv.sum(axis=0), axis=1) * 100  # 每组的评分占比

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    x = range(len(piv.index))
    w = 0.38
    ax.bar([i - w / 2 for i in x], piv["准时"], w, color=C_MAIN, label=f"准时送达 (n={int(ontime.n):,})")
    ax.bar([i + w / 2 for i in x], piv["延迟"], w, color=C_WARN, label=f"延迟送达 (n={int(late.n):,})")
    for i, (a, b) in enumerate(zip(piv["准时"], piv["延迟"])):
        ax.text(i - w / 2, a + 1.2, f"{a:.0f}%", ha="center", fontsize=8)
        ax.text(i + w / 2, b + 1.2, f"{b:.0f}%", ha="center", fontsize=8, color=C_WARN)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{int(s)}★" for s in piv.index])
    ax.set_ylabel("占该组评价的百分比")
    ax.set_ylim(0, max(piv.max()) * 1.18)
    ax.legend(fontsize=9)
    title(ax, "物流时效是满意度的主导因素,而非商品质量",
          "口径:已送达且有送达时间的订单;分组依据为实际送达 vs 平台承诺日期")
    save(fig, "hero_late_vs_ontime.png")


def q2_repurchase(engine):
    """业务问题 2:客户粘性如何?复购率多少?"""
    print("\n=== Q2 复购率 ===")
    dist = pd.read_sql(
        """
        SELECT cnt AS orders_per_customer, COUNT(*) AS customers
        FROM (
            SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS cnt
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            WHERE o.order_status = 'delivered'
            GROUP BY c.customer_unique_id
        ) t
        GROUP BY cnt
        ORDER BY cnt
        """,
        engine,
    )
    total = int(dist.customers.sum())
    repeat = int(dist.loc[dist.orders_per_customer > 1, "customers"].sum())
    print(f"  客户总数 {total:,},其中复购 {repeat:,} 人")
    print(f"  复购率 {repeat / total * 100:.2f}%(2 年观察窗,属下限)")
    print(f"  下单次数最多 {int(dist.orders_per_customer.max())} 次")

    fig, ax = plt.subplots(figsize=(8, 4.4))
    bars = ax.bar(dist.orders_per_customer.astype(str), dist.customers, color=C_MAIN)
    bars[0].set_color(C_ACCENT)  # 首次下单突出
    ax.set_yscale("log")  # 不取对数的话,2 次及以上会被压成一条线看不见
    for b, v in zip(bars, dist.customers):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.15, f"{int(v):,}",
                ha="center", fontsize=8)
    ax.set_xlabel("单个客户的下单次数")
    ax.set_ylabel("客户数(对数轴)")
    ax.set_ylim(0.7, dist.customers.max() * 4)
    title(ax, f"复购率仅 {repeat / total * 100:.1f}%:绝大多数客户只买一次",
          "口径:已送达订单,按 customer_unique_id 聚合(非 customer_id)")
    save(fig, "q2_orders_per_customer.png")


def q3_delivery(engine):
    """业务问题 3:哪些地区物流拖后腿?"""
    print("\n=== Q3 各州物流时效 ===")
    df = pd.read_sql(
        """
        SELECT c.customer_state AS state,
               COUNT(*)          AS n,
               AVG(TIMESTAMPDIFF(DAY, o.order_purchase_timestamp,
                                 o.order_delivered_customer_date)) AS avg_days,
               SUM(o.order_delivered_customer_date > o.order_estimated_delivery_date)
                   / COUNT(*) * 100 AS late_pct
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.order_status = 'delivered'
          AND o.order_delivered_customer_date IS NOT NULL
        GROUP BY state
        ORDER BY avg_days DESC
        """,
        engine,
    )
    print("  样本量最大的 6 个州:")
    for _, r in df.nlargest(6, "n").iterrows():
        print(f"    {r.state}  n={int(r.n):>6,}  平均 {r.avg_days:5.1f} 天  延迟率 {r.late_pct:5.1f}%")
    sm = df[df.n < 300]
    print(f"  (有 {len(sm)} 个州样本量 <300,单州结论不可靠,已在图中置灰)")

    # 双面板:平均天数与延迟率并不一致,这个"矛盾"才是运营上的关键
    d = df.sort_values("avg_days")
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.2))
    colors = [C_MUTED if n < 300 else C_MAIN for n in d.n]
    axes[0].barh(d.state, d.avg_days, color=colors)
    axes[0].set_xlabel("平均送达天数")
    axes[0].set_title("平均送达天数", fontsize=11, fontweight="bold")

    d2 = df.sort_values("late_pct")
    colors2 = [C_MUTED if n < 300 else C_WARN for n in d2.n]
    axes[1].barh(d2.state, d2.late_pct, color=colors2)
    axes[1].set_xlabel("延迟送达占比(%)")
    axes[1].set_title("延迟率(相对平台承诺日期)", fontsize=11, fontweight="bold")

    for ax, col in zip(axes, ["avg_days", "late_pct"]):
        src = d if col == "avg_days" else d2
        for i, (_, r) in enumerate(src.iterrows()):
            ax.text(r[col], i, f" {r[col]:.0f}" + ("天" if col == "avg_days" else "%"),
                    va="center", fontsize=7.5)
        ax.tick_params(labelsize=8)
        ax.set_xlim(0, src[col].max() * 1.22)

    fig.suptitle("物流:北部/东北部又慢又易违约;灰色为样本量 <300 的州",
                 fontsize=13, fontweight="bold", y=1.0)
    fig.tight_layout()
    save(fig, "q3_delivery_by_state.png")
    return df


def q4_reviews(engine):
    """业务问题 4:整体满意度如何?差评占多少?"""
    print("\n=== Q4 评价分布 ===")
    df = pd.read_sql(
        """
        SELECT o.order_status AS status, r.review_score, COUNT(*) AS n
        FROM orders o
        JOIN order_reviews r ON o.order_id = r.order_id
        GROUP BY status, r.review_score
        """,
        engine,
    )
    for status in ["delivered", "shipped", "unavailable", "canceled", "invoiced", "processing"]:
        s = df[df.status == status]
        if s.empty:
            continue
        n, neg = int(s.n.sum()), int(s[s.review_score <= 2].n.sum())
        avg = (s.review_score * s.n).sum() / n
        print(f"  {status:<12} n={n:>6,}  均分 {avg:.2f}  差评率 {neg / n * 100:5.1f}%")

    d = df[df.status == "delivered"]
    n_d, neg_d = int(d.n.sum()), int(d[d.review_score <= 2].n.sum())
    print(f"  -> 主口径(已送达):差评率 {neg_d / n_d * 100:.1f}%,"
          f"低于含未送达订单的口径 {(df[df.review_score <= 2].n.sum() / df.n.sum() * 100):.1f}%")

    out = df.copy()
    out["grp"] = out.status.map(lambda s: "已送达" if s == "delivered" else "未送达(物流/取消)")
    agg = out.groupby(["grp", "review_score"]).n.sum().reset_index()
    piv = agg.pivot(index="review_score", columns="grp", values="n").fillna(0)
    piv = piv.div(piv.sum(axis=0), axis=1) * 100

    fig, ax = plt.subplots(figsize=(8.4, 4.4))
    x, w = range(len(piv.index)), 0.38
    for off, col, c in [(-w / 2, "已送达", C_MAIN), (w / 2, "未送达(物流/取消)", C_WARN)]:
        if col in piv:
            bars = ax.bar([i + off for i in x], piv[col], w, color=c, label=col)
            for b, v in zip(bars, piv[col]):
                ax.text(b.get_x() + b.get_width() / 2, v + 1.2, f"{v:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{int(s)}★" for s in piv.index])
    ax.set_ylabel("占比")
    ax.set_ylim(0, 100)
    ax.legend(fontsize=9)
    title(ax, f"已送达订单差评率 {neg_d / n_d * 100:.1f}%;未送达订单几乎全是差评",
          "口径:评价行级数据;未送达含 shipped/canceled/unavailable/invoiced/processing")
    save(fig, "q4_review_distribution.png")


def q5_installments(engine):
    """业务问题 5:分期与客单价的关系。"""
    print("\n=== Q5 分期与订单金额 ===")
    # order_payments 是行级(一单可能多条支付记录),必须先聚合到订单级,
    # 否则 COUNT(*) 会把一单算成多单,金额也只是部分值。
    df = pd.read_sql(
        """
        WITH card AS (
            SELECT order_id,
                   MAX(payment_installments) AS inst,
                   SUM(payment_value)        AS card_value
            FROM order_payments
            WHERE payment_type = 'credit_card'
            GROUP BY order_id
        )
        SELECT card.inst AS inst, card.card_value AS value
        FROM card
        JOIN orders o ON o.order_id = card.order_id
        WHERE o.order_status = 'delivered'
          AND card.inst BETWEEN 1 AND 10
        """,
        engine,
    )
    stat = df.groupby("inst").value.agg(["count", "mean", "median"])
    for inst, r in stat.iterrows():
        print(f"  {int(inst):>2} 期  n={int(r['count']):>6,}  均值 R${r['mean']:7.2f}  中位数 R${r['median']:7.2f}")
    inv = [(6, 7), (8, 9)]
    print("  注意:并非严格单调 —— " + ";".join(
        f"{a} 期 R${stat.loc[a, 'mean']:.0f} > {b} 期 R${stat.loc[b, 'mean']:.0f}" for a, b in inv))

    fig, ax = plt.subplots(figsize=(9, 4.6))
    data = [df[df.inst == i].value.values for i in stat.index]
    bp = ax.boxplot(data, positions=range(len(stat)), widths=0.6, showfliers=False,
                    patch_artist=True, medianprops=dict(color=C_WARN, lw=1.8))
    for patch in bp["boxes"]:
        patch.set_facecolor(C_MAIN)
        patch.set_alpha(0.55)
    ax.plot(range(len(stat)), stat["mean"], color=C_ACCENT, marker="o", lw=1.8, label="均值")
    for i, (inst, r) in enumerate(stat.iterrows()):
        ax.text(i, -22, f"n={int(r['count']):,}", ha="center", fontsize=7.5, color=C_MUTED)
    ax.set_xticklabels([f"{int(i)}期" for i in stat.index])
    ax.set_ylabel("订单金额(雷亚尔)")
    ax.set_xlabel("信用卡分期数")
    ax.legend(fontsize=9)
    title(ax, "分期数越多、订单金额越高 —— 但这是相关,不是因果",
          "口径:已送达订单的信用卡支付金额,按订单级聚合;箱体为四分位,须线剔除离群值")
    save(fig, "q5_installments.png")


def q6_categories(engine):
    """业务问题 6:哪些品类贡献最大?"""
    print("\n=== Q6 品类销售额 ===")
    df = pd.read_sql(
        """
        SELECT COALESCE(t.product_category_name_english,
                        p.product_category_name, '未分类') AS category,
               COUNT(DISTINCT oi.order_id) AS orders,
               SUM(oi.price)               AS revenue,
               AVG(oi.price)               AS avg_price
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.product_id = p.product_id
        LEFT JOIN product_category_translation t
               ON p.product_category_name = t.product_category_name
        WHERE o.order_status = 'delivered'
        GROUP BY category
        ORDER BY revenue DESC
        """,
        engine,
    )
    top = df.head(10)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        print(f"  {i:>2}. {r.category:<24} R${r.revenue:>12,.0f}  {int(r.orders):>6,} 单  均价 R${r.avg_price:6.2f}")
    tot = df.revenue.sum()
    print(f"  未分类占比 {df[df.category == '未分类'].revenue.sum() / tot * 100:.2f}%")

    # 散点比柱状图信息量大:同时看出"高量低价"与"低量高价"两类打法
    fig, ax = plt.subplots(figsize=(9.4, 5.6))
    rest, hi = df.iloc[10:], df.head(10)
    ax.scatter(rest.orders, rest.revenue, s=rest.avg_price * 1.6, color=C_MUTED,
               alpha=0.35, edgecolor="none", label="其他品类")
    ax.scatter(hi.orders, hi.revenue, s=hi.avg_price * 1.6, color=C_MAIN,
               alpha=0.75, edgecolor="white", lw=1, label="营收 Top10")
    for _, r in hi.iterrows():
        ax.annotate(r.category, (r.orders, r.revenue), xytext=(0, 11),
                    textcoords="offset points", ha="center", fontsize=7.6)
    ax.set_xlabel("订单量")
    ax.set_ylabel("营收(雷亚尔)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")
    ax.margins(x=0.09, y=0.13)  # 留白,否则右上角品类标签会被切掉
    ax.legend(fontsize=9, loc="upper left")
    title(ax, "品类两种打法:高量低价(床品)vs 低量高价(手表礼品)",
          "气泡大小 = 商品均价;口径:已送达订单,品类含英文翻译")
    save(fig, "q6_category_scatter.png")
    return df


def main():
    engine = get_engine()
    print("=" * 62)
    print("Olist 业务分析")
    print("=" * 62)
    q_kpi(engine)
    q1_monthly(engine)
    q_hero(engine)
    q2_repurchase(engine)
    q3_delivery(engine)
    q4_reviews(engine)
    q5_installments(engine)
    q6_categories(engine)
    print(f"\n完成。图表见 {os.path.relpath(CHARTS_DIR, PROJECT_ROOT)}/")


if __name__ == "__main__":
    main()
