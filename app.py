

from flask import Flask, render_template, request, redirect, url_for, flash
import smtplib
from email.message import EmailMessage
import os

app = Flask(__name__)

# La secret_key es necesaria para poder usar mensajes flash (los avisos
# tipo "¡Gracias por escribirnos!"). En producción esto NUNCA debe ir
# escrito directo en el código: se debe leer de una variable de entorno.
app.secret_key = os.environ.get("SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")


# -----------------------------------------------------------------------
# CONFIGURACIÓN DE CORREO
# -----------------------------------------------------------------------

# Variables de entorno configuradas en Render
GMAIL_REMITENTE = os.getenv("GMAIL_REMITENTE")
GMAIL_CONTRASENA = os.getenv("GMAIL_CONTRASENA")
CORREO_DESTINO = os.getenv("CORREO_DESTINO")
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# Servidor SMTP de Gmail
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587

# Comprobación de configuración
print("REMITENTE:", GMAIL_REMITENTE)
print("DESTINO:", CORREO_DESTINO)
print("PASSWORD EXISTE:", GMAIL_CONTRASENA is not None)
print("BREVO API KEY EXISTE:", BREVO_API_KEY is not None)

def enviar_correo(nombre: str, correo_remitente: str, mensaje: str) -> bool:
    """
    Envía el mensaje del formulario de contacto.
    """

    if not GMAIL_REMITENTE or not GMAIL_CONTRASENA or not CORREO_DESTINO:
        print("[AVISO] Variables de correo no configuradas en Render.")
        print("Verifica GMAIL_REMITENTE, GMAIL_CONTRASENA y CORREO_DESTINO.")
        print(
            f"[SIMULACIÓN DE ENVÍO] "
            f"De: {nombre} <{correo_remitente}> -> {CORREO_DESTINO}"
        )
        print(f"Mensaje: {mensaje}")
        return False

    email = EmailMessage()

    email["Subject"] = f"Nuevo mensaje de contacto - {nombre}"
    email["From"] = GMAIL_REMITENTE
    email["To"] = CORREO_DESTINO
    email["Reply-To"] = correo_remitente

    email.set_content(
        f"Nombre: {nombre}\n"
        f"Correo: {correo_remitente}\n\n"
        f"Mensaje:\n{mensaje}"
    )

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as servidor:
            servidor.starttls()
            servidor.login(GMAIL_REMITENTE, GMAIL_CONTRASENA)
            servidor.send_message(email)

        print("[OK] Correo enviado correctamente.")
        return True

    except Exception as error:
        print(f"[ERROR AL ENVIAR CORREO] {error}")
        return False



# -----------------------------------------------------------------------
# RUTAS
# -----------------------------------------------------------------------

@app.route("/")
def inicio():
    """Página principal: hero + sobre nosotros + formulario de contacto."""
    return render_template("index.html")


@app.route("/contacto", methods=["POST"])
def contacto():
    """Recibe el formulario de contacto y lo envía a CONTACT_EMAIL."""
    nombre = request.form.get("nombre", "").strip()
    correo = request.form.get("correo", "").strip()
    mensaje = request.form.get("mensaje", "").strip()

    if not nombre or not correo:
        flash("Por favor completa al menos tu nombre y tu correo.", "error")
        return redirect(url_for("inicio", _anchor="contacto"))

    enviar_correo(nombre, correo, mensaje)

    # Independiente de si el correo se envió o no (por ejemplo en modo
    # desarrollo sin credenciales), le mostramos al usuario que su
    # mensaje fue recibido.
    flash("¡Gracias! Recibimos tu mensaje y te contactaremos pronto.", "success")
    return redirect(url_for("inicio", _anchor="contacto"))


@app.route("/login")
def login():
    """
    Pantalla de inicio de sesión.
    Por ahora es solo una vista (placeholder): aquí es donde un
    desarrollador junior conectaría más adelante una base de datos
    de usuarios y un sistema real de autenticación.
    """
    return render_template("login.html")


@app.route("/soporte")
def soporte():
    """Página informativa de soporte / ayuda."""
    return render_template("soporte.html")


if __name__ == "__main__":
    app.run(debug=True)
