# 1. Usamos la imagen oficial de Playwright para Python
#    (ya trae Chromium + dependencias del sistema necesarias para el scraping headless)
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# 2. Definimos la carpeta de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiamos primero SOLO requirements.txt e instalamos dependencias.
#    Esto aprovecha el cache de capas de Docker: si no cambias requirements.txt,
#    no se reinstalan las librerías en cada build, solo cuando cambia tu código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos el resto del código al contenedor (bot.py, api.py, comprador.py, etc.)
#    OJO: el .env NO debería llegar aquí — ver nota de .dockerignore más abajo.
COPY . .

# 5. Abrimos el puerto 3001 para que el Backend pueda comunicarse con este bot
EXPOSE 3001

# 6. Comando que enciende el servidor API y lo deja escuchando 24/7
ENTRYPOINT ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "3001"]