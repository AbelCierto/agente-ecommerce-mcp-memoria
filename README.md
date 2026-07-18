# Clase 3 — Agente MCP con memoria sobre datos reales de e-commerce

## Propósito del proyecto

Este proyecto continúa el laboratorio de Colab de la clase anterior. Conserva la idea central: un agente LangChain usa herramientas descubiertas desde un servidor MCP, y cada herramienta encapsula una consulta SQL explícita y revisable.

La diferencia es que esta versión deja de usar datos demo. El MCP trabaja con el archivo real `data/ecommerce_orders_dataset.csv`, con 30.000 órdenes, 8.683 clientes y 41 variables sobre ventas, productos, logística, comportamiento, devoluciones y rentabilidad.

El proyecto permite enseñar cuatro ideas a la vez:

1. cómo convertir un CSV real en una base SQLite reproducible;
2. cómo publicar capacidades analíticas personalizadas como tools MCP;
3. cómo conectar un agente LangChain + OpenAI a esas tools y añadir memoria de corto plazo;
4. cómo empaquetar el agente como un MCP que puede ser consumido desde Streamlit o Claude Desktop.

---

## Arquitectura

```text
                           ┌────────────────────────────┐
                           │       Claude Desktop       │
                           │    Host MCP externo        │
                           └──────────────┬─────────────┘
                                          │ stdio
                                          ▼
┌──────────────────────┐      ┌────────────────────────────┐
│  app_streamlit.py    │ HTTP │      mcp_agente.py         │
│  cliente MCP propio  │─────▶│ MCP que publica el agente  │
│ chat + memoria +     │      │ resolver_consulta_ecommerce│
│ traza visible        │      └──────────────┬─────────────┘
└──────────────────────┘                     │
                                               ▼
                                    ┌──────────────────────┐
                                    │     agent_core.py    │
                                    │ LangChain + OpenAI   │
                                    │ memoria por session  │
                                    └──────────┬───────────┘
                                               │ cliente MCP HTTP
                                               ▼
                                    ┌──────────────────────┐
                                    │    mcp_datos.py      │
                                    │ tools SQL de lectura │
                                    └──────────┬───────────┘
                                               ▼
                              SQLite: ecommerce_orders.db
                                               ▲
                                               │ importación reproducible
                       ecommerce_orders_dataset.csv (dataset real)
```

La interfaz no contiene la inteligencia. Streamlit solo consume la tool pública del agente. Claude Desktop también consume la misma tool, sin conocer los detalles del modelo, la memoria, las queries ni la base de datos.

---

## Progresión desde Colab a Python

| En el notebook anterior | En este proyecto |
|---|---|
| CSV o datos cargados en la sesión | CSV real incluido en `data/` |
| SQLite preparado en una celda | `import_dataset_to_sqlite.py` reproducible |
| MCP con queries SQL | `mcp_datos.py` con siete tools de negocio |
| Agente LangChain ejecutado en notebook | `agent_core.py` desacoplado de la interfaz |
| Consulta aislada | Conversación con `session_id` y memoria temporal |
| Un solo consumidor | Streamlit y Claude Desktop |

La regla de diseño no cambia: el LLM no escribe SQL libre. Selecciona tools con propósitos acotados; cada tool ejecuta SQL parametrizado y de solo lectura.

---

## Dataset real

`data/ecommerce_orders_dataset.csv` contiene 30.000 órdenes entre 2023-01-01 y 2026-12-31. Incluye, entre otros, los campos:

```text
Order_ID, Customer_ID, Order_Date, Country, City, Customer_Segment,
Product_Category, Product_Subcategory, Brand, Quantity, Order_Amount,
Traffic_Source, Device_Type, Membership_Status, Shipping_Method,
Delivery_Days, Order_Status, Returned, Review_Rating,
Customer_Lifetime_Value, Profit_Amount, Season
```

El dataset usa datos de ejemplo y sirve para aprendizaje técnico. No debe usarse como evidencia comercial real.

### Importar el CSV a SQLite

```bash
python data/import_dataset_to_sqlite.py
```

El script valida las columnas esperadas, normaliza `Order_Date`, crea `data/ecommerce_orders.db`, importa la tabla `orders` y agrega índices para consultas frecuentes. El archivo `.db` no se sube al repositorio porque puede regenerarse a partir del CSV.

---

## Tools personalizadas del MCP de datos

| Tool | Capacidad de negocio | Columnas reales principales |
|---|---|---|
| `buscar_clientes` | Encuentra clientes por ID, ubicación, segmento o membresía | `Customer_ID`, `Country`, `City`, `Customer_Segment` |
| `resumen_cliente` | Resume gasto, utilidad, ticket, actividad y CLV | `Order_Amount`, `Profit_Amount`, `Customer_Lifetime_Value` |
| `perfil_compras_cliente` | Muestra categorías y subcategorías preferidas | `Product_Category`, `Product_Subcategory`, `Discount_Percent` |
| `experiencia_cliente` | Evalúa devoluciones, rating, despacho y estados de orden | `Returned`, `Review_Rating`, `Delivery_Days`, `Order_Status` |
| `ventas_por_dimension` | Compara facturación y utilidad por país, categoría, segmento o canal | `Country`, `Product_Category`, `Traffic_Source`, `Profit_Amount` |
| `tendencia_ventas` | Analiza ventas mensuales, utilidad, ticket y devoluciones | `Year`, `Month`, `Order_Amount`, `Profit_Amount` |
| `detalle_orden` | Recupera el detalle de una orden específica | `Order_ID` y atributos de la transacción |

Estas tools están deliberadamente separadas. No existe una tool genérica como `ejecutar_sql(sql)` porque sería insegura, difícil de gobernar y poco clara para el LLM.

---

## Requisitos

- Python 3.11 o superior recomendado.
- Cuenta y clave de OpenAI API.
- Claude Desktop solo para la demostración de consumo externo.
- Puertos locales 8000 y 8001 disponibles.

El modelo configurado por defecto es `gpt-5.4-nano`. Si tu cuenta no dispone de él, reemplaza `OPENAI_MODEL` en `.env` por un modelo habilitado en tu cuenta.

---

## Instalación

### 1. Crear el entorno virtual

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

macOS / Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edita `.env`:

```text
OPENAI_API_KEY=tu_clave
OPENAI_MODEL=gpt-5.4-nano
DATA_MCP_URL=http://127.0.0.1:8000/mcp
AGENT_MCP_URL=http://127.0.0.1:8001/mcp
MEMORY_WINDOW_MESSAGES=8
```

### 4. Cargar los datos reales

```bash
python data/import_dataset_to_sqlite.py
```

### 5. Comprobar el entorno

```bash
python scripts/check_environment.py
```

---

## Ejecutar con Streamlit

Abre tres terminales en la carpeta del proyecto, con el entorno virtual activo.

Terminal 1: MCP de datos.

```bash
python mcp_datos.py
```

Terminal 2: MCP del agente por HTTP.

macOS / Linux:

```bash
MCP_AGENT_TRANSPORT=http python mcp_agente.py
```

Windows PowerShell:

```powershell
$env:MCP_AGENT_TRANSPORT="http"
python mcp_agente.py
```

Terminal 3: aplicación Streamlit.

```bash
streamlit run app_streamlit.py
```

Streamlit mostrará el chat, `session_id`, tamaño de ventana de memoria y traza de herramientas utilizadas. Esto permite que la clase observe qué herramienta fue elegida y qué resultados intermedios llegaron al agente.

### Preguntas sugeridas para probar

```text
Busca clientes Premium y dime cuál tiene mayor facturación.
```

```text
Ahora analiza sus categorías preferidas y su experiencia de compra.
```

```text
Compara las ventas por categoría durante 2025.
```

```text
Analiza la tendencia mensual de ventas de Germany en 2025.
```

```text
Revisa el detalle de la orden 615717.
```

La segunda consulta prueba la memoria: “sus” debe referirse al cliente de la primera consulta. Presiona “Nueva conversación” en Streamlit para comprobar que un nuevo `session_id` no hereda el contexto anterior.

---

## Ejecutar desde Claude Desktop

Claude Desktop funciona como host MCP y debe iniciar `mcp_agente.py` mediante `stdio`. El MCP de datos debe seguir activo por HTTP.

1. Mantén en ejecución `python mcp_datos.py`.
2. Abre `config/claude_desktop_config.example.json`.
3. Reemplaza la ruta de ejemplo por la ruta absoluta real de `mcp_agente.py`.
4. Agrega tu API key de forma segura según el entorno de tu equipo.
5. Reinicia Claude Desktop.

Claude Desktop descubrirá una única capacidad pública:

```text
resolver_consulta_ecommerce(mensaje, session_id, canal)
```

Ese es el punto pedagógico central: Claude no consume una tabla ni queries SQL. Consume un servicio agentivo que, internamente, coordina herramientas del MCP de datos.

---

## Memoria de corto plazo

`agent_core.py` implementa memoria temporal con tres piezas:

```python
CHECKPOINTER = InMemorySaver()
```

Guarda el estado de la conversación mientras el proceso permanece encendido.

```python
{"configurable": {"thread_id": session_id}}
```

Asocia los turnos a una conversación específica. En el proyecto `session_id` se traduce al `thread_id` que usa LangGraph.

```python
@before_model
def ventana_contexto(...):
```

Limita los mensajes que se entregan al modelo. La variable `MEMORY_WINDOW_MESSAGES` controla el tamaño aproximado de la ventana. Esto es equivalente, a nivel conceptual, a `ConversationBufferWindowMemory(k=...)`, pero sigue el enfoque actual de estado + checkpointer usado por LangChain/LangGraph.

Esta memoria no es conocimiento permanente. Se elimina al reiniciar el proceso del agente y debe reemplazarse por un checkpointer persistente en un entorno productivo.

---

## Responsabilidad de cada archivo

| Archivo | Rol |
|---|---|
| `data/ecommerce_orders_dataset.csv` | Fuente de datos real del laboratorio. |
| `data/import_dataset_to_sqlite.py` | Conversión reproducible CSV → SQLite. |
| `mcp_datos.py` | Servidor MCP de herramientas analíticas SQL. |
| `agent_core.py` | Agente LangChain, modelo, memoria y trazabilidad. |
| `mcp_agente.py` | Servidor MCP que empaqueta al agente. |
| `app_streamlit.py` | Cliente MCP y visualizador del proceso. |
| `config/claude_desktop_config.example.json` | Plantilla para conectar Claude Desktop. |

---

## Límites y extensiones

Esta versión es adecuada para laboratorio local. Para un despliegue real convendría sustituir SQLite por una base administrada, `InMemorySaver` por persistencia compartida, las URLs locales por servicios desplegados y añadir autenticación, autorización, límites de tasa, logging centralizado, monitoreo y pruebas automatizadas.

No expongas `mcp_datos.py` a internet sin controles. Aunque las tools sean de solo lectura, los datos pueden requerir protección y permisos.
