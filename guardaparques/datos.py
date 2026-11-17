"""Base de datos SQLite y acciones que modifican el listado."""

import csv
import io
import re
import sqlite3
from datetime import date, datetime

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id          INTEGER PRIMARY KEY,
    usuario     TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nombre      TEXT NOT NULL,
    clave_hash  TEXT NOT NULL,
    es_admin    INTEGER NOT NULL DEFAULT 0,
    activo      INTEGER NOT NULL DEFAULT 1,
    creado_en   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS seccionales (
    id      INTEGER PRIMARY KEY,
    nombre  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    zona    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS agentes (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT NOT NULL,
    legajo      TEXT NOT NULL DEFAULT '',
    activo      INTEGER NOT NULL DEFAULT 1,
    baja_fecha  TEXT,
    creado_en   TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
-- Cada destino es un período en una seccional. El actual tiene hasta = NULL.
CREATE TABLE IF NOT EXISTS destinos (
    id                INTEGER PRIMARY KEY,
    agente_id         INTEGER NOT NULL REFERENCES agentes(id) ON DELETE CASCADE,
    seccional_id      INTEGER REFERENCES seccionales(id) ON DELETE SET NULL,
    seccional_nombre  TEXT NOT NULL,
    desde             TEXT NOT NULL,
    hasta             TEXT,
    referencia        TEXT NOT NULL DEFAULT '',
    registrado_por    INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    registrado_en     TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS destinos_agente ON destinos(agente_id, hasta);
CREATE TABLE IF NOT EXISTS auditoria (
    id          INTEGER PRIMARY KEY,
    usuario_id  INTEGER,
    accion      TEXT NOT NULL,
    detalle     TEXT NOT NULL DEFAULT '',
    fecha       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,40}$")


class ErrorUsuario(Exception):
    """Error que se le muestra tal cual a quien está usando la página."""


# ---------- Conexión ----------

def db():
    if "db" not in g:
        con = sqlite3.connect(current_app.config["DB_PATH"])
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 5000")
        g.db = con
    return g.db


def cerrar(_error=None):
    con = g.pop("db", None)
    if con is not None:
        con.close()


def iniciar(app):
    with app.app_context():
        con = db()
        con.execute("PRAGMA journal_mode = WAL")
        con.executescript(ESQUEMA)


def filas(sql, params=()):
    return [dict(f) for f in db().execute(sql, params).fetchall()]


def fila(sql, params=()):
    f = db().execute(sql, params).fetchone()
    return dict(f) if f else None


def valor(sql, params=()):
    f = db().execute(sql, params).fetchone()
    return f[0] if f else None


def registrar(usuario_id, accion, detalle=""):
    db().execute("INSERT INTO auditoria (usuario_id, accion, detalle) VALUES (?, ?, ?)", (usuario_id, accion, detalle))


# ---------- Utilidades ----------

def limpiar(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def requerir(entrada, campo):
    v = limpiar(entrada.get(campo))
    if not v:
        raise ErrorUsuario(f"Falta completar el campo «{campo}».")
    return v


def requerir_fecha(entrada, campo):
    f = str(entrada.get(campo) or "")
    try:
        date.fromisoformat(f)
    except ValueError:
        raise ErrorUsuario("La fecha no es válida.") from None
    if len(f) != 10:
        raise ErrorUsuario("La fecha no es válida.")
    return f


def dmy(f):
    return datetime.strptime(f[:10], "%Y-%m-%d").strftime("%d/%m/%Y") if f else ""


def validar_clave(clave):
    if len(clave or "") < 8:
        raise ErrorUsuario("La contraseña tiene que tener al menos 8 caracteres.")


def validar_usuario(usuario):
    if not USUARIO_VALIDO.match(usuario):
        raise ErrorUsuario("El usuario solo puede tener letras sin acentos, números, punto, guion o guion bajo (3 a 40).")


# ---------- Usuarios y sesión ----------

def hay_usuarios():
    return valor("SELECT COUNT(*) FROM usuarios") > 0


def buscar_usuario_activo(uid):
    return fila("SELECT id, usuario, nombre, es_admin FROM usuarios WHERE id = ? AND activo = 1", (uid,))


def verificar_login(usuario, clave):
    u = fila("SELECT id, clave_hash FROM usuarios WHERE usuario = ? AND activo = 1", (usuario,))
    if u and check_password_hash(u["clave_hash"], clave):
        return u["id"]
    return None


def crear_usuario(usuario, nombre, clave, es_admin):
    usuario = limpiar(usuario).lower()
    validar_usuario(usuario)
    nombre = limpiar(nombre)
    if not nombre:
        raise ErrorUsuario("Completá el nombre.")
    validar_clave(clave)
    if valor("SELECT COUNT(*) FROM usuarios WHERE usuario = ?", (usuario,)):
        raise ErrorUsuario("Ese nombre de usuario ya existe.")
    cur = db().execute(
        "INSERT INTO usuarios (usuario, nombre, clave_hash, es_admin) VALUES (?, ?, ?, ?)",
        (usuario, nombre, generate_password_hash(clave), 1 if es_admin else 0),
    )
    return cur.lastrowid


# ---------- Lectura ----------

def datos_completos():
    return {
        "seccionales": filas("SELECT id, nombre, zona FROM seccionales ORDER BY nombre"),
        "agentes": filas("SELECT id, nombre, legajo, activo, baja_fecha FROM agentes ORDER BY nombre"),
        "destinos": filas(
            """SELECT d.id, d.agente_id, d.seccional_id, COALESCE(s.nombre, d.seccional_nombre) AS seccional,
                      d.desde, d.hasta, d.referencia, d.registrado_en, u.nombre AS registrado_por
               FROM destinos d
               LEFT JOIN seccionales s ON s.id = d.seccional_id
               LEFT JOIN usuarios u ON u.id = d.registrado_por
               ORDER BY d.agente_id, d.desde, d.id"""
        ),
    }


def csv_listado():
    d = datos_completos()
    zonas = {s["id"]: s["zona"] for s in d["seccionales"]}
    por_agente = {}
    for dest in d["destinos"]:
        por_agente.setdefault(dest["agente_id"], []).append(dest)

    salida = io.StringIO()
    salida.write("﻿")  # para que Excel reconozca los acentos
    w = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    w.writerow(["Guardaparque", "Legajo", "Seccional", "Zona", "Desde", "Estado", "Destinos anteriores"])
    for a in d["agentes"]:
        lista = por_agente.get(a["id"], [])
        actual = next((x for x in lista if x["hasta"] is None), None)
        anteriores = [f"{x['seccional']} ({dmy(x['desde'])}–{dmy(x['hasta'])})" for x in lista if x["hasta"] is not None]
        w.writerow([
            a["nombre"], a["legajo"],
            actual["seccional"] if actual else "",
            zonas.get(actual["seccional_id"], "") if actual else "",
            dmy(actual["desde"]) if actual else "",
            "Activo" if a["activo"] else "Baja",
            " | ".join(anteriores),
        ])
    return salida.getvalue()


# ---------- Auxiliares de escritura ----------

def buscar_seccional(sid):
    s = fila("SELECT id, nombre FROM seccionales WHERE id = ?", (sid,))
    if not s:
        raise ErrorUsuario("Esa seccional ya no existe. Recargá la página.")
    return s


def buscar_agente(aid):
    a = fila("SELECT * FROM agentes WHERE id = ?", (aid,))
    if not a:
        raise ErrorUsuario("Ese guardaparque ya no existe. Recargá la página.")
    return a


def destino_actual(agente_id):
    return fila("SELECT * FROM destinos WHERE agente_id = ? AND hasta IS NULL ORDER BY desde DESC LIMIT 1", (agente_id,))


def abrir_destino(agente_id, seccional, desde, referencia, usuario_id):
    db().execute(
        "INSERT INTO destinos (agente_id, seccional_id, seccional_nombre, desde, referencia, registrado_por) VALUES (?, ?, ?, ?, ?, ?)",
        (agente_id, seccional["id"], seccional["nombre"], desde, referencia, usuario_id),
    )


def nombre_repetido(nombre, excepto=0):
    return valor("SELECT COUNT(*) FROM agentes WHERE nombre = ? COLLATE NOCASE AND id <> ?", (nombre, excepto)) > 0


def entero(entrada, campo):
    try:
        return int(entrada.get(campo) or 0)
    except (TypeError, ValueError):
        return 0


# ---------- Acciones (cada una recibe los datos enviados y el usuario) ----------

def agente_crear(e, u):
    nombre = requerir(e, "nombre")
    legajo = limpiar(e.get("legajo"))
    if nombre_repetido(nombre) and not e.get("confirmar_repetido"):
        return {"repetido": True}
    aid = db().execute("INSERT INTO agentes (nombre, legajo) VALUES (?, ?)", (nombre, legajo)).lastrowid
    if entero(e, "seccional_id"):
        abrir_destino(aid, buscar_seccional(entero(e, "seccional_id")), requerir_fecha(e, "desde"), "", u["id"])
    registrar(u["id"], "alta guardaparque", nombre)
    return {"id": aid}


def agente_editar(e, u):
    a = buscar_agente(entero(e, "id"))
    nombre = requerir(e, "nombre")
    legajo = limpiar(e.get("legajo"))
    if nombre_repetido(nombre, a["id"]) and not e.get("confirmar_repetido"):
        return {"repetido": True}
    db().execute("UPDATE agentes SET nombre = ?, legajo = ? WHERE id = ?", (nombre, legajo, a["id"]))
    registrar(u["id"], "edición guardaparque", f"{a['nombre']} → {nombre}")
    return {}


def agente_mover(e, u):
    a = buscar_agente(entero(e, "id"))
    if not a["activo"]:
        raise ErrorUsuario("Ese guardaparque está dado de baja.")
    sec = buscar_seccional(entero(e, "seccional_id"))
    desde = requerir_fecha(e, "desde")
    ref = limpiar(e.get("referencia"))
    actual = destino_actual(a["id"])
    if actual and actual["seccional_id"] == sec["id"]:
        raise ErrorUsuario("Elegí una seccional distinta de la actual.")
    if actual and desde < actual["desde"]:
        raise ErrorUsuario(f"La fecha no puede ser anterior a la llegada a la seccional actual ({dmy(actual['desde'])}).")
    if actual:
        db().execute("UPDATE destinos SET hasta = ? WHERE id = ?", (desde, actual["id"]))
    abrir_destino(a["id"], sec, desde, ref, u["id"])
    origen = actual["seccional_nombre"] if actual else "—"
    registrar(u["id"], "cambio de seccional", f"{a['nombre']}: {origen} → {sec['nombre']} ({desde})")
    return {}


def agente_baja(e, u):
    a = buscar_agente(entero(e, "id"))
    fecha = requerir_fecha(e, "fecha")
    db().execute("UPDATE agentes SET activo = 0, baja_fecha = ? WHERE id = ?", (fecha, a["id"]))
    db().execute("UPDATE destinos SET hasta = ? WHERE agente_id = ? AND hasta IS NULL", (fecha, a["id"]))
    registrar(u["id"], "baja guardaparque", f"{a['nombre']} ({fecha})")
    return {}


def agente_reactivar(e, u):
    a = buscar_agente(entero(e, "id"))
    db().execute("UPDATE agentes SET activo = 1, baja_fecha = NULL WHERE id = ?", (a["id"],))
    registrar(u["id"], "reactivación guardaparque", a["nombre"])
    return {}


def seccional_guardar(e, u):
    nombre = requerir(e, "nombre")
    zona = limpiar(e.get("zona"))
    sid = entero(e, "id")
    if valor("SELECT COUNT(*) FROM seccionales WHERE nombre = ? COLLATE NOCASE AND id <> ?", (nombre, sid)):
        raise ErrorUsuario("Ya existe una seccional con ese nombre.")
    if sid:
        buscar_seccional(sid)
        db().execute("UPDATE seccionales SET nombre = ?, zona = ? WHERE id = ?", (nombre, zona, sid))
        registrar(u["id"], "edición seccional", nombre)
    else:
        db().execute("INSERT INTO seccionales (nombre, zona) VALUES (?, ?)", (nombre, zona))
        registrar(u["id"], "alta seccional", nombre)
    return {}


def seccional_eliminar(e, u):
    s = buscar_seccional(entero(e, "id"))
    n = valor("SELECT COUNT(*) FROM destinos WHERE seccional_id = ? AND hasta IS NULL", (s["id"],))
    if n:
        raise ErrorUsuario(f"Tiene {n} guardaparque(s) asignado(s). Trasladalos antes de eliminarla.")
    db().execute("DELETE FROM seccionales WHERE id = ?", (s["id"],))
    registrar(u["id"], "baja seccional", s["nombre"])
    return {}


def importar(e, u):
    desde = requerir_fecha(e, "desde")
    seccionales = {s["nombre"].lower(): s for s in filas("SELECT id, nombre FROM seccionales")}
    agregados, repetidos = 0, []
    for linea in str(e.get("texto") or "").splitlines():
        cols = [limpiar(c) for c in re.split(r"\t|;", linea)]
        nombre = cols[0] if cols else ""
        if not nombre:
            continue
        if nombre_repetido(nombre):
            repetidos.append(nombre)
            continue
        legajo = cols[2] if len(cols) > 2 else ""
        aid = db().execute("INSERT INTO agentes (nombre, legajo) VALUES (?, ?)", (nombre, legajo)).lastrowid
        sec_nombre = cols[1] if len(cols) > 1 else ""
        if sec_nombre:
            clave = sec_nombre.lower()
            if clave not in seccionales:
                sid = db().execute("INSERT INTO seccionales (nombre) VALUES (?)", (sec_nombre,)).lastrowid
                seccionales[clave] = {"id": sid, "nombre": sec_nombre}
            abrir_destino(aid, seccionales[clave], desde, "", u["id"])
        agregados += 1
    registrar(u["id"], "carga masiva", f"{agregados} agregados")
    return {"agregados": agregados, "repetidos": repetidos}


def requerir_admin(u):
    if not u["es_admin"]:
        raise ErrorUsuario("Solo un administrador puede gestionar usuarios.")


def usuarios_listar(e, u):
    requerir_admin(u)
    return {"usuarios": filas("SELECT id, usuario, nombre, es_admin, activo FROM usuarios ORDER BY nombre")}


def usuario_crear(e, u):
    requerir_admin(u)
    crear_usuario(e.get("usuario"), e.get("nombre"), str(e.get("clave") or ""), bool(e.get("es_admin")))
    registrar(u["id"], "alta usuario", limpiar(e.get("usuario")).lower())
    return {}


def usuario_clave(e, u):
    requerir_admin(u)
    clave = str(e.get("clave") or "")
    validar_clave(clave)
    db().execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (generate_password_hash(clave), entero(e, "id")))
    registrar(u["id"], "cambio de contraseña", f"usuario #{entero(e, 'id')}")
    return {}


def usuario_activo(e, u):
    requerir_admin(u)
    uid = entero(e, "id")
    if uid == u["id"]:
        raise ErrorUsuario("No podés desactivar tu propio usuario.")
    activo = 1 if e.get("activo") else 0
    db().execute("UPDATE usuarios SET activo = ? WHERE id = ?", (activo, uid))
    registrar(u["id"], "activación usuario" if activo else "desactivación usuario", f"usuario #{uid}")
    return {}


def mi_clave(e, u):
    actual = valor("SELECT clave_hash FROM usuarios WHERE id = ?", (u["id"],))
    if not check_password_hash(actual, str(e.get("actual") or "")):
        raise ErrorUsuario("La contraseña actual no es correcta.")
    nueva = str(e.get("nueva") or "")
    validar_clave(nueva)
    db().execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (generate_password_hash(nueva), u["id"]))
    registrar(u["id"], "cambio de contraseña propia")
    return {}


ACCIONES = {f.__name__: f for f in (
    agente_crear, agente_editar, agente_mover, agente_baja, agente_reactivar,
    seccional_guardar, seccional_eliminar, importar,
    usuarios_listar, usuario_crear, usuario_clave, usuario_activo, mi_clave,
)}
