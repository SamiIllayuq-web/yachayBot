"""Pruebas del almacen: esquema, escritura, lectura y agregados.

Estas pruebas son la red de seguridad de la migracion a PostgreSQL. Verifican
que los conteos observados en la v1 (SQLite) se reproducen exactamente en
PostgreSQL, porque el panel y el agente docente dependen de esos numeros.

Ejecutar: python -m unittest -v test_almacen.py
"""

import os
import unittest
from pathlib import Path

from sqlalchemy import text

from almacen.config import url_datos
from almacen.esquema import Base, crear_todo
from almacen.repositorio import RepositorioInteracciones

# Base de pruebas aislada. Se crea una vez y se limpia entre pruebas.
BD_PRUEBAS = os.environ.get(
    "YACHAYBOT_DB_TEST_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5432/yachaybot_test",
)


def motor_de_pruebas():
    from sqlalchemy import create_engine

    return create_engine(BD_PRUEBAS, future=True)


class AlmacenPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = motor_de_pruebas()
        from sqlalchemy.orm import sessionmaker

        cls.Sesion = sessionmaker(bind=cls.motor, future=True)
        Base.metadata.drop_all(cls.motor)
        crear_todo(cls.motor)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(cls.motor)
        cls.motor.dispose()

    def setUp(self):
        self.sesion = self.Sesion()
        self.repositorio = RepositorioInteracciones(self.sesion)
        # Cada prueba arranca con una tabla vacia y comprobable.
        self.sesion.execute(text("DELETE FROM interacciones"))
        self.sesion.commit()

    def tearDown(self):
        self.sesion.close()

    def registrar(self, **campos):
        base = {
            "fecha": "2026-08-18T09:00:00",
            "pregunta": "¿Qué es una fracción?",
            "pregunta_normalizada": "que es una fraccion",
            "respuesta": "Es una parte de un todo.",
            "origen_respuesta": "llm",
            "tema": "Matemática",
            "idioma": "Español",
            "estado": "Respondida",
            "ms_total": 1200,
        }
        base.update(campos)
        return self.repositorio.registrar(base)

    # ------------------------------------------------------------------
    # Esquema
    # ------------------------------------------------------------------

    def test_01_esquema_tiene_tabla_interacciones(self):
        filas = self.sesion.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='interacciones'"
            )
        ).all()
        self.assertEqual(len(filas), 1)

    def test_02_id_es_una_secuencia_y_no_se_reutiliza(self):
        primero = self.registrar()
        segundo = self.registrar(pregunta="otra pregunta")
        self.assertIsNotNone(primero.id)
        self.assertGreater(segundo.id, primero.id)

    def test_03_tabla_metadatos_existe(self):
        self.sesion.execute(
            text("INSERT INTO metadatos (clave, valor) VALUES ('x','y')")
        )
        self.sesion.commit()
        valor = self.sesion.execute(
            text("SELECT valor FROM metadatos WHERE clave='x'")
        ).scalar()
        self.assertEqual(valor, "y")

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def test_04_registrar_persiste_y_devuelve_id(self):
        registro = self.registrar()
        self.sesion.commit()
        total = self.sesion.execute(
            text("SELECT COUNT(*) FROM interacciones")
        ).scalar()
        self.assertEqual(total, 1)
        self.assertIsNotNone(registro.id)

    def test_05_campos_tecnicos_se_guardan(self):
        self.registrar(ms_stt=100, ms_respuesta=200, ms_tts=300, ms_total=600)
        self.sesion.commit()
        fila = self.sesion.execute(
            text(
                "SELECT ms_stt, ms_respuesta, ms_tts, ms_total "
                "FROM interacciones LIMIT 1"
            )
        ).one()
        self.assertEqual(tuple(fila), (100, 200, 300, 600))

    def test_06_estado_de_error_se_guarda_con_detalle(self):
        self.registrar(
            estado="Error del servidor", detalle_error="timeout de groq"
        )
        self.sesion.commit()
        fila = self.sesion.execute(
            text("SELECT estado, detalle_error FROM interacciones LIMIT 1")
        ).one()
        self.assertEqual(fila.estado, "Error del servidor")
        self.assertEqual(fila.detalle_error, "timeout de groq")

    # ------------------------------------------------------------------
    # Lectura y agregados (los numeros que el panel y el agente muestran)
    # ------------------------------------------------------------------

    def test_07_resumen_sin_registros_es_cero(self):
        resumen = self.repositorio.resumen()
        self.assertEqual(resumen["total"], 0)
        self.assertEqual(resumen["respondidas"], 0)
        self.assertEqual(resumen["incidencias"], 0)
        self.assertEqual(resumen["porcentaje_exito"], 0)
        self.assertEqual(resumen["promedio_s"], 0)

    def test_08_resumen_cuenta_respondidas_e_incidencias(self):
        self.registrar()
        self.registrar(estado="No comprendida")
        self.registrar(estado="Error del servidor")
        self.sesion.commit()
        resumen = self.repositorio.resumen()
        self.assertEqual(resumen["total"], 3)
        self.assertEqual(resumen["respondidas"], 1)
        self.assertEqual(resumen["incidencias"], 2)
        self.assertEqual(resumen["porcentaje_exito"], 33.3)

    def test_09_resumen_promedio_solo_de_ms_total_positivo(self):
        self.registrar(ms_total=1000)
        self.registrar(ms_total=3000)
        self.registrar(ms_total=None)
        self.sesion.commit()
        resumen = self.repositorio.resumen()
        self.assertEqual(resumen["promedio_s"], 2.0)

    def test_10_conteo_por_tema_ordenado(self):
        self.registrar(tema="Matemática")
        self.registrar(tema="Matemática")
        self.registrar(tema="Otros")
        self.sesion.commit()
        por_tema = self.repositorio.conteo_por_tema()
        self.assertEqual(por_tema[0]["tema"], "Matemática")
        self.assertEqual(por_tema[0]["cantidad"], 2)
        self.assertEqual(por_tema[1]["tema"], "Otros")
        self.assertEqual(por_tema[1]["cantidad"], 1)

    def test_11_filtro_por_tema(self):
        self.registrar(tema="Matemática")
        self.registrar(tema="Otros")
        self.sesion.commit()
        resumen = self.repositorio.resumen(tema="Matemática")
        self.assertEqual(resumen["total"], 1)

    def test_12_filtro_por_rango_de_fechas(self):
        self.registrar(fecha="2026-08-18T09:00:00")
        self.registrar(fecha="2026-08-20T12:00:00")
        self.sesion.commit()
        resumen = self.repositorio.resumen(
            desde="2026-08-18T00:00:00", hasta="2026-08-19T00:00:00"
        )
        self.assertEqual(resumen["total"], 1)

    def test_13_recientes_incluye_el_id(self):
        registro = self.registrar()
        self.sesion.commit()
        recientes = self.repositorio.recientes()
        self.assertEqual(recientes[0]["id"], registro.id)

    def test_14_temas_disponibles_sin_duplicados(self):
        self.registrar(tema="Matemática")
        self.registrar(tema="Matemática")
        self.registrar(tema="Comunicación")
        self.sesion.commit()
        self.assertEqual(
            sorted(self.repositorio.temas_disponibles()), ["Comunicación", "Matemática"]
        )

    def test_15_muestra_para_el_agente_respeta_el_filtro(self):
        self.registrar(tema="Matemática")
        self.registrar(tema="Otros")
        self.sesion.commit()
        muestra = self.repositorio.muestra(tema="Matemática")
        self.assertEqual(len(muestra), 1)
        self.assertEqual(muestra[0]["tema"], "Matemática")

    def test_16_conteo_por_dia(self):
        self.registrar(fecha="2026-08-18T09:00:00")
        self.registrar(fecha="2026-08-18T10:00:00")
        self.registrar(fecha="2026-08-20T12:00:00")
        self.sesion.commit()
        por_dia = self.repositorio.conteo_por_dia()
        dias = {fila["dia"]: fila["cantidad"] for fila in por_dia}
        self.assertEqual(dias["2026-08-18"], 2)
        self.assertEqual(dias["2026-08-20"], 1)

    def test_17_preguntas_frecuentes_excluye_sin_transcripcion(self):
        self.registrar(pregunta="¿Qué es una fracción?")
        self.registrar(pregunta="¿Qué es una fracción?")
        self.registrar(
            pregunta="(sin transcripcion)", pregunta_normalizada="sin transcripcion"
        )
        self.sesion.commit()
        frecuentes = self.repositorio.preguntas_frecuentes()
        self.assertEqual(frecuentes[0]["cantidad"], 2)
        self.assertEqual(len(frecuentes), 1)

    # ------------------------------------------------------------------
    # Seguridad
    # ------------------------------------------------------------------

    def test_18_parametros_se_ligan_y_no_se_concatenan(self):
        # Un tema con comillas debe devolver cero registros, no ejecutar SQL.
        self.registrar(tema="Matemática")
        self.sesion.commit()
        resumen = self.repositorio.resumen(tema="'; DROP TABLE interacciones; --")
        self.assertEqual(resumen["total"], 0)
        # La tabla sigue existiendo.
        total = self.sesion.execute(
            text("SELECT COUNT(*) FROM interacciones")
        ).scalar()
        self.assertEqual(total, 1)

    def test_19_exportacion_incluye_el_id(self):
        registro = self.registrar()
        self.sesion.commit()
        filas = self.repositorio.exportar()
        self.assertEqual(filas[0]["id"], registro.id)

    def test_20_la_base_de_pruebas_es_distinta_de_la_de_produccion(self):
        self.assertNotIn("/yachaybot_test", url_datos())


if __name__ == "__main__":
    unittest.main(verbosity=2)
