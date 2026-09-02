# 1. Usamos la imagen oficial de Playwright (versión Python)
# Esto nos ahorra horas de instalar dependencias de Linux para los navegadores
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# 2. Definimos la carpeta de trabajo dentro del contenedor
WORKDIR /app

# 3. Copiamos el archivo de requerimientos y lo instalamos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos tu código fuente al contenedor (asumiendo que se llama bot.py)
COPY bot.py .

# 5. Comando que se ejecutará al iniciar el contenedor
CMD ["python", "bot.py"]