from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import json

# Importamos tu función de scraping desde tu archivo bot.py
from bot import consultar_infotec_con_detalle

# Creamos la aplicación API
app = FastAPI(title="API de RPA Infotec")

# Definimos el formato en el que el Backend debe enviar la orden
class OrdenBusqueda(BaseModel):
    producto: str

# Creamos la ruta (endpoint) que tu Backend va a llamar
@app.post("/api/buscar")
def buscar_producto(orden: OrdenBusqueda):
    print(f"[*] Orden recibida desde el Backend: Buscar '{orden.producto}'")
    
    try:
        # 1. Mandamos al bot a hacer el trabajo sucio
        resultado_string = consultar_infotec_con_detalle(orden.producto)
        
        # 2. Convertimos el texto a un JSON real para enviarlo por internet
        resultado_json = json.loads(resultado_string)
        
        # 3. Se lo devolvemos al Backend Web
        return resultado_json
        
    except Exception as e:
        print(f"[!] Error crítico en el bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))