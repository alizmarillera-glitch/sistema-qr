# Sistema QR — Inventario, ventas y facturación con códigos QR

Aplicación de escritorio para la gestión de una fábrica de pistones: registro de piezas, generación de **QR y etiquetas imprimibles**, escaneo con cámara, control de producción por lotes, inventario, ventas y facturación en **USD y bolívares** con la tasa BCV.

> **Estado: en desarrollo.** Proyecto de tesis. Algunas funciones aún se están refinando; el historial de cambios está en [`docs/`](docs/).

## Funciones

- Registro y ficha técnica de pistones, con historial de precios.
- Generación de códigos QR y etiquetas imprimibles; escaneo de QR con la cámara.
- Existencias por lotes de producción en nueve etapas, con trazabilidad y piezas no conformes.
- Clientes, ventas con IVA, facturas, pagos mixtos (USD y Bs.) y comprobante en PDF.
- Tasa BCV consultada en línea, con respaldo manual e historial.
- Roles (Administrador, Cajero, CONTROL) y registro de actividad de usuarios.
- Panel de resumen con indicadores y gráficos, modo oscuro y pantalla de acceso personalizada.

## Tecnologías

Python · CustomTkinter (Tkinter) · MySQL/MariaDB (XAMPP) · Pillow · ReportLab · OpenCV · qrcode

## Instalación

Requiere Python 3.10 o superior y [XAMPP](https://www.apachefriends.org/) con MySQL encendido.

```bash
pip install -r requirements.txt
cd sistema
python main_gui.py
```

El programa crea la base `instalacion_limpia` y sus tablas al iniciarse. También puedes importar `base_de_datos/instalacion_limpia.sql` desde phpMyAdmin.

Por defecto se conecta a `localhost:3306` con usuario `root` y sin contraseña (configuración típica de XAMPP). Para cambiarlo, define antes de iniciar las variables `SISTEMA_QR_DB_HOST`, `SISTEMA_QR_DB_PORT`, `SISTEMA_QR_DB_USER` y `SISTEMA_QR_DB_PASSWORD`.

### Usuarios de demostración

| Rol | Usuario | Contraseña |
|---|---|---|
| Administrador | `admin` | `admin123` |
| Cajero | `cajero` | `cajero123` |

Son solo para probar el sistema. Cámbialas en cualquier instalación real.

## Pruebas

Estas pruebas no necesitan MySQL (usan una base SQLite simulada):

```bash
python pruebas/probar_lotes.py
python pruebas/probar_comprobante_pdf.py
```

## Estructura

```
sistema/          código de la aplicación (interfaz, repositorios, QR, PDF)
base_de_datos/    script SQL de instalación
pruebas/          pruebas de lógica
recursos/         logo, imágenes y datos de la empresa
docs/             notas de diseño y registro de cambios por fase
```

## Mejoras pendientes

- Guardar las contraseñas con un algoritmo con sal y costo ajustable (bcrypt o Argon2) en lugar de SHA-256 simple.
- Pruebas de integración automatizadas contra MySQL.
- Eliminar las credenciales de demostración y pedir crear el administrador en el primer arranque.
