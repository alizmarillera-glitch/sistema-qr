# Reconstrucción de la base de datos — Sistema_QR

## Criterio de diseño

El modelo incluye las 12 tablas obligatorias del PDF `esquema_relacional_QR_v4.pdf`. Se conservan sus nombres y los campos base mostrados en el diagrama. Se agregan campos y dos tablas auxiliares porque el profesor autorizó extensiones y el sistema necesita mantener inventario y tasas BCV.

## Tablas obligatorias (12)

1. `ROLES`
2. `USUARIOS`
3. `LOG_USUARIOS`
4. `DETALLE_PAGO`
5. `METODO_PAGO`
6. `CLIENTES`
7. `FACTURAS`
8. `PAGO`
9. `DETALLE_FACTURA`
10. `PRECIOS_PISTONES`
11. `PISTONES`
12. `CODIGOS_QR`

## Tablas adicionales (2)

- `MOVIMIENTOS_INVENTARIO`: entradas, salidas, ajustes y aperturas; cada movimiento conserva cantidad, motivo, fecha, usuario, factura relacionada y saldo anterior/nuevo.
- `TASAS_BCV`: historial de tasas consultadas, fecha efectiva, fecha de consulta, fuente y validación.

## Extensiones principales a las tablas obligatorias

- `PISTONES`: `stock_actual`, `stock_minimo`, imagen y campos técnicos adicionales que ya utiliza el formulario. `numero_piezas` es un dato técnico y no equivale a existencias.
- `FACTURAS`: tasa BCV, fecha efectiva, equivalentes de subtotal/IVA/total en bolívares y moneda base. La factura conserva la tasa histórica aplicada.
- `DETALLE_PAGO`: moneda, tasa aplicada y observación para admitir pagos mixtos y conciliación.
- `CLIENTES`: código interno para conservar el formato `CLI-000001`.

## Funcionalidades y destino de sus datos

| Funcionalidad | Tabla/campos de destino |
|---|---|
| Inicio de sesión y roles | `USUARIOS`, `ROLES` |
| Auditoría de acciones | `LOG_USUARIOS` |
| Registro y ficha técnica del pistón | `PISTONES` |
| Precio vigente e histórico | `PRECIOS_PISTONES` |
| Existencias actuales | `PISTONES.stock_actual` |
| Entradas, salidas y ajustes | `MOVIMIENTOS_INVENTARIO` |
| Salida automática al facturar | `MOVIMIENTOS_INVENTARIO` enlazada a `FACTURAS` |
| Datos de clientes | `CLIENTES` |
| Facturas y líneas | `FACTURAS`, `DETALLE_FACTURA` |
| Pagos y pagos divididos | `PAGO`, `DETALLE_PAGO`, `METODO_PAGO` |
| Consulta e historial BCV | `TASAS_BCV` |
| Tasa y equivalentes usados en una factura | Campos adicionales de `FACTURAS` |
| QR y ubicación de imagen QR | `CODIGOS_QR` |
| Fotografía del pistón | `PISTONES.imagen` |

## Diferencias detectadas en el programa recibido

- El código Python consulta nombres anteriores: `usuarios`, `factura_detalle`, `movimientos_inventario`, etc., y espera campos como `id`, `codigo`, `stock`, `precio`, `numero` y `fecha`.
- El modelo del PDF utiliza claves y nombres distintos: `id_usuario`, `codigo_piston`, `id_factura`, `nro_factura`, `fecha_hora`, `precio_unitario`, entre otros.
- El programa actual guarda el precio directamente en `PISTONES`; la reconstrucción lo traslada a `PRECIOS_PISTONES` para mantener historial de vigencia.
- El QR y la etiqueta actualmente se guardan como rutas dentro de `PISTONES`; la reconstrucción registra el QR en `CODIGOS_QR` y conserva la foto del pistón en `PISTONES.imagen`.
- La venta actual descuenta stock y genera movimiento, pero todavía no registra pagos mediante `PAGO` y `DETALLE_PAGO`. Esa integración forma parte de la adaptación del módulo de ventas.
- El módulo BCV ya consulta en línea y guarda la tasa en la factura; se agregará además el historial en `TASAS_BCV`.

## Orden de trabajo

1. Crear y validar esta estructura SQL en una base de pruebas.
2. Adaptar `conexion.py` para que no vuelva a crear el esquema antiguo.
3. Adaptar autenticación, usuarios y registro de auditoría.
4. Adaptar pistones, precios, QR y etiquetas.
5. Adaptar inventario y movimientos.
6. Adaptar clientes, facturación, tasa BCV y pagos.
7. Ejecutar pruebas de integración y entregar una versión empaquetada.

## Advertencia

El script SQL crea una estructura limpia y usuarios iniciales de instalación (`admin` y `cajero`). No importa datos de la base anterior. Antes de reemplazar la base real, exporte una copia de seguridad. La aplicación Python aún debe adaptarse a los nombres nuevos antes de ejecutar esta estructura como sistema final.
