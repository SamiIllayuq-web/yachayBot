"""Migracion del historial SQLite (v1) a PostgreSQL.

Importa las interacciones de la base entregada en la version 1 y verifica
que los conteos coincidan. Es idempotente: si la marca de migracion ya
existe, no hace nada.

Uso:
    python -m scripts.migrar_sqlite_a_postgres
    python -m scripts.migrar_sqlite_a_postgres --fuente ruta/otra.db --forzar
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from almacen.config import RUTA_BASE_SQLITE, url_datos  # noqa: E402
from almacen.esquema import Base, Interaccion, crear_todo  # noqa: E402
from almacen.repositorio import RepositorioInteracciones  # noqa: E402

MARCA_MIGRACION = "migracion_sqlite_v1"


def leer_sqlite(ruta: Path) -> list:
    """Lee todas las interacciones del archivo SQLite de origen."""
    if not ruta.exists():
        raise FileNotFoundError(f"No existe la base SQLite de origen: {ruta}")

    conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    conexion.row_factory = sqlite3.Row
    try:
        filas = conexion.execute(
            """
            SELECT id, fecha, duracion_audio_s, pregunta, pregunta_normalizada,
                   respuesta, origen_respuesta, tema, idioma, estado,
                   ms_subida, ms_stt, ms_respuesta, ms_tts, ms_total,
                   audio_guardado, archivo_audio, detalle_error
            FROM interacciones
            ORDER BY id
            """
        ).fetchall()
    except sqlite3.Error as error:
        raise RuntimeError(f"La base SQLite no tiene el esquema esperado: {error}")
    finally:
        conexion.close()
    return [dict(fila) for fila in filas]


def migrar(fuente: Path, destino_url: str, forzar: bool = False) -> dict:
    """Copia el historial de SQLite a PostgreSQL y verifica los conteos."""
    motor = create_engine(destino_url, future=True)
    crear_todo(motor)
    sesion_factory = sessionmaker(bind=motor, future=True)

    with sesion_factory() as sesion:
        repositorio = RepositorioInteracciones(sesion)

        if not forzar and repositorio.leer_metadato(MARCA_MIGRACION):
            return {
                "estado": "omitida",
                "motivo": "La migracion ya se habia ejecutado.",
                "importados": 0,
            }

        registros = leer_sqlite(fuente)
        if not registros:
            return {
                "estado": "omitida",
                "motivo": "La base SQLite no tiene interacciones.",
                "importados": 0,
            }

        for registro in registros:
            repositorio.registrar(registro)
        sesion.flush()

        repositorio.marcar_metadato(
            MARCA_MIGRACION,
            datetime.now().isoformat(timespec="seconds"),
        )
        sesion.commit()

        # Verificacion: los conteos de PostgreSQL deben coincidir con los del origen.
        total_pg = repositorio.contar()
        por_tema_pg = {
            fila["tema"]: fila["cantidad"] for fila in repositorio.conteo_por_tema()
        }

        conteo_sqlite = {}
        conexion = sqlite3.connect(f"file:{fuente}?mode=ro", uri=True)
        try:
            for tema, cantidad in conexion.execute(
                "SELECT tema, COUNT(*) FROM interacciones GROUP BY tema"
            ):
                conteo_sqlite[tema] = cantidad
        finally:
            conexion.close()

        if total_pg != len(registros) or conteo_sqlite != por_tema_pg:
            raise RuntimeError(
                "La verificacion fallo: "
                f"origen={len(registros)} postgres={total_pg}; "
                f"temas_origen={conteo_sqlite} temas_postgres={por_tema_pg}"
            )

        return {
            "estado": "migrada",
            "importados": total_pg,
            "por_tema": por_tema_pg,
            "verificacion": "coincide con el origen",
        }

    motor.dispose()


def main() -> int:
    analizador = argparse.ArgumentParser(
        description="Migra el historial de SQLite a PostgreSQL."
    )
    analizador.add_argument(
        "--fuente",
        type=Path,
        default=RUTA_BASE_SQLITE,
        help="Ruta de la base SQLite de origen.",
    )
    analizador.add_argument(
        "--destino",
        default=None,
        help="URL de PostgreSQL de destino. Por defecto usa YACHAYBOT_DB_URL.",
    )
    analizador.add_argument(
        "--forzar",
        action="store_true",
        help="Vuelve a migrar aunque la marca ya exista.",
    )
    argumentos = analizador.parse_args()

    destino = argumentos.destino or url_datos()
    try:
        resultado = migrar(argumentos.fuente, destino, argumentos.forzar)
    except Exception as error:
        print(f"[migracion] ERROR: {error}")
        return 1

    if resultado["estado"] == "omitida":
        print(f"[migracion] Omitida: {resultado['motivo']}")
        return 0

    print(
        f"[migracion] {resultado['importados']} interacciones migradas a PostgreSQL. "
        f"Verificacion: {resultado['verificacion']}."
    )
    for tema, cantidad in sorted(resultado["por_tema"].items()):
        print(f"  - {tema}: {cantidad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
