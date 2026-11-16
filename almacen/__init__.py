"""Almacen de YACHAYBOT: unico punto de acceso a los datos persistidos.

Este paquete es la frontera del sistema hacia la base de datos. Ni el robot,
ni el panel, ni el agente docente deben escribir SQL: consumen las funciones
publicas de aqui.

PostgreSQL es el almacen unico. SQLite queda como adaptador de solo lectura
para el historico entregado y para las pruebas que construyen una base
temporal sin levantar un servidor.
"""

from almacen.config import (
    DATOS_DIR,
    RUTA_BASE_SQLITE,
    url_datos,
    url_solo_lectura,
)

__all__ = [
    "DATOS_DIR",
    "RUTA_BASE_SQLITE",
    "url_datos",
    "url_solo_lectura",
]
