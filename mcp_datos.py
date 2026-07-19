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


if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    mcp.run(transport="http", host="0.0.0.0", port=port)
