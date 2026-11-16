# PRD — Hito II: PostgreSQL + módulos profundos

> **Documento de destino** de la fase 2 de la metodología de Matt Pocock.
> Describe QUÉ significa "terminado" para el Hito II, no el camino para llegar.
> Se conserva versionado como evidencia del proceso de diseño.

## Contexto

YACHAYBOT_IA v1 = `server.py` monolítico (1154 líneas, 45 funciones) + `agente_docente.py`
(194 líneas) sobre SQLite. 32 tests verdes. Defectos reales verificados ejecutando el código:
`restaurante` → `Matemática` (prefijo "resta"); `id` ausente de "recientes" y de `exportar.csv`.

## Decisiones tomadas en el grilling (2026-11-15)

| # | Decisión | Valor | Motivo |
|---|----------|-------|--------|
| 1 | Destino de la iteración | Base sólida para el Hito II (opción A) | Bugs + módulos + git + Postgres |
| 2 | Estructura | 4 paquetes: `almacen/`, `voz/`, `robot/`, `web/` | Deep modules (Ousterhout) |
| 3 | Almacén | PostgreSQL único; SQLite solo histórico/respaldo | Verificado: PG 18.6 corriendo |
| 4 | Capa de datos | SQLAlchemy 2.0 Core + Alembic | SQL explícito, visible en defensa |
| 5 | Despliegue | Linux (dev) + Windows (entrega) con Postgres local | Docker sin permisos de socket |
| 6 | Agente docente | Sin cambio de comportamiento; solo se reubica | Protege 32 pruebas + evidencia del informe |
| 7 | Informe .docx | Actualizar al final (cap. 9, 15, 16 + evid. + cap. arquitectura v2) | El informe describe un sistema que dejará de existir |
| 8 | EX05 clasificador | Corregir con TDD (test rojo → comparación por palabra completa) | Desbloquea regresión 15/15 |
| 9 | Git | Local + remoto GitHub al final (gh CLI faltante → hay que instalarlo) | Atomicidad + revisión en GitHub |
| 10 | server.py original | Reescribir a `server.py.old` (el informe cita su SHA-256) | Preserva la evidencia del informe |

## Fuera de alcance (decisiones negativas — no re-litigar)

- RAG / recuperación semántica de material curricular.
- Algoritmos genéticos de optimización.
- Diagnóstico de aprendizaje por estudiante (la frecuencia no lo permite).
- Campo de sesión por estudiante.
- Corrección del 74,5 % que cae en la categoría "Otros" (solo se arregla EX05).
- Envío de actividades al robot.
- Validación de inferencia real con Ollama/Groq (no hay Ollama instalado en esta máquina).
- Docker (sin acceso al socket de docker).

## Reglas de la iteración

- Vertical slices: cada rebanada cruza esquema + servicio + ruta + UI + test.
- TDD: test rojo primero, luego implementación.
- 1 commit atómico por rebanada.
- El agente NO cambia de comportamiento: mismos contratos, misma UI, mismos conteos.
- PostgreSQL es almacén único: robot, panel y agente leen/escriben allí.
