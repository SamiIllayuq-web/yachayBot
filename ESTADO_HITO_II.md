# ESTADO DEL TRABAJO — YACHAYBOT_IA / Hito II

> **Este archivo es la bitácora viva del proyecto.** Si una sesión termina o
> se acaban los tokens, la siguiente sesión empieza por leer este archivo.
> Se actualiza al cerrar cada rebanada.

**Proyecto:** YACHAYBOT — agente de apoyo docente integrado al robot educativo
**Ruta:** `/home/saminillayuq/Downloads/8voCICLO/IA/bot/PROYECTO_YACHAYBOT/yachaybot_ia`
**Curso:** Inteligencia Artificial — UNH, VIII ciclo, Sección B, 2026-II
**Metodología:** Matt Pocock (grill → PRD → Kanban → AFK → QA). Ver `matt/matt.txt`
**Última actualización:** 2026-11-15 (sesión de migración a PostgreSQL)

> **Para retomar el trabajo:** leer este archivo completo, luego
> `git log --oneline` y `git status`. Todo el avance está commiteado.
>
> `AGENTS.md` (en la raíz) le dice al agente que lea esta bitácora al iniciar
> sesión. Por eso basta con escribir **"continuar yachaybot"** en un chat nuevo:
> el contexto está aquí, no en la conversación anterior.

---

## 1. Estado en una frase

La v1 está congelada en git; PostgreSQL es el almacén único con Alembic y los 51
registros ya migrados; el clasificador EX05 está corregido con tests; **falta
desbloquear el blueprint del panel** para cerrar la rebanada T3.

---

## 2. Progreso del Kanban

| Issue | Estado | Commit | Qué entregó |
|-------|--------|--------|-------------|
| T0 Congelar v1 | ✅ | `24cde9f` | Commit inicial + tag `v1.0-sqlite` |
| T1/T2 Estructura + esquema PG | ✅ | `fdb19d1` | Paquetes `almacen/ voz/ robot/ web/`, Alembic, migración de datos |
| T6 Fix EX05 | ✅ | `100428d` | `robot/cerebro.py`, comparación por palabra completa |
| T3 Panel + agente sobre PG | 🔴 **EN CURSO** | — | `web/panel.py`, `web/agente.py`, `test_web.py` escritos; falta el fix del blueprint |
| T4 Escribir interacción + `id` en recientes/CSV | ⬜ | — | `/talk` persiste en PG |
| T5 Migrar 51 registros | ✅ (hecho en T2) | `fdb19d1` | `scripts/migrar_sqlite_a_postgres.py` |
| T7 Scripts Windows + README + requirements | ⬜ | — | `.bat` actualizados |
| T8 Actualizar `YACHAYBOT_IA.docx` | ⬜ | — | Cap. 9, 15, 16 + evidencias + arquitectura v2 |
| T9 Remoto GitHub + tag `v2.0-postgres` | 🟡 | `c9096c0` | Remoto configurado, rama `main` + tag `v1.0-sqlite` subidos. Falta el tag `v2.0-postgres` |

---

## 3. El bloqueo actual (leer primero)

**Síntoma:** `BuildError: Could not build url for endpoint 'dashboard'. Did you mean 'panel.dashboard'?`

**Causa:** `web/panel.py` registra las rutas en un `Blueprint("panel", ...)`,
Flask 3.1 antepone el prefijo `panel.` a los endpoints. Pero
`templates/dashboard.html:132` usa `{{ url_for('dashboard') }}` (sin prefijo).

**Fix elegido (aplicar en la próxima sesión):** registrar las rutas del panel
**directamente sobre `app`** en lugar de usar un Blueprint, con
`@app.get("/dashboard")` etc. Así los endpoints se llaman `dashboard`,
`api_estadisticas` y `exportar_csv`, igual que en la v1, y **el template no se
toca**. (El intento con `Blueprint(..., name=None)` no funciona: Flask exige un
nombre no vacío para el blueprint.)

**Alternativa válida si el fix directo da problemas:** cambiar el template a
`url_for('panel.dashboard')` — pero obliga a tocar el template y el informe
menciona la v1 con esos nombres de endpoint, así que se prefiere no hacerlo.

**Estado de los tests tras el bloqueo:** 9 de 10 pruebas de `test_web.py` pasan;
falla solo `test_01_panel_responde_200` (la que renderiza el dashboard). Las
pruebas del agente (`test_07` a `test_10`) **ya pasan**: el agente lee de
PostgreSQL correctamente.

---

## 4. Decisiones tomadas (no re-litigar)

| # | Decisión | Motivo |
|---|----------|--------|
| 1 | Destino: base sólida para el Hito II | Bugs + módulos + git + Postgres |
| 2 | PostgreSQL es el almacén **único** | SQLite queda solo como histórico/respaldo |
| 3 | SQLAlchemy 2.0 Core + Alembic | SQL explícito y visible en la defensa |
| 4 | 4 paquetes: `almacen/ voz/ robot/ web/` | Deep modules (Ousterhout) |
| 5 | El agente **no cambia de comportamiento** | Protege las 27 pruebas y la evidencia del informe |
| 6 | Se corrige EX05 con TDD | Desbloquea la regresión 15/15 |
| 7 | Git local ahora, remoto GitHub al final | `gh` no está instalado |
| 8 | `server.py` original → `server.py.old` | El informe cita su SHA-256 |
| 9 | Despliegue: Linux (dev) + Windows (entrega) | Docker sin acceso al socket |

**Fuera de alcance (decisiones negativas):** RAG · algoritmos genéticos ·
diagnóstico de aprendizaje por estudiante · campo de sesión · corrección del
74,5 % que cae en "Otros" · envío de actividades al robot · inferencia real
(no hay Ollama instalado) · Docker.

---

## 5. Reglas de la iteración

- **Vertical slices**: cada rebanada cruza esquema + servicio + ruta + UI + test.
- **TDD**: test rojo primero, luego implementación, luego refactor.
- **1 commit atómico** por rebanada; nunca `git add -A` con trabajo mezclado.
- El agente NO cambia de contratos: misma herramienta, mismos códigos de error.
- Verificar con output real, nunca con "debería funcionar".

---

## 6. Entorno verificado en esta máquina

```
Python 3.14.9 · .venv/ con: flask 3.1.3, requests 2.34.2, numpy 2.5.5,
pytest 9.2.0, sqlalchemy 2.1.8, alembic 1.20.1, psycopg 3.3.9 (v3, no psycopg2)
PostgreSQL 18.6 en 127.0.0.1:5432 · rol `postgres` (superusuario)
Bases: yachaybot (producción), yachaybot_test (pruebas)
NO hay: Ollama instalado · gh CLI · acceso al socket de Docker
```

**Comandos que funcionan aquí:**

```bash
cd /home/saminillayuq/Downloads/8voCICLO/IA/bot/PROYECTO_YACHAYBOT/yachaybot_ia
.venv/bin/python -m unittest test_robot test_almacen test_agente test_integracion test_web
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m scripts.migrar_sqlite_a_postgres
```

---

## 7. Estado de las pruebas

| Suite | Casos | Estado |
|-------|-------|--------|
| `test_almacen.py` (nuevo) | 20 | ✅ verdes |
| `test_robot.py` (nuevo) | 22 | ✅ verdes |
| `test_agente.py` (v1) | 27 | ✅ verdes |
| `test_integracion.py` (v1) | 5 | ✅ verdes |
| `test_web.py` (nuevo) | 10 | 🔴 9 verdes, 1 por el bloqueo del blueprint |
| **Total** | **84** | **83 verdes** |

---

## 8. Verificaciones ya hechas (no repetirlas sin motivo)

- **Migración**: 51 registros movidos de SQLite a PostgreSQL. Idempotente
  (la segunda ejecución omite). Verifica conteos origen vs destino.
- **Agregados en PG coinciden con el informe**: total 51, respondidas 51,
  incidencias 0, 100 %, promedio 6,09 s, 41 del 18 y 10 del 20 de agosto.
  Distribución: Otros 38 · Matemática 5 · Conversación 3 · Lenguas y quechua 3 ·
  Comunicación 1 · Tecnología 1.
- **EX05 corregido**: "restaurante" → Otros (antes Matemática); "resta" →
  Matemática; "robot" → Tecnología.
- **Trazabilidad**: `recientes` y `exportar.csv` ahora incluyen el `id`, que es
  lo que el agente cita como `[ID n]`. En la v1 ese campo faltaba.

---

## 9. Valores del informe .docx que deben seguir cuadrando

El informe cita estos números como evidencia. Si cambian, hay que actualizar el
capítulo 11 y el 16:

- 51 interacciones, 18–20 de agosto de 2026
- 14/15 casos de regresión aprobados, 1 fallido (EX05) → **con el fix pasa a 15/15**
- 27 pruebas del agente + 5 de integración (modelo simulado)
- Promedio 6,09 s · 100 % de registros con respuesta · 0 incidencias
- SHA-256 de `server.py` v1: `f61e63c8720328920c2eba899e10a9960a9e18d9eb01ad2bd370bcd8015f973d`
- SHA-256 de la base v1: `54fbc3d464a353402ef78bcb40542ede9963690cf3033284fcfeaab630e9c03e`

---

## 10. Próximos pasos, en orden

1. **Desbloquear T3**: registrar las rutas del panel sobre `app` (sin blueprint).
   Correr `test_web.py` hasta 10/10.
2. **Conectar el servidor**: `server.py` usa `web/panel.py` + `web/robot.py`;
   `/talk` escribe en PostgreSQL vía `almacen/`. Verificar con el test de
   integración adaptado.
3. **T4**: `id` en "recientes" y en el CSV (ya hecho en `web/panel.py`;
   confirmar que el template lo muestre).
4. **T7**: `.bat` de Windows (Postgres local), `requirements.txt` con
   sqlalchemy/alembic/psycopg, README actualizado.
5. **T8**: reescribir `YACHAYBOT_IA.docx` (cap. 9, 15, 16, evidencias,
   arquitectura v2) — hay skill `word-desde-markdown`.
6. **T9**: instalar `gh`, crear el remoto, tag `v2.0-postgres`.

---

## 11. Archivos clave

| Ruta | Qué es |
|------|--------|
| `almacen/` | Frontera de datos: `config.py`, `esquema.py`, `repositorio.py`, `sesiones.py` |
| `robot/cerebro.py` | Wake word, clasificación temática, idioma, respuestas locales |
| `voz/` | Pendiente de poblar (STT/TTS siguen en `server.py`) |
| `web/panel.py` | Panel docente: dashboard, API, CSV ← **bloqueado aquí** |
| `web/agente.py` | Agente docente migrado a PostgreSQL (funciona) |
| `scripts/migrar_sqlite_a_postgres.py` | Migración idempotente con verificación |
| `alembic/` + `alembic.ini` | Versionado del esquema |
| `.hermes/plans/` | PRD + Kanban (transitorios, se borran al cerrar el hito) |
| `matt/matt.txt` | Transcripción del taller de Matt Pocock |
