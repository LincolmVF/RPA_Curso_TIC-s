# 1. Usamos la imagen oficial de Playwright
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# 2. Definimos la carpeta de trabajo
WORKDIR /app

# 3. Copiamos los requerimientos y los instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos TODOS tus archivos al contenedor (bot.py y api.py)
COPY . .

# 5. Abrimos el puerto 8000 para que tu Backend pueda comunicarse con este bot
EXPOSE 8000

# 6. Comando OBLIGATORIO que enciende el servidor API y lo deja escuchando 24/7
ENTRYPOINT ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]