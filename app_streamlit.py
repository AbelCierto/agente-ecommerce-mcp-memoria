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
import hmac
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

st.set_page_config(page_title="E-commerce Agent MCP", page_icon="🛒", layout="wide")


def render_login_form() -> None:
    st.title("🔐 Iniciar sesión")
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

st.title("🛒 Agente e-commerce: Streamlit como cliente MCP")
st.caption("La UI consume el MCP del agente; el agente consume el MCP de datos.")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None

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
        "canal": "streamlit",
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
    st.write("Servidor esperado:")
    st.code(AGENT_MCP_URL)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ej.: Busca clientes Premium y analiza al de mayor gasto.")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("El cliente MCP consulta al agente..."):
            try:
                result = asyncio.run(llamar_agente(prompt))
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
