"""Entorno de Alembic para YACHAYBOT.

La URL de la base se resuelve en tiempo de ejecucion desde la configuracion
del almacen, de modo que las migraciones usen siempre la misma base que la
aplicacion, sin duplicar credenciales en el archivo de configuracion.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from almacen.config import url_datos
from almacen.esquema import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# La URL real viene del almacen (variable de entorno o valor de desarrollo).
config.set_main_option("sqlalchemy.url", url_datos())

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin ejecutarlas."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Ejecuta las migraciones contra la base configurada."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
