# Copiar este archivo como instance/config.py y completar los valores.
# La carpeta instance/ no se publica y no se sube al repositorio.

# Clave para firmar las sesiones. Generar una con:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = "pegar-aca-una-clave-larga-y-aleatoria"

# Nombre que aparece en la cabecera de la página.
NOMBRE_PARQUE = "Parque Nacional Lanín"

# True: cualquiera con la dirección ve el listado y solo RRHH edita.
# False: hay que iniciar sesión incluso para ver.
LECTURA_PUBLICA = True

# Código que se pide una sola vez, al crear el primer administrador en /instalar.
CODIGO_INSTALACION = "CAMBIAR-ESTE-CODIGO"

# Poner True cuando el sitio funcione con HTTPS (en producción, siempre).
SESSION_COOKIE_SECURE = False

# Por defecto la base queda en instance/guardaparques.sqlite. Para otra ubicación:
# DB_PATH = "/var/lib/guardaparques/guardaparques.sqlite"
