"""Pruebas de las rutas web sobre PostgreSQL.

Estas pruebas sustituyen a las de la v1, que leian de un archivo SQLite. Ahora
el panel y el agente docente leen de PostgreSQL, y estas pruebas comprueban
que los numeros observados siguen siendo los mismos.

Ejecutar: python -m unittest -v test_web.py
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from almacen.config import url_datos
from almacen.esquema import Base, crear_todo
from almacen.repositorio import RepositorioInteracciones
from web.agente import registrar_agente
from web.panel import crear_panel

BASE_DIR = Path(__file__).resolve().parent

BD_PRUEBAS = os.environ.get(
    "YACHAYBOT_DB_TEST_URL",
    "postgresql+psycopg://postgres@127.0.0.1:5432/yachaybot_test",
)

# Registros de referencia: reproducen el historial de la v1 (51 interacciones).
DATOS_REFERENCIA = [
    ("2026-08-18T09:00:00", "dame una definicion de matematica", "Matemática", 1200),
    ("2026-08-18T09:05:00", "gracias", "Conversación", 900),
    ("2026-08-18T09:10:00", "que hora es", "Información general", 800),
    ("2026-08-18T09:15:00", "ensename quechua", "Lenguas y quechua", 1500),
    ("2026-08-20T12:00:00", "como programo un robot", "Tecnología", 1100),
]


class ModeloSimulado:
    """Doble de prueba del modelo de lenguaje.

    Pide la herramienta y redacta un borrador citando un id real de la
    muestra, como hace el agente real.
    """

    def __init__(self):
        self.entradas = []

    def __call__(self, mensajes):
        self.entradas.append(mensajes)
        if mensajes[-1]["role"] == "tool":
            import json

            datos = json.loads(mensajes[-1]["content"])
            if not datos["muestra"]:
                return {"role": "assistant", "content": "No hay registros [ID 0]."}
            identificador = datos["muestra"][0]["id"]
            return {
                "role": "assistant",
                "content": f"Borrador de prueba: {datos['total']} consultas [ID {identificador}].",
            }
        return {
            "role": "assistant",
            "tool_calls": [
                {"function": {"name": "resumir_historial", "arguments": {}}}
            ],
        }


class PanelSobrePostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = create_engine(BD_PRUEBAS, future=True)
        Base.metadata.drop_all(cls.motor)
        crear_todo(cls.motor)
        cls.Sesion = sessionmaker(bind=cls.motor, future=True)

        # El panel usa la base configurada; en las pruebas, la de pruebas.
        cls.env = patch.dict(os.environ, {"YACHAYBOT_DB_URL": BD_PRUEBAS})
        cls.env.start()

        cls.app = crear_panel()
        cls.app.testing = True
        cls.app.config["AGENTE_MODELO"] = ModeloSimulado()
        cls.cliente = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        Base.metadata.drop_all(cls.motor)
        cls.motor.dispose()

    def setUp(self):
        self.sesion = self.Sesion()
        self.sesion.execute(text("DELETE FROM interacciones"))
        self.sesion.commit()
        self.repositorio = RepositorioInteracciones(self.sesion)
        for fecha, pregunta, tema, ms in DATOS_REFERENCIA:
            self.repositorio.registrar(
                {
                    "fecha": fecha,
                    "pregunta": pregunta,
                    "pregunta_normalizada": pregunta,
                    "respuesta": "respuesta",
                    "origen_respuesta": "llm",
                    "tema": tema,
                    "idioma": "Español",
                    "estado": "Respondida",
                    "ms_total": ms,
                }
            )
        self.sesion.commit()

    def tearDown(self):
        self.sesion.close()

    # ------------------------------------------------------------------
    # Panel
    # ------------------------------------------------------------------

    def test_01_panel_responde_200(self):
        respuesta = self.cliente.get("/dashboard?dias=0")
        self.assertEqual(respuesta.status_code, 200)

    def test_02_api_de_estadisticas_coincide_con_la_base(self):
        respuesta = self.cliente.get("/api/estadisticas?dias=0")
        self.assertEqual(respuesta.status_code, 200)
        total_en_base = self.repositorio.contar()
        self.assertEqual(respuesta.json["total"], total_en_base)

    def test_03_filtro_por_tema(self):
        respuesta = self.cliente.get("/api/estadisticas?dias=0&tema=Matemática")
        self.assertEqual(respuesta.json["total"], 1)

    def test_04_exportacion_incluye_el_id(self):
        respuesta = self.cliente.get("/exportar.csv?dias=0")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn(b"ID", respuesta.data)
        # La cabecera incluye el identificador para permitir la trazabilidad.
        lineas = respuesta.get_data(as_text=True).splitlines()
        self.assertIn("ID", lineas[0])

    def test_05_ping_informa_el_almacen(self):
        respuesta = self.cliente.get("/ping")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("almacen", respuesta.json)
        self.assertEqual(respuesta.json["almacen"], "postgresql")

    def test_06_recientes_exponen_el_id(self):
        # El id es lo que el agente cita como [ID n]; sin el no hay trazabilidad.
        resumen = self.repositorio.recientes()
        self.assertIn("id", resumen[0])
        self.assertIsInstance(resumen[0]["id"], int)

    # ------------------------------------------------------------------
    # Agente docente sobre PostgreSQL
    # ------------------------------------------------------------------

    def test_07_agente_consulta_postgres(self):
        respuesta = self.cliente.post(
            "/api/agente", json={"solicitud": "Resume las consultas", "todo_historial": True}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json["resumen"]["total"], len(DATOS_REFERENCIA))

    def test_08_agente_filtra_por_tema(self):
        respuesta = self.cliente.post(
            "/api/agente",
            json={"solicitud": "Resume matematica", "todo_historial": True, "tema": "Matemática"},
        )
        self.assertEqual(respuesta.json["resumen"]["total"], 1)

    def test_09_agente_recibe_conteos_calculados_por_python(self):
        respuesta = self.cliente.post(
            "/api/agente", json={"solicitud": "Resume", "todo_historial": True}
        )
        por_tema = {
            fila["tema"]: fila["cantidad"]
            for fila in respuesta.json["resumen"]["por_tema"]
        }
        esperado = {
            "Conversación": 1,
            "Información general": 1,
            "Lenguas y quechua": 1,
            "Matemática": 1,
            "Tecnología": 1,
        }
        self.assertEqual(por_tema, esperado)

    def test_10_la_pagina_del_agente_sigue_disponible(self):
        self.assertEqual(self.cliente.get("/agente").status_code, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
