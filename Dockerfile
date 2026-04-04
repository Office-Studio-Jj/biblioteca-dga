FROM python:3.11-slim

# Instalar Chrome y dependencias para Playwright/Patchright
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libatspi2.0-0 \
    fonts-liberation libappindicator3-1 xdg-utils \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar e instalar dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar navegador Chromium para patchright
RUN python -m patchright install chromium --with-deps

# Copiar código del servidor
COPY . .

# Copiar skills de notebooklm
COPY notebooklm_skill/ /app/notebooklm_skill/

# Variables de entorno
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Exponer puerto
EXPOSE 8080

# Arranque con gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT --timeout 1800 --workers 1 --threads 2 server:app
