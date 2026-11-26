# Fase 2.3 — Inventario y movimientos

## Alcance adaptado
- Entradas y salidas manuales de inventario.
- Ajustes físicos de existencias.
- Historial de movimientos con fecha, pistón, usuario, motivo y factura relacionada.
- Bloqueo de salidas superiores al stock disponible.
- Bloqueo de movimientos sobre pistones desactivados.
- Actualización de stock y registro del movimiento dentro de una misma transacción.
- Se deshabilita la eliminación física de pistones para proteger trazabilidad e historial.

## Archivos
- `sistema/inventario_repo.py`: operaciones SQL del inventario.
- `sistema/main_gui.py`: formularios de entrada, salida, ajuste e historial conectados al repositorio.
- `sistema/pistones_repo.py`: se mantiene el ajuste de stock utilizado por el catálogo.

## Esquema esperado
La implementación usa exclusivamente los nombres del nuevo modelo:
- `PISTONES.stock_actual`, `PISTONES.activo`, `PISTONES.id_piston`.
- `MOVIMIENTOS_INVENTARIO.id_movimiento`, `tipo`, `cantidad`, `motivo`, `fecha_hora`, `id_usuario`, `id_factura`, `stock_anterior`, `stock_nuevo`.
- `FACTURAS.id_factura`, `FACTURAS.nro_factura`.
- `USUARIOS.id_usuario`, `USUARIOS.nombre_usuario`.

## Validaciones realizadas
Se comprobó la sintaxis de los módulos Python con `py_compile` y la correspondencia de los SQL de inventario con el esquema incluido.

## Pendiente
La facturación aún conserva consultas antiguas y será adaptada en su fase correspondiente. Por eso esta entrega no debe considerarse una versión integral lista para operar contra MySQL.
