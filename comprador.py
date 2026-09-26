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


def enviar_correo_compra(resumen, ruta_captura=None):
    """Envía el correo de 'compra realizada' con el resumen del pedido, vía Brevo."""
    if not BREVO_LOGIN or not BREVO_KEY:
        print("[!] Faltan BREVO_SMTP_LOGIN / BREVO_SMTP_KEY en variables de entorno. No se envió el correo.")
        return False

    # msg (mixed) contiene: [alt (texto+html)] + [imagen adjunta]
    msg = MIMEMultipart("mixed")
    msg["From"] = CORREO_ORIGEN
    msg["To"] = CORREO_DESTINO
    msg["Subject"] = f"Compra Realizada (Simulación RPA) - {resumen['timestamp_consulta']}"

    alternativo = MIMEMultipart("alternative")
    msg.attach(alternativo)

    # ---------- Versión texto plano (respaldo para clientes de correo viejos) ----------
    cuerpo_texto = "Se ha simulado la siguiente compra mediante el RPA:\n\n"
    for item in resumen["productos"]:
        cuerpo_texto += f"- {item['nombre']}\n"
        cuerpo_texto += f"  Cantidad: {item['cantidad']} | Precio unitario: S/. {item['precio']}\n"
        cuerpo_texto += f"  URL: {item['url']}\n\n"
    cuerpo_texto += f"TOTAL DEL PEDIDO: S/. {resumen['total']}\n\n"
    cuerpo_texto += "Este correo fue generado automáticamente por el RPA de simulación de compras.\n"
    cuerpo_texto += "No representa un pago real; el proceso se detuvo antes de iniciar sesión y pagar.\n"
    alternativo.attach(MIMEText(cuerpo_texto, "plain"))

    # ---------- Versión HTML (comprobante de compra) ----------
    filas_productos = ""
    for item in resumen["productos"]:
        subtotal = item["precio"] * item["cantidad"]
        filas_productos += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;">
            <a href="{item['url']}" style="color:#1a1a1a;text-decoration:none;font-weight:600;">{item['nombre']}</a>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:center;">{item['cantidad']}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:right;">S/. {item['precio']:.2f}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #e5e5e5;text-align:right;font-weight:600;">S/. {subtotal:.2f}</td>
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
              <td style="background-color:#0f9d58;padding:24px 32px;">
                <span style="color:#ffffff;font-size:20px;font-weight:bold;">✔ Compra Realizada</span>
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
                  <tr>
                    <td style="text-align:right;padding-top:12px;font-size:16px;color:#1a1a1a;">
                      <strong>Total del pedido:&nbsp;&nbsp;S/. {resumen['total']:.2f}</strong>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

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


def simular_compra(urls_productos):
    """
    Recibe una lista de URLs de producto (mismo formato que 'url_producto'
    en bot.py). Agrega cada uno al carrito, y al llegar al último avanza
    al checkout para leer el total ya calculado por la tienda.
    NO inicia sesión ni completa el pago real.
    """
    respuesta = {
        "rpa_worker": "Infotec_Peru_SimuladorCompra",
        "timestamp_consulta": datetime.datetime.now().isoformat(),
        "productos_solicitados": urls_productos,
        "productos": [],
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

        try:
            for i, url in enumerate(urls_productos):
                es_ultimo = (i == len(urls_productos) - 1)

                print(f"[*] Abriendo producto {i + 1}/{len(urls_productos)}: {url}")
                page.goto(url, timeout=60000)

                # 1. Click en "COMPRAR" / agregar al carrito
                boton_comprar = page.locator("button.add-to-cart").first
                boton_comprar.click(timeout=15000)

                # 2. Esperar el modal de confirmación
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
                    "url": url
                })

                if es_ultimo:
                    # 3. Último producto: ir al checkout.
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
                    page.wait_for_selector(".cart-summary-totals", timeout=30000)

                    total_texto = page.locator(".cart-summary-line.cart-total .value").first.inner_text(timeout=10000)
                    total_match = re.findall(r'[\d,]+(?:\.\d+)?', total_texto)
                    respuesta["total"] = float(total_match[0].replace(',', '')) if total_match else 0.0

                    # Captura de pantalla del resumen final (evidencia)
                    page.screenshot(path=ruta_captura, full_page=True)
                    respuesta["captura"] = ruta_captura

                    print(f"[*] Total calculado por la tienda: S/. {respuesta['total']}")
                else:
                    # Cerrar modal y seguir con el siguiente producto
                    page.locator(
                        "button:has-text('CONTINUAR COMPRANDO'), a:has-text('CONTINUAR COMPRANDO')"
                    ).first.click(timeout=15000, force=True)
                    page.wait_for_timeout(500)

            respuesta["estado_ejecucion"] = "EXITO"

        except Exception as e:
            respuesta["mensaje_error"] = f"Error general: {str(e)}"
            print(f"[!] Error en simulación de compra: {e}")

        finally:
            browser.close()

    # 4. Si todo salió bien, enviar el correo de confirmación
    if respuesta["estado_ejecucion"] == "EXITO":
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