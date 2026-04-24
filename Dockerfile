FROM python:3.11-slim

# ── Dependencias mínimas del sistema (sin Chromium — patchright eliminado) ─
RUN apt-get update && apt-get install -y \
    ca-certificates curl \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# ── Directorio de trabajo ─────────────────────────────────────────────────
WORKDIR /app

# ── Variables de entorno ANTES de instalar Chromium ──────────────────────
# CRÍTICO: PLAYWRIGHT_BROWSERS_PATH debe estar definido ANTES de
# "patchright install chromium" para que el binario quede en /ms-playwright.
# Si se define DESPUÉS, patchright instala en ~/.cache/ms-playwright y
# luego no lo encuentra al ejecutar consultas → "Executable doesn't exist".
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# ── Instalar dependencias Python ──────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copiar código ─────────────────────────────────────────────────────────
COPY . .

# ── Crear directorio de datos ─────────────────────────────────────────────
RUN mkdir -p /app/data && chmod -R 777 /app/notebooklm_skill/data

# ── Construir base de datos Capa 1 SQLite FTS5 (arancel_rd.db) ───────────
# Tarda ~2s. Genera lookup determinista de 7,616 codigos, 0% IA.
RUN python capa1_sqlite/build_arancel_db.py

# ── Indexar biblioteca-nomenclatura FTS5 (11 PDFs → ~23 chunks) ──────────
# Tarda ~25s. Permite RAG determinista en clasificador merceologico auto.
RUN python capa1_sqlite/build_biblioteca_fts.py

# ── Exponer puerto ────────────────────────────────────────────────────────
EXPOSE 8080

# ── Arranque: 1 worker + 4 threads (permite admin y usuarios simultáneos) ──
# gthread worker: cada hilo atiende una petición independiente.
# subprocess.run() libera el GIL → consultas NotebookLM no bloquean a otros usuarios.
# 1 solo proceso → sin race conditions en los archivos JSON compartidos.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 1800 --workers 1 --worker-class gthread --threads 4 --preload server:app"]
