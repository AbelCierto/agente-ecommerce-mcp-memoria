"""
Cliente Streamlit del MCP del agente.

Esta aplicación NO contiene el LLM ni las consultas SQL.
Es un cliente que consume mcp_agente.py por HTTP y hace visible:
- el chat;
- la session_id;
- la memoria de corto plazo;
- las herramientas invocadas.
"""
from __future__ import annotations
import asyncio
import csv
import hmac
import io
import json
import os
import uuid
import streamlit as st
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

def get_config_value(name: str, default: str | None = None) -> str | None:
    # Prioriza secretos de Streamlit Cloud y luego variables locales de entorno.
    if hasattr(st, "secrets") and name in st.secrets:
        return str(st.secrets[name])
    return os.getenv(name, default)


AGENT_MCP_URL = get_config_value("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")
APP_LOGIN_USERNAME = get_config_value("APP_LOGIN_USERNAME")
APP_LOGIN_PASSWORD = get_config_value("APP_LOGIN_PASSWORD")
APP_LOGIN_ENABLED = str(
    get_config_value(
        "APP_LOGIN_ENABLED",
        "true" if APP_LOGIN_USERNAME and APP_LOGIN_PASSWORD else "false",
    )
).lower() in {"1", "true", "yes", "on"}
DEFAULT_ANALYSIS_MODE = str(get_config_value("DEFAULT_ANALYSIS_MODE", "operativo")).lower()
PDF_EXPORT_ENABLED = str(get_config_value("PDF_EXPORT_ENABLED", "true")).lower() in {
        "1",
        "true",
        "yes",
        "on",
}

st.set_page_config(page_title="E-commerce Agent MCP", page_icon="🛒", layout="wide")


st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Manrope:wght@400;600;700&display=swap');

:root {
    --bg-1: #f8fbff;
    --bg-2: #eef6ff;
    --ink: #1e293b;
    --ink-soft: #475569;
    --brand: #0f766e;
    --brand-2: #0ea5a4;
    --card: rgba(255, 255, 255, 0.92);
    --line: rgba(14, 116, 110, 0.18);
}

.stApp {
    background: radial-gradient(circle at 15% 10%, var(--bg-2) 0%, var(--bg-1) 45%, #ffffff 100%);
}

h1, h2, h3, h4 {
    font-family: 'Outfit', sans-serif !important;
    color: var(--ink);
}

p, label, .stMarkdown, .stCaption, .stText {
    font-family: 'Manrope', sans-serif !important;
    color: var(--ink-soft);
}

.hero-box {
    background: linear-gradient(120deg, rgba(15, 118, 110, 0.12), rgba(14, 165, 164, 0.12));
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 16px 18px;
    margin: 6px 0 16px 0;
}

.kpi-card {
    background: var(--card);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 14px;
    padding: 14px 16px;
    box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
}

.kpi-title {
    font-size: 0.85rem;
    color: #64748b;
    margin-bottom: 4px;
}

.kpi-value {
    font-size: 1.35rem;
    font-weight: 800;
    color: #0f172a;
}

.stChatInput {
    border-top: 1px solid rgba(148, 163, 184, 0.25);
}

@media (max-width: 900px) {
    .hero-box {
        padding: 12px 14px;
    }
    .kpi-value {
        font-size: 1.15rem;
    }
}
</style>
""",
        unsafe_allow_html=True,
)


def render_login_form() -> None:
    st.title("🔐 Iniciar sesión")
    st.markdown("### Bienvenido al trabajo final de Abel Cierto del curso: Estrategias de Integración")
    st.caption("Acceso privado al panel del agente e-commerce.")
    with st.form("login_form"):
        username = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")
        submitted = st.form_submit_button("Ingresar")

    if submitted:
        user_ok = hmac.compare_digest(username, APP_LOGIN_USERNAME or "")
        pass_ok = hmac.compare_digest(password, APP_LOGIN_PASSWORD or "")
        if user_ok and pass_ok:
            st.session_state.authenticated = True
            st.session_state.auth_user = username
            st.success("Acceso concedido")
            st.rerun()
        st.error("Usuario o contraseña inválidos")


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = ""

if APP_LOGIN_ENABLED:
    if not APP_LOGIN_USERNAME or not APP_LOGIN_PASSWORD:
        st.error(
            "Login activado pero faltan credenciales. Configura APP_LOGIN_USERNAME y APP_LOGIN_PASSWORD."
        )
        st.stop()
    if not st.session_state.authenticated:
        render_login_form()
        st.stop()

st.markdown(
    """
<div class="hero-box">
  <h1 style="margin:0;">🛒 Agente e-commerce: Centro de análisis MCP</h1>
  <p style="margin:6px 0 0 0;">Explora hallazgos, conversa con el agente y exporta análisis ejecutivos en un solo panel.</p>
</div>
""",
    unsafe_allow_html=True,
)

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "analysis_mode" not in st.session_state:
    st.session_state.analysis_mode = "ejecutivo" if DEFAULT_ANALYSIS_MODE == "ejecutivo" else "operativo"


def preparar_mensaje_usuario(mensaje: str) -> str:
    if st.session_state.analysis_mode == "ejecutivo":
        return (
            "Responde en modo ejecutivo: máximo 5 bullets, enfoque en impacto de negocio, "
            "cifras clave y recomendación accionable.\n\n"
            f"Consulta original: {mensaje}"
        )
    return mensaje


def contar_tool_calls(result: dict | None) -> int:
    if not result:
        return 0
    trace = result.get("traza", [])
    if not isinstance(trace, list):
        return 0
    return sum(1 for item in trace if isinstance(item, dict) and item.get("tipo") == "tool_call")


def export_csv_bytes(result: dict) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["campo", "valor"])
    writer.writerow(["session_id", result.get("session_id", "")])
    writer.writerow(["canal", result.get("canal", "")])
    writer.writerow(["modelo", result.get("modelo", "")])
    writer.writerow(["respuesta", result.get("respuesta", "")])
    writer.writerow(["memoria", json.dumps(result.get("memoria", {}), ensure_ascii=False)])
    writer.writerow(["traza", json.dumps(result.get("traza", []), ensure_ascii=False)])
    writer.writerow(["historial_visible", json.dumps(result.get("historial_visible", []), ensure_ascii=False)])
    return output.getvalue().encode("utf-8")


def export_pdf_bytes(result: dict) -> bytes | None:
    try:
        from fpdf import FPDF
    except Exception:
        return None

    def _safe_pdf_text(value: object) -> str:
        text = str(value)
        # fpdf core fonts no soportan unicode completo; degradamos de forma segura.
        text = text.encode("latin-1", errors="replace").decode("latin-1")
        # Evita tokens largos sin espacios que rompen el line-wrap.
        words = []
        for token in text.split(" "):
            if len(token) > 40:
                chunks = [token[i:i + 40] for i in range(0, len(token), 40)]
                words.append(" ".join(chunks))
            else:
                words.append(token)
        return " ".join(words)

    def _write_line(pdf: FPDF, text: str, h: int = 6) -> None:
        page_width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(page_width, h, _safe_pdf_text(text))

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    _write_line(pdf, "Reporte de analisis e-commerce", h=8)
    pdf.ln(1)
    pdf.set_font("Helvetica", size=11)
    _write_line(pdf, f"Session ID: {result.get('session_id', '')}")
    _write_line(pdf, f"Canal: {result.get('canal', '')}")
    _write_line(pdf, f"Modelo: {result.get('modelo', '')}")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    _write_line(pdf, "Respuesta", h=7)
    pdf.set_font("Helvetica", size=11)
    _write_line(pdf, str(result.get("respuesta", "")))
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    _write_line(pdf, "Memoria", h=7)
    pdf.set_font("Helvetica", size=10)
    _write_line(pdf, json.dumps(result.get("memoria", {}), ensure_ascii=False, indent=2), h=5)

    # output(dest='S') devuelve str en algunas versiones y bytes en otras.
    raw = pdf.output(dest="S")
    if isinstance(raw, bytes):
        return raw
    return raw.encode("latin-1", errors="ignore")

async def llamar_agente(mensaje: str) -> dict:
    client = MultiServerMCPClient(
        {"agente": {"transport": "http", "url": AGENT_MCP_URL}}
    )
    tools = await client.get_tools()
    tool_by_name = {tool.name: tool for tool in tools}
    tool = tool_by_name["resolver_consulta_ecommerce"]
    result = await tool.ainvoke({
        "mensaje": mensaje,
        "session_id": st.session_state.session_id,
        "canal": f"streamlit-{st.session_state.analysis_mode}",
    })
    # langchain_mcp_adapters puede devolver una lista de objetos de contenido MCP
    # en lugar del dict directamente. Normalizamos aquí.
    if isinstance(result, list):
        item = result[0]
        text = item.text if hasattr(item, "text") else item.get("text", str(item))
        return json.loads(text)
    if isinstance(result, str):
        return json.loads(result)
    return result

with st.sidebar:
    st.header("Sesión y memoria")
    if APP_LOGIN_ENABLED:
        st.success(f"Conectado como: {st.session_state.auth_user}")
        if st.button("Cerrar sesión"):
            st.session_state.authenticated = False
            st.session_state.auth_user = ""
            st.session_state.messages = []
            st.session_state.last_result = None
            st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
            st.rerun()
        st.divider()
    st.code(st.session_state.session_id)
    st.write("La misma `session_id` mantiene la conversación dentro del proceso del agente.")
    if st.button("Nueva conversación"):
        st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
        st.session_state.messages = []
        st.session_state.last_result = None
        st.rerun()
    st.divider()
    st.subheader("Modo de análisis")
    st.session_state.analysis_mode = st.radio(
        "Estilo de respuesta",
        options=["operativo", "ejecutivo"],
        index=1 if st.session_state.analysis_mode == "ejecutivo" else 0,
        horizontal=True,
    )
    st.caption("Ejecutivo resume hallazgos en formato corto y accionable.")
    st.divider()
    st.write("Servidor esperado:")
    st.code(AGENT_MCP_URL)


total_msgs = len(st.session_state.messages)
total_user_msgs = sum(1 for m in st.session_state.messages if m.get("role") == "user")
tool_calls = contar_tool_calls(st.session_state.last_result)
memory_type = "sin datos"
if st.session_state.last_result and isinstance(st.session_state.last_result.get("memoria"), dict):
    memory_type = st.session_state.last_result["memoria"].get("tipo", "sin datos")

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        f"<div class='kpi-card'><div class='kpi-title'>Mensajes en sesión</div><div class='kpi-value'>{total_msgs}</div></div>",
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        f"<div class='kpi-card'><div class='kpi-title'>Consultas de usuario</div><div class='kpi-value'>{total_user_msgs}</div></div>",
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        f"<div class='kpi-card'><div class='kpi-title'>Tools usadas (última)</div><div class='kpi-value'>{tool_calls}</div></div>",
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        f"<div class='kpi-card'><div class='kpi-title'>Tipo de memoria</div><div class='kpi-value'>{memory_type}</div></div>",
        unsafe_allow_html=True,
    )

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ej.: Busca clientes Premium y analiza al de mayor gasto.")
if prompt:
    prompt_to_agent = preparar_mensaje_usuario(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("El cliente MCP consulta al agente..."):
            try:
                result = asyncio.run(llamar_agente(prompt_to_agent))
                answer = result["respuesta"]
                st.markdown(answer)
                st.session_state.last_result = result
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as exc:
                st.error(f"No fue posible consultar el agente: {exc}")
                st.info(
                    "Verifica que estén activos mcp_datos.py (puerto 8000) "
                    "y mcp_agente.py en modo HTTP (puerto 8001)."
                )

if st.session_state.last_result:
    result = st.session_state.last_result
    st.divider()
    st.subheader("Exportar análisis")
    csv_bytes = export_csv_bytes(result)
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        st.download_button(
            label="Descargar CSV",
            data=csv_bytes,
            file_name=f"analisis_{st.session_state.session_id}.csv",
            mime="text/csv",
        )
    with export_col2:
        if PDF_EXPORT_ENABLED:
            try:
                pdf_bytes = export_pdf_bytes(result)
                if pdf_bytes is not None:
                    st.download_button(
                        label="Descargar PDF",
                        data=pdf_bytes,
                        file_name=f"analisis_{st.session_state.session_id}.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.info("Instala fpdf2 para habilitar exportación PDF.")
            except Exception:
                st.warning(
                    "No se pudo generar el PDF con este contenido. "
                    "Puedes exportar CSV sin problema."
                )

    left, right = st.columns(2)
    with left:
        st.subheader("Memoria de corto plazo")
        st.json(result["memoria"])
        st.caption(
            "Al cambiar la sesión se parte con memoria vacía. "
            "Al reiniciar mcp_agente.py, todas las memorias en RAM se eliminan."
        )
    with right:
        st.subheader("Traza de orquestación")
        st.json(result["traza"])
