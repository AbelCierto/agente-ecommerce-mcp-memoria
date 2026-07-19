"""MCP de datos e-commerce basado en el dataset real del proyecto.

Cada tool expone una capacidad analítica de negocio y ejecuta SQL explícito,
parametrizado y de solo lectura. El LLM no genera SQL libre.

Antes de ejecutar este servidor:
    python data/import_dataset_to_sqlite.py

Inicio local:
    python mcp_datos.py

Endpoint MCP:
    http://127.0.0.1:8000/mcp
"""
from __future__ import annotations

import json
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from fastmcp import FastMCP

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "ecommerce_orders.db"
CSV_PATH = DATA_DIR / "ecommerce_orders_dataset.csv"

mcp = FastMCP(
    name="Ecommerce Analytics Data MCP",
    instructions=(
        "Servidor MCP de analítica e-commerce de solo lectura. Usa herramientas "
        "específicas para analizar clientes, ventas, categorías, devoluciones y canales."
    ),
)


def ejecutar_sql(sql: str, parametros: tuple = ()) -> list[dict]:
    if not DB_PATH.exists():
        _bootstrap_db_if_missing()
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe {DB_PATH}. No se pudo inicializar desde {CSV_PATH}."
        )
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, parametros).fetchall()
    return [dict(row) for row in rows]


def _bootstrap_db_if_missing() -> None:
    if DB_PATH.exists():
        return
    if not CSV_PATH.exists():
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        from data.import_dataset_to_sqlite import main as import_main

        print(f"[INFO] Base no encontrada en {DB_PATH}. Generando desde CSV...")
        import_main()
        print("[INFO] Base SQLite inicializada correctamente.")
    except Exception as exc:
        print(f"[WARN] No se pudo generar SQLite automáticamente: {exc}")


def as_json(rows: list[dict], empty_message: str = "No se encontraron resultados") -> str:
    return json.dumps(rows or [{"message": empty_message}], ensure_ascii=False, default=str)


def _normalizar_texto(texto: str, max_len: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", (texto or "").strip())
    if not normalized:
        raise ValueError("El texto de búsqueda no puede estar vacío.")
    if len(normalized) > max_len:
        raise ValueError(f"El texto supera el máximo permitido ({max_len} caracteres).")
    return normalized


def _validar_customer_id(customer_id: str) -> str:
    cleaned = _normalizar_texto(customer_id, max_len=64)
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", cleaned):
        raise ValueError("Customer_ID inválido. Usa solo letras, números, guion o guion bajo.")
    return cleaned


@lru_cache(maxsize=1)
def _year_bounds() -> tuple[int, int]:
    sql = "SELECT MIN(Year) AS min_year, MAX(Year) AS max_year FROM orders"
    rows = ejecutar_sql(sql)
    if not rows:
        return (1900, 2100)
    min_year = int(rows[0].get("min_year") or 1900)
    max_year = int(rows[0].get("max_year") or 2100)
    return (min_year, max_year)


def _validar_year(year: int | None) -> int | None:
    if year is None:
        return None
    min_year, max_year = _year_bounds()
    if year < min_year or year > max_year:
        raise ValueError(
            f"Año fuera de rango para el dataset ({min_year}-{max_year})."
        )
    return year


def _parse_periodo(periodo: str) -> int | None:
    value = _normalizar_texto(periodo, max_len=16).lower()
    if value in {"all", "todo", "historico", "histórico"}:
        return None
    match = re.fullmatch(r"(\d{1,4})d", value)
    if not match:
        raise ValueError("Período inválido. Usa formatos como 30d, 90d, 180d o 'all'.")
    days = int(match.group(1))
    if days < 1 or days > 3650:
        raise ValueError("Período fuera de rango. Debe estar entre 1d y 3650d.")
    return days


def _kpis_por_periodo(days: int | None) -> dict:
    where = ""
    params: tuple[object, ...] = ()
    if days is not None:
        where = "WHERE Order_Date >= date((SELECT MAX(Order_Date) FROM orders), ?)"
        params = (f"-{days} day",)

    sql = f"""
    SELECT COUNT(*) AS Total_Orders,
           COUNT(DISTINCT Customer_ID) AS Total_Customers,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           ROUND(AVG(Profit_Margin_Percent), 2) AS Average_Profit_Margin_Percent,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent,
           ROUND(AVG(Review_Rating), 2) AS Average_Review_Rating,
           ROUND(AVG(Delivery_Days), 2) AS Average_Delivery_Days
    FROM orders
    {where}
    """
    rows = ejecutar_sql(sql, params)
    return rows[0] if rows else {}


@mcp.tool()
def buscar_clientes(texto: str, limite: int = 10) -> str:
    """Busca clientes por Customer_ID, país, ciudad, segmento o membresía.

    Úsala antes de consultar a un cliente cuando no se conoce un Customer_ID exacto.
    """
    try:
        normalized = _normalizar_texto(texto)
    except ValueError as exc:
        return as_json([], str(exc))

    limite = max(1, min(limite, 25))
    p = f"%{normalized}%"
    sql = """
    SELECT Customer_ID,
           MAX(Country) AS Country,
           MAX(City) AS City,
           MAX(Customer_Segment) AS Customer_Segment,
           MAX(Membership_Status) AS Membership_Status,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Total_Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Total_Profit
    FROM orders
    WHERE Customer_ID LIKE ? OR Country LIKE ? OR City LIKE ?
       OR Customer_Segment LIKE ? OR Membership_Status LIKE ?
    GROUP BY Customer_ID
    ORDER BY Total_Revenue DESC
    LIMIT ?
    """
    return as_json(ejecutar_sql(sql, (p, p, p, p, p, limite)))


@mcp.tool()
def resumen_cliente(customer_id: str) -> str:
    """Resume compras, gasto, utilidad, ticket promedio, unidades y período de actividad de un cliente exacto."""
    try:
        customer_id = _validar_customer_id(customer_id)
    except ValueError as exc:
        return as_json([], str(exc))

    sql = """
    SELECT Customer_ID,
           MAX(Country) AS Country,
           MAX(City) AS City,
           MAX(Customer_Segment) AS Customer_Segment,
           MAX(Membership_Status) AS Membership_Status,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Total_Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Total_Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           SUM(Quantity) AS Total_Units,
           MIN(Order_Date) AS First_Order,
           MAX(Order_Date) AS Last_Order,
           ROUND(MAX(Customer_Lifetime_Value), 2) AS Customer_Lifetime_Value
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Customer_ID
    """
    return as_json(ejecutar_sql(sql, (customer_id,)), "Cliente no encontrado")


@mcp.tool()
def perfil_compras_cliente(customer_id: str, limite: int = 8) -> str:
    """Muestra las categorías y subcategorías con mayor gasto de un cliente exacto."""
    try:
        customer_id = _validar_customer_id(customer_id)
    except ValueError as exc:
        return as_json([], str(exc))

    limite = max(1, min(limite, 20))
    sql = """
    SELECT Product_Category,
           Product_Subcategory,
           COUNT(*) AS Orders,
           SUM(Quantity) AS Units,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(AVG(Discount_Percent), 2) AS Average_Discount_Percent
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Product_Category, Product_Subcategory
    ORDER BY Revenue DESC
    LIMIT ?
    """
    return as_json(ejecutar_sql(sql, (customer_id, limite)), "Cliente no encontrado")


@mcp.tool()
def experiencia_cliente(customer_id: str) -> str:
    """Evalúa experiencia de compra: devoluciones, rating, días de entrega, estados de orden y método de envío."""
    try:
        customer_id = _validar_customer_id(customer_id)
    except ValueError as exc:
        return as_json([], str(exc))

    sql = """
    SELECT Customer_ID,
           COUNT(*) AS Total_Orders,
           SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) AS Returned_Orders,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent,
           ROUND(AVG(Review_Rating), 2) AS Average_Review_Rating,
           ROUND(AVG(Delivery_Days), 2) AS Average_Delivery_Days,
           SUM(CASE WHEN Order_Status = 'Cancelled' THEN 1 ELSE 0 END) AS Cancelled_Orders,
           SUM(CASE WHEN Order_Status = 'Delivered' THEN 1 ELSE 0 END) AS Delivered_Orders,
           MAX(Shipping_Method) AS Typical_Shipping_Method
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Customer_ID
    """
    return as_json(ejecutar_sql(sql, (customer_id,)), "Cliente no encontrado")


@mcp.tool()
def ventas_por_dimension(dimension: str, year: int | None = None, limite: int = 10) -> str:
    """Entrega ranking de ventas y utilidad por país, categoría, segmento, canal de tráfico, dispositivo o método de pago.

    dimension válida: country, category, segment, traffic_source, device_type, payment_method, warehouse_region.
    year es opcional; úsalo para comparar un año específico.
    """
    columns = {
        "country": "Country",
        "category": "Product_Category",
        "segment": "Customer_Segment",
        "traffic_source": "Traffic_Source",
        "device_type": "Device_Type",
        "payment_method": "Payment_Method",
        "warehouse_region": "Warehouse_Region",
    }
    key = dimension.strip().lower()
    if key not in columns:
        return as_json([], "Dimensión inválida. Usa: " + ", ".join(columns))
    try:
        year = _validar_year(year)
    except ValueError as exc:
        return as_json([], str(exc))

    limite = max(1, min(limite, 25))
    column = columns[key]
    if year is None:
        sql = f'''SELECT "{column}" AS Dimension,
                         COUNT(*) AS Total_Orders,
                         ROUND(SUM(Order_Amount), 2) AS Revenue,
                         ROUND(SUM(Profit_Amount), 2) AS Profit,
                         ROUND(AVG(Order_Amount), 2) AS Average_Order_Value
                  FROM orders
                  GROUP BY "{column}"
                  ORDER BY Revenue DESC
                  LIMIT ?'''
        params = (limite,)
    else:
        sql = f'''SELECT "{column}" AS Dimension,
                         COUNT(*) AS Total_Orders,
                         ROUND(SUM(Order_Amount), 2) AS Revenue,
                         ROUND(SUM(Profit_Amount), 2) AS Profit,
                         ROUND(AVG(Order_Amount), 2) AS Average_Order_Value
                  FROM orders
                  WHERE Year = ?
                  GROUP BY "{column}"
                  ORDER BY Revenue DESC
                  LIMIT ?'''
        params = (year, limite)
    return as_json(ejecutar_sql(sql, params))


@mcp.tool()
def tendencia_ventas(year: int | None = None, country: str | None = None) -> str:
    """Resume ventas mensuales, utilidad, órdenes, ticket promedio y devoluciones. Puede filtrarse por año y país."""
    try:
        year = _validar_year(year)
        if country is not None:
            country = _normalizar_texto(country, max_len=80)
    except ValueError as exc:
        return as_json([], str(exc))

    filters: list[str] = []
    params: list[object] = []
    if year is not None:
        filters.append("Year = ?")
        params.append(year)
    if country:
        filters.append("Country = ?")
        params.append(country)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    sql = f"""
    SELECT Year, Month,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent
    FROM orders
    {where}
    GROUP BY Year, Month
    ORDER BY Year, Month
    """
    return as_json(ejecutar_sql(sql, tuple(params)))


@mcp.tool()
def detalle_orden(order_id: int) -> str:
    """Recupera el detalle de una orden real por Order_ID. Úsala cuando el usuario entrega un identificador de orden."""
    if order_id <= 0:
        return as_json([], "Order_ID inválido. Debe ser un entero positivo.")

    sql = """
    SELECT Order_ID, Customer_ID, Order_Date, Country, City, Customer_Segment,
           Product_ID, Product_Category, Product_Subcategory, Brand,
           Unit_Price, Quantity, Discount_Percent, Discount_Amount,
           Shipping_Cost, Tax_Amount, Order_Amount, Payment_Method,
           Device_Type, Traffic_Source, Membership_Status, Shipping_Method,
           Delivery_Days, Order_Status, Returned, Review_Rating,
           Profit_Amount, Season, Holiday_Season, High_Value_Order
    FROM orders
    WHERE Order_ID = ?
    """
    return as_json(ejecutar_sql(sql, (order_id,)), "Orden no encontrada")


@mcp.tool()
def ayuda_analitica(consulta: str = "") -> str:
    """Guía de capacidades y límites del MCP para consultas ambiguas o fuera de alcance."""
    try:
        topic = _normalizar_texto(consulta, max_len=120) if consulta else "general"
    except ValueError:
        topic = "general"

    capabilities = [
        "Búsqueda y perfil de clientes por Customer_ID, país, ciudad, segmento y membresía.",
        "Análisis de compras por categoría/subcategoría y experiencia (devoluciones, rating, entrega).",
        "Rankings de ventas/utilidad por dimensión de negocio (país, segmento, canal, dispositivo, pago).",
        "Tendencias mensuales por año y/o país, y detalle por Order_ID.",
    ]
    limits = [
        "No ejecuta SQL libre ni operaciones de escritura (INSERT/UPDATE/DELETE).",
        "Solo responde sobre datos existentes en el dataset cargado en SQLite.",
        "No consulta fuentes externas, internet ni sistemas transaccionales en vivo.",
    ]
    examples = [
        "Busca clientes Premium en Germany y resume al de mayor facturación.",
        "Compara ventas por categoría en 2025.",
        "Analiza la tendencia mensual de ventas de France en 2024.",
        "Dame el detalle de la orden 615717.",
    ]

    return as_json(
        [
            {
                "tema": topic,
                "capacidades": capabilities,
                "limites": limits,
                "preguntas_sugeridas": examples,
            }
        ]
    )


@mcp.tool()
def resumen_base() -> str:
    """Entrega métricas globales del dataset: órdenes, clientes, países, ciudades y rango temporal."""
    sql = """
    SELECT
        COUNT(*) AS Total_Orders,
        COUNT(DISTINCT Customer_ID) AS Total_Customers,
        COUNT(DISTINCT Country) AS Total_Countries,
        COUNT(DISTINCT City) AS Total_Cities,
        MIN(Order_Date) AS First_Order_Date,
        MAX(Order_Date) AS Last_Order_Date,
        ROUND(SUM(Order_Amount), 2) AS Total_Revenue,
        ROUND(SUM(Profit_Amount), 2) AS Total_Profit
    FROM orders
    """
    return as_json(ejecutar_sql(sql))


@mcp.tool()
def listar_paises(limite: int = 300) -> str:
    """Lista países presentes en el dataset con número de órdenes y facturación por país."""
    limite = max(1, min(limite, 500))
    sql = """
    SELECT Country,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Profit
    FROM orders
    GROUP BY Country
    ORDER BY Country ASC
    LIMIT ?
    """
    return as_json(ejecutar_sql(sql, (limite,)))


@mcp.tool()
def top_kpis(periodo: str = "90d") -> str:
    """KPIs ejecutivos globales para un período reciente (ej. 30d, 90d, 180d, all)."""
    try:
        days = _parse_periodo(periodo)
    except ValueError as exc:
        return as_json([], str(exc))

    kpis = _kpis_por_periodo(days)
    kpis["Period"] = "all" if days is None else f"{days}d"
    return as_json([kpis], "No hay datos para el período solicitado")


@mcp.tool()
def comparativo_anual(year_a: int, year_b: int) -> str:
    """Compara KPIs entre dos años y devuelve variaciones absolutas y porcentuales."""
    try:
        year_a = _validar_year(year_a)
        year_b = _validar_year(year_b)
    except ValueError as exc:
        return as_json([], str(exc))

    sql = """
    SELECT Year,
           COUNT(*) AS Total_Orders,
           COUNT(DISTINCT Customer_ID) AS Total_Customers,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent
    FROM orders
    WHERE Year IN (?, ?)
    GROUP BY Year
    """
    rows = ejecutar_sql(sql, (year_a, year_b))
    data = {int(row["Year"]): row for row in rows if row.get("Year") is not None}
    if year_a not in data or year_b not in data:
        return as_json([], "No hay datos completos para ambos años solicitados")

    a = data[year_a]
    b = data[year_b]

    def delta(metric: str) -> dict:
        va = float(a.get(metric) or 0)
        vb = float(b.get(metric) or 0)
        change = round(vb - va, 2)
        pct = round((change / va) * 100, 2) if va else None
        return {
            "metric": metric,
            f"value_{year_a}": va,
            f"value_{year_b}": vb,
            "delta": change,
            "delta_percent": pct,
        }

    return as_json(
        [
            {
                "year_a": year_a,
                "year_b": year_b,
                "comparativo": [
                    delta("Revenue"),
                    delta("Profit"),
                    delta("Total_Orders"),
                    delta("Total_Customers"),
                    delta("Average_Order_Value"),
                    delta("Return_Rate_Percent"),
                ],
            }
        ]
    )


@mcp.tool()
def productos_baja_rotacion(periodo: str = "90d", limite: int = 15) -> str:
    """Detecta productos de baja rotación en un período reciente para acciones de inventario."""
    try:
        days = _parse_periodo(periodo)
    except ValueError as exc:
        return as_json([], str(exc))

    limite = max(1, min(limite, 100))
    where = ""
    params: list[object] = []
    if days is not None:
        where = "WHERE Order_Date >= date((SELECT MAX(Order_Date) FROM orders), ?)"
        params.append(f"-{days} day")

    sql = f"""
    SELECT Product_ID,
           Product_Category,
           Product_Subcategory,
           Brand,
           COUNT(*) AS Total_Orders,
           SUM(Quantity) AS Units,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(AVG(Unit_Price), 2) AS Average_Unit_Price
    FROM orders
    {where}
    GROUP BY Product_ID, Product_Category, Product_Subcategory, Brand
    HAVING SUM(Quantity) > 0
    ORDER BY Units ASC, Revenue ASC
    LIMIT ?
    """
    params.append(limite)
    return as_json(
        ejecutar_sql(sql, tuple(params)),
        "No hay datos de productos para el período solicitado",
    )


@mcp.tool()
def riesgo_churn_cliente(customer_id: str) -> str:
    """Calcula un score heurístico de riesgo de churn para un cliente específico."""
    try:
        customer_id = _validar_customer_id(customer_id)
    except ValueError as exc:
        return as_json([], str(exc))

    sql = """
    WITH global_max AS (
        SELECT MAX(Order_Date) AS max_order_date FROM orders
    ),
    customer_base AS (
        SELECT Customer_ID,
               COUNT(*) AS Total_Orders,
               ROUND(SUM(Order_Amount), 2) AS Revenue,
               ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
               ROUND(AVG(Review_Rating), 2) AS Average_Review_Rating,
               ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent,
               MAX(Order_Date) AS Last_Order_Date,
               MAX(Customer_Segment) AS Customer_Segment,
               MAX(Membership_Status) AS Membership_Status
        FROM orders
        WHERE Customer_ID = ?
        GROUP BY Customer_ID
    ),
    gaps AS (
        SELECT o.Customer_ID,
               AVG(
                   julianday(o.Order_Date) - julianday(
                       LAG(o.Order_Date) OVER (PARTITION BY o.Customer_ID ORDER BY o.Order_Date)
                   )
               ) AS Avg_Days_Between_Orders
        FROM orders o
        WHERE o.Customer_ID = ?
    )
    SELECT cb.*,
           ROUND(julianday(gm.max_order_date) - julianday(cb.Last_Order_Date), 2) AS Recency_Days,
           ROUND(COALESCE(g.Avg_Days_Between_Orders, 0), 2) AS Avg_Days_Between_Orders
    FROM customer_base cb
    CROSS JOIN global_max gm
    LEFT JOIN gaps g ON g.Customer_ID = cb.Customer_ID
    """
    rows = ejecutar_sql(sql, (customer_id, customer_id))
    if not rows:
        return as_json([], "Cliente no encontrado")

    row = rows[0]
    recency = float(row.get("Recency_Days") or 0)
    avg_gap = float(row.get("Avg_Days_Between_Orders") or 0)
    return_rate = float(row.get("Return_Rate_Percent") or 0)
    rating = float(row.get("Average_Review_Rating") or 0)

    score = 0
    factors: list[str] = []
    if avg_gap > 0 and recency > avg_gap * 2:
        score += 45
        factors.append("Recencia alta vs. patrón histórico de compra")
    elif recency > 120:
        score += 35
        factors.append("Sin compras recientes")

    if return_rate >= 25:
        score += 25
        factors.append("Tasa de devolución elevada")
    elif return_rate >= 15:
        score += 15
        factors.append("Tasa de devolución moderada")

    if rating and rating < 3.5:
        score += 20
        factors.append("Rating promedio bajo")

    level = "bajo"
    if score >= 60:
        level = "alto"
    elif score >= 30:
        level = "medio"

    return as_json(
        [
            {
                **row,
                "Churn_Risk_Score": min(score, 100),
                "Churn_Risk_Level": level,
                "Rationale": factors or ["Sin señales relevantes de churn en métricas observables"],
            }
        ]
    )


@mcp.tool()
def alertas_negocio(periodo: str = "30d") -> str:
    """Genera alertas ejecutivas simples basadas en devoluciones, margen, rating y entrega para un período."""
    try:
        days = _parse_periodo(periodo)
    except ValueError as exc:
        return as_json([], str(exc))

    kpis = _kpis_por_periodo(days)
    if not kpis:
        return as_json([], "No hay datos para generar alertas")

    alerts: list[dict] = []
    return_rate = float(kpis.get("Return_Rate_Percent") or 0)
    margin = float(kpis.get("Average_Profit_Margin_Percent") or 0)
    rating = float(kpis.get("Average_Review_Rating") or 0)
    delivery = float(kpis.get("Average_Delivery_Days") or 0)

    if return_rate >= 18:
        alerts.append({
            "severity": "high",
            "alert": "Devoluciones elevadas",
            "metric": "Return_Rate_Percent",
            "value": return_rate,
            "suggestion": "Revisar calidad por categoría y causas de devolución.",
        })
    if margin <= 18:
        alerts.append({
            "severity": "medium",
            "alert": "Margen promedio comprimido",
            "metric": "Average_Profit_Margin_Percent",
            "value": margin,
            "suggestion": "Ajustar descuentos y mix de productos de bajo margen.",
        })
    if rating and rating < 3.8:
        alerts.append({
            "severity": "medium",
            "alert": "Experiencia de cliente en riesgo",
            "metric": "Average_Review_Rating",
            "value": rating,
            "suggestion": "Priorizar mejora de postventa y tiempos de entrega.",
        })
    if delivery >= 6:
        alerts.append({
            "severity": "medium",
            "alert": "Demora logística por encima de objetivo",
            "metric": "Average_Delivery_Days",
            "value": delivery,
            "suggestion": "Revisar SLA por región y método de envío.",
        })

    if not alerts:
        alerts.append({
            "severity": "info",
            "alert": "Sin alertas críticas",
            "metric": "general_health",
            "value": "ok",
            "suggestion": "Mantener monitoreo continuo de KPIs clave.",
        })

    return as_json(
        [
            {
                "period": "all" if days is None else f"{days}d",
                "kpis_base": kpis,
                "alerts": alerts,
            }
        ]
    )


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)
