"""Gestion de la sesion de base de datos.

Una sesion por peticion es la forma correcta de trabajar con SQLAlchemy: se
abre, se usa y se cierra. Este modulo evita que cada consumidor tenga que
repetir ese ritual.
"""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from almacen.config import url_datos, url_solo_lectura

_motores = {}


def _motor(url: str):
    """Devuelve (y cachea) el motor para una URL dada."""
    if url not in _motores:
        _motores[url] = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5} if "postgresql" in url else {},
        )
    return _motores[url]


@contextmanager
def sesion_datos(url: str | None = None):
    """Sesion con permisos de lectura y escritura. Hace commit al salir."""
    motor = _motor(url or url_datos())
    fabrica = sessionmaker(bind=motor, future=True)
    sesion = fabrica()
    try:
        yield sesion
        sesion.commit()
    except Exception:
        sesion.rollback()
        raise
    finally:
        sesion.close()


@contextmanager
def sesion_solo_lectura(url: str | None = None):
    """Sesion de solo lectura. Nunca hace commit.

    Se usa para el agente docente, que debe poder consultar el historial pero
    no modificarlo. El rol de PostgreSQL deberia tener solo SELECT.
    """
    motor = _motor(url or url_solo_lectura())
    fabrica = sessionmaker(bind=motor, future=True)
    sesion = fabrica()
    try:
        yield sesion
    finally:
        sesion.close()


def cerrar_motores() -> None:
    """Cierra los motores abiertos. Se usa al apagar el servidor."""
    for motor in _motores.values():
        motor.dispose()
    _motores.clear()
