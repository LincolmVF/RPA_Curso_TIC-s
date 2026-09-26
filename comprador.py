from playwright.sync_api import sync_playwright
import datetime
import os
import re
import json
import ssl
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from dotenv import load_dotenv

# Carga las variables definidas en el archivo .env (debe estar junto a este archivo)
load_dotenv()

# ----------------------------------------------------------------------
# CONFIGURACIÓN DE CORREO (Brevo - SMTP Relay)
# ----------------------------------------------------------------------
# Por seguridad, NUNCA pongas tu clave SMTP directo aquí en el código.
# Estas variables se leen del entorno (env vars) del sistema.
#
# En PowerShell, antes de correr uvicorn, ejecuta:
#   $env:BREVO_SMTP_LOGIN="tu-login-de-brevo@smtp-brevo.com"   (el que aparece en SMTP & API)
#   $env:BREVO_SMTP_KEY="xxxxxxxxxxxxxxxxxxxxxxxx"             (tu clave SMTP generada en Brevo)
#
# Consigues ambos en: app.brevo.com -> Settings -> SMTP & API
# El remitente (FROM) debe ser un sender ya verificado en Brevo
# (Settings -> Senders, domains, IPs), en tu caso: lincolmvf@gmail.com
# ----------------------------------------------------------------------
CORREO_DESTINO = "lincolmvf@gmail.com"
CORREO_ORIGEN = "lincolmvf@gmail.com"          # Debe ser tu sender verificado en Brevo
BREVO_LOGIN = os.environ.get("BREVO_SMTP_LOGIN")
BREVO_KEY = os.environ.get("BREVO_SMTP_KEY")


# ----------------------------------------------------------------------
# NUEVO: manejo del popup flotante de Mailchimp ("mcforms-wrapper")
# ----------------------------------------------------------------------
# Ojo: el "aria-label='Close'" es solo la (X) de la tarjeta visible del
# popup. El elemento que realmente intercepta los clics es su overlay/
# wrapper (id tipo "mcforms-585347-796576"), que puede aparecer con
# retraso y a veces sobrevive aunque la tarjeta visible ya no esté.
# Por eso, en vez de depender de encontrar y clickear el botón de cerrar,
# lo eliminamos directamente del DOM por fuerza bruta.
def quitar_widgets_flotantes(page):
    """Elimina del DOM cualquier overlay conocido de Mailchimp que intercepte clics."""
    try:
        page.evaluate("""
            () => {
                const selectores = [
                    '.mcforms-wrapper',
                    '[id^="mcforms-"]',
                    '[id^="mc_embed"]',
                    '[class*="mcforms"]'
                ];
                selectores.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
            }
        """)
    except Exception:
        pass


def click_seguro(page, locator, timeout=15000, intentos=4, espera_ms=600):
    """
    Hace clic en 'locator'. Si algo lo tapa (típicamente el overlay de
    Mailchimp) y Playwright lanza Timeout, elimina los widgets flotantes
    conocidos y reintenta, en vez de fallar de una sola vez.
    """
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            locator.click(timeout=timeout)
            return
        except Exception as e:
            ultimo_error = e
            print(f"[!] Clic bloqueado (intento {intento}/{intentos}), limpiando overlays y reintentando...")
            quitar_widgets_flotantes(page)
            page.wait_for_timeout(espera_ms)
    # Si tras todos los intentos sigue fallando, propagamos el último error
    raise ultimo_error


# ----------------------------------------------------------------------
# NUEVO: lectura de precio regular / % de descuento desde el resumen
# del carrito (checkout), para enriquecer cada producto ya capturado.
# ----------------------------------------------------------------------
def enriquecer_con_descuentos(page, productos):
    """
    Recorre el resumen de compra en #js-checkout-summary y, para cada
    producto que ya capturamos desde el modal de 'Agregar al carrito',
    le agrega (si existen) el precio regular y el porcentaje de descuento
    leídos de:
        .product-price            -> precio actual
        .product-discount .regular-price        -> precio tachado
        .product-discount .discount-percentage  -> "(-30%)"
    """
    try:
        filas = page.locator("#js-checkout-summary .cart-summary-product-list li.media").all()
    except Exception:
        return productos

    for fila in filas:
        try:
            nombre_fila = fila.locator(".product-name").first.inner_text(timeout=3000).strip()
        except Exception:
            continue

        # Ubicamos a qué producto de nuestra lista corresponde esta fila
        item = next(
            (p for p in productos if p["nombre"].strip().lower() == nombre_fila.strip().lower()),
            None
        )
        if item is None:
            continue

        # Referencia (SKU) — informativo, no crítico si falla
        try:
            item["referencia"] = fila.locator(".product-reference").first.inner_text(timeout=1500).strip()
        except Exception:
            item["referencia"] = None

        # Precio regular (tachado), solo existe si el producto tiene descuento
        try:
            precio_regular_texto = fila.locator(".regular-price").first.inner_text(timeout=1500)
            precio_regular_match = re.findall(r'[\d,]+(?:\.\d+)?', precio_regular_texto)
            item["precio_regular"] = float(precio_regular_match[0].replace(',', '')) if precio_regular_match else None
        except Exception:
            item["precio_regular"] = None

        # Porcentaje de descuento, ej. "(-30%)" -> "-30%"
        try:
            descuento_texto = fila.locator(".discount-percentage").first.inner_text(timeout=1500)
            descuento_match = re.findall(r'-?\d+', descuento_texto)
            item["descuento_pct"] = f"{descuento_match[0]}%" if descuento_match else None
        except Exception:
            item["descuento_pct"] = None

    return productos


def enviar_correo_compra(resumen, ruta_captura=None):
    """Envía el correo de 'compra realizada' con el resumen del pedido, vía Brevo."""
    if not BREVO_LOGIN or not BREVO_KEY:
        print("[!] Faltan BREVO_SMTP_LOGIN / BREVO_SMTP_KEY en variables de entorno. No se envió el correo.")
        return False

    # msg (mixed) contiene: [alt (texto+html)] + [imagen adjunta]
    msg = MIMEMultipart("mixed")
    msg["From"] = CORREO_ORIGEN
    msg["To"] = CORREO_DESTINO
    prefijo_asunto = "Compra Realizada" if not (resumen.get("productos_omitidos") or []) else "Compra Realizada Parcialmente"
    msg["Subject"] = f"{prefijo_asunto} (Simulación RPA) - {resumen['timestamp_consulta']}"

    alternativo = MIMEMultipart("alternative")
    msg.attach(alternativo)

    # ---------- Versión texto plano (respaldo para clientes de correo viejos) ----------
    cuerpo_texto = "Se ha simulado la siguiente compra mediante el RPA:\n\n"
    ahorro_total = 0.0
    for item in resumen["productos"]:
        cuerpo_texto += f"- {item['nombre']}\n"
        if item.get("referencia"):
            cuerpo_texto += f"  Ref: {item['referencia']}\n"
        cuerpo_texto += f"  Cantidad: {item['cantidad']} | Precio unitario: S/. {item['precio']}\n"
        if item.get("precio_regular") and item.get("descuento_pct"):
            ahorro_unitario = item["precio_regular"] - item["precio"]
            ahorro_total += ahorro_unitario * item["cantidad"]
            cuerpo_texto += (
                f"  Precio regular: S/. {item['precio_regular']:.2f} "
                f"| Descuento: {item['descuento_pct']} "
                f"| Ahorro: S/. {ahorro_unitario * item['cantidad']:.2f}\n"
            )
        cuerpo_texto += f"  URL: {item['url']}\n\n"
    cuerpo_texto += f"TOTAL DEL PEDIDO: S/. {resumen['total']}\n"
    if ahorro_total > 0:
        cuerpo_texto += f"AHORRO TOTAL POR DESCUENTOS: S/. {ahorro_total:.2f}\n"

    omitidos_texto = resumen.get("productos_omitidos") or []
    if omitidos_texto:
        cuerpo_texto += f"\n⚠ {len(omitidos_texto)} producto(s) NO se pudieron agregar al pedido:\n"
        for om in omitidos_texto:
            cuerpo_texto += f"- {om['url']}\n  Motivo: {om['motivo']}\n"

    cuerpo_texto += "\nEste correo fue generado automáticamente por el RPA de simulación de compras.\n"
    cuerpo_texto += "No representa un pago real; el proceso se detuvo antes de iniciar sesión y pagar.\n"
    alternativo.attach(MIMEText(cuerpo_texto, "plain"))

    # ---------- Versión HTML (comprobante de compra) ----------
    filas_productos = ""
    ahorro_total = 0.0
    for item in resumen["productos"]:
        subtotal = item["precio"] * item["cantidad"]

        # Bloque de precio: si hay descuento, mostramos precio regular tachado + badge
        if item.get("precio_regular") and item.get("descuento_pct"):
            ahorro_unitario = (item["precio_regular"] - item["precio"]) * item["cantidad"]
            ahorro_total += ahorro_unitario
            bloque_precio = f"""
              <div style="line-height:1.3;">
                <span style="text-decoration:line-through;color:#999999;font-size:12px;">S/. {item['precio_regular']:.2f}</span>
                <span style="display:inline-block;margin-left:6px;background-color:#e8f5e9;color:#0f9d58;
                             font-size:11px;font-weight:bold;padding:2px 6px;border-radius:4px;">
                  {item['descuento_pct']}
                </span><br>
                <span>S/. {item['precio']:.2f}</span>
              </div>"""
        else:
            bloque_precio = f"S/. {item['precio']:.2f}"

        referencia_html = (
            f'<br><span style="color:#999999;font-size:11px;">Ref: {item["referencia"]}</span>'
            if item.get("referencia") else ""
        )

        filas_productos += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;">
            <a href="{item['url']}" style="color:#1a1a1a;text-decoration:none;font-weight:600;">{item['nombre']}</a>
            {referencia_html}
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:center;">{item['cantidad']}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:right;">{bloque_precio}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:right;font-weight:600;">S/. {subtotal:.2f}</td>
        </tr>"""

    fila_ahorro_html = ""
    if ahorro_total > 0:
        fila_ahorro_html = f"""
                  <tr>
                    <td style="text-align:right;padding-top:4px;font-size:13px;color:#0f9d58;">
                      Ahorro total por descuentos:&nbsp;&nbsp;S/. {ahorro_total:.2f}
                    </td>
                  </tr>"""

    # ---------- Bloque de productos omitidos (si los hay) ----------
    bloque_omitidos_html = ""
    omitidos = resumen.get("productos_omitidos") or []
    if omitidos:
        filas_omitidos = "".join(
            f"""
              <li style="margin-bottom:6px;">
                <a href="{om['url']}" style="color:#8a6d3b;text-decoration:none;">{om['url']}</a><br>
                <span style="color:#8a6d3b;font-size:11px;">{om['motivo']}</span>
              </li>"""
            for om in omitidos
        )
        bloque_omitidos_html = f"""
            <tr>
              <td style="background-color:#fdecea;padding:16px 32px;border-top:1px solid #f5c6cb;">
                <p style="margin:0 0 8px 0;color:#a94442;font-size:13px;font-weight:bold;">
                  ⚠ {len(omitidos)} producto(s) no se pudieron agregar al pedido:
                </p>
                <ul style="margin:0;padding-left:18px;">{filas_omitidos}</ul>
              </td>
            </tr>"""

    cuerpo_html = f"""\
<html>
  <body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0"
                 style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);">

            <tr>
              <td style="background-color:{'#0f9d58' if not omitidos else '#e8971e'};padding:24px 32px;">
                <span style="color:#ffffff;font-size:20px;font-weight:bold;">
                  {'✔ Compra Realizada' if not omitidos else '⚠ Compra Realizada Parcialmente'}
                </span>
              </td>
            </tr>

            <tr>
              <td style="padding:24px 32px 8px 32px;">
                <p style="margin:0 0 4px 0;color:#333333;font-size:14px;">
                  Hemos registrado tu pedido correctamente. A continuación el detalle:
                </p>
                <p style="margin:0;color:#999999;font-size:12px;">
                  Fecha: {resumen['timestamp_consulta']}
                </p>
              </td>
            </tr>

            <tr>
              <td style="padding:16px 32px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                  <tr style="background-color:#fafafa;">
                    <th style="padding:10px 8px;text-align:left;font-size:12px;color:#666666;text-transform:uppercase;">Producto</th>
                    <th style="padding:10px 8px;text-align:center;font-size:12px;color:#666666;text-transform:uppercase;">Cant.</th>
                    <th style="padding:10px 8px;text-align:right;font-size:12px;color:#666666;text-transform:uppercase;">Precio</th>
                    <th style="padding:10px 8px;text-align:right;font-size:12px;color:#666666;text-transform:uppercase;">Subtotal</th>
                  </tr>
                  {filas_productos}
                </table>
              </td>
            </tr>

            <tr>
              <td style="padding:8px 32px 24px 32px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                  {fila_ahorro_html}
                  <tr>
                    <td style="text-align:right;padding-top:12px;font-size:16px;color:#1a1a1a;">
                      <strong>Total del pedido:&nbsp;&nbsp;S/. {resumen['total']:.2f}</strong>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            {bloque_omitidos_html}

            <tr>
              <td style="background-color:#fff8e1;padding:16px 32px;border-top:1px solid #f0e6c8;">
                <p style="margin:0;color:#8a6d3b;font-size:12px;line-height:1.5;">
                  ⚠️ Este correo fue generado automáticamente por el RPA de simulación de compras.
                  No representa un pago real: el proceso se detuvo antes de iniciar sesión y pagar
                  en la tienda.
                </p>
              </td>
            </tr>

            <tr>
              <td style="padding:16px 32px;background-color:#1a1a1a;">
                <p style="margin:0;color:#aaaaaa;font-size:11px;text-align:center;">
                  RPA_Curso_TIC-s &middot; Simulador de compras Infotec
                </p>
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
    alternativo.attach(MIMEText(cuerpo_html, "html"))

    if ruta_captura and os.path.exists(ruta_captura):
        with open(ruta_captura, "rb") as f:
            img = MIMEImage(f.read())
            img.add_header("Content-Disposition", "attachment", filename=os.path.basename(ruta_captura))
            msg.attach(img)

    try:
        with smtplib.SMTP_SSL("smtp-relay.sendinblue.com", 465, context=ssl.create_default_context()) as server:
            server.login(BREVO_LOGIN, BREVO_KEY)
            server.sendmail(CORREO_ORIGEN, CORREO_DESTINO, msg.as_string())
        print("[*] Correo de confirmación enviado correctamente (vía Brevo).")
        return True
    except Exception as e:
        print(f"[!] Error enviando correo: {e}")
        return False


def esperar_boton_habilitado(page, boton, intentos=6, espera_ms=500):
    """
    Da un pequeño margen antes de rendirnos con un botón deshabilitado:
    algunas tiendas lo habilitan vía JS recién después de verificar stock
    o de que se auto-seleccione una variante por defecto.
    Devuelve True si en algún momento queda visible y habilitado.
    """
    for _ in range(intentos):
        try:
            if boton.is_visible() and not boton.is_disabled():
                return True
        except Exception:
            pass
        page.wait_for_timeout(espera_ms)
    return False


def simular_compra(urls_productos):
    """
    Recibe una lista de URLs de producto (mismo formato que 'url_producto'
    en bot.py). Agrega cada uno al carrito de forma independiente: si un
    producto no se puede agregar (sin stock, requiere elegir una variante,
    error de la página, etc.) se omite y se registra el motivo, mientras
    el resto de la orden continúa. Al finalizar, si se logró agregar al
    menos un producto, se avanza al checkout para leer el total real
    calculado por la tienda y el detalle de descuentos.
    NO inicia sesión ni completa el pago real.
    """
    respuesta = {
        "rpa_worker": "Infotec_Peru_SimuladorCompra",
        "timestamp_consulta": datetime.datetime.now().isoformat(),
        "productos_solicitados": urls_productos,
        "productos": [],
        "productos_omitidos": [],
        "total": 0.0,
        "estado_ejecucion": "ERROR",
        "mensaje_error": None,
        "correo_enviado": False,
        "captura": None
    }

    if not urls_productos:
        respuesta["mensaje_error"] = "No se envió ninguna URL de producto."
        return json.dumps(respuesta, indent=2, ensure_ascii=False)

    carpeta_captura = os.path.join("ejecuciones", datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(carpeta_captura, exist_ok=True)
    ruta_captura = os.path.join(carpeta_captura, "checkout.png")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        # ------------------------------------------------------------
        # 1. Agregar cada producto al carrito, de forma independiente
        # ------------------------------------------------------------
        for i, url in enumerate(urls_productos):
            print(f"[*] Abriendo producto {i + 1}/{len(urls_productos)}: {url}")
            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(1000)     # deja que el popup termine de aparecer si va a hacerlo
                quitar_widgets_flotantes(page)  # elimina el overlay de Mailchimp por si ya cargó

                # ":visible" evita que .first agarre un botón oculto de un
                # carrusel de "productos relacionados" que también tiene
                # class="add-to-cart" pero no es el botón principal.
                boton_comprar = page.locator("button.add-to-cart:visible").first

                # Si el botón sigue deshabilitado tras esperar un poco, no
                # insistimos: es una condición real del producto (sin stock
                # o requiere seleccionar una variante), no un bug del bot.
                if not esperar_boton_habilitado(page, boton_comprar):
                    # Intentamos leer el motivo real desde el badge de
                    # disponibilidad de la tienda (ej. "Fuera de stock"),
                    # y si no existe, dejamos un motivo genérico.
                    try:
                        motivo_tienda = page.locator("#product-availability").first.inner_text(timeout=2000).strip()
                    except Exception:
                        motivo_tienda = None

                    motivo = motivo_tienda if motivo_tienda else \
                        "Botón de compra deshabilitado (sin stock disponible o requiere seleccionar una variante)."
                    print(f"  [!] Producto omitido: {motivo}")
                    respuesta["productos_omitidos"].append({"url": url, "motivo": motivo})
                    continue

                click_seguro(page, boton_comprar, timeout=15000)

                # Esperar el modal de confirmación
                page.wait_for_selector("#blockcart-modal", timeout=15000)

                nombre = page.locator("#blockcart-modal .product-name").first.inner_text(timeout=10000)
                cantidad_texto = page.locator("#blockcart-modal .text-muted").first.inner_text(timeout=5000)
                # El precio es el ÚLTIMO span dentro de .col-info (no el 2do, ese es "1 x")
                precio_texto = page.locator("#blockcart-modal .col-info span").last.inner_text(timeout=5000)

                cantidad_match = re.findall(r'\d+', cantidad_texto)
                cantidad = int(cantidad_match[0]) if cantidad_match else 1

                precio_match = re.findall(r'[\d,]+(?:\.\d+)?', precio_texto)
                precio = float(precio_match[0].replace(',', '')) if precio_match else 0.0

                respuesta["productos"].append({
                    "nombre": nombre.strip(),
                    "cantidad": cantidad,
                    "precio": precio,
                    "url": url,
                    "referencia": None,        # se completa en el checkout
                    "precio_regular": None,    # se completa en el checkout, si hay descuento
                    "descuento_pct": None      # se completa en el checkout, si hay descuento
                })

                # Cerrar el modal para poder seguir navegando al siguiente producto
                boton_continuar = page.locator(
                    "button:has-text('CONTINUAR COMPRANDO'), a:has-text('CONTINUAR COMPRANDO')"
                ).first
                click_seguro(page, boton_continuar, timeout=15000)
                page.wait_for_timeout(500)

            except Exception as ex_producto:
                motivo = f"Error al agregar al carrito: {ex_producto}"
                print(f"  [!] Producto omitido: {motivo}")
                respuesta["productos_omitidos"].append({"url": url, "motivo": motivo})
                continue

        # ------------------------------------------------------------
        # 2. Si se logró agregar al menos un producto, ir al checkout
        #    a leer el total real y el detalle de descuentos.
        # ------------------------------------------------------------
        if respuesta["productos"]:
            try:
                # OJO: NO hacemos click en "PAGAR" porque un widget flotante
                # (mcforms-wrapper) suele taparlo e interceptar el click.
                # En vez de eso, leemos su href y navegamos directo.
                enlace_pagar = page.locator("a:has-text('PAGAR')").first
                href_pagar = enlace_pagar.get_attribute("href", timeout=10000)

                if href_pagar.startswith("//"):
                    url_checkout = "https:" + href_pagar
                elif href_pagar.startswith("/"):
                    url_checkout = "https://infotec.com.pe" + href_pagar
                else:
                    url_checkout = href_pagar

                page.goto(url_checkout, timeout=30000)
                page.wait_for_timeout(1000)
                quitar_widgets_flotantes(page)  # también puede aparecer aquí
                page.wait_for_selector(".cart-summary-totals", timeout=30000)

                # Completamos precio regular / % descuento por producto
                respuesta["productos"] = enriquecer_con_descuentos(page, respuesta["productos"])

                total_texto = page.locator(".cart-summary-line.cart-total .value").first.inner_text(timeout=10000)
                total_match = re.findall(r'[\d,]+(?:\.\d+)?', total_texto)
                respuesta["total"] = float(total_match[0].replace(',', '')) if total_match else 0.0

                # Captura de pantalla del resumen final (evidencia)
                page.screenshot(path=ruta_captura, full_page=True)
                respuesta["captura"] = ruta_captura

                print(f"[*] Total calculado por la tienda: S/. {respuesta['total']}")

                # EXITO si se agregó todo lo solicitado; EXITO_PARCIAL si
                # se omitió alguno pero al menos uno llegó al checkout.
                if respuesta["productos_omitidos"]:
                    respuesta["estado_ejecucion"] = "EXITO_PARCIAL"
                else:
                    respuesta["estado_ejecucion"] = "EXITO"

            except Exception as e:
                respuesta["mensaje_error"] = f"Error llegando al checkout: {str(e)}"
                print(f"[!] Error en checkout: {e}")
        else:
            respuesta["mensaje_error"] = "No se pudo agregar ningún producto al carrito."

        browser.close()

    # 3. Si hubo al menos éxito parcial, enviar el correo de confirmación
    if respuesta["estado_ejecucion"] in ("EXITO", "EXITO_PARCIAL"):
        respuesta["correo_enviado"] = enviar_correo_compra(respuesta, ruta_captura=respuesta.get("captura"))

    return json.dumps(respuesta, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        urls = sys.argv[1:]
    else:
        # URL de ejemplo por si lo corres sin argumentos
        urls = ["https://infotec.com.pe/tinta/16373-tinta-epson-t504420-yellow-c13t03n42a.html"]

    print(f"Simulando compra de {len(urls)} producto(s)...")
    resultado = simular_compra(urls)

    print("\n--- REPORTE JSON DE LA COMPRA SIMULADA ---")
    print(resultado)