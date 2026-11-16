"""Pruebas del cerebro del robot: wake word, clasificacion y respuestas.

La clasificacion tematica se prueba con casos de borde, no solo con lo que
funciona. El caso 'restaurante' es el que la v1 entregaba mal: la comparacion
por prefijo hacia coincidir 'resta' dentro de 'restaurante'.

Ejecutar: python -m unittest -v test_robot.py
"""

import unittest

from robot.cerebro import (
    clasificar_tema,
    contiene_wake_word,
    detectar_idioma,
    extraer_pregunta_con_wake,
    normalizar_texto,
    responder_localmente,
)


class Normalizacion(unittest.TestCase):
    def test_01_quita_tildes_y_pasa_a_minusculas(self):
        self.assertEqual(normalizar_texto("Matemática"), "matematica")

    def test_02_puntua_y_palabras_vacias(self):
        self.assertEqual(normalizar_texto("¿Qué es una fracción?"), "que es una fraccion")

    def test_03_colapsa_espacios(self):
        self.assertEqual(normalizar_texto("  hola   mundo  "), "hola mundo")


class WakeWord(unittest.TestCase):
    def test_04_reconoce_el_nombre_del_robot(self):
        self.assertTrue(contiene_wake_word("Yachaybot, que hora es"))

    def test_05_acepta_variantes_de_transcripcion(self):
        self.assertTrue(contiene_wake_word("yachaibot hola"))

    def test_06_no_acepta_texto_largo_sin_el_nombre(self):
        self.assertFalse(contiene_wake_word("esta es una frase larga " * 5))

    def test_07_extrae_la_pregunta_junto_al_nombre(self):
        self.assertEqual(
            extraer_pregunta_con_wake("Yachaybot que hora es"),
            "que hora es",
        )

    def test_08_no_extrae_pregunta_si_solo_hay_saludo(self):
        self.assertEqual(extraer_pregunta_con_wake("Yachaybot hola"), "")


class ClasificacionTematica(unittest.TestCase):
    def test_09_matematica_por_palabra_clave(self):
        self.assertEqual(clasificar_tema("dame una definicion de matematica"), "Matemática")

    def test_10_computacion_por_palabra_clave(self):
        self.assertEqual(clasificar_tema("como programo un robot"), "Tecnología")

    def test_11_quechua_se_detecta_como_tema(self):
        self.assertEqual(clasificar_tema("ensename quechua por favor"), "Lenguas y quechua")

    def test_12_cortesia_es_conversacion(self):
        self.assertEqual(clasificar_tema("gracias"), "Conversación")

    def test_13_pregunta_sin_palabras_clave_es_otros(self):
        self.assertEqual(clasificar_tema("xyzzy plugh"), "Otros")

    # ------------------------------------------------------------------
    # Casos de borde: la v1 fallaba en estos.
    # ------------------------------------------------------------------

    def test_14_restaurante_no_es_matematica(self):
        """Regresion EX05: 'restaurante' empieza con 'resta'.

        La v1 comparaba por prefijo, por lo que una palabra que nada tiene
        que ver con matematicas caia en la categoria equivoca. Ahora la
        coincidencia es por palabra completa.
        """
        self.assertNotEqual(clasificar_tema("quiero ir a un restaurante"), "Matemática")

    def test_15_resta_si_es_matematica(self):
        """El control: la palabra exacta si debe seguir clasificando bien."""
        self.assertEqual(clasificar_tema("haz una resta de 5 y 3"), "Matemática")

    def test_16_resta_con_mas_palabras_sigue_siendo_matematica(self):
        self.assertEqual(clasificar_tema("por favor haz una resta"), "Matemática")

    def test_17_otras_palabras_con_prefijo_matematico(self):
        """Palabras reales que empiezan igual que terminos matematicos.

        La normalizacion convierte los guiones en espacios, asi que un token
        con guion no es una palabra: estos casos son los que un estudiante
        escribiria de verdad.
        """
        for texto in (
            "restaurante de comida",
            "resistencia de materiales",
            "prestamo de dinero",
            "restauracion de muebles",
            "respaldo de informacion",
            "estrenamiento de datos",
        ):
            with self.subTest(texto=texto):
                self.assertNotEqual(clasificar_tema(texto), "Matemática")


class Idioma(unittest.TestCase):
    def test_18_español_por_defecto(self):
        self.assertEqual(detectar_idioma("hola que tal"), "Español")

    def test_19_quechua_solicitado(self):
        self.assertEqual(detectar_idioma("quiero que hables quechua"), "Quechua solicitado")


class RespuestasLocales(unittest.TestCase):
    def test_20_hora_y_fecha_no_se_delegan_al_modelo(self):
        self.assertIsNotNone(responder_localmente("que hora es"))
        self.assertIsNotNone(responder_localmente("que fecha es hoy"))

    def test_21_nombre_del_robot(self):
        self.assertIn("Yachaybot", responder_localmente("como te llamas"))

    def test_22_una_consulta_general_no_tiene_respuesta_local(self):
        self.assertIsNone(responder_localmente("dame una definicion de matematica"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
