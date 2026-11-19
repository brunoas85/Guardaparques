"""Completa el DNI de los guardaparques a partir del listado de agentes del parque (Excel).

Uso:
    python scripts/importar_dni.py "LISTADO DE AGENTES DEL P.N.LANIN.xlsx"            (solo muestra)
    python scripts/importar_dni.py "LISTADO DE AGENTES DEL P.N.LANIN.xlsx" --grabar   (graba)

Columnas esperadas en la primera hoja: CUIL, APELLIDO, NOMBRE, LEGAJO. El DNI sale del CUIL
(los 8 dígitos del medio). Cada guardaparque se busca primero por legajo y, si no aparece, por
nombre. Solo se completan los DNI vacíos; con --pisar también se reemplazan los distintos.
Por pantalla no se muestran los DNI, solo a quién se le encontró.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl  # noqa: E402

from guardaparques import crear_app, datos  # noqa: E402
from scripts.importar_planilla import nombre_agente  # noqa: E402


def leer(ruta):
    """Devuelve dos índices de DNI: por legajo y por nombre ('APELLIDO, Nombre I.' en mayúsculas)."""
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True).worksheets[0]
    filas = hoja.iter_rows(values_only=True)
    cab = [datos.limpiar(c).upper() for c in next(filas)]
    col = {n: cab.index(n) for n in ("CUIL", "APELLIDO", "NOMBRE", "LEGAJO")}
    por_legajo, por_nombre = {}, {}
    for f in filas:
        dni = datos.dni_de_cuil(f[col["CUIL"]])
        if not dni:
            continue
        legajo = datos.limpiar(f[col["LEGAJO"]])
        if legajo:
            por_legajo.setdefault(legajo, set()).add(dni)
        nombre = nombre_agente(f[col["APELLIDO"]] or "", f[col["NOMBRE"]] or "").upper()
        por_nombre.setdefault(nombre, set()).add(dni)
    return por_legajo, por_nombre


def buscar(agente, por_legajo, por_nombre):
    """(dni, cómo se encontró) o (None, motivo)."""
    for indice, clave, como in ((por_legajo, agente["legajo"], "legajo"), (por_nombre, agente["nombre"].upper(), "nombre")):
        encontrados = indice.get(clave) if clave else None
        if encontrados and len(encontrados) == 1:
            return next(iter(encontrados)), como
        if encontrados:
            return None, f"más de un DNI para ese {como}"
    return None, "no está en el listado"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("listado")
    ap.add_argument("--grabar", action="store_true", help="sin esto solo muestra lo que haría")
    ap.add_argument("--pisar", action="store_true", help="reemplaza también los DNI ya cargados que no coinciden")
    args = ap.parse_args()

    por_legajo, por_nombre = leer(args.listado)
    app = crear_app()
    with app.app_context(), datos.db():
        agentes = datos.filas("SELECT id, nombre, legajo, dni FROM agentes ORDER BY nombre")
        cambios, sin_dato, iguales, distintos = [], [], 0, []
        for a in agentes:
            dni, como = buscar(a, por_legajo, por_nombre)
            if not dni:
                sin_dato.append((a["nombre"], como))
            elif a["dni"] == dni:
                iguales += 1
            elif a["dni"] and not args.pisar:
                distintos.append(a["nombre"])
            elif datos.dni_repetido(dni, a["id"]):
                sin_dato.append((a["nombre"], "ese DNI ya lo tiene otra persona en la base"))
            else:
                cambios.append((a, dni, como))

        print(f"{len(agentes)} guardaparques en la base\n")
        print(f"Se completa el DNI de {len(cambios)}:")
        for a, _dni, como in cambios:
            print(f"  {a['nombre']:<32} (por {como})")
        if iguales:
            print(f"\n{iguales} ya tenían el mismo DNI.")
        if distintos:
            print(f"\n{len(distintos)} ya tienen otro DNI cargado (no se tocan; usá --pisar para reemplazarlo):")
            for n in distintos:
                print(f"  {n}")
        if sin_dato:
            print(f"\n{len(sin_dato)} quedan sin DNI (cargalo a mano desde Editar):")
            for n, motivo in sin_dato:
                print(f"  {n:<32} {motivo}")

        if not args.grabar:
            print("\nNo se grabó nada. Agregá --grabar para guardar.")
            return
        for a, dni, _como in cambios:
            datos.db().execute("UPDATE agentes SET dni = ? WHERE id = ?", (dni, a["id"]))
        datos.registrar(None, "importación de DNI", f"{os.path.basename(args.listado)}: {len(cambios)} completados")
    print(f"\nGrabado: {len(cambios)} DNI completados.")


if __name__ == "__main__":
    main()
