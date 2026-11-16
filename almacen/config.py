"""Configuracion de rutas y credenciales de YACHAYBOT.

Las credenciales nunca se escriben en el codigo: se leen de variables de
entorno. Si no estan definidas se usan valores de desarrollo locales para
que el proyecto funcione en la laptop sin configuracion adicional.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Carpeta de datos locales: copia historica, audio opcional y bitacoras.
DATOS_DIR = Path(os.environ.get("YACHAYBOT_DATA_DIR") or (BASE_DIR / "datos"))

# Base SQLite entregada en la v1. Se conserva como historico y respaldo; el
# sistema ya no escribe en ella.
RUTA_BASE_SQLITE = DATOS_DIR / "yachaybot.db"

# Bitacora de ejecuciones del agente docente.
RUTA_BITACORA_AGENTE = DATOS_DIR / "agente_ejecuciones.jsonl"


def url_datos() -> str:
    """URL de PostgreSQL con permisos de lectura y escritura (robot y panel)."""
    return os.environ.get(
        "YACHAYBOT_DB_URL",
        "postgresql+psycopg://postgres@127.0.0.1:5432/yachaybot",
    )


def url_solo_lectura() -> str:
    """URL de PostgreSQL con permisos de solo lectura (agente docente).

    Por defecto es la misma que :func:`url_datos`. En la laptop de la escuela
    conviene definir YACHAYBOT_DB_RO_URL con un rol de PostgreSQL que solo
    tenga SELECT sobre el esquema public.
    """
    return os.environ.get("YACHAYBOT_DB_RO_URL") or url_datos()
