# Kanban — Hito II YACHAYBOT

> **Tablero de trabajo** de la fase 3 de la metodología de Matt Pocock.
> Cada issue es una rebanada vertical: cruza esquema + servicio + ruta + UI + test.
> "bloqueado por" define qué debe estar verde antes de tomar el issue.
> Se conserva versionado como evidencia del proceso de planificación.

## T0 — Congelar la v1 (AFK)
- [x] T0 · Commit inicial + tag `v1.0-sqlite` con los 32 tests verdes — `24cde9f`
- [ ] T0 · `server.py` → `server.py.old` (preserva el SHA-256 citado en el informe)

## Fase 1 — Fundaciones (paralelo tras T0)
- [x] T1 · Git + estructura de paquetes `almacen/ voz/ robot/ web/` + config — `fdb19d1`
- [x] T2 · Esquema PostgreSQL con Alembic + `almacen/` como único punto de acceso — `fdb19d1`

## Fase 2 — Rebanadas verticales (paralelo tras T2)
- [ ] T3 · Rebanada "leer historial": `almacen/` expone conteos; `/api/estadisticas` y `/dashboard`
      leen de Postgres; el agente consume `almacen/` en solo lectura. Test end-to-end del esquema al panel.
      **Estado: en curso.** `web/panel.py`, `web/agente.py`, `almacen/sesiones.py` y `test_web.py`
      están escritos y commiteados (`57d632c`). 9 de 10 pruebas pasan. Falta corregir el nombre de
      los endpoints del panel: el blueprint antepone el prefijo `panel.` y
      `templates/dashboard.html:132` usa `url_for('dashboard')` sin prefijo → `BuildError`.
      Fix: registrar las rutas directamente sobre `app`, sin blueprint.
- [ ] T4 · Rebanada "registrar interacción": `/talk` persiste en Postgres vía `almacen/`; el `id` queda
      expuesto en "recientes" y en el CSV. Test del ciclo escribir→leer (bloqueado por T3)
- [x] T5 · Rebanada "migrar 51 registros": script SQLite→Postgres idempotente + verificación de conteos — `fdb19d1`
- [x] T6 · Rebanada "fix EX05": test rojo con `restaurante`→espera `Otros`; comparación por palabra
      completa. Sin cambio de comportamiento para los demás casos — `582936d`

## Fase 3 — Cierre
- [ ] T7 · Scripts Windows actualizados (.bat) + README + `requirements.txt` (bloqueado por T4)
- [ ] T8 · Actualizar `YACHAYBOT_IA.docx`: cap. 9, 15, 16, evidencias + arquitectura v2 (bloqueado por T7)
- [x] T9a · Remoto GitHub configurado; rama `master` y tag `v1.0-sqlite` subidos
- [ ] T9b · Tag `v2.0-postgres` al cerrar el hito (bloqueado por T8)

## Notas de secuencia

- T3 es la rebanada que da feedback end-to-end pronto: si funciona, el resto son variaciones.
- T4 y T5 son paralelizables entre sí; T6 también es independiente de T3/T4.
- T6 no depende de Postgres a propósito: es un fix puro del clasificador.

## Verificaciones ya ejecutadas (no repetirlas sin motivo)

- Migración de los 51 registros: idempotente, conteos origen vs destino coinciden.
- Agregados en PostgreSQL = valores del informe: total 51, respondidas 51, incidencias 0,
  100 %, promedio 6,09 s, 41 del 18 y 10 del 20 de agosto de 2026.
- EX05: "restaurante" → Otros; "resta" → Matemática; "robot" → Tecnología.
- Suite: 83 de 84 pruebas verdes (la que falla es el render del dashboard, por el bloqueo de T3).
