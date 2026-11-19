# Guardaparques por Seccional

App web para que RRHH del Parque Nacional Lanín mantenga el listado de guardaparques con la seccional donde presta funciones cada uno y su historial de traslados. Lectura pública (configurable) y edición con usuario y contraseña.

## Stack

- Python 3.9+ con Flask 3; Waitress como servidor de producción (`wsgi.py`).
- SQLite con el módulo `sqlite3` de la biblioteca estándar. Sin ORM.
- Frontend sin build: HTML con Jinja, un `app.css` y un `app.js` en JavaScript puro, sin frameworks.
- Sin dependencias nuevas salvo que sea imprescindible: tiene que poder instalarse fácil en un servidor institucional.

## Comandos

```
.venv\Scripts\python wsgi.py                          # servidor en http://localhost:8000
.venv\Scripts\python -m unittest discover tests       # pruebas
```

`instance/config.py` tiene SECRET_KEY y CODIGO_INSTALACION reales de esta PC: no mostrarlos ni copiarlos a otros archivos. `instance/` está en .gitignore y también tiene la base `guardaparques.sqlite`, con los datos reales del personal. No borrarla ni sobrescribirla sin preguntar.

## Estructura

- `guardaparques/__init__.py`: `crear_app()` con las páginas (`/`, `/login`, `/logout`, `/instalar`), la sesión, el CSRF y la API (`GET /api/datos`, `GET /api/csv`, `POST /api/<accion>`).
- `guardaparques/datos.py`: esquema, conexión y todas las acciones de escritura. Cada acción es `fn(entrada: dict, usuario: dict) -> dict` y se registra en `ACCIONES`. La API las corre dentro de `with datos.db():` (una transacción).
- `guardaparques/templates/`: `base.html` (cabecera común), `index.html`, `login.html`, `instalar.html`.
- `guardaparques/static/app.js`: lee todo con `api/datos` y arma las vistas del lado del cliente.
- `tests/test_app.py`: pruebas de punta a punta con el test client de Flask y una base temporal.
- `scripts/importar_planilla.py`: importa los guardaparques (CONVENIO = GUARDAPARQUES) de la planilla Excel de personal. Sin `--grabar` solo muestra la vista previa. Nombres como `APELLIDO, Nombre I.`; la columna FUNCIÓN se normaliza como destino ("SECC. X" → "Seccional X") y SECTORES da la zona (UGD Sur/Centro/Norte).
- `scripts/importar_dni.py`: completa el DNI desde el listado de agentes (columnas CUIL, APELLIDO, NOMBRE, LEGAJO), buscando por legajo y si no por nombre. Sin `--grabar` solo muestra a quién se le encontró, sin imprimir los DNI.

## Modelo de datos

- `agentes`: nombre, legajo, dni (solo dígitos, sin puntos), activo, baja_fecha. El DNI es dato personal: `api/datos` y el CSV lo incluyen solo con sesión iniciada. Las columnas nuevas se agregan a bases existentes en `datos.migrar()`.
- `seccionales`: nombre (único, sin distinguir mayúsculas), zona.
- `destinos`: un período de un agente en una seccional (`desde`/`hasta`). El destino actual es el que tiene `hasta IS NULL`. Cambiar de seccional cierra el actual con la fecha del traslado y abre uno nuevo, así se arma el historial. `seccional_nombre` guarda el nombre al momento de asignarse, para que el historial sobreviva si se borra la seccional.
- `usuarios`: cuentas de RRHH; `es_admin` gestiona usuarios.
- `auditoria`: cada acción de escritura llama a `registrar()`.

Fechas en ISO `YYYY-MM-DD` en la base y en la API; en pantalla y en el CSV, `dd/mm/aaaa`.

## Datos cargados

Los 49 guardaparques vienen de `PERSONAL PNL-DATOS (2).xlsx` (planilla de oct-2026), importada el 17/11/2026 con `desde = 2026-10-01` para todos. Los que no están en una seccional tienen su función como destino (Taller, Operativo, Administrativa, etc.). El 19/11/2026 se completó el DNI de 43 desde `LISTADO DE AGENTES DEL P.N.LANIN (1).xlsx` (sacado del CUIL); 6 no figuran en ese listado y no tienen DNI. Las planillas `.xlsx` tienen datos personales y están en .gitignore.

## Convenciones

- Código, nombres y comentarios en español (`agente_mover`, `requerir_fecha`, `ErrorUsuario`).
- Textos de la interfaz en español rioplatense con voseo ("Elegí", "Recargá"), frases cortas y directas. Los errores dicen qué pasó y cómo seguir.
- Errores que ve la persona usuaria: `raise ErrorUsuario("...")` en `datos.py`, que la API devuelve como 422.
- Seguridad: todo POST de la API exige sesión y la cabecera `X-CSRF`, y los formularios llevan el campo `csrf`. En JS, todo texto que va a `innerHTML` pasa por `esc()`. Jinja escapa solo: no usar `|safe` con datos.
- Al agregar una acción: función en `datos.py`, sumarla a `ACCIONES`, llamarla desde `app.js` con `enviar()`/`guardar()` y agregarle una prueba.

## Diseño

Cabecera estilo cartel de madera de Parques Nacionales: fondo marrón `--wood` con letras amarillas `--wood-fg`. Acento verde bosque `--accent`. Fuentes: Barlow Semi Condensed para títulos, etiquetas y números de la cabecera, y Source Sans 3 para el texto, las dos desde Google Fonts y con fuentes de respaldo del sistema.

Cada tarjeta de seccional tiene un encabezado tipo cartel (`--sign` / `--sign-fg`) con la zona y un contador; "Sin seccional asignada" usa la variante apagada `.secc.sin`.

Los colores son variables en `:root` de `app.css`. Hay tres temas: Auto sigue a `prefers-color-scheme`, y Claro u Oscuro fijan `data-theme` en `<html>`. Se eligen con el selector de `base.html` y se guardan en `localStorage` (`gp-tema`). Cada token oscuro está definido dos veces (en el media query y en `[data-theme="dark"]`): al cambiar uno, cambiar los dos. No usar colores sueltos en los componentes. Tiene que funcionar en el celular (ancho de unos 400 px) sin scroll horizontal; las tablas se desplazan dentro de `.tablebox`.

## Despliegue

Pendiente de definir con Sistemas de APN: servidor y subdominio con HTTPS. Ver `NOTA-SISTEMAS.md` y `README.md`. En producción: `SESSION_COOKIE_SECURE = True` y proxy inverso hacia Waitress en el puerto 8000.
