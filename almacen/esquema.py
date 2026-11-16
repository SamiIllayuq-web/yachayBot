"""Esquema de datos de YACHAYBOT en PostgreSQL.

El esquema conserva los nombres de campo de la v1 (SQLite) para que los
conteos, el panel y las citas [ID n] del agente signifiquen exactamente lo
mismo que en la version 1.

Se declaran modelos ORM (para escribir) y se exponen las tablas del Core (para
consultar). El SQL de los agregados es explicito y visible, lo que importa en
una defensa de proyecto.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base

# Convencion de nombres explicita: las migraciones de Alembic y el historial
# de la base de datos comparten la misma nomenclatura.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


class Interaccion(Base):
    """Una conversacion registrada por el robot."""

    __tablename__ = "interacciones"

    # Identificador estable. En SQLite era INTEGER PRIMARY KEY AUTOINCREMENT;
    # aqui es una secuencia de PostgreSQL, que es su equivalente nativo.
    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(DateTime, nullable=False)
    duracion_audio_s = Column(Float)
    pregunta = Column(Text, nullable=False)
    pregunta_normalizada = Column(Text, nullable=False)
    respuesta = Column(Text)
    origen_respuesta = Column(String(64))
    tema = Column(String(64), nullable=False)
    idioma = Column(String(64), nullable=False)
    estado = Column(String(64), nullable=False)
    ms_subida = Column(Integer)
    ms_stt = Column(Integer)
    ms_respuesta = Column(Integer)
    ms_tts = Column(Integer)
    ms_total = Column(Integer)
    audio_guardado = Column(Boolean, nullable=False, default=False)
    archivo_audio = Column(Text)
    detalle_error = Column(Text)

    __table_args__ = (
        Index("ix_interacciones_fecha", "fecha"),
        Index("ix_interacciones_tema", "tema"),
        Index("ix_interacciones_estado", "estado"),
    )


class Metadato(Base):
    """Clave-valor interno del sistema (marcas de migracion, etc.)."""

    __tablename__ = "metadatos"

    clave = Column(String(128), primary_key=True)
    valor = Column(Text)


# Tablas del Core, para consultas y agregados.
interacciones = Interaccion.__table__
metadatos = Metadato.__table__


def crear_todo(motor) -> None:
    """Crea las tablas que no existen. Idempotente."""
    Base.metadata.create_all(motor)
