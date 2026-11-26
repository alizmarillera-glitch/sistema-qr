# Fase 3 — Validación del modelo relacional

## Resultado del diseño
- 12 tablas obligatorias del PDF: ROLES, USUARIOS, LOG_USUARIOS, DETALLE_PAGO, METODO_PAGO, CLIENTES, FACTURAS, PAGO, DETALLE_FACTURA, PRECIOS_PISTONES, PISTONES y CODIGOS_QR.
- 2 tablas auxiliares: MOVIMIENTOS_INVENTARIO y TASAS_BCV.
- Las tablas usan InnoDB y tipos coincidentes en las relaciones.
- Las FK que dependen de tablas creadas posteriormente se agregan al final mediante ALTER TABLE.

## Instalación recomendada
1. En XAMPP, iniciar MySQL.
2. Abrir phpMyAdmin.
3. Seleccionar la pestaña Importar y elegir `instalacion_limpia.sql`.
4. Este archivo crea (si no existe) únicamente `instalacion_limpia`. No elimina ni modifica `tesis_qr` ni `tesis_qr_v2`.
5. No ejecutar `esquema_tesis.sql` después de `instalacion_limpia.sql`: ambos crean el mismo modelo. El primero es la versión no destructiva para una base vacía; el segundo es el instalador repetible y limpio.

## Datos iniciales
Se crean los roles Administrador, Inventario y Cajero; y los métodos Zelle, Pago móvil, Transferencia, Bolívares y Divisa. Se crean los usuarios `admin` y `cajero` con contraseñas temporales `admin123` y `cajero123`. Cambiar ambas contraseñas después de la instalación.

## Validación efectuada en esta entrega
- Revisión estática de las 14 sentencias CREATE TABLE.
- Revisión de las FK declaradas y de las columnas referenciadas.
- Verificación de que los tipos de las columnas FK coinciden con las PK referenciadas.
- Revisión de las consultas de los repositorios de pistones, inventario, ventas, pagos y tasas contra los nombres de columnas del esquema.
- Compilación sintáctica de los archivos Python del proyecto.

## Limitación
No se pudo ejecutar una prueba de integración contra el MySQL del equipo del usuario. La creación efectiva, los permisos y la compatibilidad concreta dependen de la versión local de MySQL/MariaDB. La interfaz gráfica antigua aún requiere una ronda de pruebas funcionales completa; esta fase valida y corrige el modelo SQL y sus repositorios, no certifica toda la GUI.
