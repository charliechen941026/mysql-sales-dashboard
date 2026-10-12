
import os
import ssl
from datetime import date, datetime
from decimal import Decimal

import pymysql
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# 只允許你的 GitHub Pages 網站跨來源讀取
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "https://charliechen941026.github.io"
            ]
        }
    }
)

ALLOWED_TABLES = {
    "sales_original_300",
    "sales_updated_300"
}


def get_connection():
    # 讀取 Render 的環境變數
    ca_path = os.environ["MYSQL_CA_PATH"]

    ssl_context = ssl.create_default_context(
        cafile=ca_path
    )

    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        ssl=ssl_context,
        connect_timeout=15,
        read_timeout=15,
        cursorclass=pymysql.cursors.DictCursor
    )


def json_safe(value):
    # 處理 MySQL 日期與 Decimal 型態
    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    return value


@app.route("/")
def home():
    return jsonify({
        "message": "MySQL Sales API is running"
    })


@app.route("/api/sales", methods=["GET"])
def get_sales():
    try:
        conn = get_connection()

        try:
            with conn.cursor() as cursor:

                # 讀取目前啟用的資料表
                cursor.execute("""
                    SELECT active_table
                    FROM dashboard_settings
                    WHERE id = 1
                """)

                setting = cursor.fetchone()

                if not setting:
                    return jsonify({
                        "error": "找不到版本設定"
                    }), 500

                table_name = setting["active_table"]

                # 防止任意 SQL 資料表名稱注入
                if table_name not in ALLOWED_TABLES:
                    return jsonify({
                        "error": "不允許的資料表"
                    }), 500

                # 查詢目前版本的銷售資料
                cursor.execute(f"""
                    SELECT
                        sale_id,
                        sale_date,
                        product_id,
                        product_name,
                        category,
                        channel,
                        unit_price,
                        quantity,
                        returned_quantity
                    FROM `{table_name}`
                    ORDER BY sale_date, sale_id
                """)

                rows = cursor.fetchall()

        finally:
            conn.close()

        records = []

        for row in rows:
            record = {
                key: json_safe(value)
                for key, value in row.items()
            }

            record["net_revenue"] = (
                record["unit_price"] *
                (
                    record["quantity"] -
                    record["returned_quantity"]
                )
            )

            records.append(record)

        total_quantity = sum(
            r["quantity"] for r in records
        )

        total_returns = sum(
            r["returned_quantity"] for r in records
        )

        total_revenue = sum(
            r["net_revenue"] for r in records
        )

        # 三張圖表的分組資料
        daily = {}
        products = {}
        categories = {}

        for r in records:
            day = r["sale_date"]
            product = r["product_name"]
            category = r["category"]
            revenue = r["net_revenue"]

            daily[day] = daily.get(day, 0) + revenue

            products[product] = (
                products.get(product, 0) + revenue
            )

            categories[category] = (
                categories.get(category, 0) + revenue
            )

        response = {
            "version": table_name,
            "summary": {
                "total_records": len(records),
                "total_quantity": total_quantity,
                "total_returns": total_returns,
                "total_revenue": total_revenue
            },
            "charts": {
                "daily": [
                    {"name": k, "value": v}
                    for k, v in sorted(daily.items())
                ],
                "products": [
                    {"name": k, "value": v}
                    for k, v in sorted(
                        products.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                ],
                "categories": [
                    {"name": k, "value": v}
                    for k, v in categories.items()
                ]
            }
        }

        result = jsonify(response)

        # 避免瀏覽器使用舊資料
        result.headers["Cache-Control"] = "no-store"

        return result

    except Exception:
        app.logger.exception("MySQL API error")

        return jsonify({
            "error": "資料庫讀取失敗"
        }), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
