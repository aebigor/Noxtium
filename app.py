"""
NOXTIUM - Sitio web institucional
==================================
Aplicación Flask muy sencilla, pensada para que cualquier desarrollador
junior pueda seguir editándola sin complicaciones.

Estructura del proyecto:
    app.py                -> este archivo. Rutas y lógica del servidor.
    templates/             -> archivos .html (Jinja2)
        base.html          -> esqueleto común (navbar, footer, head)
        index.html          -> página de inicio (hero + sobre nosotros + contacto)
        login.html          -> pantalla de "Iniciar sesión" (placeholder)
        soporte.html        -> página de soporte
    static/
        css/style.css      -> todos los estilos del sitio
        js/main.js         -> pequeñas interacciones (menú móvil, scroll suave, formulario)
        img/                -> aquí van logos e imágenes

Cómo correrlo localmente:
    1. python -m venv venv && source venv/bin/activate   (Windows: venv\\Scripts\\activate)
    2. pip install -r requirements.txt
    3. python app.py
    4. Abrir http://127.0.0.1:5000
"""

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
# Correo al que van a llegar los mensajes del formulario de contacto.
CONTACT_EMAIL = "santicris162@gmail.com"

# Estas credenciales son las de la cuenta que ENVÍA el correo (no tienen
# que ser las de santicris162@gmail.com). Se recomienda usar una cuenta
# de Gmail con una "contraseña de aplicación" y guardarlas como variables
# de entorno, nunca escritas directamente aquí.
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 587


def enviar_correo(nombre: str, correo_remitente: str, mensaje: str) -> bool:
    """
    Envía el mensaje del formulario de contacto a CONTACT_EMAIL.

    Si no hay credenciales configuradas (MAIL_USERNAME / MAIL_PASSWORD),
    la función no falla: simplemente no envía el correo y devuelve False.
    Esto permite que el sitio funcione en desarrollo aunque todavía no
    se haya configurado el correo real.
    """
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[AVISO] Credenciales de correo no configuradas. "
              "Revisa las variables de entorno MAIL_USERNAME y MAIL_PASSWORD.")
        print(f"[SIMULACIÓN DE ENVÍO] De: {nombre} <{correo_remitente}> -> {CONTACT_EMAIL}")
        print(f"Mensaje: {mensaje}")
        return False

    email = EmailMessage()
    email["Subject"] = f"Nuevo mensaje de contacto - {nombre}"
    email["From"] = MAIL_USERNAME
    email["To"] = CONTACT_EMAIL
    email["Reply-To"] = correo_remitente
    email.set_content(
        f"Nombre: {nombre}\n"
        f"Correo: {correo_remitente}\n\n"
        f"Mensaje:\n{mensaje}"
    )

    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as servidor:
            servidor.starttls()
            servidor.login(MAIL_USERNAME, MAIL_PASSWORD)
            servidor.send_message(email)
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
