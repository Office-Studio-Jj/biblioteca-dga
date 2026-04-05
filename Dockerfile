FROM python:3.11-slim

# ── Dependencias del sistema para Chromium headless en Railway ────────────
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 libx11-6 \
    libx11-xcb1 libxcb1 libxext6 libxfixes3 libxi6 \
    fonts-liberation xdg-utils \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# ── Directorio de trabajo ─────────────────────────────────────────────────
WORKDIR /app

# ── Instalar dependencias Python ──────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Instalar Chromium vía patchright (NO Google Chrome) ───────────────────
RUN python -m patchright install chromium --with-deps

# ── Copiar código ─────────────────────────────────────────────────────────
COPY . .

# ── Variables de entorno de Railway ──────────────────────────────────────
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV DISPLAY=""
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# ── Crear directorios de datos y perfil del navegador ────────────────────
RUN mkdir -p /app/data \
 && mkdir -p /app/notebooklm_skill/data/browser_state/browser_profile \
 && chmod -R 777 /app/notebooklm_skill/data

# ── Exponer puerto ────────────────────────────────────────────────────────
EXPOSE 8080

# ── Arranque: 1 worker + 4 threads (permite admin y usuarios simultáneos) ──
# gthread worker: cada hilo atiende una petición independiente.
# subprocess.run() libera el GIL → consultas NotebookLM no bloquean a otros usuarios.
# 1 solo proceso → sin race conditions en los archivos JSON compartidos.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --timeout 1800 --workers 1 --worker-class gthread --threads 4 --preload server:app"]
