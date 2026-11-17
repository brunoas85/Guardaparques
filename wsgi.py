"""Punto de entrada para el servidor de producción (Waitress, Gunicorn, mod_wsgi, etc.)."""

from guardaparques import crear_app

app = crear_app()

if __name__ == "__main__":
    # Servidor de producción simple, funciona igual en Windows y Linux.
    from waitress import serve

    serve(app, host="0.0.0.0", port=8000)
