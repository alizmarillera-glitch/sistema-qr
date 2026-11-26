# Fase 2.2 — Adaptación del catálogo de pistones

## Qué se adaptó

- El inicio de sesión ahora utiliza `db.autenticar_usuario()` y las tablas `USUARIOS` + `ROLES`.
- Se incorporó `sistema/pistones_repo.py` como repositorio del modelo nuevo.
- El catálogo consulta `PISTONES`, `PRECIOS_PISTONES` y `CODIGOS_QR`.
- El alta crea el pistón, su precio inicial y su registro QR dentro de una transacción.
- La edición técnica actualiza las columnas del modelo nuevo y refresca el contenido QR.
- El cambio de imagen actualiza `PISTONES.imagen` y el registro activo de `CODIGOS_QR`.
- La activación/desactivación actualiza `PISTONES.activo`.
- El ajuste manual de existencias registra el cambio en `MOVIMIENTOS_INVENTARIO`.
- El precio se guarda como historial en `PRECIOS_PISTONES`, cerrando el precio vigente anterior.
- Se cambió la base de datos predeterminada a `tesis_qr_v2` para no chocar con la estructura antigua `tesis_qr`.

## Importante: alcance de esta entrega

La fase 2.2 cubre el catálogo de pistones y su ficha. Todavía quedan consultas SQL antiguas en módulos de movimientos de inventario, facturación, detalle de facturas, clientes y administración de usuarios. Esos módulos deben adaptarse en las siguientes subfases antes de considerar que toda la aplicación está lista para producción.

No ejecutar todavía la interfaz completa como prueba integral. Primero instalar la base nueva y continuar la adaptación de inventario/ventas/pagos.

## Instalación SQL corregida

Importar `base_de_datos/esquema_tesis.sql`. El archivo crea/usa `tesis_qr_v2`; no reutiliza la base antigua `tesis_qr`. Si `tesis_qr_v2` ya existe de un intento anterior, no se borran sus datos automáticamente. En ese caso, revisar su contenido antes de volver a importar porque el script usa `CREATE TABLE` sin `IF NOT EXISTS`.

## Verificaciones realizadas en esta entrega

- Compilación sintáctica de los archivos Python con `py_compile`.
- Revisión estática de los nombres de las 12 tablas obligatorias y 2 adicionales en el SQL.
- No se pudo probar una conexión MySQL real desde este entorno.
