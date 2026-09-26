import ssl
import socket

HOST = "smtp-relay.brevo.com"
PORT = 465

# Desactivamos la verificación SOLO para poder leer el certificado
# que está siendo entregado (sea el real o uno falso interceptado).
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

with socket.create_connection((HOST, PORT), timeout=10) as sock:
    with ctx.wrap_socket(sock, server_hostname=HOST) as ssock:
        der_cert = ssock.getpeercert(binary_form=True)
        pem_cert = ssl.DER_cert_to_PEM_cert(der_cert)

with open("cert_debug.pem", "w") as f:
    f.write(pem_cert)

print("Certificado guardado en cert_debug.pem")
print("Ahora corre en la misma terminal:")
print("   certutil -dump cert_debug.pem")