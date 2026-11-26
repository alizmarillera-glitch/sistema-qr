# Cambios: sin rol Inventario e interruptor de estado de pistones

Archivos: `conexion.py`, `produccion_repo.py`, `main_gui.py`, `existencias_ui.py`, `instalacion_limpia.sql`, `pruebas/probar_lotes.py`, `LEEME.txt`.

## 1. Rol Inventario eliminado
- Ya no se crea (semillas y `instalacion_limpia.sql`) ni aparece al crear/editar usuarios. Roles vigentes: Administrador, Cajero y CONTROL.
- **Migración automática** (al iniciar, idempotente): los usuarios que tenían el rol pasan a **Cajero** (el de menor alcance), se anotan en la
  bitácora (`ROL_ELIMINADO`) y se borra el rol de la tabla `roles`. El administrador puede reasignarlos después con «Editar rol / etapa».
- Permisos: lo que antes tenía Inventario (producción, precios, administrar lotes) queda solo para el Administrador. El módulo Inventario sigue igual.

## 2. Interruptor de activar/desactivar pistones
- Reemplaza el botón «Activar / desactivar» (solo Administrador). Refleja el pistón seleccionado: **verde = activo, rojo = desactivado**; sin selección queda gris y deshabilitado.
- Pide confirmación; si se cancela, vuelve a su posición.
- La columna ESTADO usa el estilo de Usuarios: «● Activo» en verde y «● Desactivado» en rojo (reemplaza el gris anterior).
- Solo cambia `pistones.activo`: no elimina el pistón ni toca sus existencias. Ventas (agregar, escanear QR) y Facturación ya rechazaban pistones desactivados.

## Validación
- `py pruebas/probar_lotes.py`: 136 comprobaciones correctas.
- MariaDB real: migración de una base con rol Inventario y un usuario asignado (dos arranques), instalación limpia y SQL.
- Interfaz ejecutada en pantalla virtual: interruptor (activar, desactivar, cancelar), colores, existencias intactas y menú/permisos de CONTROL.

## A tener en cuenta
Un pistón desactivado con un lote en producción no podrá liberarse al stock en el paso 9 hasta reactivarlo (regla que ya existía).
