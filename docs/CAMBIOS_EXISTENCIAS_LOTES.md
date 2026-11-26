# Módulo Existencias: seguimiento de producción por lotes

No se cambió el framework, el menú lateral ni el diseño (tema oscuro, tarjetas, tipografías). Archivos modificados:

| Archivo | Cambio |
|---|---|
| `sistema/existencias_ui.py` | Pantalla reescrita con la misma estructura visual: lotes activos/finalizados, resumen del lote, 9 pasos, registro de resultados, no conformes y trazabilidad. |
| `sistema/produccion_repo.py` | Lógica de lotes, calidad por etapa, no conformes, reproceso y liberación única al stock. |
| `sistema/conexion.py` | Esquema nuevo + migración automática de bases ya creadas (se ejecuta sola al iniciar). |
| `sistema/panel_graficos.py` | La tarjeta «En revisión / rechazo» muestra dos cifras separadas. |
| `sistema/main_gui.py` | Se eliminaron los diálogos de Entrada, Salida y Ajuste físico. «Precio USD» se conserva. |
| `pruebas/probar_lotes.py` | Prueba automática de las reglas (no requiere XAMPP). |

## Cómo funciona

**Botones.** Desaparecen Entrada, Salida y Ajuste físico. La barra queda: Nueva orden, Completar paso, Lotes activos (n), Finalizados, No conformes, Materia prima (recepción) y Precio USD.

**Varios lotes.** «Lotes activos» lista cada lote con modelo, «Paso N de 9» y estado. Al elegir uno (doble clic o «Ver lote») toda la pantalla cambia a ese lote. Las cuatro tarjetas superiores siempre muestran los totales generales.

**Nueva orden.** Pide código del lote, pistón, cantidad inicial, materia prima (kg), fecha de inicio, responsable y observaciones. Crea 9 etapas nuevas (la 1 «En proceso», las demás «Pendiente») sin tocar lotes anteriores. El código del lote se sugiere (AL-001, AL-002…) pero se puede editar; no se permiten repetidos.

**Completar paso.** Abre el registro de resultados: recibidas, procesadas, aprobadas, rechazadas, pendientes, motivo, defectos, observaciones, responsable y fecha/hora. Valida que aprobadas + rechazadas + pendientes = procesadas (y que se procesen todas las recibidas). Solo las aprobadas pasan a la etapa siguiente.

**Estados de etapa.** Pendiente, En proceso, Completado, Completado con observaciones (si hubo rechazos, pendientes u observaciones) y Bloqueado (botón «Bloquear por incidencia»; no se puede completar hasta desbloquear).

**No conformes.** Los rechazos se guardan en un registro independiente (lote, modelo, etapa, cantidad, motivo, defectos, responsable, fecha) y nunca entran al stock. «Registrar reproceso» exige una nueva inspección; solo las piezas recuperadas ingresan al stock y el saldo del registro baja en la misma transacción, por lo que no se pueden contar dos veces.

**Pendientes de evaluación.** Quedan retenidas en su etapa y no avanzan. «Evaluar piezas pendientes» las aprueba (se suman a lo que recibe la etapa siguiente, si esta aún no se completó) o las rechaza (pasan a no conformes).

**Ingreso al stock.** Ocurre al completar el paso 9 (Liberación para la venta): un movimiento de tipo `PRODUCCION` vinculado a lote y orden (ej.: 67 + 92 = 159). Se ejecuta una sola vez: la orden queda marcada como liberada y se bloquea la fila durante la operación. Consultar o reabrir el lote no suma nada.

**Trazabilidad.** «Ver trazabilidad y control de calidad» muestra fechas de inicio y fin, etapas con cantidades y responsables, no conformes, movimientos de materia prima, ingreso al almacén e historial. «Finalizados» conserva los lotes terminados.

## Decisiones que conviene validar

1. **Pasos 1 a 3 (materia prima) no cuentan piezas**: registran responsable, fecha/hora y observaciones. El conteo de piezas empieza en el paso 4 (Moldeado), como ya funcionaba.
2. **El stock entra en el paso 9**, no en el 8 como antes. El paso 8 solo recibe los aprobados en el almacén.
3. **Un paso con 0 aprobadas cierra el lote** sin producción (si además hay pendientes, primero deben evaluarse).
4. **Reproceso**: solo puede recuperar piezas hacia el stock cuando el lote ya fue liberado.
5. **Tarjeta «Rechazados»**: suma lo rechazado que no se recuperó (incluye lo descartado).
6. **Materia prima disponible** es el saldo de recepciones menos consumos; no hay estado de aprobación del aluminio por separado.
7. Se quitó el ajuste físico: ya no hay forma de corregir el stock desde la pantalla. Si la necesita para diferencias de conteo, conviene un ajuste restringido al administrador.

## Bases de datos existentes

Al iniciar, `init_db()` amplía las columnas y los ENUM, y marca como ya liberadas las órdenes antiguas que sumaron stock al completar el paso 8 (para no duplicarlo). Copia sus rechazos antiguos al registro de no conformes, una sola vez. Haga una copia de seguridad antes del primer arranque.

El archivo `instalacion_limpia.sql` no incluye las tablas de producción (ya era así); las crea el programa.
