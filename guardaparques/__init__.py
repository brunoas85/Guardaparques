"""Guardaparques por Seccional: aplicación Flask."""

import hmac
import os
import secrets
import time

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

from . import datos
from .datos import ErrorUsuario


def crear_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=None,
        NOMBRE_PARQUE="Parque Nacional",
        LECTURA_PUBLICA=True,
        CODIGO_INSTALACION="",
        DB_PATH=os.path.join(app.instance_path, "guardaparques.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,
    )
    app.config.from_pyfile("config.py", silent=True)
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Falta SECRET_KEY. Copiá config.example.py como instance/config.py y completalo.")

    os.makedirs(os.path.dirname(app.config["DB_PATH"]) or ".", exist_ok=True)
    app.teardown_appcontext(datos.cerrar)
    datos.iniciar(app)

    # ---------- Sesión ----------

    def usuario_actual():
        uid = session.get("uid")
        return datos.buscar_usuario_activo(uid) if uid else None

    def token_csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(32)
        return session["csrf"]

    def csrf_valido(token):
        esperado = session.get("csrf")
        return bool(esperado and token and hmac.compare_digest(esperado, token))

    def entrar(uid):
        session.clear()
        session["uid"] = uid

    @app.after_request
    def cabeceras(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp

    @app.context_processor
    def globales():
        return {"nombre_parque": app.config["NOMBRE_PARQUE"]}

    # ---------- Páginas ----------

    @app.get("/")
    def inicio():
        if not datos.hay_usuarios():
            return redirect(url_for("instalar"))
        u = usuario_actual()
        if not u and not app.config["LECTURA_PUBLICA"]:
            return redirect(url_for("login"))
        app_data = {
            "usuario": {"nombre": u["nombre"], "admin": bool(u["es_admin"])} if u else None,
            "csrf": token_csrf() if u else None,
        }
        return render_template("index.html", u=u, app_data=app_data)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not datos.hay_usuarios():
            return redirect(url_for("instalar"))
        error, usuario = "", ""
        if request.method == "POST":
            usuario = request.form.get("usuario", "").strip()
            if not csrf_valido(request.form.get("csrf")):
                error = "El formulario venció. Probá de nuevo."
            else:
                uid = datos.verificar_login(usuario, request.form.get("clave", ""))
                if uid:
                    entrar(uid)
                    with datos.db():
                        datos.registrar(uid, "inicio de sesión")
                    return redirect(url_for("inicio"))
                time.sleep(1)  # frena intentos repetidos de adivinar contraseñas
                error = "Usuario o contraseña incorrectos."
        return render_template("login.html", error=error, usuario=usuario, csrf=token_csrf(),
                               lectura_publica=app.config["LECTURA_PUBLICA"])

    @app.post("/logout")
    def logout():
        if csrf_valido(request.form.get("csrf")):
            session.clear()
        return redirect(url_for("inicio"))

    @app.route("/instalar", methods=["GET", "POST"])
    def instalar():
        if datos.hay_usuarios():
            return redirect(url_for("inicio"))
        codigo = app.config["CODIGO_INSTALACION"]
        if not codigo or codigo == "CAMBIAR-ESTE-CODIGO":
            return render_template("instalar.html", falta_config=True)
        error, v = "", {"usuario": "", "nombre": ""}
        if request.method == "POST":
            v = {"usuario": request.form.get("usuario", "").strip().lower(), "nombre": request.form.get("nombre", "")}
            clave = request.form.get("clave", "")
            if not csrf_valido(request.form.get("csrf")):
                error = "El formulario venció. Probá de nuevo."
            elif not hmac.compare_digest(codigo, request.form.get("codigo", "")):
                time.sleep(1)
                error = "El código de instalación no coincide con el de la configuración."
            elif clave != request.form.get("clave2", ""):
                error = "Las contraseñas no coinciden."
            else:
                try:
                    with datos.db():
                        uid = datos.crear_usuario(v["usuario"], v["nombre"], clave, True)
                        datos.registrar(uid, "instalación", "primer administrador")
                    entrar(uid)
                    return redirect(url_for("inicio"))
                except ErrorUsuario as e:
                    error = str(e)
        return render_template("instalar.html", falta_config=False, error=error, v=v, csrf=token_csrf())

    # ---------- API ----------

    def puede_leer():
        return app.config["LECTURA_PUBLICA"] or usuario_actual() is not None

    @app.get("/api/datos")
    def api_datos():
        if not puede_leer():
            return jsonify(error="Iniciá sesión para ver el listado."), 401
        resp = jsonify(datos.datos_completos())
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.get("/api/csv")
    def api_csv():
        if not puede_leer():
            return redirect(url_for("login"))
        nombre = f"guardaparques-seccionales-{time.strftime('%Y-%m-%d')}.csv"
        return Response(datos.csv_listado(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @app.post("/api/<accion>")
    def api_accion(accion):
        u = usuario_actual()
        if not u:
            return jsonify(error="Tu sesión terminó. Volvé a iniciar sesión."), 401
        if not csrf_valido(request.headers.get("X-CSRF")):
            return jsonify(error="La página quedó desactualizada. Recargala y probá de nuevo."), 403
        fn = datos.ACCIONES.get(accion)
        if not fn:
            return jsonify(error="Acción desconocida."), 404
        entrada = request.get_json(silent=True)
        try:
            with datos.db():  # confirma todo junto o deshace si hay error
                resultado = fn(entrada if isinstance(entrada, dict) else {}, u)
        except ErrorUsuario as e:
            return jsonify(error=str(e)), 422
        return jsonify(ok=True, **resultado)

    @app.errorhandler(500)
    def error_interno(_e):
        if request.path.startswith("/api/"):
            return jsonify(error="Error interno del servidor. Si se repite, avisá a Sistemas."), 500
        return "Error interno del servidor.", 500

    return app
