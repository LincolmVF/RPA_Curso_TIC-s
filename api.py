from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import json

# Importamos las funciones de nuestros dos bots
from bot import consultar_infotec_con_detalle
from comprador import simular_compra

# Creamos la aplicación API
app = FastAPI(title="API de RPA Infotec")


# Formato para el endpoint de búsqueda (ya existente)
class OrdenBusqueda(BaseModel):
    producto: str


# Formato para el endpoint de compra (NUEVO)
class OrdenCompra(BaseModel):
    productos: List[str]  # Array de URLs de producto


# ------------------------------------------------------------------
# Endpoint existente: buscar productos
# ------------------------------------------------------------------
@app.post("/api/buscar")
def buscar_producto(orden: OrdenBusqueda):
    print(f"[*] Orden recibida desde el Backend: Buscar '{orden.producto}'")

    try:
        resultado_string = consultar_infotec_con_detalle(orden.producto)
        resultado_json = json.loads(resultado_string)
        return resultado_json

    except Exception as e:
        print(f"[!] Error crítico en el bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Endpoint NUEVO: simular compra de uno o varios productos
# ------------------------------------------------------------------
@app.post("/api/comprar")
def comprar_producto(orden: OrdenCompra):
    print(f"[*] Orden de compra recibida desde el Backend: {orden.productos}")

    try:
        resultado_string = simular_compra(orden.productos)
        resultado_json = json.loads(resultado_string)
        return resultado_json

    except Exception as e:
        print(f"[!] Error crítico en el bot de compra: {e}")
        raise HTTPException(status_code=500, detail=str(e))