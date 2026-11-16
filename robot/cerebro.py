"""Cerebro de YACHAYBOT: comprension del texto y respuestas.

Contiene la logica que no necesita base de datos ni audio: normalizacion,
wake word, clasificacion tematica, deteccion de idioma y las respuestas
exactas que nunca deben ser inventadas por el modelo de lenguaje.
"""

import re
import unicodedata
from datetime import datetime

# ----------------------------- Normalizacion -----------------------------


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes, sin puntuacion y con espacios colapsados."""
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


# ----------------------------- Wake word -----------------------------

VARIANTES_WAKE = (
    "yachaybot",
    "yachay bot",
    "yachaibot",
    "yachai bot",
    "yachay pod",
)


def contiene_wake_word(texto: str) -> bool:
    """Acepta variantes frecuentes de transcripcion del nombre Yachaybot."""
    limpio = normalizar_texto(texto)
    if len(limpio.split()) > 20:
        return False
    return any(variante in limpio for variante in VARIANTES_WAKE)


def extraer_pregunta_con_wake(texto: str) -> str:
    """Extrae lo dicho junto al nombre del robot, si existe una pregunta."""
    limpio = normalizar_texto(texto)
    for variante in sorted(VARIANTES_WAKE, key=len, reverse=True):
        posicion = limpio.find(variante)
        if posicion >= 0:
            resto = (limpio[:posicion] + " " + limpio[posicion + len(variante):]).strip()
            resto = re.sub(r"\s+", " ", resto)
            # "hola", "oye" o "por favor" no constituyen por si solos una consulta.
            palabras_vacias = {"hola", "oye", "por", "favor", "robot"}
            utiles = [p for p in resto.split() if p not in palabras_vacias]
            return resto if len(utiles) >= 2 else ""
    return ""


# ----------------------------- Clasificacion tematica -----------------------------

CATEGORIAS_TEMATICAS = {
    "Matemática": (
        "matematica", "numero", "suma", "resta", "multiplicacion", "division",
        "fraccion", "decimal", "geometria", "triangulo", "cuadrado",
        "algebra", "ecuacion", "porcentaje", "raiz", "potencia", "logaritmo",
        "angulo", "perimetro", "area", "volumen", "estadistica", "promedio",
        "figura", "materia", "sustantivo", "adjetivo", "verbo",
        "problema matematico",
    ),
    "Comunicación": (
        "comunicacion", "expresion", "lenguaje", "redaccion", "ortografia",
        "lectura", "escritura", "carta", "resumen", "exposicion", "discurso",
        "significado", "signos", "puntuacion", "diccionario",
    ),
    "Ciencias naturales": (
        "ciencia", "biologia", "quimica", "fisica", "celula", "planta",
        "animal", "ecosistema", "agua", "aire", "cuerpo", "seres vivos",
        "fotosintesis", "atomo", "energia", "fuerza", "gravedad",
    ),
    "Ciencias sociales": (
        "historia", "geografia", "peru", "huancavelica", "tayacaja", "inca",
        "independencia", "guerra", "presidente", "departamento", "provincia",
        "distrito", "mapa", "pais", "continente", "cultura",
    ),
    "Tecnología": (
        "tecnologia", "robot", "computadora", "internet", "programacion",
        "codigo", "inteligencia artificial", "celular", "wifi", "sensor",
    ),
    "Lenguas y quechua": (
        "quechua", "runa simi", "allinllachu", "imaynalla", "sulpayki",
        "idioma", "traducir", "traduccion",
    ),
    "Convivencia y bienestar": (
        "amistad", "amigo", "familia", "respeto", "violencia", "bullying",
        "acoso", "miedo", "triste", "tristeza", "enojado", "salud",
        "higiene", "alimentacion", "emocion", "convivencia",
    ),
}

# Palabras sueltas que no bastan para clasificar. Son tan comunes en
# cualquier frase que producirian falsos positivos: "area" (la de una
# figura o de un terreno), "agua" (el recurso o el tema), "mapa", "pais",
# "robot" (el propio nombre del dispositivo que el estudiante menciona al
# preguntarle a Yachaybot), "codigo", "cultura", "idioma".
# Se comparan por palabra completa, no por prefijo: ver _coincide_palabra.
PALABRAS_CORTAS_EXCLUIDAS = frozenset(
    {"area", "agua", "aire", "mapa", "pais", "cultura", "codigo", "idioma"}
)


def _coincide_palabra(termino: str, tokens: set, limpio: str) -> bool:
    """Indica si un termino aparece en el texto.

    La coincidencia es por palabra completa. La v1 comparaba por prefijo, lo
    que hacia que 'restaurante' contenga 'resta' y se clasificara como
    matematica (regresion EX05).
    """
    if " " in termino:
        return termino in limpio
    if termino in PALABRAS_CORTAS_EXCLUIDAS:
        return False
    return termino in tokens


def clasificar_tema(texto: str) -> str:
    """Devuelve la categoria tematica de una consulta."""
    limpio = normalizar_texto(texto)
    tokens = set(limpio.split())
    mejor_tema = "Otros"
    mejor_puntaje = 0

    for tema, palabras in CATEGORIAS_TEMATICAS.items():
        puntaje = 0
        for palabra in palabras:
            termino = normalizar_texto(palabra)
            if _coincide_palabra(termino, tokens, limpio):
                puntaje += 2 if " " in termino else 1
        if puntaje > mejor_puntaje:
            mejor_tema = tema
            mejor_puntaje = puntaje

    if mejor_puntaje == 0 and any(
        frase in limpio for frase in ("que hora", "que fecha", "que dia", "como te llamas")
    ):
        return "Información general"
    if mejor_puntaje == 0 and any(
        palabra in tokens for palabra in ("hola", "gracias", "adios", "buenos", "buenas")
    ):
        return "Conversación"
    return mejor_tema


def detectar_idioma(texto: str) -> str:
    """Detecta si se solicita quechua. No certifica competencia bilingue."""
    limpio = normalizar_texto(texto)
    indicadores = ("quechua", "runa simi", "allinllachu", "imaynalla", "sulpayki")
    return "Quechua solicitado" if any(x in limpio for x in indicadores) else "Español"


# ----------------------------- Respuestas locales -----------------------------

DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

# Agregar aqui solo respuestas revisadas por una persona competente en la
# variedad de quechua que se usara en Tayacaja. Se deja vacio intencionalmente.
# Ejemplo de estructura (NO copiar como traduccion):
# RESPUESTAS_QUECHUA_VALIDADAS["clave normalizada"] = "respuesta validada"
RESPUESTAS_QUECHUA_VALIDADAS = {}


def buscar_respuesta_quechua_validada(texto: str):
    """Respuesta en quechua validada por un hablante, si existe."""
    return RESPUESTAS_QUECHUA_VALIDADAS.get(normalizar_texto(texto))


def respuesta_hora(ahora: datetime) -> str:
    hora_12 = ahora.hour % 12 or 12
    periodo = (
        "de la manana" if ahora.hour < 12 else ("de la tarde" if ahora.hour < 19 else "de la noche")
    )
    if ahora.minute == 0:
        minuto_texto = "en punto"
    elif ahora.minute == 1:
        minuto_texto = "y un minuto"
    else:
        minuto_texto = f"y {ahora.minute} minutos"
    inicio = "Es la" if hora_12 == 1 else "Son las"
    return f"{inicio} {hora_12} {minuto_texto} {periodo}."


def respuesta_fecha(ahora: datetime) -> str:
    return (
        f"Hoy es {DIAS[ahora.weekday()]}, {ahora.day} de "
        f"{MESES[ahora.month - 1]} de {ahora.year}."
    )


def responder_localmente(texto: str):
    """Respuestas exactas que nunca deben ser inventadas por el LLM."""
    limpio = normalizar_texto(texto)
    ahora = datetime.now()  # La laptop debe tener configurada la hora de Peru.

    frases_hora = ("que hora", "dime la hora", "hora actual", "cual es la hora")
    if any(frase in limpio for frase in frases_hora):
        return respuesta_hora(ahora)

    frases_fecha = (
        "que fecha", "fecha de hoy", "que dia es", "dime la fecha", "dia de hoy"
    )
    if any(frase in limpio for frase in frases_fecha):
        return respuesta_fecha(ahora)

    if "como te llamas" in limpio or "cual es tu nombre" in limpio:
        return "Me llamo Yachaybot, y estoy aqui para aprender contigo."

    if "quechua" in limpio and any(
        palabra in limpio for palabra in ("hablar", "responder", "sabes", "puedes")
    ):
        return (
            "Por ahora converso en espanol. Mis respuestas en quechua se "
            "incorporaran despues de ser revisadas por un hablante competente."
        )

    return None
