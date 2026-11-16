# AGENTS.md — YACHAYBOT

Instrucciones para el agente que trabaja en este repositorio. Se cargan al
iniciar sesión en esta carpeta.

## Regla principal: lee el estado antes de actuar

**Al empezar cualquier sesión en este repositorio, lee `ESTADO_HITO_II.md`
completo antes de tocar nada.** Ese archivo contiene: el bloqueo técnico
actual con su causa y su fix, las decisiones ya tomadas, el estado de cada
suite de pruebas, los comandos que funcionan en esta máquina y los próximos
pasos en orden.

Si el usuario dice "continuar yachaybot", "seguimos con el hito" o cualquier
frase de reanudación, el contexto está en `ESTADO_HITO_II.md`: léelo y retoma
desde ahí. No pidas que repita el estado.

Después de leerlo, ejecuta `git log --oneline` y `git status` para confirmar
en qué commit y con qué cambios sin commitear está el árbol.

## Documentos de referencia

| Archivo | Para qué sirve |
|---------|----------------|
| `ESTADO_HITO_II.md` | **Bitácora viva.** Estado, bloqueo actual, próximos pasos. Actualizarla al cerrar cada rebanada. |
| `docs/PRD_HITO_II.md` | Documento de destino del Hito II (fase 2 de la metodología de Matt). Decisiones y fuera de alcance. |
| `docs/KANBAN_HITO_II.md` | Tablero de trabajo (fase 3). Estado real de cada issue T0–T9. |
| `matt/matt.txt` | Transcripción del taller de Matt Pocock. Base de la metodología. |
| `README_AGENTE.md` | Instrucciones de uso del agente docente y sus límites. |

## Metodología de trabajo

La metodología es la de Matt Pocock, resumida en `matt/matt.txt`:

1. **Grilling** (HITL, siempre humano): preguntar una cosa a la vez, cada
   pregunta con una respuesta recomendada, para alcanzar un diseño compartido.
2. **PRD** (HITL): documento de destino, no de camino. Incluye el
   **fuera de alcance**, que es lo que le da límite a "terminado".
3. **Kanban** (HITL): romper el PRD en issues independientes con bloqueos
   explícitos. Es un **DAG**, no una lista secuencial: los issues sin
   dependencias se pueden tomar en paralelo.
4. **Implementación** (AFK): rebanadas **verticales**, nunca horizontales.
   TDD obligatorio: test rojo → implementación → refactor. Módulos profundos
   (Ousterhout): interfaz pequeña, lógica densa detrás.
5. **QA** (HITL): el humano impone el criterio. La QA genera issues nuevos
   de vuelta al tablero.

### Reglas no negociables

- **Vertical slices.** Cada rebanada cruza esquema + servicio + ruta + UI + su
  test. Nada de "toda la base de datos, luego toda la API, luego todo el front".
- **TDD.** El test rojo primero. Si la suite no está verde, no se avanza.
- **1 commit atómico por rebanada.** El mensaje describe qué se rompe, por qué
  (mecanismo), cómo se corrige y cómo se verifica.
- **Nunca `git add -A`** cuando hay trabajo de más de un incremento mezclado:
  usa `git add <rutas explícitas>`.
- **Verificar con output real**, nunca con "debería funcionar". Un build que
  "debería pasar" no es un build que pasa.
- **El agente docente no cambia de comportamiento** sin que se decida
  explícitamente: misma herramienta, mismos códigos de error, mismos campos.
- **Fuera de alcance ya decidido** (ver `docs/PRD_HITO_II.md`): RAG, algoritmos
  genéticos, diagnóstico por estudiante, campo de sesión, envío de actividades
  al robot, inferencia real con Ollama/Groq, Docker. No re-litigar esto.

## Estructura del proyecto

```
almacen/    Frontera de datos. Único punto de acceso a PostgreSQL.
            config.py (URLs) · esquema.py (ORM+Core) · repositorio.py
            (operaciones con significado) · sesiones.py (sesión por petición)
robot/      Cerebro del robot. cerebro.py: wake word, clasificación temática,
            idioma, respuestas locales. NO toca la base de datos.
voz/        Audio del robot (STT/TTS). Pendiente de poblar: la lógica de
            voz sigue en server.py.
web/        Rutas Flask. panel.py (dashboard, API, CSV) · agente.py
            (agente docente con herramientas de solo lectura).
scripts/    Utilidades: migrar_sqlite_a_postgres.py.
alembic/    Versionado del esquema de la base.
evidencias/ Resultados de pruebas que respaldan el informe.
docs/       PRD y Kanban del Hito II (evidencia del proceso).
```

`server.py` es el **composition root**: solo cablea. Si crece, es una señal de
que falta un módulo.

## Entorno

```bash
cd /home/saminillayuq/Downloads/8voCICLO/IA/bot/PROYECTO_YACHAYBOT/yachaybot_ia
.venv/bin/python -m unittest test_robot test_almacen test_agente test_integracion test_web
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.migrar_sqlite_a_postgres
```

PostgreSQL 18.6 en `127.0.0.1:5432`, rol `postgres`. Bases: `yachaybot`
(producción) y `yachaybot_test` (pruebas). El driver es **psycopg v3**, no
psycopg2.

**No hay** Ollama instalado, ni `gh` CLI, ni acceso al socket de Docker. No
prometas inferencia real ni validaciones que requieran esas herramientas.

## Git

- Rama: `main`. Remoto: `origin` → `https://github.com/SamiIllayuq-web/yachayBot.git`
- Tags: `v1.0-sqlite` (la v1 congelada, con el SHA-256 que cita el informe).
  `v2.0-postgres` se crea al cerrar el Hito II.
- El informe `YACHAYBOT_IA.docx` cita el SHA-256 de `server.py` de la v1
  (`f61e63c8...`). Ese archivo no debe modificarse ni eliminarse sin
  actualizar antes el informe.
- `clave.txt`, `datos/` y `voces/` nunca se versionan: están en `.gitignore`.

## Al cerrar el hito

Actualiza `ESTADO_HITO_II.md` y `docs/KANBAN_HITO_II.md` con el estado real,
crea el tag `v2.0-postgres`, y actualiza el informe `.docx` (capítulos 9, 15,
16, las evidencias y un capítulo de arquitectura v2).
