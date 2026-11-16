# YACHAYBOT con agente de apoyo docente

## Inicio en Windows

1. Descomprime el proyecto en otra carpeta para conservar tu instalación anterior.
2. Instala dependencias con `1_INSTALAR.bat`, si todavía no están instaladas.
3. Para usar Groq, conserva tu `clave.txt` original junto a `server.py`, o define `GROQ_API_KEY`. El paquete actualizado no contiene claves privadas.
4. Ejecuta `6_ARRANCAR_AGENTE.bat` y elige proveedor. Puedes seguir utilizando los scripts anteriores para el robot.
5. Abre <http://127.0.0.1:8000/agente>, o pulsa **Abrir agente docente** desde el panel.
6. Escribe tu solicitud; elige informe o actividades, tema y fechas. Para los datos históricos de agosto, marca **Todo el historial**. Para actividades indica grado y cantidad.
7. Revisa el borrador, la tabla calculada con Python y las referencias `[ID n]` antes de usarlo.

## Ollama local

Instala Ollama desde <https://ollama.com/download>. En una terminal:

```text
ollama pull qwen3:4b
ollama serve
```

Si la aplicación de Ollama ya está abierta, no ejecutes otro servidor en el mismo puerto. Descargar el modelo requiere internet y espacio disponible. La memoria y velocidad deben comprobarse en tu equipo.

El valor inicial es `http://127.0.0.1:11434`. Puedes definir `OLLAMA_HOST` para otro servidor y `YACHAYBOT_AGENT_MODEL` para otro modelo compatible con herramientas. El script 6 fija sus valores iniciales; para configuraciones propias, define las variables y ejecuta directamente `python server.py`.

```text
set YACHAYBOT_AGENT_PROVIDER=ollama
set YACHAYBOT_AGENT_MODEL=qwen3:4b
python server.py
```

## Groq

```text
set YACHAYBOT_AGENT_PROVIDER=groq
set YACHAYBOT_AGENT_MODEL=openai/gpt-oss-20b
python server.py
```

El robot conserva su proveedor original. La configuración anterior cambia únicamente el agente docente. No hay cambio automático de proveedor si falla uno. Groq necesita conexión y una clave válida. El proveedor del agente recibe una muestra de hasta 30 preguntas del historial filtrado para redactar el borrador.

## Pruebas reproducibles

```text
python -m unittest -v test_agente.py test_integracion.py
```

La suite usa bases temporales y modelos simulados, sin consumir APIs. Comprueba 27 escenarios del agente y cinco de integración con el servidor. Los casos del agente cubren escenarios de herramientas, filtros, citas, fechas, autorización, errores, límites y conservación de datos. Las evidencias incluyen resultados separados para las pruebas automáticas, la integración con `server.py` y los intentos con servicios reales. No confundir los contratos HTTP simulados con inferencia real.

## Arquitectura y límites

- `agente_docente.py`: validación, lectura SQLite, adaptadores HTTP, ciclo de herramientas y bitácora.
- `templates/agente.html`: interfaz docente; no refresca automáticamente durante la redacción.
- `server.py`: registra el módulo en `/agente` y `/api/agente`.
- `resumir_historial`: única herramienta permitida; usa parámetros SQL y una conexión de solo lectura. Sus filtros vienen del formulario y no pueden cambiarse desde el modelo.
- `datos/agente_ejecuciones.jsonl`: traza separada con identificadores, códigos y huella de solicitud; no contiene claves ni textos completos.
- Si defines `YACHAYBOT_TOKEN`, la API del agente exige el encabezado `X-Yachay-Token`; el formulario permite introducirlo sin guardarlo.
- El agente exige una llamada a herramienta y referencias válidas. Los conteos visibles se calculan con Python; el texto del modelo aún necesita revisión y puede contener errores.
- Las actividades son borradores sin RAG ni validación pedagógica. La frecuencia de consulta no permite diagnosticar aprendizaje. No se asignan notas ni se envían actividades al robot.
- El clasificador temático original se conserva; su falso positivo `restaurante`/`resta` está documentado en el informe.

## Fuentes técnicas

- <https://docs.ollama.com/capabilities/tool-calling>
- <https://console.groq.com/docs/tool-use/overview>
