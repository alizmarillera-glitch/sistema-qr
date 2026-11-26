# Cambios: permisos del Cajero y «Editar usuario»

Archivos: `main_gui.py`, `panel_ui.py`, `LEEME.txt`. Sin cambios en la base de datos.

## 3. Permisos del rol Cajero
- Accede solo a: Resumen general, Inventario (solo consulta), Ventas y Facturación.
- Registrar pistón, Existencias y Usuarios muestran «Acceso denegado» (el mismo mensaje y mecanismo que CONTROL). El menú lateral es igual para todos los roles.
- Inventario sin edición: no tiene interruptor de estado, «Eliminar» ni «Modificar precio», y la ficha del pistón es de solo lectura.
- Accesos rápidos del Resumen: Inventario, Nueva venta y Facturación.
- Administrador y CONTROL no cambian. Los permisos ahora viven en una sola tabla (`MODULOS_ROL` en `main_gui.py`).

## 4. Módulo Usuarios
- Se eliminó «Cambiar contraseña». «Editar rol / etapa» pasó a **Editar usuario** (también con doble clic en la fila).
- La ventana muestra ID, fecha de creación y último acceso, y permite cambiar: nombre de usuario, contraseña (con confirmación; en blanco conserva la actual), rol, etapa (solo si el rol es CONTROL) y estado (activo/desactivado).
- Validaciones: nombre obligatorio, máximo 40 caracteres y único; contraseñas que coinciden; CONTROL exige etapa; al pasar a otro rol se borra la etapa; si no hay cambios lo avisa.
- En la cuenta propia se puede cambiar nombre y contraseña, pero no el rol ni el estado (evita quedarse sin administrador).
- Solo el Administrador puede editar usuarios. Cada edición queda en la bitácora (`USUARIO_EDITADO`) con el detalle de lo cambiado; la contraseña nunca se registra.

## Validación
- Interfaz ejecutada en pantalla virtual sobre MariaDB real: acceso/denegación de los siete módulos para Cajero, Administrador y CONTROL; edición de usuario (nombre, contraseña, rol, etapa, estado), duplicados, confirmación distinta, contraseña en blanco, cuenta propia y verificación de inicio de sesión con las credenciales nuevas.
- `py pruebas/probar_lotes.py`: sin regresiones.
