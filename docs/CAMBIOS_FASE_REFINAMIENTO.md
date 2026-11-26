# Fase de refinamiento: cambios

## 1. Mensaje de inicio de sesión con usuario desactivado
- `sistema/conexion.py`: nueva `verificar_credenciales()` (busca por usuario y contraseña **sin** filtrar por estado),
  excepción `UsuarioDesactivado` y constante `MSG_USUARIO_DESACTIVADO`. `autenticar_usuario()` ahora la usa.
- `sistema/main_gui.py` (`Login.entrar`): si las credenciales son correctas pero `usuarios.estado = 0`, muestra
  «Este usuario se encuentra desactivado. Comuníquese con el administrador del sistema.» (aviso ámbar, de 2 líneas)
  y registra el intento en `log_usuarios` como FALLIDO con descripción específica.
- Si la contraseña es incorrecta se sigue mostrando «Usuario o contraseña incorrectos.», aunque la cuenta esté
  desactivada (no se revela el estado de una cuenta a quien no conoce la contraseña).
- No hay cambios en la base de datos.

## 2. Ficha del pistón al escanear un QR (`mostrar_detalle_piston`)
- Cabecera fija + cuerpo con desplazamiento vertical (rueda del ratón y barra) + botón «Continuar» siempre visible.
- Ventana redimensionable (mínimo 640 x 420); los textos largos reajustan su salto de línea al ancho de la tarjeta.
- Sin cambios de colores ni de distribución.

## 3. Iconografía (estilo Lucide)
- Nuevo `sistema/iconos.py`: catálogo de iconos en geometría SVG de Lucide (rejilla 24, trazo redondeado) y dibujo con
  Pillow. Mismo grosor de trazo (1,6 px) en todos los tamaños; variantes clara/oscura automáticas.
  Para cambiar un icono, pegue en `ICONOS` el contenido del SVG de lucide.dev.
- Navegación: Resumen = layout-dashboard · Registrar pistón = piston (diseño propio) · Inventario = boxes ·
  Existencias = arrow-left-right · Ventas = shopping-cart · Facturación = receipt-text · Usuarios = users.
  Activo = azul sobre fondo suave; inactivo = gris.
- KPI: Referencias = tag · Unidades = package · Stock bajo = triangle-alert · Desactivados = ban.
- Marca (sidebar y login) = qr-code; checks del login = check; mostrar/ocultar contraseña = eye / eye-off.
- Botones: Escanear QR = scan-qr-code · entrada = plus · salida = minus · Actualizar = refresh-cw ·
  Agregar usuario = user-plus · Cerrar sesión = log-out · «Abrir →» = arrow-right · Datos del cliente = id-card.
- Avisos y notificaciones: check / triangle-alert / x / circle-help.
- Disponible sin uso todavía: `sliders-horizontal` (para una futura pantalla de Configuración).

## 4. Buscador del inventario
- **Diseño** (`ui.Buscador`): campo limpio con **lupa** como único identificador (ya no hay un rótulo «Buscar por código o
  descripción»). Texto de ayuda breve y discreto («Código, marca, modelo, motor…») que desaparece al escribir. Al enfocarlo, el
  borde y la lupa pasan a azul cobalto; aparece una «×» para borrar (también Esc). Nuevo icono `search` en `iconos.py`.
- **Búsqueda dinámica**: los resultados se actualizan mientras se escribe (pausa de 120 ms para no recalcular en cada tecla),
  también al pegar o cortar. Debajo del campo se informa «N de M · orden alfabético / orden por código» o «Sin resultados».
- **Dónde busca** (`sistema/busqueda.py`): código, descripción (que es donde hoy viven marca, modelo, motor y aplicación del
  vehículo) y especificación de cámara. Las palabras se combinan con «y» (`ford 1.6`) y pueden ir en cualquier orden.
  No distingue mayúsculas ni tildes (`camion` encuentra «Camión»). El código también se encuentra sin guiones
  (`epv1725`, `1254asu`) a partir de 4 caracteres.
  Si en el futuro la tabla `pistones` incorpora columnas `marca`, `modelo`, `motor` o `aplicacion`, ya están previstas en
  `busqueda.CAMPOS_BUSQUEDA` y se usan automáticamente.
- **Orden**: si lo escrito coincide con el código (o no se escribió nada) → orden natural de códigos
  (`12-54ASU`, `14-09ZA`, `18-05`, `21-12GRU`, `21-22`, …, `1009`, `EPV-…`: los números se comparan como números, `9` < `10`).
  En cualquier otro caso (marca, modelo, motor, aplicación, descripción) → orden alfabético por descripción
  (Chevrolet, Ford, Hyundai, Toyota…), y a igualdad por código.
- **Sin duplicados** (cada pistón sale una vez, por su `id`) y **sin tocar los datos**: el catálogo se lee una vez, se filtra
  y se ordena una copia en memoria; la base de datos y el orden original no se modifican. Además ya no se consulta MySQL en
  cada tecla (antes eran una consulta más una por fila), solo al abrir la pantalla y tras cada cambio.
- La fila seleccionada se conserva mientras siga apareciendo en los resultados.
- Pruebas de la lógica: `py probar_busqueda.py` (desde `sistema`).

## 5. Estados visuales de los botones
Sistema de tres estados en `ui.Boton` (colores nuevos en `estilos.py`: `cobalto`, `cobalto_soft`, `btn_borde`…):

| Estado | Aspecto |
|---|---|
| Normal | fondo blanco (o transparente), borde fino, texto e icono oscuros, esquinas redondeadas |
| Hover | fondo azul muy suave, borde y texto en azul cobalto, icono azul; el cambio es instantáneo (CustomTkinter no anima colores) |
| Presionado / seleccionado | azul cobalto `#0047AB` completo, texto e icono blancos |
| Deshabilitado | atenuado y sin respuesta al cursor |

Tipos (`estilo=`):
- `accion` — acción puntual (Registrar entrada, Registrar salida, Buscar cliente, Agregar pago, Escanear QR, Comprobar código,
  Agregar usuario…): se ilumina al pasar el cursor, destella en cobalto al pulsar (160 ms) y **vuelve a reposo**.
- `pri` — principal (Guardar…, Ingresar, Continuar · Facturar, Confirmar pago…): conserva el relleno cobalto (más luminoso en
  hover, más profundo al pulsar). Se reservó para la acción que cierra cada pantalla o ventana.
- `danger` — destructivas (Eliminar, Cancelar orden, Cerrar sesión): mismos tres estados en rojo.
- `ghost` — discreta, sin borde (Actualizar).
- `nav` — navegación (menú lateral): reposo gris, hover azul suave y la **pantalla activa queda en cobalto** con texto e icono
  blancos (`seleccionar()`).
- `seleccion` — selección persistente (para filtros o interruptores): cada clic alterna y lo seleccionado se queda en cobalto.
  Hoy ninguna pantalla lo usa; está listo.
- Los alias `sec` y `outline` equivalen a `accion`.

Efecto: los botones que antes estaban siempre rellenos de azul (p. ej. «Registrar entrada», «Escanear QR», «Agregar usuario»)
pasan a ser `accion`; el azul lleno queda para lo principal y para lo que el usuario acaba de activar.
Limitación de CustomTkinter: no dibuja sombras con difuminado; el «relieve discreto» se logra con el borde fino de tono propio
y el cambio de fondo en hover.

## 6. Teléfono del cliente: prefijo + siete dígitos
- **Pantalla** (`ui.CampoTelefono`, usado en «Datos del cliente» al facturar): `[ 0412 ▼ ] [ 1234567 ]`.
  - Selector con los prefijos 0412, 0414, 0416, 0422, 0424 y 0426; valor predeterminado **0412**.
  - El segundo campo solo acepta dígitos (teclado y pegado) y como máximo **7**.
  - Al guardar un cliente nuevo se rechaza un número vacío o incompleto, con un mensaje que indica cuántos dígitos faltan.
- **Base de datos**: sin cambios. Se guarda el número completo en `clientes.telefono` (VARCHAR(40)), p. ej. `04221234567`.
- **Recuperación**: al buscar un cliente existente, el prefijo y los siete dígitos se separan solos (también si el
  número se guardó como `0412-1234567`, `+58 412 1234567` o `4121234567`). Un teléfono guardado con otro formato
  (p. ej. fijo) se muestra sin alterarlo.
- **Ampliar la lista**: agregue el prefijo a `PREFIJOS_MOVIL` en `sistema/telefono.py` (único lugar).
- **Doble validación**: `ventas_repo.guardar_cliente` repite la comprobación (prefijo de la lista + 7 dígitos) antes de insertar.
- Nota: la aplicación no tiene hoy una pantalla de edición de clientes; el selector ya expone `set()/get()` para cuando exista.

## 7. Registro de pistones con los datos de la etiqueta física
- **Formulario** (`main_gui.construir_campos_piston`, compartido por «Registrar pistón» y la ficha de edición), en tres secciones:
  - **A · Identificación**: código del pistón, cantidad de piezas, offset, fecha.
  - **B · Aplicación del vehículo**: marca, modelo o aplicación, motor, año o rango de años.
  - **C · Características técnicas**: trazabilidad, diámetro del pistón (mm), diámetro del cilindro (mm).
  - «Otras medidas (opcional)»: sobremedida, altura de compresión, diámetro del pasador y especificación de cámara (ya existían; se conservan para no perder datos ni cambiar etiquetas/QR).
- **Sin cambios**: la imagen, el código principal (comprobación de duplicados, formato EPV-XXXXX-XXX-X), el QR, la etiqueta y el stock.
- **Obligatorios al registrar** (marcados con *): código, marca, modelo o aplicación, cantidad de piezas y diámetro del pistón.
  El resto es opcional. Para exigir más campos, edite `OBLIGATORIOS_NUEVO` en `main_gui.py`.
- **Validaciones**: cantidad de piezas solo dígitos (1–999999); diámetros numéricos con punto o coma (pistón 2 decimales,
  cilindro 3); fecha DD/MM/AAAA (se normaliza; se propone la de hoy); año `2005` o rango `2005-2010` (no invertido);
  textos con el largo máximo de la columna. Los campos filtran lo que se teclea y lo que se pega.
- **Descripción automática**: se arma como «Marca Modelo Motor» (p. ej. *Ford F-150 4.2L V6*) y se muestra en vivo.
  Es la que usan el inventario, las ventas y la etiqueta, por lo que nada existente cambia. Si los tres datos están vacíos
  (pistones antiguos), se conserva la descripción que ya tenían.
- **Base de datos** (`conexion.py`): `pistones` gana `marca_vehiculo`, `modelo_aplicacion` y `motor`. Las demás columnas de la etiqueta
  (año, piezas, offset, fecha, trazabilidad, diámetro del cilindro) ya existían. La migración es **aditiva e idempotente**: al abrir el
  programa agrega solo las columnas que falten, sin tocar los datos. `instalacion_limpia.sql` también las incluye.
- **Cantidad de piezas ≠ existencias**: se guarda como dato técnico (`numero_piezas`). El stock sigue naciendo en 0 y solo cambia con
  entradas, salidas y ajustes, como antes.
- **Buscador, ficha y QR**: el buscador del inventario encuentra por marca, modelo, motor y año sin cambios; la ficha del QR y la
  ficha de inventario muestran y permiten editar los datos nuevos (los pistones antiguos se pueden editar sin que se exija lo nuevo).

## 8. Identidad visual: logo y banner de la empresa
- **Archivos** (carpeta `recursos/`): `logo_empresa.png` (logo con fondo transparente) y `banner_login.jpg` (banner del acceso).
  Para cambiarlos, reemplace los archivos conservando el nombre. El código está en `sistema/marca.py`.
- **Acceso (panel izquierdo)**: el banner con el logo ocupa la parte superior del panel (esquinas redondeadas, recortado sin deformarse);
  debajo siguen el titular y las viñetas. Se adapta al tamaño de la ventana; en ventanas bajas reduce tamaños y omite viñetas que no caben.
  El ícono QR y los textos de marca que había arriba se quitaron porque el banner ya trae el logo.
- **Barra lateral**: se reemplazó el ícono QR + «Sistema QR / Manufacturas de Aluminio» por el logo de la empresa (pistón y
  «Manufacturas de Aluminio I, C.A.»). El logo se muestra con tinta negra en modo claro y blanca en modo oscuro (se genera solo).
- **Título de la ventana**: «Sistema QR - usuario (rol)» pasó a «Manufacturas de Aluminio I, C.A. - usuario (rol)».
- Si falta alguna imagen, el programa abre igual con la marca de texto anterior.
- No cambian: los íconos funcionales (p. ej. «Escanear QR»), las etiquetas QR de los pistones ni las facturas.
