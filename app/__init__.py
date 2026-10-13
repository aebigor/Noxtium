from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import Config
from .database import db
from .routes.meta import meta_bp
from .routes.webhooks import webhook_bp
from .routes.portal import portal_bp


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
        static_url_path="/static",
    )
    app.config.from_object(Config)
    db.init_app(app)

    app.register_blueprint(meta_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(portal_bp)

    @app.context_processor
    def inject_account_state():
        from app.routes.portal import current_user, active_subscription
        user = current_user()
        return {
            "current_account_user": user,
            "current_subscription": active_subscription(user.company_id) if user and user.role != "admin" else None,
            "current_is_admin": bool(user and user.role == "admin"),
        }

    @app.get("/")
    def inicio():
        from app.routes.portal import current_user
        user = current_user()
        if user and user.role == "admin":
            return redirect(url_for("portal.admin_dashboard"))
        return render_template("index.html")

    @app.get("/login")
    def login():
        if session.get("user_id"):
            return redirect(url_for("portal.dashboard"))
        return render_template("login.html")

    @app.get("/403")
    def forbidden_page():
        return render_template("403.html"), 403

    @app.get("/soporte")
    def soporte():
        return render_template("soporte.html")

    @app.post("/contacto")
    def contacto():
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip()
        mensaje = request.form.get("mensaje", "").strip()
        if not nombre or not correo:
            flash("Nombre y correo son obligatorios.", "error")
            return redirect(url_for("inicio") + "#contacto")
        app.logger.info("Contacto NOXTIUM: %s <%s> - %s", nombre, correo, mensaje)
        flash("Recibimos tu mensaje. Nos pondremos en contacto contigo.", "success")
        return redirect(url_for("inicio") + "#contacto")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
