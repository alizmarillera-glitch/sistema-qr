# Cambios: precio en Inventario y ventana «No conformes» con pestañas

Sin cambios de base de datos (no hay tablas ni columnas nuevas). Archivos modificados:
`sistema/main_gui.py`, `sistema/existencias_ui.py`, `sistema/produccion_repo.py`, `sistema/ventas_repo.py` (solo un texto),
`pruebas/probar_lotes.py` (sección 8 nueva).

## 1. Precio USD pasa a Inventario
- Se eliminó el botón «Precio USD» de Existencias.
- Inventario → barra de administración: botón **Modificar precio** (Administrador e Inventario) sobre el pistón seleccionado.
- Ficha del pistón (doble clic): botón **Modificar precio**; el precio mostrado se actualiza al guardar.
- El diálogo ya no tiene lista desplegable: queda fijo en el pistón elegido y muestra el historial de precios.
- Sigue usando `db.establecer_precio` (cierra el precio vigente y abre uno nuevo): Ventas y Facturación leen el mismo precio vigente
  y las facturas anteriores no cambian. Si hay una orden de venta abierta, se refresca con el precio nuevo.

## 2. No conformes: ventana con dos pestañas
**Pistones rechazados** (por defecto, todos los lotes): registros con piezas por recuperar o descartar. Botón **Recuperar / rechazar**
(el mismo proceso de reproceso de antes). «Mostrar historial» añade los ya resueltos.

**Pistones en revisión** (todos los lotes): piezas retenidas sin evaluar. Botón **Aprobar / rechazar**: las aprobadas continúan al
paso siguiente; las rechazadas pasan a la pestaña «Pistones rechazados». «Mostrar historial» añade las ya evaluadas.

Cada pestaña muestra su conteo. «Solo el lote elegido» ya no viene activado por defecto (antes ocultaba los demás lotes).

### Conteos
- Una pieza recuperada deja de contarse como rechazada: tarjeta general, resumen del lote, trazabilidad y lista de finalizados.
- Una pieza evaluada deja de estar «en revisión».
- No se borra ni modifica nada original: motivo, defectos, cantidad, etapa, fecha, reprocesos e historial del lote se conservan.
  La trazabilidad del lote incluye una sección nueva de piezas en revisión.

## Reglas que se mantienen (conviene confirmar)
- Recuperar por reproceso exige que el lote ya esté liberado (para no duplicar stock).
- Piezas en revisión: solo pueden aprobarse si el lote sigue en producción y el paso siguiente no está completado; si no, solo se rechazan.
- «Rechazados» de la tarjeta suma lo no recuperado (incluye lo descartado, que es el rechazo definitivo).

## Validación
`py pruebas/probar_lotes.py` (SQLite en memoria, sin XAMPP): todas las secciones correctas. La pantalla (Tkinter/MySQL) no pudo
ejecutarse en el entorno de desarrollo: pruébela una vez en su equipo.
