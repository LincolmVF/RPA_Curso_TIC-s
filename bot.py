from playwright.sync_api import sync_playwright
import json
import datetime
import re
import sys # <-- NUEVO: Para recibir argumentos desde la terminal/backend
import requests # <-- NUEVO: Para enviar el JSON a tu backend en el futuro

def consultar_infotec_con_detalle(producto_buscar):
    respuesta = {
        "rpa_worker": "Infotec_Peru_Detalle",
        "timestamp_consulta": datetime.datetime.now().isoformat(),
        "busqueda_original": producto_buscar,
        "resultados": [],
        "estado_ejecucion": "ERROR",
        "mensaje_error": None
    }

    with sync_playwright() as p:
        # 1. Lanzamos Chromium de forma invisible (headless=True)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        try:
            # 1. Búsqueda principal
            query_url = producto_buscar.replace(" ", "+")
            url_busqueda = f"https://www.infotec.com.pe/busqueda?controller=search&search_query={query_url}"
            
            # --- CAMBIO 1: TIMEOUT AUMENTADO A 60 SEGUNDOS (60000 ms) ---
            page.goto(url_busqueda, timeout=60000)

            # --- CAMBIO 2: TIMEOUT AUMENTADO A 30 SEGUNDOS ---
            page.wait_for_selector('#js-product-list', timeout=30000)

            # 2. Capturamos URLs de los productos de la grilla (sin el límite de 3)
            links_productos = []
            tarjetas = page.locator('article.js-product-miniature').all()
            for tarjeta in tarjetas:
                try:
                    # También le subimos el tiempo aquí un poco por si la carga es lenta
                    enlace = tarjeta.locator('a.thumbnail, .product-title a').first.get_attribute('href', timeout=5000)
                    if enlace:
                        links_productos.append(enlace)
                except:
                    continue

            # 3. Visitar cada página de detalle
            for url_detalle in links_productos:
                try:
                    print(f"Visitando detalle: {url_detalle}")
                    
                    # --- CAMBIO 3: TIMEOUT AUMENTADO A 60 SEGUNDOS ---
                    page.goto(url_detalle, timeout=60000)

                    # TÍTULO
                    titulo = page.locator('h1.h1.page-title span').first.inner_text(timeout=10000)

                    # PRECIO
                    precio_texto = page.locator('.current-price-value').first.inner_text(timeout=10000)
                    precios = re.findall(r'[\d,]+(?:\.\d+)?', precio_texto)
                    precio_float = float(precios[0].replace(',', '')) if precios else 0.0

                    # STOCK
                    tiene_stock = page.locator('button.add-to-cart').first.is_visible(timeout=5000)

                    # IMAGEN PRINCIPAL
                    try:
                        url_imagen = page.locator('a.js-easyzoom-trigger').first.get_attribute('href', timeout=5000)
                    except:
                        url_imagen = "No disponible"

                    # FICHA TÉCNICA
                    try:
                        bloque_descripcion = page.locator('.product-description-short, .rte-content.product-description').first.inner_text(timeout=10000)
                        ficha_tecnica = re.sub(r'\n+', ' | ', bloque_descripcion).strip()
                    except:
                        ficha_tecnica = "No se pudo extraer la descripción detallada"

                    respuesta["resultados"].append({
                        "producto_evaluado": titulo,
                        "precio_soles": precio_float,
                        "tiene_stock_inmediato": tiene_stock,
                        "url_producto": url_detalle,
                        "url_imagen": url_imagen,
                        "especificaciones_crudas": ficha_tecnica
                    })
                    
                    page.wait_for_timeout(500)

                except Exception as ex_detalle:
                    print(f"  [!] Error en detalle: {ex_detalle}")
                    continue

            if len(respuesta["resultados"]) > 0:
                respuesta["estado_ejecucion"] = "EXITO"
            else:
                respuesta["mensaje_error"] = "No se extrajo info válida de ningún detalle."

        except Exception as e:
            respuesta["mensaje_error"] = f"Error general: {str(e)}"
            
        finally:
            browser.close()

    return json.dumps(respuesta, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # --- CAMBIO 4: PREPARANDO PARA EL BACKEND ---
    # sys.argv capta las palabras que le mandes al ejecutar el archivo
    # sys.argv[0] es "bot.py", sys.argv[1] será el producto.
    
    if len(sys.argv) > 1:
        # Si el backend le mandó un producto, usa ese:
        producto = sys.argv[1] 
    else:
        # Si no le mandaste nada, usa este por defecto para que no falle:
        producto = "impresoras epson" 

    print(f"Iniciando Escaneo Detallado de: '{producto}' ...")
    resultado_json = consultar_infotec_con_detalle(producto)
    
    print("\n--- REPORTE JSON PARA LA IA ---")
    print(resultado_json)

    # --- CAMBIO 5: EL FUTURO (COMENTADO POR AHORA) ---
    # Cuando tengas tu backend listo, descomentas esto y el bot le enviará 
    # la respuesta automáticamente sin necesidad de que nadie mire la consola.
    
    # url_de_tu_backend = "https://tupaginaweb.com/api/recibir-resultados"
    # try:
    #     requests.post(url_de_tu_backend, json=json.loads(resultado_json))
    # except Exception as error:
    #     print(f"No se pudo enviar al backend: {error}")