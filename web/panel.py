"""Panel docente de YACHAYBOT: estadisticas, historial y exportacion.

Las rutas leen de PostgreSQL mediante el almacen. Los indicadores calculados
aqui son los mismos que muestra la v1, con una diferencia deliberada: las
filas recientes y la exportacion incluyen el identificador del registro, que
es lo que permite al agente citar [ID n] de forma trazable.
"""

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, render_template, request, url_for

from almacen.sesiones import sesion_datos
from almacen.repositorio import RepositorioInteracciones

DIAS_VALIDOS = (0, 7, 30, 90, 365)


def leer_filtros_peticion():
    """Lee los filtros de la peticion: dias y tema. Valores no validos -> 30 dias."""
    try:
        dias = int(request.args.get("dias", "30"))
    except ValueError:
        dias = 30
    if dias not in DIAS_VALIDOS:
        dias = 30
    return dias, request.args.get("tema", "Todos").strip() or "Todos"


def _rango_por_dias(dias: int):
    """Devuelve el limite inferior del filtro temporal, o None para todo el historial."""
    if dias <= 0:
        return None, None
    desde = datetime.now() - timedelta(days=dias)
    return desde.isoformat(timespec="seconds"), None


def obtener_estadisticas(dias=30, tema="Todos") -> dict:
    """Los indicadores del panel, calculados en la base de datos."""
    desde, hasta = _rango_por_dias(dias)

    with sesion_datos() as sesion:
        repositorio = RepositorioInteracciones(sesion)
        resumen = repositorio.resumen(tema=tema, desde=desde, hasta=hasta)
        por_tema = repositorio.conteo_por_tema(tema=tema, desde=desde, hasta=hasta)
        por_dia = repositorio.conteo_por_dia(tema=tema, desde=desde, hasta=hasta)
        frecuentes = repositorio.preguntas_frecuentes(
            tema=tema, desde=desde, hasta=hasta
        )
        recientes = repositorio.recientes(tema=tema, desde=desde, hasta=hasta)
        temas_disponibles = repositorio.temas_disponibles()

    total = resumen["total"]
    max_tema = max((fila["cantidad"] for fila in por_tema), default=1)
    max_dia = max((fila["cantidad"] for fila in por_dia), default=1)

    return {
        **resumen,
        "por_tema": [
            {
                "tema": fila["tema"],
                "cantidad": fila["cantidad"],
                "porcentaje": round(fila["cantidad"] * 100 / total, 1) if total else 0,
                "ancho": round(fila["cantidad"] * 100 / max_tema, 1),
            }
            for fila in por_tema
        ],
        "frecuentes": frecuentes,
        "recientes": recientes,
        "por_dia": [
            {
                "dia": fila["dia"],
                "cantidad": fila["cantidad"],
                "ancho": round(fila["cantidad"] * 100 / max_dia, 1),
            }
            for fila in reversed(por_dia)
        ],
        "temas_disponibles": temas_disponibles,
    }


def crear_panel():
    """Crea la aplicacion Flask con el panel y las rutas del agente."""
    from flask import Flask

    from web.agente import registrar_agente

    app = Flask(
        __name__,
        template_folder=str(__import__("pathlib").Path(__file__).resolve().parent.parent / "templates"),
    )

    # El blueprint no lleva nombre propio para que los endpoints se
    # llame dashboard, api_estadisticas y exportar_csv, igual que en la v1.
    # Los templates los usan con url_for y no deben cambiar.
    bp = Blueprint(__name__.rsplit(".", 1)[-1], __name__)

    @bp.get("/dashboard")
    def dashboard():
        dias, tema = leer_filtros_peticion()
        estadisticas = obtener_estadisticas(dias, tema)
        opciones_dias = (
            (7, "Ultimos 7 dias"),
            (30, "Ultimos 30 dias"),
            (90, "Ultimos 90 dias"),
            (365, "Ultimo ano"),
            (0, "Todo el historial"),
        )
        return render_template(
            "dashboard.html",
            datos=estadisticas,
            dias=dias,
            tema_seleccionado=tema,
            opciones_dias=opciones_dias,
            exportar_url=url_for("panel.exportar_csv", dias=dias, tema=tema),
        )

    @bp.get("/api/estadisticas")
    def api_estadisticas():
        dias, tema = leer_filtros_peticion()
        datos = obtener_estadisticas(dias, tema)
        return jsonify(
            {
                "filtros": {"dias": dias, "tema": tema},
                "total": datos["total"],
                "respondidas": datos["respondidas"],
                "incidencias": datos["incidencias"],
                "porcentaje_exito": datos["porcentaje_exito"],
                "promedio_s": datos["promedio_s"],
                "por_tema": datos["por_tema"],
                "preguntas_frecuentes": datos["frecuentes"],
                "por_dia": datos["por_dia"],
            }
        )

    @bp.get("/exportar.csv")
    def exportar_csv():
        dias, tema = leer_filtros_peticion()
        desde, hasta = _rango_por_dias(dias)
        with sesion_datos() as sesion:
            repositorio = RepositorioInteracciones(sesion)
            filas = repositorio.exportar(tema=tema, desde=desde, hasta=hasta)

        salida = io.StringIO(newline="")
        escritor = csv.writer(salida, delimiter=";")
        escritor.writerow(
            (
                "ID", "Fecha", "Pregunta anónima", "Tema", "Idioma", "Respuesta",
                "Estado", "Origen", "STT ms", "Respuesta ms", "TTS ms", "Total ms",
            )
        )
        for fila in filas:
            escritor.writerow(
                (
                    fila["id"], fila["fecha"], fila["pregunta"], fila["tema"],
                    fila["idioma"], fila["respuesta"], fila["estado"],
                    fila["origen_respuesta"], fila["ms_stt"], fila["ms_respuesta"],
                    fila["ms_tts"], fila["ms_total"],
                )
            )

        contenido = "\ufeff" + salida.getvalue()
        nombre = f"yachaybot_interacciones_{datetime.now():%Y%m%d_%H%M}.csv"
        return Response(
            contenido,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
        )

    # El blueprint se registra sin prefijo para conservar los nombres de
    # endpoint de la v1 (dashboard, api_estadisticas, exportar_csv). Los
    # templates los usan tal cual y no deben cambiar.
    app.register_blueprint(bp)

    registrar_agente(app, lambda: "")

    @app.get("/ping")
    def ping():
        from almacen.sesiones import sesion_datos as _sesion

        try:
            with _sesion() as sesion:
                total = RepositorioInteracciones(sesion).contar()
        except Exception:  # noqa: BLE001
            total = None
        return {
            "estado": "ok",
            "robot": "YACHAYBOT",
            "almacen": "postgresql",
            "interacciones_guardadas": total,
        }

    return app
