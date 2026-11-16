"""Servidor puente mejorado de YACHAYBOT.

Flujo:
1. /wake recibe una frase y solo confirma si contiene "Yachaybot".
2. El ESP32 gira, emite un beep y luego envia la pregunta a /talk.
3. /talk responde hora/fecha localmente y usa Groq para preguntas educativas.
4. Piper genera la voz en espanol y la devuelve como PCM mono a 8 kHz.
5. SQLite guarda la pregunta anonimizada, el tema y los tiempos tecnicos.
6. /dashboard presenta estadisticas para apoyar la planificacion docente.

La futura funcion de quechua queda preparada para incorporar unicamente
respuestas revisadas por un hablante/docente de la variedad local.
"""

import csv
import io
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import wave
from datetime import datetime, timedelta

import numpy as np
import requests
from flask import Flask, Response, jsonify, render_template, request, url_for


# ----------------------------- Configuracion -----------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def leer_clave_groq():
    """Busca la clave en una variable de entorno o en clave.txt."""
    clave = os.environ.get("GROQ_API_KEY", "").strip()
    if clave:
        return clave
    ruta = os.path.join(BASE_DIR, "clave.txt")
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as archivo:
            return archivo.read().strip()
    return ""


GROQ_API_KEY = leer_clave_groq()
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_SESSION = requests.Session()
MODELO_STT = "whisper-large-v3-turbo"
# Groq retiro llama-3.3-70b-versatile para las capas gratuita y developer el
# 16/08/2026. Se permite forzar otro modelo con GROQ_LLM_MODEL, pero por defecto
# se usan los reemplazos de produccion recomendados por Groq.
MODELO_LLM_FORZADO = os.environ.get("GROQ_LLM_MODEL", "").strip()
MODELOS_LLM = (
    (MODELO_LLM_FORZADO,)
    if MODELO_LLM_FORZADO
    else ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
)

IDIOMA_STT = "es"
SAMPLE_RATE_ENTRADA = 16000
SAMPLE_RATE_SALIDA = 8000  # Debe coincidir con SPK_SAMPLE_RATE del ESP32.
PUERTO = 8000

NOMBRE_VOZ = "es_MX-ald-medium"
VELOCIDAD_VOZ = 0.95

# Si se define YACHAYBOT_TOKEN en Windows, se puede exigir el mismo valor en
# las peticiones. Se deja vacio por compatibilidad con el firmware entregado.
SERVER_TOKEN = os.environ.get("YACHAYBOT_TOKEN", "").strip()

BASE_VOCES = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
RUTAS_VOCES = {
    "es_MX-claude-high": "es/es_MX/claude/high/es_MX-claude-high",
    "es_MX-ald-medium": "es/es_MX/ald/medium/es_MX-ald-medium",
    "es_ES-davefx-medium": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "es_ES-sharvard-medium": "es/es_ES/sharvard/medium/es_ES-sharvard-medium",
    "es_AR-daniela-high": "es/es_AR/daniela/high/es_AR-daniela-high",
}

DICCIONARIO_PRONUNCIACION = {
    "Yachaybot": "Yachaibot",
    "YACHAYBOT": "Yachaibot",
}

CARPETA_DATOS = os.environ.get(
    "YACHAYBOT_DATA_DIR", os.path.join(BASE_DIR, "datos")
)
os.makedirs(CARPETA_DATOS, exist_ok=True)

# La base SQLite contiene las preguntas anonimizadas y sus estadisticas.
# El audio queda desactivado por defecto para no conservar voces de menores.
RUTA_BASE_DATOS = os.path.join(CARPETA_DATOS, "yachaybot.db")
GUARDAR_AUDIO = os.environ.get("YACHAYBOT_GUARDAR_AUDIO", "0").strip() == "1"
CARPETA_AUDIO = os.path.join(CARPETA_DATOS, "audio")
if GUARDAR_AUDIO:
    os.makedirs(CARPETA_AUDIO, exist_ok=True)

PERSONALIDAD = (
    "Eres YACHAYBOT, un robot educativo para ninos y ninas de escuelas rurales "
    "de Huancavelica, Peru. Responde siempre en espanol sencillo, respetuoso y "
    "amable. Usa como maximo dos oraciones y 35 palabras. No uses listas, emojis, "
    "asteriscos ni parentesis porque tu texto se convertira en voz. Si la pregunta "
    "es educativa, explicala con ejemplos del campo, la chacra, los animales o la "
    "sierra peruana cuando sea apropiado. No inventes datos actuales. Si una "
    "pregunta llega incompleta o no tiene sentido, pide que la repitan en una sola "
    "oracion corta. Nunca menciones modelos, empresas ni que eres una IA."
)

HISTORIAL = []
MAX_TURNOS = 6
HISTORIAL_LOCK = threading.Lock()

# Cuando el usuario dice "Yachaybot, que hora es", /wake ya obtuvo una
# transcripcion correcta. El ESP32 vuelve a enviar exactamente el mismo PCM a
# /talk; esta cache evita transcribirlo por segunda vez y obtener otro texto.
WAKE_CACHE = {}
WAKE_CACHE_LOCK = threading.Lock()
WAKE_CACHE_TTL_S = 120

app = Flask(__name__)


# ----------------------------- Texto y wake word -----------------------------


def normalizar_texto(texto):
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


VARIANTES_WAKE = (
    "yachaybot",
    "yachay bot",
    "yachaibot",
    "yachai bot",
    "yachay pod",
)


def contiene_wake_word(texto):
    """Acepta variantes frecuentes de transcripcion del nombre Yachaybot."""
    limpio = normalizar_texto(texto)
    if len(limpio.split()) > 20:
        return False
    return any(variante in limpio for variante in VARIANTES_WAKE)


def extraer_pregunta_con_wake(texto):
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


def clave_audio(pcm):
    return hashlib.sha256(pcm).hexdigest()


def guardar_pregunta_wake(pcm, pregunta):
    ahora = time.monotonic()
    with WAKE_CACHE_LOCK:
        vencidas = [
            clave for clave, (marca, _) in WAKE_CACHE.items()
            if ahora - marca > WAKE_CACHE_TTL_S
        ]
        for clave in vencidas:
            WAKE_CACHE.pop(clave, None)
        WAKE_CACHE[clave_audio(pcm)] = (ahora, pregunta)


def recuperar_pregunta_wake(pcm):
    with WAKE_CACHE_LOCK:
        elemento = WAKE_CACHE.pop(clave_audio(pcm), None)
    if not elemento:
        return ""
    marca, pregunta = elemento
    return pregunta if time.monotonic() - marca <= WAKE_CACHE_TTL_S else ""


# Agregar aqui solo respuestas revisadas por una persona competente en la
# variedad de quechua que se usara en Tayacaja. Se deja vacio intencionalmente.
# Ejemplo de estructura (NO copiar como traduccion):
# RESPUESTAS_QUECHUA_VALIDADAS["clave normalizada"] = "respuesta validada"
RESPUESTAS_QUECHUA_VALIDADAS = {}


def buscar_respuesta_quechua_validada(texto):
    return RESPUESTAS_QUECHUA_VALIDADAS.get(normalizar_texto(texto))


# ----------------------------- Hora y fecha locales -----------------------------

DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def respuesta_hora(ahora):
    hora_12 = ahora.hour % 12 or 12
    periodo = "de la manana" if ahora.hour < 12 else (
        "de la tarde" if ahora.hour < 19 else "de la noche"
    )
    if ahora.minute == 0:
        minuto_texto = "en punto"
    elif ahora.minute == 1:
        minuto_texto = "y un minuto"
    else:
        minuto_texto = f"y {ahora.minute} minutos"
    inicio = "Es la" if hora_12 == 1 else "Son las"
    return f"{inicio} {hora_12} {minuto_texto} {periodo}."


def respuesta_fecha(ahora):
    return (
        f"Hoy es {DIAS[ahora.weekday()]}, {ahora.day} de "
        f"{MESES[ahora.month - 1]} de {ahora.year}."
    )


def responder_localmente(texto):
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


# ----------------------------- Audio -----------------------------


def pcm_a_wav(pcm_bytes, rate=SAMPLE_RATE_ENTRADA):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm_bytes)
    return buffer.getvalue()


def remuestrear(pcm_bytes, rate_origen, rate_destino=SAMPLE_RATE_SALIDA):
    if rate_origen == rate_destino:
        return pcm_bytes
    datos = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if len(datos) == 0:
        return b""

    if rate_destino < rate_origen and len(datos) > 8:
        factor = rate_origen / float(rate_destino)
        n = max(3, int(2 * factor) | 1)
        ventana = np.hanning(n)
        ventana /= ventana.sum()
        datos = np.convolve(datos, ventana, mode="same")

    n_destino = max(1, int(len(datos) * rate_destino / rate_origen))
    x_viejo = np.linspace(0.0, 1.0, num=len(datos), endpoint=False)
    x_nuevo = np.linspace(0.0, 1.0, num=n_destino, endpoint=False)
    salida = np.interp(x_nuevo, x_viejo, datos)
    return np.clip(salida, -32768, 32767).astype(np.int16).tobytes()


# ----------------------------- Groq -----------------------------


def transcribir(pcm_bytes, modo_wake=False):
    wav = pcm_a_wav(pcm_bytes)
    datos = {
        "model": MODELO_STT,
        "language": IDIOMA_STT,
        "temperature": "0",
    }
    if modo_wake:
        datos["prompt"] = "El nombre del robot es Yachaybot."

    respuesta = GROQ_SESSION.post(
        f"{GROQ_BASE}/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        files={"file": ("audio.wav", wav, "audio/wav")},
        data=datos,
        timeout=60,
    )
    respuesta.raise_for_status()
    return respuesta.json().get("text", "").strip()


def pensar(texto_usuario):
    with HISTORIAL_LOCK:
        memoria = list(HISTORIAL[-(MAX_TURNOS * 2):])

    mensajes = [{"role": "system", "content": PERSONALIDAD}]
    mensajes.extend(memoria)
    mensajes.append({"role": "user", "content": texto_usuario})

    respuesta_http = None
    texto_respuesta = ""
    for modelo in MODELOS_LLM:
        candidato = GROQ_SESSION.post(
            f"{GROQ_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": modelo,
                "messages": mensajes,
                "temperature": 0.35,
                "max_completion_tokens": 256,
                "reasoning_effort": "low",
                "include_reasoning": False,
            },
            timeout=60,
        )
        if candidato.ok:
            respuesta_http = candidato
            contenido = candidato.json()["choices"][0]["message"].get("content")
            texto_respuesta = (contenido or "").strip()
            if texto_respuesta:
                print(f"[modelo] {modelo}")
                break
            print(f"[modelo] {modelo} devolvio texto vacio; probando respaldo...")
            continue

        detalle = candidato.text.lower()
        if "model_not_found" in detalle or "does not exist" in detalle:
            print(f"[modelo] {modelo} no disponible; probando respaldo...")
            respuesta_http = candidato
            continue

        candidato.raise_for_status()

    if respuesta_http is None or not respuesta_http.ok:
        if respuesta_http is not None:
            respuesta_http.raise_for_status()
        raise RuntimeError("No hay un modelo de texto disponible en Groq")

    if not texto_respuesta:
        texto_respuesta = "No pude formar una respuesta. Por favor, pregunta nuevamente."

    with HISTORIAL_LOCK:
        HISTORIAL.append({"role": "user", "content": texto_usuario})
        HISTORIAL.append({"role": "assistant", "content": texto_respuesta})
        del HISTORIAL[:max(0, len(HISTORIAL) - MAX_TURNOS * 2)]

    return texto_respuesta


def responder(texto):
    respuesta = responder_localmente(texto)
    if respuesta:
        return respuesta, "local"

    respuesta = buscar_respuesta_quechua_validada(texto)
    if respuesta:
        return respuesta, "quechua_validado"

    return pensar(texto), "llm"


# ----------------------------- Piper TTS -----------------------------


def asegurar_voz(nombre):
    carpeta = os.path.join(BASE_DIR, "voces")
    os.makedirs(carpeta, exist_ok=True)
    modelo = os.path.join(carpeta, nombre + ".onnx")
    if os.path.exists(modelo) and os.path.getsize(modelo) > 1000:
        return modelo
    if os.environ.get("YACHAYBOT_NO_DESCARGAR_VOZ", "0") == "1":
        return modelo

    ruta_remota = RUTAS_VOCES.get(nombre)
    if not ruta_remota:
        return modelo

    print(f"Falta la voz {nombre}. Descargando una sola vez...")
    for extension in (".onnx", ".onnx.json"):
        destino = os.path.join(carpeta, nombre + extension)
        if os.path.exists(destino) and os.path.getsize(destino) > 1000:
            continue
        descarga = requests.get(
            f"{BASE_VOCES}/{ruta_remota}{extension}", stream=True, timeout=600
        )
        descarga.raise_for_status()
        with open(destino, "wb") as archivo:
            for bloque in descarga.iter_content(1 << 16):
                archivo.write(bloque)
    return modelo


VOZ_PIPER = asegurar_voz(NOMBRE_VOZ)
VOZ_CARGADA = None
PIPER_LIB_OK = True


def corregir_pronunciacion(texto):
    for original, pronunciacion in DICCIONARIO_PRONUNCIACION.items():
        texto = texto.replace(original, pronunciacion)
    return texto


def cargar_voz_en_memoria():
    global VOZ_CARGADA
    if VOZ_CARGADA is None:
        from piper import PiperVoice

        VOZ_CARGADA = PiperVoice.load(VOZ_PIPER)
        try:
            VOZ_CARGADA.config.length_scale = float(VELOCIDAD_VOZ)
        except Exception:
            pass
        print(f"Voz de Piper cargada en memoria: {NOMBRE_VOZ}")
    return VOZ_CARGADA


def sintetizar_en_memoria(texto):
    voz = cargar_voz_en_memoria()

    try:
        trozos = []
        rate = None
        for fragmento in voz.synthesize(texto):
            if not hasattr(fragmento, "audio_int16_bytes"):
                raise TypeError("API antigua de Piper")
            trozos.append(fragmento.audio_int16_bytes)
            rate = fragmento.sample_rate
        if trozos:
            return b"".join(trozos), rate
    except TypeError:
        pass

    if hasattr(voz, "synthesize_stream_raw"):
        pcm = b"".join(voz.synthesize_stream_raw(texto))
        return pcm, voz.config.sample_rate

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        voz.synthesize(texto, wav)
    buffer.seek(0)
    with wave.open(buffer, "rb") as wav:
        return wav.readframes(wav.getnframes()), wav.getframerate()


def comando_piper(modelo, salida_wav):
    if shutil.which("piper"):
        return ["piper", "-m", modelo, "-f", salida_wav]
    return [sys.executable, "-m", "piper", "-m", modelo, "-f", salida_wav]


def sintetizar_lento(texto):
    temporal = os.path.join(
        tempfile.gettempdir(), f"yachaybot_{int(time.time() * 1000)}.wav"
    )
    try:
        proceso = subprocess.run(
            comando_piper(VOZ_PIPER, temporal),
            input=texto.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        if proceso.returncode != 0 or not os.path.exists(temporal):
            raise RuntimeError(proceso.stderr.decode("utf-8", "ignore")[:400])

        with wave.open(temporal, "rb") as wav:
            rate = wav.getframerate()
            canales = wav.getnchannels()
            pcm = wav.readframes(wav.getnframes())

        if canales == 2:
            pcm = np.frombuffer(pcm, dtype=np.int16)[::2].tobytes()
        return remuestrear(pcm, rate)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def sintetizar(texto):
    global PIPER_LIB_OK
    texto = (texto or "").strip()
    if not texto:
        texto = "No pude formar una respuesta. Por favor, pregunta nuevamente."
    texto = corregir_pronunciacion(texto)
    if not os.path.exists(VOZ_PIPER):
        raise FileNotFoundError(f"No encuentro la voz de Piper: {VOZ_PIPER}")

    if PIPER_LIB_OK:
        try:
            pcm, rate = sintetizar_en_memoria(texto)
            return remuestrear(pcm, rate)
        except Exception as error:
            print(f"Piper en memoria fallo ({error}). Se usara el modo compatible.")
            PIPER_LIB_OK = False
    return sintetizar_lento(texto)


# ----------------------------- Datos de investigacion -----------------------------


CATEGORIAS_TEMATICAS = {
    "Matemática": (
        "matematica", "numero", "suma", "sumar", "resta", "restar",
        "multiplicacion", "multiplicar", "division", "dividir", "fraccion",
        "decimal", "porcentaje", "geometria", "triangulo", "cuadrado",
        "circulo", "ecuacion", "problema matematico",
    ),
    "Ciencia y ambiente": (
        "ciencia", "planta", "animal", "agua", "aire", "suelo", "tierra",
        "sol", "luna", "planeta", "universo", "energia", "cuerpo humano",
        "celula", "ecosistema", "contaminacion", "naturaleza", "clima",
        "lluvia", "volcan", "terremoto",
    ),
    "Comunicación": (
        "comunicacion", "palabra", "oracion", "sustantivo", "adjetivo",
        "verbo", "pronombre", "cuento", "poema", "lectura", "leer",
        "escribir", "ortografia", "significado", "sinonimo", "antonimo",
        "vocal", "consonante",
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


def anonimizar_texto(texto):
    """Oculta datos personales evidentes antes de guardar la transcripcion."""
    texto = (texto or "").strip()
    texto = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[correo omitido]",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"\b\d{8}\b", "[numero omitido]", texto)
    texto = re.sub(r"(?<!\d)(?:\+?51[ -]?)?9\d{8}(?!\d)", "[telefono omitido]", texto)
    return texto[:1000]


def clasificar_tema(texto):
    limpio = normalizar_texto(texto)
    tokens = set(limpio.split())
    mejor_tema = "Otros"
    mejor_puntaje = 0

    for tema, palabras in CATEGORIAS_TEMATICAS.items():
        puntaje = 0
        for palabra in palabras:
            termino = normalizar_texto(palabra)
            coincide_palabra = termino in tokens
            if " " not in termino and len(termino) >= 4:
                coincide_palabra = coincide_palabra or any(
                    token.startswith(termino) for token in tokens
                )
            if (" " in termino and termino in limpio) or coincide_palabra:
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


def detectar_idioma(texto):
    limpio = normalizar_texto(texto)
    indicadores = ("quechua", "runa simi", "allinllachu", "imaynalla", "sulpayki")
    return "Quechua solicitado" if any(x in limpio for x in indicadores) else "Español"


def conectar_base_datos():
    conexion = sqlite3.connect(RUTA_BASE_DATOS, timeout=15)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA busy_timeout = 15000")
    conexion.execute("PRAGMA journal_mode = WAL")
    return conexion


def inicializar_base_datos():
    with conectar_base_datos() as conexion:
        conexion.executescript(
            """
            CREATE TABLE IF NOT EXISTS interacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                duracion_audio_s REAL,
                pregunta TEXT NOT NULL,
                pregunta_normalizada TEXT NOT NULL,
                respuesta TEXT,
                origen_respuesta TEXT,
                tema TEXT NOT NULL,
                idioma TEXT NOT NULL,
                estado TEXT NOT NULL,
                ms_subida INTEGER,
                ms_stt INTEGER,
                ms_respuesta INTEGER,
                ms_tts INTEGER,
                ms_total INTEGER,
                audio_guardado INTEGER NOT NULL DEFAULT 0,
                archivo_audio TEXT,
                detalle_error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_interacciones_fecha
                ON interacciones(fecha);
            CREATE INDEX IF NOT EXISTS idx_interacciones_tema
                ON interacciones(tema);
            CREATE INDEX IF NOT EXISTS idx_interacciones_estado
                ON interacciones(estado);
            CREATE TABLE IF NOT EXISTS metadatos (
                clave TEXT PRIMARY KEY,
                valor TEXT
            );
            """
        )


def insertar_interaccion(conexion, registro):
    conexion.execute(
        """
        INSERT INTO interacciones (
            fecha, duracion_audio_s, pregunta, pregunta_normalizada,
            respuesta, origen_respuesta, tema, idioma, estado,
            ms_subida, ms_stt, ms_respuesta, ms_tts, ms_total,
            audio_guardado, archivo_audio, detalle_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            registro["fecha"], registro.get("duracion_audio_s"),
            registro["pregunta"], registro["pregunta_normalizada"],
            registro.get("respuesta"), registro.get("origen_respuesta"),
            registro["tema"], registro["idioma"], registro["estado"],
            registro.get("ms_subida"), registro.get("ms_stt"),
            registro.get("ms_respuesta"), registro.get("ms_tts"),
            registro.get("ms_total"), int(registro.get("audio_guardado", False)),
            registro.get("archivo_audio"), registro.get("detalle_error"),
        ),
    )


def migrar_jsonl_anterior():
    """Importa una sola vez el conversaciones.jsonl creado por versiones previas."""
    ruta = os.path.join(CARPETA_DATOS, "conversaciones.jsonl")
    if not os.path.exists(ruta):
        return 0

    with conectar_base_datos() as conexion:
        hecho = conexion.execute(
            "SELECT valor FROM metadatos WHERE clave = 'jsonl_migrado'"
        ).fetchone()
        if hecho:
            return 0

        importados = 0
        with open(ruta, "r", encoding="utf-8") as archivo:
            for linea in archivo:
                try:
                    anterior = json.loads(linea)
                    pregunta = anonimizar_texto(anterior.get("transcripcion", ""))
                    if not pregunta:
                        pregunta = "(sin transcripcion)"
                    respuesta = anonimizar_texto(anterior.get("respuesta", ""))
                    registro = {
                        "fecha": anterior.get("fecha") or datetime.now().isoformat(timespec="seconds"),
                        "duracion_audio_s": anterior.get("duracion_audio_s"),
                        "pregunta": pregunta,
                        "pregunta_normalizada": normalizar_texto(pregunta),
                        "respuesta": respuesta,
                        "origen_respuesta": anterior.get("origen_respuesta", "version_anterior"),
                        "tema": clasificar_tema(pregunta),
                        "idioma": detectar_idioma(pregunta),
                        "estado": "Respondida" if respuesta else "No comprendida",
                        "ms_subida": anterior.get("ms_subida"),
                        "ms_stt": anterior.get("ms_stt"),
                        "ms_respuesta": anterior.get("ms_respuesta"),
                        "ms_tts": anterior.get("ms_tts"),
                        "ms_total": anterior.get("ms_total"),
                        "audio_guardado": bool(anterior.get("archivo_audio")),
                        "archivo_audio": anterior.get("archivo_audio"),
                    }
                    insertar_interaccion(conexion, registro)
                    importados += 1
                except (ValueError, TypeError, KeyError) as error:
                    print(f"[datos] Registro JSONL omitido: {error}")

        conexion.execute(
            "INSERT OR REPLACE INTO metadatos(clave, valor) VALUES ('jsonl_migrado', ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        return importados


def guardar_interaccion(
    pcm, transcripcion, respuesta, origen, tiempos, estado="Respondida", detalle_error=None
):
    """Registra la interaccion sin impedir que el robot responda si SQLite falla."""
    try:
        pregunta = anonimizar_texto(transcripcion)
        if not pregunta:
            pregunta = "(sin transcripcion)"
        respuesta_segura = anonimizar_texto(respuesta)
        nombre_wav = None

        if GUARDAR_AUDIO and pcm:
            marca = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            nombre_wav = f"{marca}_entrada.wav"
            with open(os.path.join(CARPETA_AUDIO, nombre_wav), "wb") as archivo:
                archivo.write(pcm_a_wav(pcm))

        registro = {
            "fecha": datetime.now().isoformat(timespec="seconds"),
            "duracion_audio_s": round(len(pcm) / 2 / SAMPLE_RATE_ENTRADA, 2) if pcm else 0,
            "pregunta": pregunta,
            "pregunta_normalizada": normalizar_texto(pregunta),
            "respuesta": respuesta_segura,
            "origen_respuesta": origen,
            "tema": clasificar_tema(pregunta),
            "idioma": detectar_idioma(pregunta),
            "estado": estado,
            "ms_subida": tiempos.get("subida"),
            "ms_stt": tiempos.get("stt"),
            "ms_respuesta": tiempos.get("respuesta"),
            "ms_tts": tiempos.get("tts"),
            "ms_total": tiempos.get("total"),
            "audio_guardado": bool(nombre_wav),
            "archivo_audio": nombre_wav,
            "detalle_error": anonimizar_texto(detalle_error),
        }
        with conectar_base_datos() as conexion:
            insertar_interaccion(conexion, registro)
    except Exception as error:
        print(f"[datos] No se pudo guardar la interaccion: {error}")


def preparar_filtros(dias, tema):
    condiciones = []
    parametros = []
    if dias > 0:
        desde = (datetime.now() - timedelta(days=dias)).isoformat(timespec="seconds")
        condiciones.append("fecha >= ?")
        parametros.append(desde)
    if tema and tema != "Todos":
        condiciones.append("tema = ?")
        parametros.append(tema)
    clausula = " WHERE " + " AND ".join(condiciones) if condiciones else ""
    return clausula, parametros


def leer_filtros_peticion():
    try:
        dias = int(request.args.get("dias", "30"))
    except ValueError:
        dias = 30
    if dias not in (0, 7, 30, 90, 365):
        dias = 30
    return dias, request.args.get("tema", "Todos").strip() or "Todos"


def obtener_estadisticas(dias=30, tema="Todos"):
    clausula, parametros = preparar_filtros(dias, tema)
    with conectar_base_datos() as conexion:
        resumen = conexion.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado = 'Respondida' THEN 1 ELSE 0 END) AS respondidas,
                SUM(CASE WHEN estado != 'Respondida' THEN 1 ELSE 0 END) AS incidencias,
                AVG(CASE WHEN ms_total > 0 THEN ms_total END) AS promedio_ms
            FROM interacciones{clausula}
            """,
            parametros,
        ).fetchone()

        por_tema = conexion.execute(
            f"""
            SELECT tema, COUNT(*) AS cantidad
            FROM interacciones{clausula}
            GROUP BY tema ORDER BY cantidad DESC, tema
            """,
            parametros,
        ).fetchall()

        frecuentes = conexion.execute(
            f"""
            SELECT MIN(pregunta) AS pregunta, tema, COUNT(*) AS cantidad
            FROM interacciones{clausula}
            {"AND" if clausula else "WHERE"} pregunta_normalizada != 'sin transcripcion'
            GROUP BY pregunta_normalizada, tema
            ORDER BY cantidad DESC, MAX(fecha) DESC LIMIT 10
            """,
            parametros,
        ).fetchall()

        recientes = conexion.execute(
            f"""
            SELECT fecha, pregunta, respuesta, tema, idioma, estado, ms_total
            FROM interacciones{clausula}
            ORDER BY fecha DESC, id DESC LIMIT 100
            """,
            parametros,
        ).fetchall()

        por_dia = conexion.execute(
            f"""
            SELECT substr(fecha, 1, 10) AS dia, COUNT(*) AS cantidad
            FROM interacciones{clausula}
            GROUP BY substr(fecha, 1, 10)
            ORDER BY dia DESC LIMIT 14
            """,
            parametros,
        ).fetchall()

        temas_disponibles = [
            fila["tema"] for fila in conexion.execute(
                "SELECT DISTINCT tema FROM interacciones ORDER BY tema"
            ).fetchall()
        ]

    total = int(resumen["total"] or 0)
    respondidas = int(resumen["respondidas"] or 0)
    incidencias = int(resumen["incidencias"] or 0)
    max_tema = max((fila["cantidad"] for fila in por_tema), default=1)
    max_dia = max((fila["cantidad"] for fila in por_dia), default=1)

    return {
        "total": total,
        "respondidas": respondidas,
        "incidencias": incidencias,
        "porcentaje_exito": round(respondidas * 100 / total, 1) if total else 0,
        "promedio_s": round((resumen["promedio_ms"] or 0) / 1000, 2),
        "por_tema": [
            {
                "tema": fila["tema"],
                "cantidad": fila["cantidad"],
                "porcentaje": round(fila["cantidad"] * 100 / total, 1) if total else 0,
                "ancho": round(fila["cantidad"] * 100 / max_tema, 1),
            }
            for fila in por_tema
        ],
        "frecuentes": [dict(fila) for fila in frecuentes],
        "recientes": [dict(fila) for fila in recientes],
        "por_dia": [
            {"dia": fila["dia"], "cantidad": fila["cantidad"],
             "ancho": round(fila["cantidad"] * 100 / max_dia, 1)}
            for fila in reversed(por_dia)
        ],
        "temas_disponibles": temas_disponibles,
    }


inicializar_base_datos()
REGISTROS_MIGRADOS = migrar_jsonl_anterior()


def peticion_autorizada():
    if not SERVER_TOKEN:
        return True
    return request.headers.get("X-Yachay-Token", "") == SERVER_TOKEN


# ----------------------------- Endpoints -----------------------------


@app.route("/wake", methods=["POST"])
def wake():
    if not peticion_autorizada():
        return Response("0", status=401, mimetype="text/plain")

    inicio = time.time()
    pcm = request.get_data()
    subida_ms = int((time.time() - inicio) * 1000)
    if len(pcm) < 4000:
        return Response("0", mimetype="text/plain")

    try:
        etapa = time.time()
        texto = transcribir(pcm, modo_wake=True)
        stt_ms = int((time.time() - etapa) * 1000)
        detectado = contiene_wake_word(texto)
        pregunta_incluida = extraer_pregunta_con_wake(texto) if detectado else ""
        if pregunta_incluida:
            guardar_pregunta_wake(pcm, pregunta_incluida)
        estado = "PREGUNTA_INCLUIDA" if pregunta_incluida else (
            "ACTIVADO" if detectado else "ignorado"
        )
        print(f"[wake] '{texto}' -> {estado} | subida={subida_ms} ms, STT={stt_ms} ms")
        # 2 permite al ESP32 reutilizar el mismo audio en /talk, evitando que
        # el estudiante tenga que repetir la pregunta tras la latencia de STT.
        return Response(
            "2" if pregunta_incluida else ("1" if detectado else "0"),
            mimetype="text/plain",
        )
    except Exception as error:
        print(f"[wake] Error: {error}")
        return Response("0", mimetype="text/plain")


@app.route("/talk", methods=["POST"])
def talk():
    if not peticion_autorizada():
        return Response(b"", status=401, mimetype="application/octet-stream")

    inicio = time.time()
    pcm = request.get_data()
    subida_ms = int((time.time() - inicio) * 1000)
    print(f"\n[<-] Pregunta: {len(pcm)} bytes ({len(pcm)/2/SAMPLE_RATE_ENTRADA:.2f} s)")
    if len(pcm) < 4000:
        return Response(b"", mimetype="application/octet-stream")

    tiempos = {"subida": subida_ms}
    texto = ""
    try:
        texto = recuperar_pregunta_wake(pcm)
        if texto:
            tiempos["stt"] = 0
            print(f"[oreja/cache] '{texto}' (transcripcion reutilizada)")
        else:
            etapa = time.time()
            texto = transcribir(pcm)
            tiempos["stt"] = int((time.time() - etapa) * 1000)
            print(f"[oreja] '{texto}' ({tiempos['stt']} ms)")

        if not texto or len(normalizar_texto(texto)) < 2:
            print("[silencio] Whisper no encontro una pregunta valida.")
            tiempos["total"] = int((time.time() - inicio) * 1000)
            guardar_interaccion(
                pcm, texto, "", "sin_respuesta", tiempos, estado="No comprendida"
            )
            return Response(b"", mimetype="application/octet-stream")

        etapa = time.time()
        texto_respuesta, origen = responder(texto)
        tiempos["respuesta"] = int((time.time() - etapa) * 1000)
        print(f"[boca/{origen}] '{texto_respuesta}' ({tiempos['respuesta']} ms)")

        etapa = time.time()
        audio = sintetizar(texto_respuesta)
        tiempos["tts"] = int((time.time() - etapa) * 1000)
        tiempos["total"] = int((time.time() - inicio) * 1000)

        guardar_interaccion(pcm, texto, texto_respuesta, origen, tiempos)
        print(
            f"[->] {len(audio)} bytes a {SAMPLE_RATE_SALIDA} Hz | "
            f"SUBIDA={tiempos['subida']} ms | STT={tiempos['stt']} ms | "
            f"TTS={tiempos['tts']} ms | TOTAL={tiempos['total']} ms"
        )
        return Response(audio, mimetype="application/octet-stream")
    except requests.HTTPError as error:
        detalle = error.response.text[:300] if error.response is not None else str(error)
        print(f"[!] Error de Groq: {detalle}")
        tiempos["total"] = int((time.time() - inicio) * 1000)
        guardar_interaccion(
            pcm, texto, "", "error_groq", tiempos,
            estado="Error del servicio", detalle_error=detalle,
        )
        return Response(b"", mimetype="application/octet-stream")
    except Exception as error:
        print(f"[!] Error inesperado: {error}")
        tiempos["total"] = int((time.time() - inicio) * 1000)
        guardar_interaccion(
            pcm, texto, "", "error_servidor", tiempos,
            estado="Error del servidor", detalle_error=str(error),
        )
        return Response(b"", mimetype="application/octet-stream")


@app.route("/ping", methods=["GET"])
def ping():
    with conectar_base_datos() as conexion:
        total_registros = conexion.execute(
            "SELECT COUNT(*) FROM interacciones"
        ).fetchone()[0]
    return {
        "estado": "ok",
        "robot": "YACHAYBOT",
        "wake_word": "Yachaybot",
        "idioma": IDIOMA_STT,
        "modelos_llm": MODELOS_LLM,
        "groq_key": bool(GROQ_API_KEY),
        "voz": NOMBRE_VOZ,
        "voz_piper": os.path.exists(VOZ_PIPER),
        "analitica": True,
        "interacciones_guardadas": total_registros,
        "guardar_audio": GUARDAR_AUDIO,
        "hora_laptop": datetime.now().isoformat(timespec="seconds"),
    }


@app.route("/dashboard", methods=["GET"])
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
        guardar_audio=GUARDAR_AUDIO,
        exportar_url=url_for("exportar_csv", dias=dias, tema=tema),
    )


@app.route("/api/estadisticas", methods=["GET"])
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


@app.route("/exportar.csv", methods=["GET"])
def exportar_csv():
    dias, tema = leer_filtros_peticion()
    clausula, parametros = preparar_filtros(dias, tema)
    with conectar_base_datos() as conexion:
        filas = conexion.execute(
            f"""
            SELECT fecha, pregunta, tema, idioma, respuesta, estado,
                   origen_respuesta, ms_stt, ms_respuesta, ms_tts, ms_total
            FROM interacciones{clausula}
            ORDER BY fecha DESC, id DESC
            """,
            parametros,
        ).fetchall()

    salida = io.StringIO(newline="")
    escritor = csv.writer(salida, delimiter=";")
    escritor.writerow(
        (
            "Fecha", "Pregunta anónima", "Tema", "Idioma", "Respuesta",
            "Estado", "Origen", "STT ms", "Respuesta ms", "TTS ms", "Total ms",
        )
    )
    for fila in filas:
        escritor.writerow(tuple(fila))

    contenido = "\ufeff" + salida.getvalue()
    nombre = f"yachaybot_interacciones_{datetime.now():%Y%m%d_%H%M}.csv"
    return Response(
        contenido,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


from agente_docente import registrar_agente
registrar_agente(app, lambda: RUTA_BASE_DATOS, leer_clave_groq)


if __name__ == "__main__":
    print("=" * 64)
    print("YACHAYBOT - servidor con wake word y analitica educativa")
    print("=" * 64)
    if not GROQ_API_KEY:
        print("[!] Falta GROQ_API_KEY o clave.txt.")
    try:
        etapa_calentamiento = time.time()
        sintetizar("Yachaybot esta listo.")
        print(
            "Piper precargado en "
            f"{int((time.time() - etapa_calentamiento) * 1000)} ms."
        )
    except Exception as error:
        print(f"[!] No se pudo precargar Piper: {error}")
    print(f"Servidor: http://0.0.0.0:{PUERTO}")
    print(f"Dashboard: http://127.0.0.1:{PUERTO}/dashboard")
    print(f"Modelos de texto: {', '.join(MODELOS_LLM)}")
    print("Wake word: POST /wake | Preguntas: POST /talk | Prueba: GET /ping")
    print(f"Base de datos: {RUTA_BASE_DATOS}")
    print(f"Guardar audio: {'SI' if GUARDAR_AUDIO else 'NO (recomendado)'}")
    if REGISTROS_MIGRADOS:
        print(f"Registros anteriores importados: {REGISTROS_MIGRADOS}")
    print("La hora de Windows debe estar configurada para Peru.")
    print("=" * 64)
    app.run(host="0.0.0.0", port=PUERTO, threaded=True)
