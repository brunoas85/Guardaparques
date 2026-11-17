# Pedido a Sistemas: alojamiento de "Guardaparques por Seccional"

**Qué es:** una aplicación web chica para que RRHH mantenga actualizado el listado de guardaparques del Parque Nacional Lanín, con la seccional de cada uno y su historial de traslados.

**Qué necesita:**

| | |
|---|---|
| Lenguaje | Python 3.9 o superior. Dependencias: Flask y Waitress |
| Base de datos | Ninguna aparte: usa un archivo SQLite dentro de `instance/` |
| Espacio | Menos de 50 MB, contando el entorno de Python |
| Servidor | Linux o Windows. La app escucha en un puerto local (8000) y se publica detrás de Nginx, Apache o IIS como proxy inverso |
| HTTPS | Necesario, porque hay inicio de sesión con contraseña |
| Dominio | Un subdominio, por ejemplo `guardaparques.<dominio-del-parque>` (a definir) |
| Correo, tareas programadas, otros servicios | No usa |

**Accesos:**
- Lectura del listado: pública o solo red interna, según lo que se decida. Se configura en `instance/config.py`.
- Edición: solo usuarios de RRHH con usuario y contraseña. Las contraseñas se guardan con hash; hay protección CSRF.

**Mantenimiento:** hacer una copia periódica de `instance/guardaparques.sqlite`.

**Preguntas para Sistemas:**
1. ¿Hay un servidor institucional donde se pueda correr una aplicación Python?
2. ¿Se puede asignar un subdominio con certificado HTTPS?
3. ¿Prefieren que el sitio quede accesible solo desde la red interna?

Las instrucciones de instalación están en `README.md`.
