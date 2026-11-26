# Sistema_QR — Fase 2.1: conexión y autenticación

## Qué se actualizó
- `sistema/conexion.py` ahora se conecta a `tesis_qr` y comprueba las 12 tablas obligatorias más `MOVIMIENTOS_INVENTARIO` y `TASAS_BCV`.
- Se eliminó la creación automática del esquema antiguo. Python ya no crea tablas distintas al modelo aprobado.
- Se mantuvo SHA-256 para compatibilidad con los usuarios iniciales insertados por el SQL (`SHA2(..., 256)`).
- Se añadieron funciones de autenticación, consulta, transacción, registro de auditoría, listado/creación de usuarios y cambio de estado/contraseña.
- Se añadió `sistema/probar_acceso_bd.py` para probar conexión y acceso sin abrir todavía las pantallas funcionales antiguas.

## Importante: alcance de esta entrega
Esta es la primera subfase de adaptación. La interfaz V2 original se conserva completa, pero todavía consulta varias tablas/campos antiguos (`pistones`, `facturas`, `factura_detalle`, etc.). Por eso **no ejecute todavía `main_gui.py` esperando que todos los módulos funcionen**. Primero se adaptarán los módulos de pistones, inventario, ventas, facturas y BCV al nuevo modelo.

## Cómo probar esta subfase
1. Haga una copia de seguridad de cualquier base de datos que desee conservar.
2. Importe `base_de_datos/esquema_tesis.sql` en phpMyAdmin.
3. Encienda MySQL en XAMPP.
4. Abra una terminal en `Sistema_QR_V2/sistema`.
5. Ejecute `py probar_acceso_bd.py`.
6. Pruebe `admin` / `admin123` o `cajero` / `cajero123` si esos usuarios fueron creados por el SQL.

## Configuración opcional de MySQL
Por defecto se usa XAMPP local: host `localhost`, puerto `3306`, usuario `root`, contraseña vacía y base `tesis_qr`.
Se pueden definir las variables `SISTEMA_QR_DB_HOST`, `SISTEMA_QR_DB_PORT`, `SISTEMA_QR_DB_USER`, `SISTEMA_QR_DB_PASSWORD` y `SISTEMA_QR_DB_NAME`.

## Próxima subfase
Adaptar el módulo de usuarios de la interfaz y luego pistones/QR, manteniendo los nombres del modelo relacional en SQL.
