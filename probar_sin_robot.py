"""Prueba /wake y /talk usando el microfono de la laptop."""

import sys
import wave

import requests

URL_BASE = "http://127.0.0.1:8000"
RATE_ENTRADA = 16000
RATE_SALIDA = 8000


def grabar(segundos, mensaje):
    try:
        import sounddevice as sd
    except ImportError:
        print("Falta sounddevice. Ejecuta 1_INSTALAR.bat")
        sys.exit(1)

    print(f"{mensaje} ({segundos} segundos)...")
    audio = sd.rec(
        int(RATE_ENTRADA * segundos),
        samplerate=RATE_ENTRADA,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    return audio.tobytes()


audio_wake = grabar(3, "Di solamente Yachaybot")
respuesta_wake = requests.post(
    f"{URL_BASE}/wake",
    data=audio_wake,
    headers={"Content-Type": "application/octet-stream"},
    timeout=60,
)

if respuesta_wake.status_code != 200 or respuesta_wake.text.strip() != "1":
    print("No se detecto Yachaybot. Revisa la ventana del servidor y repite.")
    sys.exit(1)

print("Yachaybot detectado correctamente.")
audio_pregunta = grabar(5, "Haz una pregunta, por ejemplo: Que hora es")
respuesta = requests.post(
    f"{URL_BASE}/talk",
    data=audio_pregunta,
    headers={"Content-Type": "application/octet-stream"},
    timeout=120,
)

print("HTTP", respuesta.status_code, "-", len(respuesta.content), "bytes")
if respuesta.status_code != 200 or not respuesta.content:
    print("El servidor no devolvio audio. Revisa su ventana.")
    sys.exit(1)

with wave.open("respuesta.wav", "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(RATE_SALIDA)
    wav.writeframes(respuesta.content)

print("Respuesta guardada en respuesta.wav a 8000 Hz.")
