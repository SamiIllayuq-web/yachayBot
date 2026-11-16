"""Repositorio de interacciones: la interfaz publica del almacen.

Este es el unico lugar del sistema donde se escribe SQL. Quien lo consume
pide datos con significado (un resumen, un conteo, una muestra) y recibe
diccionarios planos, sin conocer el motor ni el dialecto.

Todos los valores llegan como parametros vinculados. Nunca se concatena
entrada del usuario dentro de una cadena SQL.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import Integer, cast, func, select

from almacen.esquema import Interaccion, Metadato


def _a_fecha(valor):
    """Acepta 'AAAA-MM-DD' o un datetime y devuelve un datetime comparable."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    return datetime.fromisoformat(str(valor))


class RepositorioInteracciones:
    """Operaciones sobre las interacciones del robot.

    La instancia recibe una sesion de SQLAlchemy. El repositorio no abre ni
    cierra conexiones: eso es responsabilidad de quien lo construye.
    """

    def __init__(self, sesion):
        self.sesion = sesion

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def registrar(self, registro: dict) -> Interaccion:
        """Guarda una interaccion y devuelve el objeto con su id asignado.

        No hace commit: la transaccion la decide quien llama, de modo que el
        robot pueda seguir respondiendo aunque el guardado falle.
        """
        campos = {
            "fecha": _a_fecha(registro.get("fecha")) or datetime.now(),
            "duracion_audio_s": registro.get("duracion_audio_s"),
            "pregunta": registro.get("pregunta") or "(sin transcripcion)",
            "pregunta_normalizada": registro.get("pregunta_normalizada") or "",
            "respuesta": registro.get("respuesta"),
            "origen_respuesta": registro.get("origen_respuesta"),
            "tema": registro.get("tema") or "Otros",
            "idioma": registro.get("idioma") or "Español",
            "estado": registro.get("estado") or "Respondida",
            "ms_subida": registro.get("ms_subida"),
            "ms_stt": registro.get("ms_stt"),
            "ms_respuesta": registro.get("ms_respuesta"),
            "ms_tts": registro.get("ms_tts"),
            "ms_total": registro.get("ms_total"),
            "audio_guardado": bool(registro.get("audio_guardado", False)),
            "archivo_audio": registro.get("archivo_audio"),
            "detalle_error": registro.get("detalle_error"),
        }
        interaccion = Interaccion(**campos)
        self.sesion.add(interaccion)
        self.sesion.flush()
        return interaccion

    def marcar_metadato(self, clave: str, valor: str) -> None:
        """Guarda una marca interna (por ejemplo, una migracion ya hecha)."""
        existente = self.sesion.get(Metadato, clave)
        if existente is None:
            self.sesion.add(Metadato(clave=clave, valor=valor))
        else:
            existente.valor = valor
        self.sesion.flush()

    def leer_metadato(self, clave: str):
        marca = self.sesion.get(Metadato, clave)
        return marca.valor if marca is not None else None

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def _condiciones(self, tema=None, desde=None, hasta=None):
        """Construye las condiciones de filtro y sus parametros."""
        condiciones = []
        if tema and tema != "Todos":
            condiciones.append(Interaccion.tema == tema)
        if desde is not None:
            condiciones.append(Interaccion.fecha >= _a_fecha(desde))
        if hasta is not None:
            condiciones.append(Interaccion.fecha < _a_fecha(hasta))
        return condiciones

    def resumen(self, tema=None, desde=None, hasta=None) -> dict:
        """Totales, respondidas, incidencias y promedio de tiempo.

        Reproduce exactamente los indicadores que muestra el panel en la v1:
        porcentaje_exito = respondidas * 100 / total, y promedio_s es el
        promedio de ms_total solo sobre los valores positivos.
        """
        condiciones = self._condiciones(tema, desde, hasta)

        fila = self.sesion.execute(
            select(
                func.count(Interaccion.id).label("total"),
                func.sum(
                    cast(Interaccion.estado == "Respondida", Integer)
                ).label("respondidas"),
                func.sum(
                    cast(Interaccion.estado != "Respondida", Integer)
                ).label("incidencias"),
                func.avg(
                    cast(Interaccion.ms_total > 0, Integer) * Interaccion.ms_total
                ).label("promedio_ms"),
            ).where(*condiciones)
        ).one()

        total = int(fila.total or 0)
        respondidas = int(fila.respondidas or 0)
        incidencias = int(fila.incidencias or 0)
        promedio_ms = fila.promedio_ms or 0

        return {
            "total": total,
            "respondidas": respondidas,
            "incidencias": incidencias,
            "porcentaje_exito": round(respondidas * 100 / total, 1) if total else 0,
            "promedio_s": round(float(promedio_ms) / 1000, 2),
        }

    def conteo_por_tema(self, tema=None, desde=None, hasta=None) -> list:
        """Frecuencia por tema, de mayor a menor."""
        condiciones = self._condiciones(tema, desde, hasta)
        filas = self.sesion.execute(
            select(Interaccion.tema, func.count(Interaccion.id).label("cantidad"))
            .where(*condiciones)
            .group_by(Interaccion.tema)
            .order_by(func.count(Interaccion.id).desc(), Interaccion.tema)
        ).all()
        return [{"tema": f.tema, "cantidad": f.cantidad} for f in filas]

    def conteo_por_dia(self, tema=None, desde=None, hasta=None) -> list:
        """Frecuencia por dia (fecha sin hora), del dia mas reciente al mas antiguo."""
        condiciones = self._condiciones(tema, desde, hasta)
        dia = func.date_trunc("day", Interaccion.fecha)
        filas = self.sesion.execute(
            select(dia.label("dia"), func.count(Interaccion.id).label("cantidad"))
            .where(*condiciones)
            .group_by(dia)
            .order_by(dia.desc())
            .limit(14)
        ).all()
        return [{"dia": str(f.dia)[:10], "cantidad": f.cantidad} for f in filas]

    def preguntas_frecuentes(self, tema=None, desde=None, hasta=None, limite=10):
        """Preguntas repetidas, agrupadas por su forma normalizada.

        Excluye las entradas sin transcripcion, igual que la v1.
        """
        condiciones = self._condiciones(tema, desde, hasta)
        condiciones.append(Interaccion.pregunta_normalizada != "sin transcripcion")
        filas = self.sesion.execute(
            select(
                func.min(Interaccion.pregunta).label("pregunta"),
                Interaccion.tema,
                func.count(Interaccion.id).label("cantidad"),
            )
            .where(*condiciones)
            .group_by(Interaccion.pregunta_normalizada, Interaccion.tema)
            .order_by(func.count(Interaccion.id).desc(), func.max(Interaccion.fecha).desc())
            .limit(limite)
        ).all()
        return [
            {"pregunta": f.pregunta, "tema": f.tema, "cantidad": f.cantidad}
            for f in filas
        ]

    def recientes(self, tema=None, desde=None, hasta=None, limite=100) -> list:
        """Ultimas interacciones. Incluye el id para permitir citas [ID n]."""
        condiciones = self._condiciones(tema, desde, hasta)
        filas = self.sesion.execute(
            select(
                Interaccion.id,
                Interaccion.fecha,
                Interaccion.pregunta,
                Interaccion.respuesta,
                Interaccion.tema,
                Interaccion.idioma,
                Interaccion.estado,
                Interaccion.ms_total,
            )
            .where(*condiciones)
            .order_by(Interaccion.fecha.desc(), Interaccion.id.desc())
            .limit(limite)
        ).all()
        return [
            {
                "id": f.id,
                "fecha": f.fecha.isoformat() if f.fecha else None,
                "pregunta": f.pregunta,
                "respuesta": f.respuesta,
                "tema": f.tema,
                "idioma": f.idioma,
                "estado": f.estado,
                "ms_total": f.ms_total,
            }
            for f in filas
        ]

    def muestra(self, tema=None, desde=None, hasta=None, limite=30) -> list:
        """Muestra de registros para el agente docente.

        Se reparte round-robin entre temas para que la muestra sea variada y
        no se concentre en un solo tema. Las preguntas se recortan para no
        volcar textos largos al modelo.
        """
        condiciones = self._condiciones(tema, desde, hasta)
        filas = self.sesion.execute(
            select(
                Interaccion.id,
                Interaccion.fecha,
                Interaccion.pregunta,
                Interaccion.tema,
            )
            .where(*condiciones)
            .order_by(Interaccion.tema, Interaccion.fecha.desc(), Interaccion.id.desc())
        ).all()

        grupos = {}
        for f in filas:
            grupos.setdefault(f.tema, []).append(f)

        muestra = []
        for desplazamiento in range(limite):
            for grupo in grupos.values():
                if desplazamiento < len(grupo) and len(muestra) < limite:
                    f = grupo[desplazamiento]
                    muestra.append(
                        {
                            "id": f.id,
                            "fecha": f.fecha.isoformat() if f.fecha else None,
                            "pregunta": (f.pregunta or "")[:400],
                            "tema": f.tema,
                        }
                    )
        return muestra

    def temas_disponibles(self) -> list:
        """Temas presentes en el historial, sin duplicados y en orden alfabetico."""
        filas = self.sesion.execute(
            select(Interaccion.tema).distinct().order_by(Interaccion.tema)
        ).all()
        return [f.tema for f in filas]

    def exportar(self, tema=None, desde=None, hasta=None) -> list:
        """Filas para la exportacion CSV. Incluye el id para trazabilidad."""
        condiciones = self._condiciones(tema, desde, hasta)
        filas = self.sesion.execute(
            select(
                Interaccion.id,
                Interaccion.fecha,
                Interaccion.pregunta,
                Interaccion.tema,
                Interaccion.idioma,
                Interaccion.respuesta,
                Interaccion.estado,
                Interaccion.origen_respuesta,
                Interaccion.ms_stt,
                Interaccion.ms_respuesta,
                Interaccion.ms_tts,
                Interaccion.ms_total,
            )
            .where(*condiciones)
            .order_by(Interaccion.fecha.desc(), Interaccion.id.desc())
        ).all()
        return [
            {
                "id": f.id,
                "fecha": f.fecha.isoformat() if f.fecha else "",
                "pregunta": f.pregunta,
                "tema": f.tema,
                "idioma": f.idioma,
                "respuesta": f.respuesta,
                "estado": f.estado,
                "origen_respuesta": f.origen_respuesta,
                "ms_stt": f.ms_stt,
                "ms_respuesta": f.ms_respuesta,
                "ms_tts": f.ms_tts,
                "ms_total": f.ms_total,
            }
            for f in filas
        ]

    def contar(self) -> int:
        """Numero total de interacciones registradas."""
        return int(
            self.sesion.execute(select(func.count(Interaccion.id))).scalar() or 0
        )

    def todos_los_registros(self) -> list:
        """Todos los registros, para la migracion y la verificacion de conteos."""
        filas = self.sesion.execute(
            select(
                Interaccion.id,
                Interaccion.fecha,
                Interaccion.duracion_audio_s,
                Interaccion.pregunta,
                Interaccion.pregunta_normalizada,
                Interaccion.respuesta,
                Interaccion.origen_respuesta,
                Interaccion.tema,
                Interaccion.idioma,
                Interaccion.estado,
                Interaccion.ms_subida,
                Interaccion.ms_stt,
                Interaccion.ms_respuesta,
                Interaccion.ms_tts,
                Interaccion.ms_total,
                Interaccion.audio_guardado,
                Interaccion.archivo_audio,
                Interaccion.detalle_error,
            ).order_by(Interaccion.id)
        ).all()
        return [dict(fila._mapping) for fila in filas]

    @staticmethod
    def rango_de_fechas(desde: str, hasta: str):
        """Traduce un periodo 'AAAA-MM-DD' al intervalo [desde, hasta+1 dia).

        El limite superior es exclusivo para incluir todo el dia final.
        """
        inicio = _a_fecha(desde)
        final = _a_fecha(hasta) + timedelta(days=1)
        if inicio is None or final is None:
            raise ValueError("El periodo requiere ambas fechas.")
        return inicio, final
