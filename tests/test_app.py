"""Pruebas de punta a punta con el cliente de pruebas de Flask.

Correr con:  python -m unittest discover tests
"""

import os
import re
import tempfile
import unittest

from guardaparques import crear_app


class Base(unittest.TestCase):
    lectura_publica = True

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = crear_app({
            "TESTING": True,
            "SECRET_KEY": "prueba",
            "CODIGO_INSTALACION": "codigo-secreto",
            "LECTURA_PUBLICA": self.lectura_publica,
            "DB_PATH": os.path.join(self.tmp.name, "prueba.sqlite"),
        })
        self.c = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def csrf(self, ruta="/"):
        html = self.c.get(ruta).get_data(as_text=True)
        m = re.search(r'name="csrf" value="([0-9a-f]+)"', html)
        return m.group(1) if m else None

    def instalar(self):
        token = self.csrf("/instalar")
        return self.c.post("/instalar", data={
            "csrf": token, "codigo": "codigo-secreto", "nombre": "Admin RRHH",
            "usuario": "admin", "clave": "clave-segura", "clave2": "clave-segura",
        })

    def api(self, accion, datos=None, token=None):
        return self.c.post(f"/api/{accion}", json=datos or {}, headers={"X-CSRF": token or self.token})

    def datos(self):
        return self.c.get("/api/datos").get_json()


class Instalacion(Base):
    def test_sin_usuarios_redirige_a_instalar(self):
        self.assertIn("/instalar", self.c.get("/").headers["Location"])

    def test_codigo_incorrecto(self):
        token = self.csrf("/instalar")
        r = self.c.post("/instalar", data={"csrf": token, "codigo": "otro", "nombre": "X", "usuario": "admin", "clave": "12345678", "clave2": "12345678"})
        self.assertIn("no coincide", r.get_data(as_text=True))

    def test_instalar_y_quedar_desactivada(self):
        self.assertEqual(self.instalar().status_code, 302)
        self.assertIn("Sesión de", self.c.get("/").get_data(as_text=True))
        self.assertEqual(self.c.get("/instalar").status_code, 302)


class Flujo(Base):
    def setUp(self):
        super().setUp()
        self.instalar()
        self.token = self.csrf("/")

    def test_carga_traslado_historial_y_baja(self):
        r = self.api("importar", {"texto": "Pérez, Juan ; Seccional Quillén ; 111\nGómez, Ana\tSeccional Tromen\n\nPérez, Juan ; Otra", "desde": "2024-03-01"})
        self.assertEqual(r.get_json(), {"ok": True, "agregados": 2, "repetidos": ["Pérez, Juan"]})
        d = self.datos()
        self.assertEqual({s["nombre"] for s in d["seccionales"]}, {"Seccional Quillén", "Seccional Tromen"})
        juan = next(a for a in d["agentes"] if a["nombre"] == "Pérez, Juan")
        self.assertEqual(juan["legajo"], "111")
        tromen = next(s for s in d["seccionales"] if s["nombre"] == "Seccional Tromen")

        # Fecha anterior a la llegada: rechazada
        r = self.api("agente_mover", {"id": juan["id"], "seccional_id": tromen["id"], "desde": "2023-01-01"})
        self.assertEqual(r.status_code, 422)

        r = self.api("agente_mover", {"id": juan["id"], "seccional_id": tromen["id"], "desde": "2026-11-17", "referencia": "Disp. 123/2026"})
        self.assertEqual(r.status_code, 200)
        dest = [x for x in self.datos()["destinos"] if x["agente_id"] == juan["id"]]
        self.assertEqual([(x["seccional"], x["desde"], x["hasta"]) for x in dest], [
            ("Seccional Quillén", "2024-03-01", "2026-11-17"),
            ("Seccional Tromen", "2026-11-17", None),
        ])
        self.assertEqual(dest[1]["registrado_por"], "Admin RRHH")

        # Misma seccional: rechazado
        self.assertEqual(self.api("agente_mover", {"id": juan["id"], "seccional_id": tromen["id"], "desde": "2026-11-18"}).status_code, 422)

        # No se puede borrar una seccional con gente
        self.assertEqual(self.api("seccional_eliminar", {"id": tromen["id"]}).status_code, 422)

        self.api("agente_baja", {"id": juan["id"], "fecha": "2026-12-01"})
        d = self.datos()
        self.assertFalse(next(a for a in d["agentes"] if a["id"] == juan["id"])["activo"])
        self.assertTrue(all(x["hasta"] for x in d["destinos"] if x["agente_id"] == juan["id"]))

        csv = self.c.get("/api/csv").get_data(as_text=True)
        self.assertIn("Pérez, Juan;111;;;;;Baja;Seccional Quillén (01/03/2024–17/11/2026) | Seccional Tromen (17/11/2026–01/12/2026)", csv)

    def test_seccional_renombrada_y_eliminada_conserva_historial(self):
        self.api("seccional_guardar", {"nombre": "Lolog"})
        sid = self.datos()["seccionales"][0]["id"]
        self.assertEqual(self.api("seccional_guardar", {"nombre": "lolog"}).status_code, 422)
        aid = self.api("agente_crear", {"nombre": "Ruiz, Eva", "seccional_id": sid, "desde": "2025-01-01"}).get_json()["id"]
        self.api("seccional_guardar", {"id": sid, "nombre": "Seccional Lolog", "zona": "Sur"})
        self.assertEqual(self.datos()["destinos"][0]["seccional"], "Seccional Lolog")
        self.api("agente_baja", {"id": aid, "fecha": "2026-01-01"})
        self.assertEqual(self.api("seccional_eliminar", {"id": sid}).status_code, 200)
        self.assertEqual(self.datos()["destinos"][0]["seccional"], "Lolog")  # nombre guardado al asignarla

    def test_nombre_repetido_pide_confirmacion(self):
        self.api("agente_crear", {"nombre": "Díaz, Luis"})
        self.assertTrue(self.api("agente_crear", {"nombre": "díaz, luis"}).get_json()["repetido"])
        self.assertIn("id", self.api("agente_crear", {"nombre": "díaz, luis", "confirmar_repetido": True}).get_json())

    def test_error_deshace_todo(self):
        aid = self.api("agente_crear", {"nombre": "Sosa, Ema"}).get_json()["id"]
        r = self.api("agente_crear", {"nombre": "Nuevo", "seccional_id": 999, "desde": "2026-01-01"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual([a["id"] for a in self.datos()["agentes"]], [aid])

    def test_csrf_y_sesion(self):
        self.assertEqual(self.api("seccional_guardar", {"nombre": "X"}, token="malo").status_code, 403)
        self.c.post("/logout", data={"csrf": self.token})
        self.assertEqual(self.api("seccional_guardar", {"nombre": "X"}).status_code, 401)
        self.assertEqual(self.c.get("/api/datos").status_code, 200)  # lectura pública

    def test_usuarios(self):
        self.assertEqual(self.api("usuario_crear", {"usuario": "aperez", "nombre": "Ana Pérez", "clave": "corta"}).status_code, 422)
        self.assertEqual(self.api("usuario_crear", {"usuario": "aperez", "nombre": "Ana Pérez", "clave": "clave-de-ana"}).status_code, 200)
        self.c.post("/logout", data={"csrf": self.token})
        r = self.c.post("/login", data={"csrf": self.csrf("/login"), "usuario": "aperez", "clave": "clave-de-ana"})
        self.assertEqual(r.status_code, 302)
        self.token = self.csrf("/")
        self.assertEqual(self.api("usuarios_listar").status_code, 422)  # no es administradora
        self.assertEqual(self.api("seccional_guardar", {"nombre": "Hua Hum"}).status_code, 200)

    def test_html_escapado(self):
        self.api("usuario_crear", {"usuario": "xss", "nombre": "<script>alert(1)</script>", "clave": "12345678"})
        self.c.post("/logout", data={"csrf": self.token})
        self.c.post("/login", data={"csrf": self.csrf("/login"), "usuario": "xss", "clave": "12345678"})
        html = self.c.get("/").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)", html)

    def test_dni_solo_con_sesion(self):
        r = self.api("agente_crear", {"nombre": "Pérez, Juan", "dni": "11.222.333"})
        aid = r.get_json()["id"]
        juan = self.datos()["agentes"][0]
        self.assertEqual(juan["dni"], "11222333")
        self.assertIn("DNI", self.c.get("/api/csv").get_data(as_text=True))

        # Validación y repetidos
        self.assertEqual(self.api("agente_crear", {"nombre": "Otro", "dni": "12ab"}).status_code, 422)
        r = self.api("agente_crear", {"nombre": "Otro", "dni": "11222333"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Pérez, Juan", r.get_json()["error"])

        # Editar sin mandar el DNI lo conserva; mandarlo vacío lo borra
        self.api("agente_editar", {"id": aid, "nombre": "Pérez, Juan", "legajo": "1"})
        self.assertEqual(self.datos()["agentes"][0]["dni"], "11222333")
        self.api("agente_editar", {"id": aid, "nombre": "Pérez, Juan", "dni": ""})
        self.assertEqual(self.datos()["agentes"][0]["dni"], "")
        self.api("agente_editar", {"id": aid, "nombre": "Pérez, Juan", "dni": "11222333"})

        # Sin sesión (lectura pública) no se ve
        self.c.post("/logout", data={"csrf": self.token})
        self.assertNotIn("dni", self.datos()["agentes"][0])
        self.assertNotIn("11222333", self.c.get("/api/csv").get_data(as_text=True))

    def test_dni_de_cuil(self):
        from guardaparques import datos
        self.assertEqual(datos.dni_de_cuil("27-11222333-9"), "11222333")
        self.assertEqual(datos.dni_de_cuil("20-07123456-3"), "7123456")
        self.assertEqual(datos.dni_de_cuil("123"), "")


class LecturaPrivada(Base):
    lectura_publica = False

    def test_sin_login_no_se_ve_nada(self):
        self.instalar()
        token = self.csrf("/")
        self.c.post("/logout", data={"csrf": token})
        self.assertIn("/login", self.c.get("/").headers["Location"])
        self.assertEqual(self.c.get("/api/datos").status_code, 401)


if __name__ == "__main__":
    unittest.main()
