# Implementation Guide — Clase 3: Agente MCP con Memoria

## Resumen del Proyecto

Este proyecto convierte un agente LangChain/OpenAI sobre datos reales de e-commerce en una **capacidad reutilizable empaquetada como MCP**. La idea central: el agente puede consumir herramientas publicadas por otros MCPs y, al mismo tiempo, ser publicado como MCP para que múltiples clientes lo consuman sin duplicar lógica.

### Archivos del proyecto

```
clase3_agente_mcp_memoria/
├── mcp_datos.py       # servidor MCP de datos — tools SQL de lectura
├── agent_core.py      # LangChain + OpenAI + memoria por sesión
├── mcp_agente.py      # servidor MCP que empaqueta la capacidad agente
├── app_streamlit.py   # cliente visual propio (chat + trazas + memoria)
├── data/              # CSV original + script de importación a SQLite
├── config/            # ejemplo de configuración para Claude Desktop
└── README.md          # guía práctica de instalación y ejecución
```

### Arquitectura

```text
┌──────────────────────┐      ┌────────────────────────────┐
│   app_streamlit.py   │─HTTP▶│      mcp_agente.py         │
│   cliente MCP propio │      │  resolver_consulta_         │
│  chat + trazas +     │      │  ecommerce(msg, session_id) │
│  memoria visible     │      └──────────────┬─────────────┘
└──────────────────────┘                     │
                                             ▼
              ┌──────────────────────────────────────────┐
              │            agent_core.py                 │
              │  LangChain + OpenAI + memoria (session)  │
              └──────────────────┬───────────────────────┘
                                 │  cliente MCP HTTP
                                 ▼
              ┌──────────────────────────────────────────┐
              │           mcp_datos.py                   │
              │  buscar_clientes · resumen_cliente       │
              │  ventas_por_dimension · tendencia_ventas │
              │  perfil_compras · experiencia · detalle  │
              └──────────────────┬───────────────────────┘
                                 ▼
                    SQLite: ecommerce_orders.db
                    (30 000 órdenes / 8 683 clientes)

      Claude Desktop (host MCP)
      └─stdio─▶ mcp_agente.py  ──▶ (mismo agent_core + mcp_datos)
```

**Principio de diseño**: la interfaz no contiene la inteligencia. Streamlit y Claude Desktop consumen la misma tool pública del agente; ninguno conoce las queries SQL, la estrategia de memoria ni los detalles del modelo.

---

## Conceptos Fundamentales

Antes de ejecutar, conviene entender qué hace cada capa.

### Elementos MCP

| Elemento | Rol | Ejemplo en el laboratorio |
|---|---|---|
| Host | Aplicación que coordina modelo, clientes MCP y UX | Claude Desktop |
| Cliente MCP | Conexión hacia un servidor MCP | Streamlit → MCP agente; agente → MCP datos |
| Servidor MCP | Proceso que publica capacidades con contrato común | `mcp_datos.py` y `mcp_agente.py` |
| Tool | Operación invocable con nombre, descripción y parámetros | `resumen_cliente(customer_id)` |
| Resource | Contenido contextual disponible (lectura) | Guía de negocio, catálogo |
| Prompt | Plantilla reutilizable para una tarea | Análisis comercial estándar |

### Diseño correcto de tools

Una tool no representa una tabla ni una query genérica. Expresa una **capacidad de negocio acotada** que el LLM puede seleccionar por su descripción.

| Diseño débil ❌ | Diseño recomendable ✅ |
|---|---|
| `consultar_sql(sql)` | `resumen_cliente(customer_id)` |
| `obtener_tabla_orders()` | `ordenes_recientes_cliente(customer_id, limite)` |
| `ejecutar_operacion(nombre, payload)` | `experiencia_cliente(customer_id)` |

> **Regla operativa**: toda afirmación factual sobre clientes, compras o experiencia debe provenir de una tool. El modelo explica y sintetiza; la tool entrega evidencia.

### Transporte: HTTP vs stdio

| Transporte | Cuándo se usa | Ventaja |
|---|---|---|
| `http` | Streamlit se conecta a `mcp_agente.py` como servicio | Varios consumidores simultáneos |
| `stdio` | Claude Desktop inicia `mcp_agente.py` como proceso hijo | Configuración simple, integración local |

La lógica del agente no cambia con el transporte; solo cambia la forma de conectarse.

### LLM, agente y tool: no son lo mismo

| Concepto | Qué hace | Qué NO hace |
|---|---|---|
| LLM | Interpreta lenguaje, genera texto, propone llamadas a tools | No conoce datos privados ni mantiene estado externo |
| Tool | Ejecuta una operación y devuelve resultado estructurado | No decide cuándo usarla ni redacta la explicación |
| Agente | Coordina modelo, tools, reglas y memoria | No reemplaza controles de acceso ni reglas de negocio críticas |

### Memoria de corto plazo

El modelo no recuerda entre llamadas. La memoria es responsabilidad de la aplicación.

| Elemento | Rol |
|---|---|
| `session_id` | Identifica una conversación; debe mantenerse estable en el hilo |
| `checkpointer` | Almacena el estado de mensajes por sesión durante la ejecución |
| `InMemorySaver` | Implementación en RAM (formativo); se pierde al reiniciar |
| `MEMORY_WINDOW_MESSAGES` | Conserva instrucciones iniciales + últimos N mensajes |
| `thread_id` | Identificador interno del runtime; se alimenta desde `session_id` |

```
Contexto al modelo = instrucciones + mensaje inicial + últimos 8 mensajes
```

---

## Requisitos Previos

- **Python 3.11+** instalado
- **OpenAI API Key** (https://platform.openai.com/account/api-keys)
- **Git Bash** (instalado con Git para Windows)
- **Puertos disponibles**: 8000 y 8001
- **~5 min de tiempo** para la instalación

### Verificar Python

```bash
python --version
python -m pip --version
```

Si ves versión 3.11 o superior, estás listo.

---

## Paso 1: Preparar el Entorno Virtual

En **Git Bash**, navega a la carpeta del proyecto:

```bash
cd /c/python-dev/agent_mpc_memory/clase3_agente_mcp_memoria
```

Crea el entorno virtual:

```bash
python -m venv .venv
```

Activa el entorno:

```bash
source .venv/Scripts/activate
```

Deberías ver `(.venv)` al inicio de tu prompt en Git Bash.

**Nota**: Si usas PowerShell, usa `.venv\Scripts\Activate.ps1`

---

## Paso 2: Instalar Dependencias

Con el entorno activado:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Las dependencias principales son:
- `fastmcp`: para crear servidores MCP
- `langchain`: orquestación del agente
- `langchain-openai`: integración con OpenAI
- `langgraph`: gestión de estado y memoria
- `streamlit`: interfaz web
- `pandas`: manipulación de datos

Espera a que termine (suele ser ~1-2 minutos).

---

## Paso 3: Configurar Variables de Entorno

Copia el archivo ejemplo:

```bash
cp .env.example .env
```

Abre `.env` con tu editor favorito y edita:

```bash
# .env
OPENAI_API_KEY=sk-PEGA_TU_CLAVE_AQUI
OPENAI_MODEL=gpt-5.4-nano
DATA_MCP_URL=http://127.0.0.1:8000/mcp
AGENT_MCP_URL=http://127.0.0.1:8001/mcp
MEMORY_WINDOW_MESSAGES=8
```

**Importante**:
- Reemplaza `sk-PEGA_TU_CLAVE_AQUI` con tu clave de OpenAI real
- **Nunca** subas `.env` al repositorio
- Si no tienes acceso a `gpt-5.4-nano`, reemplázalo por `gpt-4o-mini` o `gpt-3.5-turbo`

### ¿Dónde obtener tu clave?

1. Ve a https://platform.openai.com/account/api-keys
2. Haz clic en "Create new secret key"
3. Copia el valor (solo aparece una vez)
4. Pégalo en `.env`

---

## Paso 4: Importar Dataset a SQLite

El proyecto incluye un CSV real con 30,000 órdenes de e-commerce. Necesitas convertirlo a SQLite:

```bash
python data/import_dataset_to_sqlite.py
```

Esperado ver:
```
✓ Dataset validado
✓ BD creada: data/ecommerce_orders.db
✓ Tabla 'orders' importada: 30000 registros
✓ Índices creados
```

Este paso crea `data/ecommerce_orders.db` (archivo que NO sube al repo, es regenerable).

---

## Paso 5: Verificar el Entorno

Comprueba que todo está conectado correctamente:

```bash
python scripts/check_environment.py
```

Deberías ver algo como:
```
✓ Variables de entorno cargadas
✓ SQLite disponible: data/ecommerce_orders.db
✓ OpenAI API conectada
✓ Todos los módulos importados correctamente
```

Si hay errores, verifica:
- `.env` existe y tiene la clave correcta
- `data/ecommerce_orders.db` fue creado en paso anterior
- Python 3.11+

---

## Paso 6: Ejecutar el Sistema (3 Terminales Git Bash)

El sistema necesita **3 procesos ejecutándose simultáneamente**. Abre 3 ventanas de Git Bash.

### Terminal 1: MCP de Datos (Puerto 8000)

```bash
cd /c/python-dev/agent_mpc_memory/clase3_agente_mcp_memoria
source .venv/Scripts/activate
python mcp_datos.py
```

Esperado ver:
```
Iniciando servidor MCP de datos en http://0.0.0.0:8000/mcp
Herramientas registradas:
  - buscar_clientes
  - resumen_cliente
  - perfil_compras_cliente
  - experiencia_cliente
  - ventas_por_dimension
  - tendencia_ventas
  - detalle_orden
```

**Deja corriendo este terminal.**

### Terminal 2: MCP del Agente (Puerto 8001)

```bash
cd /c/python-dev/agent_mpc_memory/clase3_agente_mcp_memoria
source .venv/Scripts/activate
export MCP_AGENT_TRANSPORT=http
python mcp_agente.py
```

Esperado ver:
```
Iniciando servidor MCP del agente en http://0.0.0.0:8001/mcp
Conectando a MCP de datos en http://127.0.0.1:8000/mcp
Herramientas disponibles descubiertas: [7 tools]
✓ Servidor listo
```

**Deja corriendo este terminal.**

### Terminal 3: Cliente Streamlit

```bash
cd /c/python-dev/agent_mpc_memory/clase3_agente_mcp_memoria
source .venv/Scripts/activate
streamlit run app_streamlit.py
```

Streamlit debería abrir automáticamente en `http://localhost:8501` en tu navegador.

Si no se abre, copia y pega la URL manualmente en tu navegador.

---

## Paso 7: Usar la Interfaz

### En Streamlit

1. **Panel izquierdo**: 
   - Estado de sesión (session_id) – se genera automáticamente
   - Botón "Nueva sesión" para iniciar conversación nueva

2. **Chat principal**:
   - Escribe una pregunta natural
   - El agente busca tools, ejecuta queries SQL y responde

3. **Paneles informativos**:
   - "Memoria visible": últimos mensajes que el agente recuerda
   - "Traza de tools": qué herramientas usó y con qué argumentos
   - "Evidencia": datos reales recuperados

### Ejemplos de preguntas

```
"Busca clientes Premium en España"
"¿Cuál es el cliente con mayor gasto?"
"Análisis de devoluciones por país"
"Tendencia de ventas últimos 3 meses"
"Detalle de la orden 12345"
```

### Prueba de Memoria

1. Pregunta: "Busca clientes Premium"
2. Luego: "Analiza al de mayor consumo"
3. Observa que el agente entiende la referencia (memoria funciona)
4. Haz clic en "Nueva sesión"
5. Repite pregunta 2: sin memoria anterior, no entiende la referencia

---

## (Opcional) Paso 8: Integrar con Claude Desktop

Claude Desktop actúa como un **host externo** que puede consumir el agente sin crear interfaz propia.

### 8.1 Localizar carpeta de configuración

En **Windows**, Claude Desktop espera la config aquí:

```bash
# Desde Git Bash ($USERNAME en Windows, no $USER)
ls /c/Users/$USERNAME/AppData/Roaming/Claude/
```

Si no existe la carpeta `Claude`, créala:

```bash
mkdir -p /c/Users/$USERNAME/AppData/Roaming/Claude
```

### 8.2 Crear archivo de configuración

Copia el archivo ejemplo:

```bash
cp config/claude_desktop_config.example.json \
   /c/Users/$USERNAME/AppData/Roaming/Claude/claude_desktop_config.json
```

Abre el archivo copiado y **reemplaza `/RUTA_ABSOLUTA/` con tu ruta real**:

```json
{
  "mcpServers": {
    "agente-ecommerce": {
      "command": "python",
      "args": [
        "C:/python-dev/agent_mpc_memory/clase3_agente_mcp_memoria/mcp_agente.py"
      ],
      "env": {
        "OPENAI_API_KEY": "sk-TU_CLAVE",
        "OPENAI_MODEL": "gpt-5.4-nano",
        "DATA_MCP_URL": "http://127.0.0.1:8000/mcp",
        "MEMORY_WINDOW_MESSAGES": "8"
      }
    }
  }
}
```

### 8.3 Asegurarse de que el MCP de datos está corriendo

**Solo necesitas Terminal 1** (mcp_datos.py en puerto 8000). Claude Desktop usa transporte `stdio` y lanza `mcp_agente.py` por su cuenta como proceso hijo — **no debes iniciar Terminal 2 manualmente**.

> Para Claude Desktop solo necesitas: Terminal 1 activo + Claude Desktop arrancado.

### 8.4 Reiniciar Claude Desktop

1. Cierra Claude Desktop completamente
2. Reabre Claude Desktop
3. Claude Desktop detecta la config, lanza `mcp_agente.py` vía stdio y conecta con `mcp_datos.py` (HTTP)
4. El agente debería aparecer como herramienta disponible en la conversación

### Diferencia entre Streamlit y Claude Desktop

| Aspecto | Streamlit | Claude Desktop |
|---|---|---|
| Rol | Cliente creado por el equipo | Host MCP externo ya construido |
| Transporte | HTTP → `mcp_agente.py` como servicio | stdio → Claude inicia `mcp_agente.py` |
| Terminales necesarias | 3 (datos + agente + streamlit) | 1 (solo datos; agente lo maneja Claude) |
| Valor pedagógico | Hace visible el proceso interno | Demuestra interoperabilidad y reutilización |

---

## Arquitectura en Acción

```
Usuario escribe en Streamlit/Claude Desktop
         │
         ▼
┌─────────────────────────────────────────────┐
│      resolver_consulta_ecommerce()          │
│      (tool pública del MCP del agente)       │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
         ┌─────────────────────────────────────┐
         │      agent_core.py                  │
         │  • Recupera sesión (session_id)     │
         │  • Aplica ventana de memoria        │
         │  • Invoca LangChain/OpenAI          │
         │  • El modelo elige una tool         │
         └──────────────────┬──────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │      MCP de datos (mcp_datos.py)    │
         │  • buscar_clientes                  │
         │  • resumen_cliente                  │
         │  • ventas_por_dimension             │
         │  • ... (7 tools SQL parametrizadas) │
         └──────────────────┬──────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────┐
         │  SQLite: ecommerce_orders.db         │
         │  (30,000 órdenes, 8,683 clientes)   │
         └──────────────────────────────────────┘

Respuesta fluye hacia atrás:
Resultado → Agent Core → MCP Agente → Streamlit/Claude
```

---

## Seguridad: Riesgos y Controles

Conectar un modelo a herramientas externas concentra riesgos en nuevas interfaces. MCP **no reemplaza** autenticación, autorización, auditoría ni control de costos.

| Riesgo | Control aplicado en el laboratorio |
|---|---|
| SQL arbitrario | No existe tool genérica de SQL; queries explícitas y parametrizadas |
| Datos inventados | Instrucción de sistema: toda cifra factual debe venir de una tool |
| Contexto excesivo | `MEMORY_WINDOW_MESSAGES` limita tokens enviados al modelo |
| Acciones sensibles | Todas las tools son de **solo lectura** |
| Pérdida de estado | `InMemorySaver` es transitorio por diseño; documentado como tal |
| Credenciales expuestas | `.env` fuera de control de versiones; `.gitignore` incluido |
| Prompt injection | Contenido externo tratado como datos, no como instrucciones |

> Un LLM **no debe ser la única barrera** antes de una operación sensible.

### Observabilidad mínima recomendada

Para debug y auditoría en producción, registra por request:

```
request_id | session_id | tool | argumentos | estado | duracion_ms | error | timestamp
```

---

## Solución de Problemas

### "Port 8000 already in use"

Otro proceso está usando puerto 8000. Elige un nuevo puerto:

```bash
# Terminal 1
python mcp_datos.py --port 8002
```

Y edita `.env` con `DATA_MCP_URL=http://127.0.0.1:8002/mcp`

### "OPENAI_API_KEY not found"

- Verifica que `.env` existe en la carpeta principal
- Verifica que contiene `OPENAI_API_KEY=sk-...` (sin comillas)
- Reinicia el terminal después de editar `.env`

### "No module named 'fastmcp'"

Asegúrate de que el entorno virtual está activado:

```bash
source .venv/Scripts/activate
pip list | grep fastmcp
```

Reinstala si es necesario:

```bash
pip install fastmcp langchain langchain-openai langgraph
```

### "SQLite database not found"

Ejecuta nuevamente:

```bash
python data/import_dataset_to_sqlite.py
```

### "The agent responds but refuses to use tools"

- Verifica que `DATA_MCP_URL` en `.env` es correcta
- Verifica que Terminal 1 (MCP de datos) sigue corriendo
- Verifica que Terminal 2 (MCP del agente) sigue corriendo
- Mira los logs en esos terminals

### El chat de Streamlit está lento

- Es normal en primeras llamadas (compilación LangChain)
- Puede ser latencia de OpenAI API
- Verifica que tienes suficiente saldo en tu cuenta OpenAI

---

## Flujo de Mensajes (Entendimiento Profundo)

### ¿Qué sucede cuando escribo "Busca clientes Premium en España"?

1. **Streamlit captura el mensaje**
   - `app_streamlit.py` invoca `resolver_consulta_ecommerce(mensaje, session_id, "streamlit")`

2. **MCP del agente recibe la llamada**
   - `mcp_agente.py` delega a `agent_core.py`

3. **Agent Core recupera contexto**
   - Busca `session_id` en memoria
   - Aplica ventana de memoria (últimos 8 mensajes)
   - Arma contexto: `instrucciones + mensaje_inicial + memoria_reciente + tu_pregunta`

4. **LangChain invoca OpenAI**
   - OpenAI analiza contexto y disponibles tools
   - OpenAI elige: "Necesito `buscar_clientes` con `segmento='Premium'` y `pais='España'`"
   - **El LLM NO escribe SQL; solo selecciona tool y parámetros**

5. **MCP de datos ejecuta consulta segura**
   - `buscar_clientes` valida parámetros
   - Ejecuta: `SELECT * FROM orders WHERE Customer_Segment='Premium' AND Country='España' ...`
   - Devuelve resultados (cero SQL libre, cero inyección)

6. **Agente sintetiza respuesta**
   - Recibe datos, redacta respuesta clara
   - Guarda en memoria: tu pregunta + respuesta + tools usadas

7. **Streamlit muestra resultado**
   - Chat: tu pregunta y la respuesta
   - Traza: "buscar_clientes" + parámetros + 45 registros
   - Memoria visible: últimos 8 mensajes para próximo turno

---

## Variables de Entorno Explicadas

| Variable | Valor ejemplo | Qué es |
|---|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` | Tu credencial (nunca commits) |
| `OPENAI_MODEL` | `gpt-5.4-nano` | Modelo (o `gpt-4o-mini`) |
| `DATA_MCP_URL` | `http://127.0.0.1:8000/mcp` | Dónde está MCP datos |
| `AGENT_MCP_URL` | `http://127.0.0.1:8001/mcp` | Dónde está MCP agente |
| `MEMORY_WINDOW_MESSAGES` | `8` | Últimos N mensajes en memoria |
| `MCP_AGENT_TRANSPORT` | `http` o `stdio` | Protocolo (http para Streamlit, stdio para Claude) |

---

## Próximos Pasos

1. **Explora el código**:
   - `mcp_datos.py`: cómo se define una tool MCP
   - `agent_core.py`: cómo se orchestan modelo + tools + memoria
   - `mcp_agente.py`: cómo se empaqueta como MCP
   - `app_streamlit.py`: cómo un cliente consume el MCP

2. **Experimenta**:
   - Modifica prompts del sistema en `agent_core.py`
   - Agrega nuevas tools en `mcp_datos.py`
   - Cambia el modelo en `.env`

3. **Asegura**:
   - Revisa los controles de seguridad (sin SQL libre, validación de parámetros)
   - Entiende la traza para debugging

4. **Integra en producción**:
   - Reemplaza SQLite con PostgreSQL/MySQL
   - Agrega logging estructurado
   - Implementa persistencia de memoria en BD
   - Agrega autenticación y RBAC
   - Containeriza con Docker

---

## Recorrido Didáctico Recomendado

Usa el proyecto como secuencia de descubrimiento, no solo como demostración final.

| Momento | Actividad | Aprendizaje |
|---|---|---|
| 1. Recuperar el notebook | Ejecutar una consulta aislada contra las tools SQL | El LLM necesita capacidades externas para datos reales |
| 2. Separar archivos | Revisar `mcp_datos.py`, `agent_core.py`, `mcp_agente.py` | La arquitectura separa datos, decisión e interfaz |
| 3. Probar memoria | Dos turnos dependientes; cambiar `session_id` | La memoria es estado gestionado por la aplicación |
| 4. Abrir Streamlit | Revisar chat, traza y memoria visible | Un frontend puede ser cliente sin contener la inteligencia |
| 5. Abrir Claude Desktop | Consumir la misma tool desde un host externo | MCP permite interoperabilidad y reutilización |
| 6. Diseñar extensión | Proponer Telegram, Slack o API REST como nuevo cliente | La nueva integración no debe duplicar el agente |

### Preguntas de discusión

- ¿Qué parte del sistema cambia si se reemplaza Streamlit por Telegram?
- ¿Qué parte debe permanecer idéntica al agregar un nuevo cliente MCP?
- ¿Cuándo una tool de bajo nivel debería convertirse en capacidad de alto nivel?
- ¿Qué datos son aceptables en memoria temporal y cuáles deben persistir de forma controlada?
- ¿Cómo se agrega una tool de escritura sin permitir acciones irreversibles sin supervisión?

---

## Glosario

| Término | Definición aplicada al proyecto |
|---|---|
| Agente | Componente que coordina modelo, herramientas, reglas y estado para resolver una tarea |
| Checkpointer | Mecanismo que guarda el estado de conversación asociado a una sesión |
| Context window | Parte de la conversación e instrucciones que se envía al modelo en una llamada |
| FastMCP | Biblioteca Python para declarar y ejecutar servidores MCP de forma simple |
| Host MCP | Aplicación que gestiona el modelo y crea conexiones hacia uno o varios servidores MCP |
| LLM | Modelo de lenguaje grande; en el laboratorio se usa mediante `ChatOpenAI` |
| MCP | Protocolo para publicar y consumir capacidades externas mediante un contrato estándar |
| Memoria de corto plazo | Estado conversacional temporal para interpretar turnos recientes dentro de un `session_id` |
| session_id | Identificador estable que vincula los mensajes de una misma conversación |
| Tool | Función con contrato explícito que ejecuta una capacidad externa o de negocio |
| Trazabilidad | Registro de qué acciones se ejecutaron, con qué argumentos y qué resultados produjeron |

---

## Referencias

- Documentación completa: [docs/PROGRESION_COLAB_A_PYTHON.md](docs/PROGRESION_COLAB_A_PYTHON.md)
- Referencias oficiales: [docs/REFERENCIAS_OFICIALES.md](docs/REFERENCIAS_OFICIALES.md)
- MCP — especificación: https://modelcontextprotocol.io/
- MCP — arquitectura cliente-servidor: https://modelcontextprotocol.io/specification/2025-11-25/architecture/index
- MCP — tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- LangChain — memoria de corto plazo: https://docs.langchain.com/oss/python/langchain/short-term-memory
- LangChain — integración OpenAI: https://python.langchain.com/docs/integrations/chat/openai/
- Streamlit — chat elements: https://docs.streamlit.io/develop/api-reference/chat
- Streamlit — Session State: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- OpenAI — modelos: https://platform.openai.com/docs/models

---

**¡Listo para ejecutar!** Sigue los 7 pasos en Git Bash y tendrás un agente de IA conversacional con acceso a datos reales, empaquetado como MCP y consumible desde múltiples clientes.
