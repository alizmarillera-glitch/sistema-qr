# Cambios: botón Historial y rol CONTROL

Archivos: `conexion.py`, `produccion_repo.py`, `existencias_ui.py`, `main_gui.py`, `panel_ui.py`, `iconos.py`,
`verificar_esquema.py`, `instalacion_limpia.sql`, `pruebas/probar_lotes.py`. Al iniciar, `init_db()` migra solo
(haga copia de seguridad antes del primer arranque).

## 3. Botón Historial (Existencias)
- «Precio USD» ya se había movido a Inventario en la versión anterior; el botón **Historial** ocupa ese lugar en la barra.
- Muestra solo **rechazos definitivos** = piezas descartadas en «Recuperar / rechazar». Las rechazadas que aún esperan decisión siguen en «No conformes».
- Columnas: código y modelo, lote, cantidad rechazada, fecha, etapa del defecto, motivo y responsable de la decisión (el detalle añade defectos, observaciones y usuario).
- Filtros combinables: fecha desde/hasta, mes, año, lote, modelo y etapa.
- Contador del mes en curso (vuelve a cero cada mes) + total del filtro aplicado.
- **Permanente**: tabla propia `rechazos_definitivos` (copia de los datos, no depende del catálogo) con triggers que impiden UPDATE y DELETE.
  Los descartes anteriores se copian automáticamente al migrar (sin duplicar).

## 4. Rol CONTROL
- Rol nuevo `CONTROL` y columna `usuarios.etapa_asignada` (1 a 9). Un solo rol, la etapa se elige por usuario.
- Usuarios: al crear, aparece «Etapa asignada» si el rol es CONTROL; nuevo botón **Editar rol / etapa** (o doble clic). No puede cambiar su propio rol.

## 5. Permisos de CONTROL
- Ve el Resumen y Existencias (todos los lotes, 9 etapas, cantidades, resultados, observaciones, historial).
- Registrar pistón, Inventario, Ventas, Facturación y Usuarios: mensaje «No tiene permisos para acceder a este módulo.» (también la ficha del pistón desde el Resumen).
- Modifica solo su etapa y solo cuando el lote está en ella. Las reglas se validan en `produccion_repo`, no solo ocultando botones.

## Decisiones a confirmar
1. Para CONTROL, evaluar pendientes y recuperar/descartar no conformes solo aplica a los originados en **su** etapa.
2. CONTROL no crea órdenes ni registra materia prima (no pertenecen a una etapa). Si Control 1 debe recibir materia prima, es un cambio de una línea.
3. Existe además el rol **Inventario** (ya estaba); se mantiene con acceso a todas las etapas.
4. Los cambios de etapa de un usuario rigen en cuanto abre/refresca Existencias.

## Validación
- `py pruebas/probar_lotes.py`: 135 comprobaciones correctas (SQLite).
- Probado contra MariaDB 10.11 real: instalación limpia, `instalacion_limpia.sql`, migración de una base creada con la versión anterior (dos arranques seguidos), triggers de protección, permisos por etapa y filtros.
- **No se pudo ejecutar la pantalla (Tkinter) en este entorno**: revise visualmente Historial, Usuarios y el acceso de un usuario CONTROL.
