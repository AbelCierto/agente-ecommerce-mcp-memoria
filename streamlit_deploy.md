# Despliegue en Streamlit Community Cloud

## Arquitectura en la nube

El proyecto tiene **3 procesos** que localmente corren en terminales separadas. En la nube hay que tomar una decisión arquitectónica:

```
┌─────────────────────────────────────────────────────────────────┐
│  LOCAL (3 terminales)         NUBE (opciones)                   │
│                                                                 │
│  Terminal 1: mcp_datos.py  ─► Servicio backend (Railway/Render) │
│  Terminal 2: mcp_agente.py ─► Servicio backend (Railway/Render) │
│  Terminal 3: streamlit     ─► Streamlit Community Cloud         │
└─────────────────────────────────────────────────────────────────┘
```

**Opción A — Recomendada para esta clase**: desplegar solo Streamlit en la nube y los MCPs en un VPS o servidor externo.

**Opción B — Producción real**: desplegar los 3 servicios en Railway/Render como servicios separados.

**Opción C — Todo en uno**: empaquetar los 3 procesos en un solo contenedor Docker.

---

## Prerrequisitos

- Cuenta en [GitHub](https://github.com) (repositorio público o privado)
- Cuenta en [Streamlit Community Cloud](https://share.streamlit.io) (gratis)
- Los servidores `mcp_datos.py` y `mcp_agente.py` accesibles por URL pública

---

## Paso 1: Preparar el repositorio

### 1.1 Verificar `.gitignore`

El `.gitignore` ya debe excluir estos archivos sensibles:

```
.env
data/ecommerce_orders.db
.venv/
__pycache__/
```

Verifica desde Git Bash:

```bash
cat .gitignore
```

### 1.2 Crear archivo de secretos para Streamlit Cloud

Streamlit Cloud NO usa `.env`. Los secretos van en `secrets.toml` **solo para desarrollo local** en `.streamlit/secrets.toml` (no subir al repo), o en el panel web de Streamlit Cloud.

Crea la carpeta de configuración de Streamlit:

```bash
mkdir -p .streamlit
```

Crea `.streamlit/secrets.toml` (agrégalo al `.gitignore`):

```toml
# .streamlit/secrets.toml — NO subir al repositorio
OPENAI_API_KEY = "sk-proj-tu_clave_aqui"
OPENAI_MODEL = "gpt-5.4-nano"
AGENT_MCP_URL = "https://tu-mcp-agente.railway.app/mcp"
```

Agrega al `.gitignore`:

```bash
echo ".streamlit/secrets.toml" >> .gitignore
```

### 1.3 Adaptar `app_streamlit.py` para leer secretos de Streamlit

Streamlit Cloud expone los secretos como `st.secrets`. Actualiza la lectura de variables en `app_streamlit.py`:

En la línea donde se lee `AGENT_MCP_URL`, asegúrate de que el código soporte ambos orígenes:

```python
# Lee desde st.secrets (Streamlit Cloud) o desde .env (local)
AGENT_MCP_URL = (
    st.secrets.get("AGENT_MCP_URL")
    if hasattr(st, "secrets") and "AGENT_MCP_URL" in st.secrets
    else os.getenv("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")
)
```

### 1.4 Subir al repositorio

```bash
git init                        # si aún no es un repo git
git add .
git commit -m "feat: agente ecommerce MCP con memoria"
git remote add origin https://github.com/TU_USUARIO/nombre-repo.git
git push -u origin main
```

---

## Paso 2: Desplegar los backends MCP (Railway)

Los servicios `mcp_datos.py` y `mcp_agente.py` necesitan estar en un servidor con URL pública para que Streamlit Cloud pueda conectarse.

### 2.1 Crear cuenta en Railway

1. Ve a https://railway.app
2. Regístrate con GitHub
3. Plan Starter: $5 créditos gratis al mes (suficiente para una demo)

### 2.2 Servicio 1 — MCP de datos

Desde el dashboard de Railway:

1. **New Project** → **Deploy from GitHub repo**
2. Selecciona tu repositorio
3. En **Settings → Start Command**:
   ```
   python mcp_datos.py
   ```
4. En **Variables** agrega:
   ```
   PORT=8000
   ```
5. En **Networking → Expose port**: `8000`
6. Copia la URL pública que genera Railway: `https://xxxxx.railway.app`

### 2.3 Servicio 2 — MCP del agente

1. **New Service** en el mismo proyecto
2. Mismo repositorio, rama `main`
3. **Start Command**:
   ```
   MCP_AGENT_TRANSPORT=http python mcp_agente.py
   ```
4. **Variables**:
   ```
   OPENAI_API_KEY=sk-proj-tu_clave
   OPENAI_MODEL=gpt-5.4-nano
   DATA_MCP_URL=https://xxxxx-mcp-datos.railway.app/mcp
   MEMORY_WINDOW_MESSAGES=8
   PORT=8001
   ```
5. **Networking → Expose port**: `8001`
6. Copia la URL: `https://yyyyy-mcp-agente.railway.app`

> **Nota sobre el dataset**: Railway no incluye `ecommerce_orders.db` porque está en `.gitignore`. Opciones:
> - Agregar un **start command** que ejecute `python data/import_dataset_to_sqlite.py` antes de iniciar
> - O subir solo el CSV al repo y regenerar la BD en el arranque

### 2.4 Verificar los backends

Desde el navegador o curl, verifica que los servicios responden:

```bash
curl https://xxxxx-mcp-datos.railway.app/mcp
curl https://yyyyy-mcp-agente.railway.app/mcp
```

Deben responder con el descriptor MCP del servidor.

---

## Paso 3: Desplegar Streamlit Community Cloud

### 3.1 Conectar el repositorio

1. Ve a https://share.streamlit.io
2. **New app**
3. Selecciona tu repositorio y rama `main`
4. **Main file path**: `app_streamlit.py`
5. Clic en **Deploy**

### 3.2 Configurar secretos en Streamlit Cloud

En el panel de tu app desplegada:

1. Clic en el ícono ⚙️ (Settings)
2. Sección **Secrets**
3. Pega el contenido:

```toml
OPENAI_API_KEY = "sk-proj-tu_clave"
OPENAI_MODEL = "gpt-5.4-nano"
AGENT_MCP_URL = "https://yyyyy-mcp-agente.railway.app/mcp"
```

4. **Save** → la app se reinicia automáticamente

### 3.3 URL pública

Streamlit Community Cloud asigna una URL del tipo:

```
https://tu-usuario-nombre-repo-app-streamlit-xxxx.streamlit.app
```

---

## Paso 4 (Alternativo): Todo en un solo proceso

Si no quieres pagar Railway, puedes modificar `app_streamlit.py` para que levante los MCPs internamente al arrancar. Esto es útil para demos rápidas pero **no es buena práctica para producción**.

Agrega al inicio de `app_streamlit.py`:

```python
import subprocess
import threading
import time

def _start_services():
    """Lanza mcp_datos y mcp_agente en subprocesos."""
    subprocess.Popen(["python", "mcp_datos.py"])
    time.sleep(2)  # espera a que mcp_datos levante
    subprocess.Popen(
        ["python", "mcp_agente.py"],
        env={**os.environ, "MCP_AGENT_TRANSPORT": "http"}
    )

# Solo lanzar una vez (Streamlit re-ejecuta el script en cada interacción)
if "services_started" not in st.session_state:
    threading.Thread(target=_start_services, daemon=True).start()
    st.session_state.services_started = True
    time.sleep(3)  # espera inicial para que los servicios levanten
```

> ⚠️ **Limitación**: Streamlit Community Cloud tiene límite de RAM (~1 GB). Los 3 procesos más el modelo pueden superar ese límite. Usar solo para demos.

---

## Variables de entorno por entorno

| Variable | Local (`.env`) | Streamlit Cloud (Secrets) | Railway (Variables) |
|---|---|---|---|
| `OPENAI_API_KEY` | `sk-proj-...` | `sk-proj-...` | `sk-proj-...` |
| `OPENAI_MODEL` | `gpt-5.4-nano` | `gpt-5.4-nano` | `gpt-5.4-nano` |
| `AGENT_MCP_URL` | `http://127.0.0.1:8001/mcp` | `https://agente.railway.app/mcp` | — |
| `DATA_MCP_URL` | `http://127.0.0.1:8000/mcp` | — | `https://datos.railway.app/mcp` |
| `MEMORY_WINDOW_MESSAGES` | `8` | `8` | `8` |
| `MCP_AGENT_TRANSPORT` | `http` (export manual) | — | `http` |

---

## Consideraciones para producción

### Base de datos
`InMemorySaver` se reinicia con cada redeploy. Para persistencia real:
- Reemplazar por `SqliteSaver` o `PostgresSaver` de LangGraph
- Railway ofrece PostgreSQL como servicio adicional

### Seguridad
- Nunca subir `.env` ni `secrets.toml` al repositorio
- Rotar la API key si fue expuesta accidentalmente
- Agregar autenticación a los endpoints MCP si son públicos

### Costos estimados
| Servicio | Costo |
|---|---|
| Streamlit Community Cloud | Gratis |
| Railway Starter | $5 créditos/mes (suele alcanzar para una demo) |
| OpenAI API (`gpt-5.4-nano`) | ~$0.001 por consulta |

---

## Checklist de despliegue

- [ ] `.gitignore` incluye `.env`, `*.db`, `.streamlit/secrets.toml`
- [ ] `app_streamlit.py` lee secretos desde `st.secrets` o `os.getenv`
- [ ] Repositorio subido a GitHub
- [ ] `mcp_datos.py` desplegado y accesible por URL pública
- [ ] `mcp_agente.py` desplegado con `DATA_MCP_URL` apuntando al servicio de datos
- [ ] Secretos configurados en Streamlit Cloud
- [ ] App desplegada y probada con preguntas reales

---

## Referencias

- Streamlit Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud
- Streamlit Secrets: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management
- Railway docs: https://docs.railway.app
- FastMCP deployment: https://gofastmcp.com/deployment/running-your-server
