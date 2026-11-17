"""Importa guardaparques desde la planilla de personal (Excel) a la base.

Uso:
    python scripts/importar_planilla.py "PERSONAL PNL-DATOS.xlsx" --desde 2026-10-01           (solo muestra)
    python scripts/importar_planilla.py "PERSONAL PNL-DATOS.xlsx" --desde 2026-10-01 --grabar  (graba)

Columnas esperadas en la primera hoja: LEGAJO, APELLIDO, NOMBRE, CONVENIO, SECTORES, FUNCIÓN.
Se importan solo las filas con CONVENIO = GUARDAPARQUES. Quien ya existe (mismo nombre) se saltea.
"""

import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl  # noqa: E402

from guardaparques import crear_app, datos  # noqa: E402

SIGLAS = {"UGD", "ICE", "RN", "II", "III", "IV"}
MINUSCULAS = {"de", "del", "y", "e"}
ABREVIATURAS = {"pto.": "Puerto", "pto": "Puerto", "secc.": "Seccional", "coord.": "Coordinación", "2do": "2.º"}
TILDES = {"area": "Área", "tecnico": "Técnico", "pucara": "Pucará"}


def titulo(texto):
    """'SECCIONAL QUILA QUINA' -> 'Seccional Quila Quina', respetando siglas y preposiciones."""
    palabras = []
    for i, p in enumerate(texto.split()):
        bajo = p.lower()
        if p.upper() in SIGLAS:
            palabras.append(p.upper())
        elif bajo in ABREVIATURAS:
            palabras.append(ABREVIATURAS[bajo])
        elif bajo in TILDES:
            palabras.append(TILDES[bajo])
        elif i > 0 and bajo in MINUSCULAS:
            palabras.append(bajo)
        else:
            palabras.append(bajo[:1].upper() + bajo[1:])
    return " ".join(palabras)


def nombre_agente(apellido, nombres):
    """'ACUÑA', 'ANDREA NATALIA' -> 'ACUÑA, Andrea N.'"""
    partes = datos.limpiar(nombres).split()
    if not partes:
        return datos.limpiar(apellido).upper()
    pila = partes[0].lower().capitalize()
    iniciales = [p[0].upper() + "." for p in partes[1:]]
    return f"{datos.limpiar(apellido).upper()}, {' '.join([pila] + iniciales)}"


def destino(funcion):
    """Devuelve (nombre del destino, referencia) a partir de la columna FUNCIÓN."""
    f = datos.limpiar(funcion)
    f = re.sub(r"(?i)^secc(ional)?\.?\s*", "SECCIONAL ", f)  # 'SECC. TROMEN', 'SECC.LAS TAGUAS'
    m = re.match(r"(?i)^coord\.\s*(UGD\s+\w+).*?\by\s+(SECC.+)$", f)
    if m:  # 'COORD. UGD CENTRO-JUNÍN- Y SECC. PTO ARTURO / LOLOG'
        return f"Coordinación {titulo(m.group(1))}", f"También a cargo de {titulo(m.group(2))}"
    if "-" in f and not f.upper().startswith("ICE-"):
        principal, extra = [x.strip(" -") for x in f.split("-", 1)]
        return normalizar_principal(principal), titulo(extra)
    return normalizar_principal(f.replace("ICE-", "ICE – ")), ""


def normalizar_principal(texto):
    t = titulo(texto)
    return {"Operativa": "Operativo"}.get(t, t)


def zona(sector):
    m = re.search(r"UGD\s+(SUR|CENTRO|CTRO|NORTE)", (sector or "").upper())
    return {"SUR": "UGD Sur", "CENTRO": "UGD Centro", "CTRO": "UGD Centro", "NORTE": "UGD Norte"}[m.group(1)] if m else ""


def leer(ruta):
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True).worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    cab = [datos.limpiar(c).upper() for c in next(filas)]
    col = {n: cab.index(n) for n in ("LEGAJO", "APELLIDO", "NOMBRE", "CONVENIO", "SECTORES")}
    col["FUNCION"] = next(i for i, c in enumerate(cab) if c.startswith("FUNCI"))
    for f in filas:
        if datos.limpiar(f[col["CONVENIO"]]).upper() != "GUARDAPARQUES":
            continue
        dest, ref = destino(f[col["FUNCION"]] or "")
        yield {
            "nombre": nombre_agente(f[col["APELLIDO"]] or "", f[col["NOMBRE"]] or ""),
            "legajo": datos.limpiar(f[col["LEGAJO"]]),
            "destino": dest,
            "referencia": ref,
            "zona": zona(f[col["SECTORES"]]),
        }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("planilla")
    ap.add_argument("--desde", required=True, help="fecha de la asignación actual, AAAA-MM-DD")
    ap.add_argument("--fuente", default="Planilla de personal", help="texto que se agrega a la referencia de cada destino")
    ap.add_argument("--grabar", action="store_true", help="sin esto solo muestra lo que haría")
    args = ap.parse_args()
    datos.requerir_fecha({"d": args.desde}, "d")

    agentes = list(leer(args.planilla))
    print(f"{len(agentes)} guardaparques en la planilla\n")
    for a in agentes:
        print(f"  {a['nombre']:<32} {a['legajo']:>7}  {a['destino']}" + (f"  ({a['referencia']})" if a["referencia"] else ""))
    print("\nDestinos:")
    for d, n in sorted(Counter(a["destino"] for a in agentes).items()):
        z = next((a["zona"] for a in agentes if a["destino"] == d and a["zona"]), "")
        print(f"  {n:>2}  {d}" + (f"  · {z}" if z else ""))

    if not args.grabar:
        print("\nNo se grabó nada. Agregá --grabar para importar.")
        return

    app = crear_app()
    with app.app_context(), datos.db():
        seccionales = {s["nombre"].lower(): s for s in datos.filas("SELECT id, nombre FROM seccionales")}
        nuevos = saltados = 0
        for a in agentes:
            if datos.nombre_repetido(a["nombre"]):
                saltados += 1
                continue
            clave = a["destino"].lower()
            if clave not in seccionales:
                sid = datos.db().execute("INSERT INTO seccionales (nombre, zona) VALUES (?, ?)", (a["destino"], a["zona"])).lastrowid
                seccionales[clave] = {"id": sid, "nombre": a["destino"]}
            aid = datos.db().execute("INSERT INTO agentes (nombre, legajo) VALUES (?, ?)", (a["nombre"], a["legajo"])).lastrowid
            ref = " · ".join(x for x in (a["referencia"], args.fuente) if x)
            datos.abrir_destino(aid, seccionales[clave], args.desde, ref, None)
            nuevos += 1
        datos.registrar(None, "importación de planilla", f"{os.path.basename(args.planilla)}: {nuevos} agregados, {saltados} ya existían")
    print(f"\nGrabado: {nuevos} agregados, {saltados} ya existían.")


if __name__ == "__main__":
    main()
