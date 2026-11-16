"""Descarga la misma voz medium configurada en server.py."""

import os

import requests

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
VOZ = "es/es_MX/ald/medium/es_MX-ald-medium"

destino = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voces")
os.makedirs(destino, exist_ok=True)

for extension in (".onnx", ".onnx.json"):
    nombre = os.path.basename(VOZ) + extension
    salida = os.path.join(destino, nombre)
    if os.path.exists(salida) and os.path.getsize(salida) > 1000:
        print(f"Ya existe: {nombre}")
        continue

    print(f"Descargando {nombre}...")
    respuesta = requests.get(
        f"{BASE}/{VOZ}{extension}", stream=True, timeout=600
    )
    respuesta.raise_for_status()
    with open(salida, "wb") as archivo:
        for bloque in respuesta.iter_content(1 << 16):
            archivo.write(bloque)
    print(f"Lista: {salida} ({os.path.getsize(salida) / 1e6:.1f} MB)")

print("Voz lista. Ahora ejecuta 2_ARRANCAR.bat")
