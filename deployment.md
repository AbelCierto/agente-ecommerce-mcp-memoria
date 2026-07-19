# Deployment Guide (Resumen)

Este archivo resume el despliegue actual del proyecto con Redis y apunta a la guia detallada.

## Referencia completa

- Guia completa: [streamlit_deploy.md](streamlit_deploy.md)

## Arquitectura desplegada

- Frontend (UI): Streamlit Community Cloud
- Backend agente MCP: Railway
- Backend datos MCP: Railway
- Memoria persistente: Redis en Railway (conectado al agente)

## URLs de referencia

- Frontend: https://abelcierto-agente-ecommerce-mcp-memoria.streamlit.app/
- Agente: https://agentempcabelcierto.up.railway.app/mcp
- Datos: https://datampcurlabelcierto.up.railway.app/mcp

## Variables minimas del agente en Railway

- OPENAI_API_KEY
- OPENAI_MODEL
- DATA_MCP_URL
- MCP_AGENT_TRANSPORT=http
- MEMORY_WINDOW_MESSAGES=8
- REDIS_URL (Variable Reference al servicio Redis)

## Nota local

Para desarrollo local con persistencia, iniciar Redis via Docker antes de levantar los MCPs.
