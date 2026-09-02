from playwright.sync_api import sync_playwright
import json
import datetime
import re

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
        # --- SOLUCIÓN PANTALLA COMPLETA ---
        # 1. Lanzamos Chromium maximizado
        browser = p.chromium.launch(headless=True)
        # 2. Desactivamos el tamaño por defecto (viewport) para que ocupe todo el monitor
        context = browser.new_context(no_viewport=True)
        # 3. Creamos la página en ese contexto amplio
        page = context.new_page()

        try:
            # 1. Búsqueda principal
            query_url = producto_buscar.replace(" ", "+")
            url_busqueda = f"https://www.infotec.com.pe/busqueda?controller=search&search_query={query_url}"
            page.goto(url_busqueda, timeout=10000)

            page.wait_for_selector('#js-product-list', timeout=5000)

            # 2. Capturamos URLs de los primeros 3 productos de la grilla
            links_productos = []
            tarjetas = page.locator('article.js-product-miniature').all()
            for tarjeta in tarjetas:
                try:
                    # En la grilla, el link suele estar en la imagen (thumbnail) o en el título
                    enlace = tarjeta.locator('a.thumbnail, .product-title a').first.get_attribute('href', timeout=2000)
                    if enlace:
                        links_productos.append(enlace)
                except:
                    continue

            # 3. Visitar cada página de detalle
            for url_detalle in links_productos:
                try:
                    print(f"Visitando detalle: {url_detalle}")
                    page.goto(url_detalle, timeout=15000)

                    # --- Extracción ajustada al HTML real ---

                    # TÍTULO: Exactamente como está en el HTML (h1.h1.page-title)
                    titulo = page.locator('h1.h1.page-title span').first.inner_text(timeout=3000)

                    # PRECIO: Exactamente como está en el HTML (.current-price-value)
                    precio_texto = page.locator('.current-price-value').first.inner_text(timeout=2000)
                    precios = re.findall(r'[\d,]+(?:\.\d+)?', precio_texto)
                    precio_float = float(precios[0].replace(',', '')) if precios else 0.0

                    # STOCK: Buscamos el botón COMPRAR (.add-to-cart)
                    tiene_stock = page.locator('button.add-to-cart').first.is_visible(timeout=1000)

                    # IMAGEN PRINCIPAL: Exactamente como está en el HTML (.js-easyzoom-trigger)
                    try:
                        url_imagen = page.locator('a.js-easyzoom-trigger').first.get_attribute('href', timeout=1000)
                    except:
                        url_imagen = "No disponible"

                    # FICHA TÉCNICA: Extraemos TODO el bloque de descripción corta como texto plano
                    # El LLM (Gemini/OpenAI) es lo suficientemente inteligente para extraer de aquí "Procesador", "RAM", etc.
                    try:
                        bloque_descripcion = page.locator('.product-description-short, .rte-content.product-description').first.inner_text(timeout=2000)
                        # Limpiamos saltos de línea excesivos
                        ficha_tecnica = re.sub(r'\n+', ' | ', bloque_descripcion).strip()
                    except:
                        ficha_tecnica = "No se pudo extraer la descripción detallada"

                    respuesta["resultados"].append({
                        "producto_evaluado": titulo,
                        "precio_soles": precio_float,
                        "tiene_stock_inmediato": tiene_stock,
                        "url_producto": url_detalle,
                        "url_imagen": url_imagen,
                        "especificaciones_crudas": ficha_tecnica # Enviamos el texto crudo a la IA
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
    print("Iniciando Escaneo Detallado en Pantalla Completa...")
    producto = "impresoras epson" 
    resultado_json = consultar_infotec_con_detalle(producto)
    print("\n--- REPORTE JSON PARA LA IA ---")
    print(resultado_json)