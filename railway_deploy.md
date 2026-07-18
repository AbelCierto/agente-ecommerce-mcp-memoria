# Deployment en Railway: Servicios MCP

Guía paso a paso para desplegar **mcp_datos.py** y **mcp_agente.py** en Railway.

---

## Parte 0: Preparación local

### 0.1 Verificar que los servicios funcionan localmente

```bash
# Terminal 1: mcp_datos (puerto 8000)
python mcp_datos.py

# Terminal 2: mcp_agente (puerto 8001)
MCP_AGENT_TRANSPORT=http python mcp_agente.py

# Terminal 3: Streamlit (puerto 8501)
streamlit run app_streamlit.py
```

### 0.2 Crear/actualizar `.gitignore`

```
.venv/
__pycache__/
*.pyc
.env
.streamlit/secrets.toml
.DS_Store
*.db
```

### 0.3 Confirmar que `requirements.txt` está actualizado

```bash
pip freeze > requirements.txt
```

Asegurate que incluya:
```
fastmcp>=2.0.0
langchain>=1.0.0
langchain-openai>=1.0.0
langchain-mcp-adapters>=0.1.0
langgraph>=1.0.0
python-dotenv>=1.0.1
pandas>=2.0.0
sqlite3  # (viene con Python, pero mencionar)
```

---

## Parte 1: Crear cuenta en Railway

### 1.1 Ir a railway.app

https://railway.app

### 1.2 Sign up con GitHub

- Click "Login"
- Selecciona "GitHub"
- Autoriza Railway a acceder a tu GitHub
- Conecta tu repo del proyecto

### 1.3 Dashboard inicial

Una vez logueado, verás:
- Projects
- Services
- Deployments

---

## Parte 2: Desplegar mcp_datos (Servicio 1)

### 2.1 Crear nuevo proyecto

- Click **"New Project"** en dashboard
- Selecciona **"Deploy from GitHub"**
- Busca tu repo: `agent_mpc_memory` (o el nombre que uses)
- Click **"Connect Repo"**

### 2.2 Crear servicio 1: mcp_datos

Una vez conectado el repo:
- Click **"Add Service"** → **"GitHub Repo"**
- Selecciona el repo que conectaste
- Railway detectará `requirements.txt` y Python automáticamente
- Click **"Deploy"**

### 2.3 Configurar variables de entorno para mcp_datos

En Railway dashboard, dentro del servicio `mcp_datos`:

1. Click en la tarjeta del servicio
2. Ir a **"Variables"** tab
3. Agregar variables:

```
PORT=8000
MCP_DATOS_URL=http://localhost:8000/mcp
SQLITE_DB_PATH=data/ecommerce_orders.db
```

⚠️ **Nota importante**: Railway ejecuta cada comando Python desde la raíz del repo. Si necesitas que lea `data/ecommerce_orders.db`, asegurate que:
- El archivo existe en el repo (comitear a Git)
- O el script lo genera automáticamente (`import_dataset_to_sqlite.py` debe correr al inicio)

### 2.4 Configurar comando de ejecución

En **"Settings"** → **"Start Command"**:

```bash
python mcp_datos.py
```

### 2.5 Obtener URL pública

Una vez desplegado:
- En la tarjeta del servicio, verás una URL como: `https://xxxxxx-mcp-datos-prod.up.railway.app`
- **Copia esta URL** — la necesitarás para mcp_agente

Nota: Railway automáticamente expone el puerto en HTTPS.

---

## Parte 3: Desplegar mcp_agente (Servicio 2)

### 3.1 Crear segundo servicio

En el mismo proyecto:
- Click **"Add Service"** → **"GitHub Repo"**
- Selecciona el mismo repo
- Click **"Deploy"**

### 3.2 Configurar variables de entorno para mcp_agente

En Railway dashboard, servicio `mcp_agente`:

1. Click **"Variables"** tab
2. Agregar variables:

```
PORT=8001
MCP_AGENT_TRANSPORT=http
DATA_MCP_URL=https://xxxxxx-mcp-datos-prod.up.railway.app/mcp
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
```

**⚠️ CRÍTICO**: 
- `DATA_MCP_URL` debe apuntar a la URL **pública** de mcp_datos (la que obtuviste en 2.5)
- `OPENAI_API_KEY` debe ser tu API key de OpenAI (obtén en platform.openai.com)

### 3.3 Configurar comando de ejecución

En **"Settings"** → **"Start Command"**:

```bash
python mcp_agente.py
```

### 3.4 Obtener URL pública de mcp_agente

Una vez desplegado:
- URL será algo como: `https://yyyyyy-mcp-agente-prod.up.railway.app`
- **Copia esta URL** — la necesitarás para Streamlit

---

## Parte 4: Verificar conexión entre servicios

### 4.1 Test desde línea de comandos (local)

Una vez que ambos servicios estén desplegados en Railway, prueba que se comunican:

```bash
# Desde tu terminal local, con URLs de Railway:
curl "https://xxxxxx-mcp-datos-prod.up.railway.app/mcp" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

Deberías recibir una respuesta JSON con las herramientas disponibles.

### 4.2 Revisar logs en Railway

Si algo no funciona:
1. En Railroad dashboard, click en servicio
2. Ir a **"Logs"** tab
3. Ver errores en tiempo real

Errores comunes:
- `Connection refused` → mcp_datos no está corriendo
- `Timeout` → firewall o PORT no configurado
- `ModuleNotFoundError` → falta instalar dependencias en requirements.txt

### 4.3 Verificar que mcp_agente puede llamar a DATA_MCP_URL

En los logs de `mcp_agente`, deberías ver:
```
[INFO] Connecting to DATA_MCP_URL: https://xxxxxx-mcp-datos-prod.up.railway.app/mcp
[INFO] Tools discovered: [buscar_clientes, resumen_cliente, ...]
```

Si no ves esto, check:
- Variable `DATA_MCP_URL` está correcta en Railway
- URL de mcp_datos es accesible públicamente

---

## Parte 5: Integración con Streamlit Cloud

Una vez que mcp_agente está funcionando en Railway:

### 5.1 En tu Streamlit Cloud app (streamlit_deploy.md Paso 3):

Configurar secret:
```
AGENT_MCP_URL=https://yyyyyy-mcp-agente-prod.up.railway.app/mcp
```

### 5.2 Actualizar `app_streamlit.py` (verificar que use la variable correcta)

```python
import os

AGENT_MCP_URL = os.getenv("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")
```

---

## Parte 6: Estructura final en Railway

```
Railway Project
├─ Servicio 1: mcp_datos
│  ├─ GitHub Repo: https://github.com/tuusuario/repo
│  ├─ Start Command: python mcp_datos.py
│  ├─ PORT: 8000
│  ├─ URL Pública: https://xxxxxx-mcp-datos-prod.up.railway.app
│  └─ Logs: Watcheable en dashboard
│
└─ Servicio 2: mcp_agente
   ├─ GitHub Repo: https://github.com/tuusuario/repo
   ├─ Start Command: python mcp_agente.py
   ├─ PORT: 8001
   ├─ ENV: DATA_MCP_URL=https://xxxxxx-mcp-datos-prod.up.railway.app/mcp
   ├─ ENV: OPENAI_API_KEY=sk-xxxxx
   ├─ URL Pública: https://yyyyyy-mcp-agente-prod.up.railway.app
   └─ Logs: Watcheable en dashboard
```

---

## Parte 7: Costos y límites

| Servicio | Plan | Costo | Límite |
|---|---|---|---|
| **mcp_datos** | Starter | $5/mes | 100 GB bandwidth/mes |
| **mcp_agente** | Starter | $5/mes | 100 GB bandwidth/mes |
| **Streamlit Cloud** | Community | Gratis | 3 apps, 1 GB RAM |
| **Total** | — | ~$10/mes | Suficiente para producción pequeña |

---

## Troubleshooting

### "Service not responding"
- Revisar logs en Railway
- Verificar que `PORT` está configurado correctamente
- Comprobar que el comando de inicio es `python mcp_datos.py` (no `python -m mcp_datos`)

### "Cannot connect to DATA_MCP_URL"
- Verificar que la URL en `AGENT_MCP_URL` es correcta (incluir `/mcp` al final)
- Comprobar que mcp_datos está corriendo (logs verdes en Railway)
- Probar URL manualmente con `curl` desde terminal

### "ModuleNotFoundError: No module named 'fastmcp'"
- Correr `pip freeze > requirements.txt` localmente
- Comitear cambios a Git
- Railway redeploy automáticamente

### "OPENAI_API_KEY not found"
- Verificar que la variable está configurada en Railway dashboard
- Reiniciar el servicio (click "Redeploy")
- Comprobar que no hay espacios en blanco en la key

---

## Resumen: Deploy completo

```bash
# 1. Preparar localmente
git add .
git commit -m "Ready for Railway deployment"
git push origin main

# 2. En Railway dashboard:
# - Crear proyecto y conectar repo
# - Crear servicio mcp_datos
#   - Variables: PORT=8000
#   - Copiar URL pública
# - Crear servicio mcp_agente
#   - Variables: PORT=8001, DATA_MCP_URL=<URL de mcp_datos>, OPENAI_API_KEY=sk-...
#   - Copiar URL pública
# - Verificar logs

# 3. En Streamlit Cloud:
#   - Agregar secret: AGENT_MCP_URL=<URL de mcp_agente>/mcp
#   - Deploy o redeploy

# 4. Probar
#   - Abrir https://tu-usuario-agente-ecommerce.streamlit.app
#   - Chatear con el agente
#   - Ver logs en Railway si hay errores
```

---

**Siguiente paso**: [streamlit_deploy.md](streamlit_deploy.md) para desplegar el frontend.
