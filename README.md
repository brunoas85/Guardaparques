# Guardaparques por Seccional

Listado de guardaparques con la seccional donde presta funciones cada uno. Guarda el historial de traslados.
Cualquiera con la dirección puede ver el listado. Para editarlo, el personal de RRHH inicia sesión con usuario y contraseña.

Hecho en Python con Flask. La base de datos es un archivo SQLite.

## Qué hace

- **Por seccional**: cada seccional con su gente y la fecha de llegada de cada persona.
- **Listado**: tabla con nombre, legajo, seccional y fecha "desde".
- **Movimientos**: todos los traslados, del más reciente al más viejo, con la referencia (disposición, nota) y quién los cargó.
- **Cambiar seccional**: el destino anterior se cierra con la fecha del traslado y queda en el historial.
- **Bajas**: la persona sale del listado activo y su historial se conserva. Se puede reactivar.
- **Cargar listado**: se pegan líneas `Apellido, Nombre ; Seccional ; Legajo` o columnas copiadas de Excel.
- **Exportar CSV**: abre en Excel e incluye los destinos anteriores.
- **Usuarios**: un administrador crea las cuentas de RRHH, genera contraseñas nuevas y desactiva cuentas.
- Cada acción queda registrada en la tabla `auditoria` de la base.

## Estructura

```
guardaparques/
├── guardaparques/         la aplicación
│   ├── __init__.py        páginas, login y API
│   ├── datos.py           base de datos y acciones
│   ├── templates/         HTML
│   └── static/            app.css, app.js
├── instance/              configuración y base de datos (no se publica ni se sube al repositorio)
├── tests/test_app.py      pruebas automáticas
├── config.example.py      plantilla de configuración
├── wsgi.py                arranque para producción
└── requirements.txt       Flask y Waitress
```

## Probarlo en la PC

```
cd D:\Documents\bruno\dev\guardaparques
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.py instance\config.py     (completar SECRET_KEY y CODIGO_INSTALACION)
.venv\Scripts\python wsgi.py
```

Abrir <http://localhost:8000>. La primera vez aparece la pantalla de instalación: pide el código de instalación y crea el primer administrador.

Pruebas automáticas: `.venv\Scripts\python -m unittest discover tests`

## Importar la planilla de personal

```
.venv\Scripts\python scripts\importar_planilla.py "PERSONAL PNL-DATOS.xlsx" --desde 2026-10-01 --fuente "Planilla personal PNL oct-2026"
```

Muestra cómo quedaría cada guardaparque y su destino. Si está bien, repetir con `--grabar`. Quien ya está cargado (mismo nombre) se saltea.

## Instalarlo en un servidor

1. Copiar la carpeta al servidor, que tiene que tener Python 3.9 o más nuevo.
2. Crear el entorno e instalar las dependencias, igual que en la PC.
3. Crear `instance/config.py` a partir de `config.example.py`:
   - `SECRET_KEY`: generarla con `python -c "import secrets; print(secrets.token_hex(32))"`.
   - `CODIGO_INSTALACION`: un código largo inventado, se usa una sola vez.
   - `SESSION_COOKIE_SECURE = True`: el sitio tiene que funcionar con HTTPS.
   - `LECTURA_PUBLICA = False` si se quiere pedir login también para ver.
4. Dejar corriendo `wsgi.py` (Waitress, puerto 8000) como servicio:
   - en Linux, con systemd;
   - en Windows, con NSSM o el Programador de tareas.
5. Poner adelante un servidor web con HTTPS (Nginx, Apache o IIS) que reenvíe el dominio a `http://127.0.0.1:8000`.
6. Entrar al sitio, crear el administrador y, desde **Usuarios**, las cuentas del resto de RRHH.

También funciona en servicios como PythonAnywhere: se apunta su configuración WSGI a `wsgi.py` (variable `app`).

## Copias de seguridad

Todos los datos están en `instance/guardaparques.sqlite`. Alcanza con copiar ese archivo periódicamente.
Si el sistema está en uso, copiar también `guardaparques.sqlite-wal` si existe.

## Privacidad

Con `LECTURA_PUBLICA = True`, el listado (nombres, legajos y seccionales) lo ve cualquiera que tenga la dirección.
Si no se quiere publicar los legajos, poner `LECTURA_PUBLICA = False` o dejar el sitio solo en la red interna.
