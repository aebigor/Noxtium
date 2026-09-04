# NOXTIUM — Sitio web institucional

Landing page en **Flask** con navbar, sección "sobre nosotros", arquitectura
de módulos y formulario de contacto que envía los mensajes a
`santicris162@gmail.com`.

## Estructura

```
noxtium_web/
├── app.py                 # rutas y lógica del servidor
├── requirements.txt
├── templates/
│   ├── base.html          # navbar + footer (se repite en todas las páginas)
│   ├── index.html         # inicio: hero, sobre nosotros, módulos, contacto
│   ├── login.html         # placeholder de inicio de sesión
│   └── soporte.html       # página de soporte
└── static/
    ├── css/style.css      # todos los estilos (variables de marca al inicio)
    ├── js/main.js         # menú móvil
    └── img/                # logos e imágenes que agregues
```

## Cómo correrlo

```bash
python -m venv venv
source venv/bin/activate      # En Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000`.

## Conectar el envío real de correos

El formulario de contacto ya está construido para enviar el mensaje a
`santicris162@gmail.com` usando `smtplib` (ver `enviar_correo()` en
`app.py`). Mientras no configures credenciales, el sitio sigue
funcionando: el mensaje solo se imprime en la consola en vez de enviarse.

Para activarlo de verdad, define estas variables de entorno antes de
correr `python app.py` (usa una cuenta de Gmail con una "contraseña de
aplicación", nunca tu contraseña normal):

```bash
export MAIL_USERNAME="tu_cuenta_envio@gmail.com"
export MAIL_PASSWORD="tu_contraseña_de_aplicacion"
```

## Próximos pasos sugeridos para un junior

- Reemplazar el isotipo SVG del navbar por el logo oficial en `static/img/`.
- Conectar `login.html` a un sistema real de usuarios (por ejemplo con `Flask-Login`).
- Guardar los mensajes del formulario en una base de datos, además de enviarlos por correo.
- Agregar imágenes reales del "Caso piloto: piqueteadero" en la sección de módulos.
