# Cambios: registro de pistón y etiqueta

La etiqueta lleva exactamente los datos del formulario de registro:

| Sección | Datos |
|---|---|
| 1 Información general | Número de piezas (del pistón, no del stock), offset, fecha (automática del equipo), código del pistón, código QR |
| 2 Información del motor | Aplicación (ej. Chrysler 318 - V8 - 5.2 Lts), características adicionales (ej. A/C - C/R) |
| 3 Tipo de cabeza | Imagen del pistón |
| 4 Medidas | Diámetro del pistón y del cilindro, en mm y pulgadas (ej. 100,789 mm (3.9681")) |
| 5 Trazabilidad | Ej. 14Q |

## Archivos modificados
- `sistema/main_gui.py`: formulario de registro con las 5 secciones; marca/modelo/motor/año se reemplazan por
  «Aplicación» y «Características adicionales»; la fecha es de solo lectura (fecha del equipo); diámetros con 3 decimales.
  La ficha de edición usa el mismo formulario y conserva «Otras medidas» (no van en la etiqueta).
- `sistema/generador_etiqueta.py`: nuevo diseño de la etiqueta (1000 x 730 px). Pulgadas = mm / 25,4 con 4 decimales.
- `sistema/conexion.py` y `base_de_datos/instalacion_limpia.sql`: columna nueva `pistones.caracteristicas_adicionales`;
  `diametro_mm` pasa a DECIMAL(10,3) (antes DECIMAL(8,2) en bases creadas por el programa, lo que redondeaba 100,789 a 100,79).
  La migración es automática al iniciar y no borra datos.

## Compatibilidad
- La «Aplicación» se guarda en `descripcion`, igual que antes (inventario y búsqueda no cambian).
- Las columnas marca_vehiculo, modelo_aplicacion, motor y anio ya no se escriben; los pistones antiguos conservan sus valores.
- Al abrir el programa, todas las etiquetas existentes se regeneran con el nuevo diseño.
