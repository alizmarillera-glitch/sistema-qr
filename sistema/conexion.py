"""Conexión a MySQL (XAMPP) y esquema relacional de la base «instalacion_limpia».

Tablas principales: roles, usuarios, log_usuarios, clientes, facturas, detalle_factura,
pago, detalle_pago, metodo_pago, pistones, precios_pistones, codigos_qr.

Tablas complementarias: existencias (stock físico), movimientos_inventario (trazabilidad),
tasa_factura (tasa y equivalentes en Bs. de cada factura) y tasas_bcv (historial de tasas).
"""
import contextlib
import glob
import hashlib
import os

import mysql.connector

# Configuración XAMPP por defecto. Puede personalizarse mediante variables de entorno.
CFG = dict(
    host=os.getenv("SISTEMA_QR_DB_HOST", "localhost"),
    port=int(os.getenv("SISTEMA_QR_DB_PORT", "3306")),
    user=os.getenv("SISTEMA_QR_DB_USER", "root"),
    password=os.getenv("SISTEMA_QR_DB_PASSWORD", ""),
    charset="utf8mb4",
)
DB = "instalacion_limpia"

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE, "imagenes_pistones")
ETQ_DIR = os.path.join(BASE, "etiquetas_generadas")

# --------------------------------------------------------------------------- ESQUEMA
SCHEMA = [
# ---- Seguridad
"""CREATE TABLE IF NOT EXISTS roles(
  id_rol INT AUTO_INCREMENT PRIMARY KEY,
  nombre_rol VARCHAR(40) NOT NULL,
  descripcion VARCHAR(255) NULL,
  UNIQUE KEY uq_roles_nombre (nombre_rol))""",
"""CREATE TABLE IF NOT EXISTS usuarios(
  id_usuario INT AUTO_INCREMENT PRIMARY KEY,
  id_rol INT NOT NULL,
  nombre_usuario VARCHAR(40) NOT NULL,
  clave_hash VARCHAR(255) NOT NULL,
  estado TINYINT(1) NOT NULL DEFAULT 1,
  fecha_creacion TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  etapa_asignada TINYINT NULL,
  UNIQUE KEY uq_usuarios_nombre (nombre_usuario),
  CONSTRAINT fk_usuarios_roles FOREIGN KEY (id_rol) REFERENCES roles(id_rol))""",
"""CREATE TABLE IF NOT EXISTS log_usuarios(
  id_log BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_usuario INT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  accion VARCHAR(60) NOT NULL,
  descripcion VARCHAR(500) NULL,
  resultado VARCHAR(20) NOT NULL DEFAULT 'OK',
  INDEX idx_log_usuario_fecha (id_usuario, fecha_hora),
  CONSTRAINT fk_log_usuarios FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario))""",
# ---- Clientes
"""CREATE TABLE IF NOT EXISTS clientes(
  id_cliente INT AUTO_INCREMENT PRIMARY KEY,
  tipo_documento ENUM('V','E','J','P') NOT NULL,
  documento VARCHAR(40) NOT NULL,
  nombre_razon_social VARCHAR(150) NOT NULL,
  telefono VARCHAR(40) NULL,
  correo VARCHAR(150) NULL,
  direccion VARCHAR(255) NULL,
  fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  codigo_cliente VARCHAR(20) NULL,
  UNIQUE KEY uq_clientes_documento (documento),
  UNIQUE KEY uq_clientes_codigo (codigo_cliente))""",
# ---- Pistones
"""CREATE TABLE IF NOT EXISTS pistones(
  id_piston INT AUTO_INCREMENT PRIMARY KEY,
  codigo_piston VARCHAR(40) NOT NULL,
  descripcion VARCHAR(255) NOT NULL,
  diametro_mm DECIMAL(10,3) NULL,
  sobremedida_mm DECIMAL(8,2) NULL,
  altura_compresion_mm DECIMAL(8,2) NULL,
  diametro_pasador_mm DECIMAL(8,2) NULL,
  especificacion_camara VARCHAR(255) NULL,
  activo TINYINT(1) NOT NULL DEFAULT 1,
  tipo_auto VARCHAR(120) NULL,
  anio VARCHAR(20) NULL,
  numero_piezas INT NOT NULL DEFAULT 0,
  fecha_fabricacion VARCHAR(20) NULL,
  offset_mm VARCHAR(20) NULL,
  trazabilidad VARCHAR(80) NULL,
  diametro_cilindro_mm DECIMAL(10,3) NULL,
  marca_vehiculo VARCHAR(80) NULL,
  modelo_aplicacion VARCHAR(120) NULL,
  motor VARCHAR(80) NULL,
  caracteristicas_adicionales VARCHAR(120) NULL,
  imagen VARCHAR(255) NULL,
  stock_actual INT NOT NULL DEFAULT 0,
  stock_minimo INT NOT NULL DEFAULT 0,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_actualizacion DATETIME NULL ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_pistones_codigo (codigo_piston))""",
"""CREATE TABLE IF NOT EXISTS precios_pistones(
  id_precio INT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  precio_base DECIMAL(10,2) NOT NULL,
  moneda CHAR(3) NOT NULL DEFAULT 'USD',
  vigente_desde DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  vigente_hasta DATETIME NULL,
  INDEX idx_precios_vigencia (id_piston, vigente_hasta),
  CONSTRAINT fk_precios_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston))""",
"""CREATE TABLE IF NOT EXISTS codigos_qr(
  id_qr INT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  contenido_qr VARCHAR(600) NOT NULL,
  ruta_imagen VARCHAR(255) NULL,
  fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
  UNIQUE KEY uq_qr_contenido (contenido_qr(191)),
  CONSTRAINT fk_qr_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston))""",
# ---- Complemento: existencias (stock actual por pistón)
"""CREATE TABLE IF NOT EXISTS existencias(
  id_piston INT NOT NULL PRIMARY KEY,
  stock INT NOT NULL DEFAULT 0,
  CONSTRAINT fk_exist_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston))""",
# ---- Facturación
"""CREATE TABLE IF NOT EXISTS facturas(
  id_factura INT AUTO_INCREMENT PRIMARY KEY,
  nro_factura VARCHAR(20) NOT NULL,
  id_cliente INT NOT NULL,
  id_usuario INT NULL,
  fecha_hora DATETIME NOT NULL,
  subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
  monto_iva DECIMAL(12,2) NOT NULL DEFAULT 0,
  total DECIMAL(12,2) NOT NULL DEFAULT 0,
  estado VARCHAR(30) NOT NULL DEFAULT 'EMITIDA',
  tasa_bcv DECIMAL(14,6) NULL,
  fecha_tasa DATE NULL,
  subtotal_bs DECIMAL(16,2) NULL,
  iva_bs DECIMAL(16,2) NULL,
  total_bs DECIMAL(16,2) NULL,
  moneda_base CHAR(3) NOT NULL DEFAULT 'USD',
  observacion TEXT NULL,
  UNIQUE KEY uq_facturas_nro (nro_factura),
  CONSTRAINT fk_facturas_clientes FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
  CONSTRAINT fk_facturas_usuarios FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario))""",
"""CREATE TABLE IF NOT EXISTS detalle_factura(
  id_detalle INT AUTO_INCREMENT PRIMARY KEY,
  id_factura INT NOT NULL,
  id_piston INT NOT NULL,
  cantidad INT NOT NULL,
  precio_unitario DECIMAL(10,2) NOT NULL,
  subtotal_linea DECIMAL(12,2) NOT NULL,
  CONSTRAINT fk_detfac_facturas FOREIGN KEY (id_factura) REFERENCES facturas(id_factura),
  CONSTRAINT fk_detfac_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston))""",
# ---- Complemento: tasa BCV y equivalentes en Bs de cada factura
"""CREATE TABLE IF NOT EXISTS tasa_factura(
  id_factura INT NOT NULL PRIMARY KEY,
  tasa_bcv DECIMAL(12,4) NOT NULL,
  fecha_tasa DATE NULL,
  subtotal_bs DECIMAL(14,2) NULL,
  monto_iva_bs DECIMAL(14,2) NULL,
  total_bs DECIMAL(14,2) NULL,
  CONSTRAINT fk_tasa_facturas FOREIGN KEY (id_factura) REFERENCES facturas(id_factura))""",
# ---- Pagos
"""CREATE TABLE IF NOT EXISTS metodo_pago(
  id_metodo_pago INT AUTO_INCREMENT PRIMARY KEY,
  nombre_metodo VARCHAR(40) NOT NULL,
  estado TINYINT(1) NOT NULL DEFAULT 1,
  UNIQUE KEY uq_metodo_nombre (nombre_metodo))""",
"""CREATE TABLE IF NOT EXISTS pago(
  id_pago INT AUTO_INCREMENT PRIMARY KEY,
  id_factura INT NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  monto_total DECIMAL(12,2) NOT NULL,
  estado VARCHAR(20) NOT NULL DEFAULT 'PAGADO',
  CONSTRAINT fk_pago_facturas FOREIGN KEY (id_factura) REFERENCES facturas(id_factura))""",
"""CREATE TABLE IF NOT EXISTS detalle_pago(
  id_detalle_pago INT AUTO_INCREMENT PRIMARY KEY,
  id_pago INT NOT NULL,
  metodo_pago INT NOT NULL,
  monto DECIMAL(12,2) NOT NULL,
  referencia VARCHAR(100) NULL,
  fecha_pago DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado VARCHAR(30) NOT NULL DEFAULT 'CONFIRMADO',
  moneda CHAR(3) NOT NULL DEFAULT 'USD',
  tasa_aplicada DECIMAL(14,6) NULL,
  observacion VARCHAR(255) NULL,
  CONSTRAINT fk_detpago_pago FOREIGN KEY (id_pago) REFERENCES pago(id_pago),
  CONSTRAINT fk_detpago_metodo FOREIGN KEY (metodo_pago) REFERENCES metodo_pago(id_metodo_pago))""",
# ---- Complemento: historial de tasas USD -> Bs. (BCV o ingresadas manualmente)
"""CREATE TABLE IF NOT EXISTS tasas_bcv(
  id_tasa INT AUTO_INCREMENT PRIMARY KEY,
  moneda_origen CHAR(3) NOT NULL DEFAULT 'USD',
  moneda_destino CHAR(3) NOT NULL DEFAULT 'VES',
  tasa DECIMAL(14,6) NOT NULL,
  fecha_efectiva DATE NOT NULL,
  fecha_consulta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fuente VARCHAR(160) NOT NULL,
  validada TINYINT(1) NOT NULL DEFAULT 1,
  INDEX idx_tasas_consulta (fecha_consulta, id_tasa))""",
# ---- Complemento: historial de existencias
"""CREATE TABLE IF NOT EXISTS movimientos_inventario(
  id_movimiento BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  tipo ENUM('APERTURA','ENTRADA','SALIDA','AJUSTE','PRODUCCION') NOT NULL,
  cantidad INT NOT NULL,
  motivo VARCHAR(255) NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario INT NULL,
  id_factura INT NULL,
  stock_anterior INT NULL,
  stock_nuevo INT NULL,
  id_orden INT NULL,
  lote VARCHAR(30) NULL,
  INDEX idx_mov_piston_fecha (id_piston, fecha_hora),
  INDEX idx_mov_factura (id_factura),
  CONSTRAINT fk_movinv_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston),
  CONSTRAINT fk_movinv_usuarios FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
  CONSTRAINT fk_movinv_facturas FOREIGN KEY (id_factura) REFERENCES facturas(id_factura))""",
# ---- Producción: materia prima, órdenes, etapas (9 pasos) y bitácora del lote
"""CREATE TABLE IF NOT EXISTS ordenes_produccion(
  id_orden INT AUTO_INCREMENT PRIMARY KEY,
  codigo_orden VARCHAR(30) NOT NULL UNIQUE,
  lote VARCHAR(30) NOT NULL UNIQUE,
  id_piston INT NULL,
  cantidad_plan INT NOT NULL,
  kg_aluminio DECIMAL(12,3) NOT NULL DEFAULT 0,
  estado ENUM('EN_PRODUCCION','FINALIZADA','CANCELADA') NOT NULL DEFAULT 'EN_PRODUCCION',
  paso_actual TINYINT NOT NULL DEFAULT 1,
  creada DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario INT NULL,
  responsable VARCHAR(80) NULL,
  observaciones VARCHAR(255) NULL,
  fecha_inicio DATE NULL,
  fecha_fin DATETIME NULL,
  aprobados_final INT NOT NULL DEFAULT 0,
  liberada TINYINT(1) NOT NULL DEFAULT 0,
  fecha_liberacion DATETIME NULL,
  motivo_cierre VARCHAR(255) NULL,
  INDEX idx_orden_estado (estado))""",
"""CREATE TABLE IF NOT EXISTS orden_etapas(
  id_etapa INT AUTO_INCREMENT PRIMARY KEY,
  id_orden INT NOT NULL,
  paso TINYINT NOT NULL,
  estado ENUM('PENDIENTE','EN_PROCESO','COMPLETADO','COMPLETADO_OBS','BLOQUEADO') NOT NULL DEFAULT 'PENDIENTE',
  fecha DATE NULL,
  aprobados INT NOT NULL DEFAULT 0,
  rechazados INT NOT NULL DEFAULT 0,
  motivo VARCHAR(255) NULL,
  observaciones VARCHAR(255) NULL,
  cant_recibida INT NULL,
  cant_procesada INT NULL,
  pendientes INT NOT NULL DEFAULT 0,
  pend_aprobados INT NOT NULL DEFAULT 0,
  pend_rechazados INT NOT NULL DEFAULT 0,
  defectos VARCHAR(500) NULL,
  responsable VARCHAR(80) NULL,
  fecha_hora DATETIME NULL,
  inicio DATETIME NULL,
  bloqueo VARCHAR(255) NULL,
  UNIQUE KEY uq_etapa (id_orden, paso),
  CONSTRAINT fk_etapa_orden FOREIGN KEY (id_orden) REFERENCES ordenes_produccion(id_orden) ON DELETE CASCADE)""",
"""CREATE TABLE IF NOT EXISTS materia_prima_mov(
  id_mov BIGINT AUTO_INCREMENT PRIMARY KEY,
  tipo ENUM('ENTRADA','CONSUMO','AJUSTE') NOT NULL,
  kg DECIMAL(12,3) NOT NULL,
  descripcion VARCHAR(255) NOT NULL,
  id_orden INT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario INT NULL,
  INDEX idx_mp_fecha (fecha_hora))""",
"""CREATE TABLE IF NOT EXISTS orden_historial(
  id_hist BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_orden INT NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  movimiento VARCHAR(120) NOT NULL,
  cantidad VARCHAR(40) NULL,
  estado VARCHAR(30) NULL,
  id_usuario INT NULL,
  observaciones VARCHAR(255) NULL,
  INDEX idx_hist_orden (id_orden, fecha_hora),
  CONSTRAINT fk_hist_orden FOREIGN KEY (id_orden) REFERENCES ordenes_produccion(id_orden) ON DELETE CASCADE)""",
"""CREATE TABLE IF NOT EXISTS productos_no_conformes(
  id_nc BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_orden INT NOT NULL,
  id_piston INT NULL,
  paso TINYINT NOT NULL,
  cantidad INT NOT NULL,
  recuperadas INT NOT NULL DEFAULT 0,
  descartadas INT NOT NULL DEFAULT 0,
  motivo VARCHAR(255) NOT NULL,
  defectos VARCHAR(500) NULL,
  observaciones VARCHAR(255) NULL,
  responsable VARCHAR(80) NULL,
  origen ENUM('ETAPA','PENDIENTE') NOT NULL DEFAULT 'ETAPA',
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario INT NULL,
  INDEX idx_nc_orden (id_orden),
  CONSTRAINT fk_nc_orden FOREIGN KEY (id_orden) REFERENCES ordenes_produccion(id_orden))""",
"""CREATE TABLE IF NOT EXISTS nc_reprocesos(
  id_rep BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_nc BIGINT NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  aprobadas INT NOT NULL DEFAULT 0,
  rechazadas INT NOT NULL DEFAULT 0,
  responsable VARCHAR(80) NULL,
  observaciones VARCHAR(255) NULL,
  id_usuario INT NULL,
  INDEX idx_rep_nc (id_nc),
  CONSTRAINT fk_rep_nc FOREIGN KEY (id_nc) REFERENCES productos_no_conformes(id_nc))""",
# ---- Historial permanente de pistones rechazados definitivamente (copia propia: no depende de otras tablas)
"""CREATE TABLE IF NOT EXISTS rechazos_definitivos(
  id_rechazo BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_rep BIGINT NULL,
  id_nc BIGINT NOT NULL,
  id_orden INT NOT NULL,
  id_piston INT NULL,
  codigo_piston VARCHAR(40) NULL,
  modelo VARCHAR(255) NULL,
  lote VARCHAR(30) NOT NULL,
  cantidad INT NOT NULL,
  fecha_rechazo DATETIME NOT NULL,
  paso TINYINT NOT NULL,
  motivo VARCHAR(255) NOT NULL,
  defectos VARCHAR(500) NULL,
  observaciones VARCHAR(255) NULL,
  responsable VARCHAR(80) NULL,
  id_usuario INT NULL,
  usuario VARCHAR(40) NULL,
  UNIQUE KEY uq_rechazo_rep (id_rep),
  INDEX idx_rechazo_fecha (fecha_rechazo),
  INDEX idx_rechazo_lote (lote),
  INDEX idx_rechazo_paso (paso),
  INDEX idx_rechazo_piston (id_piston))""",
]

SEMILLAS = [
"""INSERT IGNORE INTO roles(id_rol,nombre_rol,descripcion) VALUES
  (1,'Administrador','Acceso completo al sistema'),
  (3,'Cajero','Registra ventas y cobros')""",
"""INSERT IGNORE INTO roles(nombre_rol,descripcion) VALUES
  ('CONTROL','Responsable de una de las nueve etapas de producción')""",
# Registros de METODO_PAGO indicados en el PDF.
"""INSERT IGNORE INTO metodo_pago(id_metodo_pago,nombre_metodo,estado) VALUES
  (1,'Zelle',1),(2,'Pago móvil',1),(3,'Transferencia',1),(4,'Bolívares',1),(5,'Divisa',1)""",
]

# --------------------------------------------------------------------------- CONSULTAS BASE
# Lectura de pistones con precio vigente y stock actual (alias cortos usados por la interfaz).
SQL_PISTON = """SELECT p.id_piston AS id, p.codigo_piston AS codigo, p.descripcion,
  p.diametro_mm, p.sobremedida_mm, p.altura_compresion_mm, p.diametro_pasador_mm,
  p.especificacion_camara, p.activo, p.stock_minimo, COALESCE(e.stock,0) AS stock,
  p.marca_vehiculo AS marca, p.modelo_aplicacion AS modelo, p.motor, p.anio, p.numero_piezas,
  p.caracteristicas_adicionales,
  p.fecha_fabricacion, p.offset_mm, p.trazabilidad, p.diametro_cilindro_mm,
  COALESCE((SELECT pr.precio_base FROM precios_pistones pr
            WHERE pr.id_piston=p.id_piston AND pr.vigente_hasta IS NULL
            ORDER BY pr.vigente_desde DESC, pr.id_precio DESC LIMIT 1),0) AS precio
  FROM pistones p LEFT JOIN existencias e ON e.id_piston=p.id_piston"""

SQL_USUARIO = """SELECT u.id_usuario AS id, u.nombre_usuario AS usuario, u.nombre_usuario AS nombre,
  r.nombre_rol AS rol, u.estado AS activo, u.etapa_asignada AS etapa
  FROM usuarios u JOIN roles r ON r.id_rol=u.id_rol"""

SQL_PRECIO_VIGENTE = """SELECT precio_base FROM precios_pistones WHERE id_piston=%s AND vigente_hasta IS NULL
  ORDER BY vigente_desde DESC, id_precio DESC LIMIT 1"""
SQL_STOCK_BLOQUEAR = """SELECT COALESCE(e.stock,0), p.activo FROM pistones p
  LEFT JOIN existencias e ON e.id_piston=p.id_piston WHERE p.id_piston=%s FOR UPDATE"""
SQL_STOCK_FIJAR = """INSERT INTO existencias(id_piston,stock) VALUES(%s,%s)
  ON DUPLICATE KEY UPDATE stock=VALUES(stock)"""


def hash_clave(c):
    return hashlib.sha256(c.encode()).hexdigest()


def conectar():
    """Abre una conexión a la base activa del sistema."""
    return mysql.connector.connect(database=DB, **CFG)


def consulta(sql, params=(), uno=False, commit=False):
    """Ejecuta consultas y garantiza el cierre aun cuando MySQL devuelva un error."""
    c = conectar()
    cur = c.cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        if commit:
            c.commit()
            return cur.lastrowid
        return cur.fetchone() if uno else cur.fetchall()
    except Exception:
        if commit:
            c.rollback()
        raise
    finally:
        cur.close()
        c.close()


@contextlib.contextmanager
def transaccion(dictionary=False):
    """Bloque transaccional: confirma al salir bien, revierte ante cualquier error y siempre cierra.

        with db.transaccion() as (conn, cur):
            cur.execute(...)
    """
    c = conectar()
    cur = c.cursor(dictionary=dictionary)
    try:
        yield c, cur
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        cur.close()
        c.close()


MSG_USUARIO_DESACTIVADO = "Este usuario se encuentra desactivado. Comuníquese con el administrador del sistema."


class UsuarioDesactivado(Exception):
    """Las credenciales son correctas, pero la cuenta tiene estado = 0 (desactivada)."""


def verificar_credenciales(usuario, clave):
    """Busca al usuario por nombre y contraseña SIN filtrar por estado.

    Devuelve la fila del usuario (con la clave ``activo`` = 1 / 0) o None si el usuario no existe
    o la contraseña no coincide. Así quien llama puede distinguir «credenciales incorrectas» de
    «cuenta desactivada». Solo se revela que la cuenta está desactivada cuando la contraseña es correcta.
    """
    return consulta(SQL_USUARIO + " WHERE u.nombre_usuario=%s AND u.clave_hash=%s",
                    (usuario.strip(), hash_clave(clave)), uno=True)


def autenticar_usuario(usuario, clave):
    """Devuelve {'id_usuario','nombre_usuario','nombre_rol'} si las credenciales son correctas.

    Devuelve None si son incorrectas y lanza ``UsuarioDesactivado`` si son correctas pero la cuenta está desactivada.
    """
    fila = verificar_credenciales(usuario, clave)
    if not fila:
        log(None, "LOGIN", f"Intento de acceso con el usuario «{usuario.strip()}»", "FALLIDO")
        return None
    if not fila["activo"]:
        log(fila["id"], "LOGIN", f"Intento de acceso con la cuenta desactivada «{usuario.strip()}»", "FALLIDO")
        raise UsuarioDesactivado(MSG_USUARIO_DESACTIVADO)
    log(fila["id"], "LOGIN", "Inicio de sesión", "OK")
    return {"id_usuario": fila["id"], "nombre_usuario": fila["usuario"], "nombre_rol": fila["rol"]}


# --------------------------------------------------------------------------- ARCHIVOS DEL PISTÓN
def ruta_imagen(codigo):
    """La fotografía no se guarda en la BD (el PDF no tiene columna para ella): se busca por código."""
    archivos = []
    for ext in ("jpg", "jpeg", "png"):
        archivos += glob.glob(os.path.join(IMG_DIR, glob.escape(codigo) + "." + ext))
    return max(archivos, key=os.path.getmtime) if archivos else ""


def ruta_etiqueta(codigo):
    r = os.path.join(ETQ_DIR, f"ETQ-{codigo}.png")
    return r if os.path.exists(r) else ""


def _completar(p):
    if p:
        p["imagen"] = ruta_imagen(p["codigo"])
        p["etiqueta"] = ruta_etiqueta(p["codigo"])
        q = consulta("SELECT ruta_imagen FROM codigos_qr WHERE id_piston=%s AND estado='ACTIVO' "
                     "ORDER BY id_qr DESC LIMIT 1", (p["id"],), uno=True)
        p["qr"] = os.path.join(BASE, q["ruta_imagen"]) if q and q["ruta_imagen"] else ""
    return p


def piston(where, params=()):
    return _completar(consulta(SQL_PISTON + " WHERE " + where, params, uno=True))


def pistones(where="1=1", params=(), orden="p.codigo_piston"):
    return [_completar(p) for p in consulta(f"{SQL_PISTON} WHERE {where} ORDER BY {orden}", params)]


# --------------------------------------------------------------------------- OPERACIONES
def log(id_usuario, accion, descripcion="", resultado="OK"):
    """Bitácora LOG_USUARIOS. Nunca interrumpe la operación principal."""
    try:
        consulta("INSERT INTO log_usuarios(id_usuario,accion,descripcion,resultado) VALUES(%s,%s,%s,%s)",
                 (id_usuario, accion, (descripcion or "")[:500], resultado), commit=True)
    except Exception:
        pass


# Columnas editables de PISTONES: clave del diccionario de la interfaz -> columna MySQL.
COLUMNAS_PISTON = (
    # «descripcion» es la «Aplicación» de la etiqueta (ej.: Chrysler 318 - V8 - 5.2 Lts). Las columnas antiguas
    # marca_vehiculo / modelo_aplicacion / motor / anio ya no se escriben: conservan lo que tenían los pistones viejos.
    ("descripcion", "descripcion"), ("caracteristicas_adicionales", "caracteristicas_adicionales"),
    ("numero_piezas", "numero_piezas"),
    ("fecha_fabricacion", "fecha_fabricacion"), ("offset_mm", "offset_mm"),
    ("trazabilidad", "trazabilidad"), ("diametro_mm", "diametro_mm"),
    ("diametro_cilindro_mm", "diametro_cilindro_mm"), ("sobremedida_mm", "sobremedida_mm"),
    ("altura_compresion_mm", "altura_compresion_mm"), ("diametro_pasador_mm", "diametro_pasador_mm"),
    ("especificacion_camara", "especificacion_camara"),
)


def _valores_piston(v):
    # numero_piezas es NOT NULL: si no viene, 0 (es un dato técnico de la etiqueta, no el stock).
    return [(v.get(k) if k != "numero_piezas" else (v.get(k) or 0)) for k, _col in COLUMNAS_PISTON]


def crear_piston(v, id_usuario=None):
    """Inserta pistón + existencias en 0 + movimiento de apertura. Devuelve id_piston.

    ``numero_piezas`` guarda la «cantidad de piezas» de la etiqueta; el stock físico sigue naciendo en 0
    y solo cambia con entradas, salidas y ajustes (movimientos_inventario).
    """
    columnas = ["codigo_piston"] + [col for _k, col in COLUMNAS_PISTON]
    c = conectar(); cur = c.cursor()
    try:
        cur.execute(f"INSERT INTO pistones({','.join(columnas)}) VALUES({','.join(['%s'] * len(columnas))})",
                    [v["codigo"]] + _valores_piston(v))
        pid = cur.lastrowid
        cur.execute("INSERT INTO existencias(id_piston,stock) VALUES(%s,0)", (pid,))
        cur.execute("""INSERT INTO movimientos_inventario(id_piston,tipo,cantidad,motivo,id_usuario,stock_anterior,stock_nuevo)
            VALUES(%s,'APERTURA',0,'Registro inicial del pistón',%s,0,0)""", (pid, id_usuario))
        c.commit()
        return pid
    except Exception:
        c.rollback(); raise
    finally:
        c.close()


def actualizar_piston(pid, v):
    sets = ",".join(f"{col}=%s" for _k, col in COLUMNAS_PISTON)
    consulta(f"UPDATE pistones SET {sets} WHERE id_piston=%s", _valores_piston(v) + [pid], commit=True)


def eliminar_piston(pid):
    c = conectar(); cur = c.cursor()
    try:
        for t in ("codigos_qr", "precios_pistones", "movimientos_inventario", "existencias"):
            cur.execute(f"DELETE FROM {t} WHERE id_piston=%s", (pid,))
        cur.execute("DELETE FROM pistones WHERE id_piston=%s", (pid,))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()


def establecer_precio(pid, precio, moneda="USD"):
    """Cierra el precio vigente y abre uno nuevo; las facturas anteriores conservan su precio."""
    c = conectar(); cur = c.cursor()
    try:
        cur.execute("UPDATE precios_pistones SET vigente_hasta=NOW() WHERE id_piston=%s AND vigente_hasta IS NULL", (pid,))
        cur.execute("INSERT INTO precios_pistones(id_piston,precio_base,moneda) VALUES(%s,%s,%s)", (pid, precio, moneda))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()


def registrar_qr(id_piston, contenido, ruta_abs):
    """Guarda el QR vigente en CODIGOS_QR. Si el contenido cambió, el anterior queda INACTIVO."""
    ruta = os.path.relpath(ruta_abs, BASE).replace("\\", "/")
    c = conectar(); cur = c.cursor()
    try:
        cur.execute("UPDATE codigos_qr SET estado='INACTIVO' WHERE id_piston=%s AND estado='ACTIVO' AND contenido_qr<>%s",
                    (id_piston, contenido))
        cur.execute("SELECT id_qr FROM codigos_qr WHERE contenido_qr=%s", (contenido,))
        fila = cur.fetchone()
        if fila:
            cur.execute("UPDATE codigos_qr SET estado='ACTIVO', ruta_imagen=%s WHERE id_qr=%s", (ruta, fila[0]))
        else:
            cur.execute("INSERT INTO codigos_qr(id_piston,contenido_qr,ruta_imagen,estado) VALUES(%s,%s,%s,'ACTIVO')",
                        (id_piston, contenido, ruta))
        c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()


# --------------------------------------------------------------------------- INICIALIZACIÓN
def _asegurar_triggers_stock(cur):
    """Mantiene pistones.stock_actual como espejo de existencias y protege el historial permanente de rechazos."""
    triggers = {
        "trg_existencias_ai": "CREATE TRIGGER trg_existencias_ai AFTER INSERT ON existencias FOR EACH ROW UPDATE pistones SET stock_actual=NEW.stock WHERE id_piston=NEW.id_piston",
        "trg_existencias_au": "CREATE TRIGGER trg_existencias_au AFTER UPDATE ON existencias FOR EACH ROW UPDATE pistones SET stock_actual=NEW.stock WHERE id_piston=NEW.id_piston",
        "trg_existencias_ad": "CREATE TRIGGER trg_existencias_ad AFTER DELETE ON existencias FOR EACH ROW UPDATE pistones SET stock_actual=0 WHERE id_piston=OLD.id_piston",
    }
    # El historial de rechazos definitivos es permanente: ni se modifica ni se borra, ni siquiera por error.
    for accion, verbo in (("bu", "UPDATE"), ("bd", "DELETE")):
        triggers[f"trg_rechazos_def_{accion}"] = (
            f"CREATE TRIGGER trg_rechazos_def_{accion} BEFORE {verbo} ON rechazos_definitivos FOR EACH ROW "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='El historial de rechazos definitivos es permanente y no admite cambios.'")
    for nombre, sentencia in triggers.items():
        cur.execute("SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME=%s", (DB, nombre))
        if not cur.fetchone():
            cur.execute(sentencia)


# Columnas añadidas después de la primera versión. Se crean solo si faltan; no se toca ningún dato existente.
COLUMNAS_NUEVAS = {
    # Rol CONTROL: etapa de producción (1 a 9) que el usuario puede modificar.
    "usuarios": (("etapa_asignada", "TINYINT NULL"),),
    "pistones": (("marca_vehiculo", "VARCHAR(80) NULL"),
                 ("modelo_aplicacion", "VARCHAR(120) NULL"),
                 ("motor", "VARCHAR(80) NULL"),
                 # Etiqueta: «Características adicionales» (ej.: A/C - C/R).
                 ("caracteristicas_adicionales", "VARCHAR(120) NULL")),
    # Módulo Existencias por lotes: bases creadas con la versión anterior reciben estas columnas.
    "movimientos_inventario": (("id_orden", "INT NULL"), ("lote", "VARCHAR(30) NULL")),
    "ordenes_produccion": (("responsable", "VARCHAR(80) NULL"), ("observaciones", "VARCHAR(255) NULL"),
                           ("fecha_inicio", "DATE NULL"), ("fecha_fin", "DATETIME NULL"),
                           ("aprobados_final", "INT NOT NULL DEFAULT 0"), ("liberada", "TINYINT(1) NOT NULL DEFAULT 0"),
                           ("fecha_liberacion", "DATETIME NULL"), ("motivo_cierre", "VARCHAR(255) NULL")),
    "orden_etapas": (("cant_recibida", "INT NULL"), ("cant_procesada", "INT NULL"),
                     ("pendientes", "INT NOT NULL DEFAULT 0"), ("pend_aprobados", "INT NOT NULL DEFAULT 0"),
                     ("pend_rechazados", "INT NOT NULL DEFAULT 0"), ("defectos", "VARCHAR(500) NULL"),
                     ("responsable", "VARCHAR(80) NULL"), ("fecha_hora", "DATETIME NULL"),
                     ("inicio", "DATETIME NULL"), ("bloqueo", "VARCHAR(255) NULL")),
}

# Columnas ENUM ampliadas: (tabla, columna, valor que debe existir, definición completa).
ENUMS_AMPLIADOS = (
    ("orden_etapas", "estado", "BLOQUEADO",
     "ENUM('PENDIENTE','EN_PROCESO','COMPLETADO','COMPLETADO_OBS','BLOQUEADO') NOT NULL DEFAULT 'PENDIENTE'"),
    ("movimientos_inventario", "tipo", "PRODUCCION",
     "ENUM('APERTURA','ENTRADA','SALIDA','AJUSTE','PRODUCCION') NOT NULL"),
)


def _asegurar_columnas(cur):
    """Migración aditiva para bases ya creadas (compatible con MySQL y MariaDB)."""
    for tabla, columnas in COLUMNAS_NUEVAS.items():
        for nombre, definicion in columnas:
            cur.execute("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                        "AND COLUMN_NAME=%s", (DB, tabla, nombre))
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {definicion}")
    # El diámetro del pistón se mide al milésimo (100,789 mm): bases antiguas lo guardaban con 2 decimales.
    cur.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='pistones' "
                "AND COLUMN_NAME='diametro_mm'", (DB,))
    fila = cur.fetchone()
    if fila and "decimal(8,2)" in str(fila[0]).lower():
        cur.execute("ALTER TABLE pistones MODIFY COLUMN diametro_mm DECIMAL(10,3) NULL")


def _columna_existe(cur, tabla, columna):
    cur.execute("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                (DB, tabla, columna))
    return cur.fetchone() is not None


def _tabla_existe(cur, tabla):
    cur.execute("SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s", (DB, tabla))
    return cur.fetchone() is not None


def _migrar_produccion(cur, nc_existia):
    """Lleva una base de la versión anterior al esquema de lotes sin perder ni duplicar nada.

    * Amplía los ENUM (Completado con observaciones, Bloqueado, movimiento de producción).
    * Marca como ya liberadas las órdenes antiguas que sumaron stock al completar el paso 8, para que la
      nueva liberación (paso 9) no vuelva a sumar sus piezas.
    * Copia los rechazos antiguos al registro independiente de productos no conformes (una sola vez).
    """
    era_antigua = not _columna_existe(cur, "ordenes_produccion", "liberada")
    _asegurar_columnas(cur)
    for tabla, columna, valor, definicion in ENUMS_AMPLIADOS:
        cur.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                    "AND COLUMN_NAME=%s", (DB, tabla, columna))
        fila = cur.fetchone()
        if fila and valor not in str(fila[0]):
            cur.execute(f"ALTER TABLE {tabla} MODIFY COLUMN {columna} {definicion}")
    cur.execute("UPDATE ordenes_produccion SET fecha_inicio=DATE(creada) WHERE fecha_inicio IS NULL")
    if era_antigua:
        cur.execute("""UPDATE ordenes_produccion o SET o.liberada=1, o.fecha_liberacion=o.creada,
              o.aprobados_final=COALESCE((SELECT et.aprobados FROM orden_etapas et
                                          WHERE et.id_orden=o.id_orden AND et.paso=8),0)
            WHERE o.paso_actual>=9 OR o.estado='FINALIZADA'""")
        cur.execute("UPDATE ordenes_produccion SET fecha_fin=creada WHERE estado='FINALIZADA' AND fecha_fin IS NULL")
        cur.execute("""UPDATE orden_etapas SET cant_procesada=aprobados+rechazados,
              cant_recibida=aprobados+rechazados WHERE estado='COMPLETADO' AND paso>=4""")
    if not nc_existia:
        cur.execute("""INSERT INTO productos_no_conformes(id_orden,id_piston,paso,cantidad,motivo,observaciones,fecha_hora)
            SELECT et.id_orden, o.id_piston, et.paso, et.rechazados, COALESCE(et.motivo,'Sin motivo registrado'),
                   et.observaciones, COALESCE(CAST(et.fecha AS DATETIME), o.creada)
            FROM orden_etapas et JOIN ordenes_produccion o ON o.id_orden=et.id_orden
            WHERE et.rechazados>0""")
    _copiar_rechazos_definitivos(cur)


def _copiar_rechazos_definitivos(cur):
    """Copia al historial permanente los descartes ya registrados antes de existir la tabla (idempotente).

    Cada reproceso con piezas rechazadas otra vez es un rechazo definitivo. ``id_rep`` es único, así que ejecutar esto
    en cada arranque no duplica nada.
    """
    cur.execute("""INSERT IGNORE INTO rechazos_definitivos(id_rep,id_nc,id_orden,id_piston,codigo_piston,modelo,lote,cantidad,
              fecha_rechazo,paso,motivo,defectos,observaciones,responsable,id_usuario,usuario)
        SELECT r.id_rep, nc.id_nc, nc.id_orden, nc.id_piston, p.codigo_piston, p.descripcion, o.lote, r.rechazadas,
               r.fecha_hora, nc.paso, nc.motivo, nc.defectos, r.observaciones, COALESCE(r.responsable, nc.responsable),
               r.id_usuario, u.nombre_usuario
        FROM nc_reprocesos r JOIN productos_no_conformes nc ON nc.id_nc=r.id_nc
        JOIN ordenes_produccion o ON o.id_orden=nc.id_orden
        LEFT JOIN pistones p ON p.id_piston=nc.id_piston
        LEFT JOIN usuarios u ON u.id_usuario=r.id_usuario
        WHERE r.rechazadas>0 AND NOT EXISTS (SELECT 1 FROM rechazos_definitivos d WHERE d.id_rep=r.id_rep)""")


def _retirar_rol_inventario(cur):
    """Elimina el rol «Inventario» (Inventario es solo un módulo). Idempotente.

    Los usuarios que lo tenían pasan a «Cajero» (el rol de menor alcance) y quedan anotados en la bitácora, para que el
    administrador les asigne después el rol que corresponda (Administrador, Cajero o CONTROL con su etapa).
    """
    cur.execute("SELECT id_rol FROM roles WHERE nombre_rol='Inventario'")
    viejo = cur.fetchone()
    if not viejo:
        return
    cur.execute("SELECT id_rol FROM roles WHERE nombre_rol='Cajero'")
    cajero = cur.fetchone()[0]
    cur.execute("SELECT id_usuario, nombre_usuario FROM usuarios WHERE id_rol=%s", (viejo[0],))
    for id_usuario, nombre in cur.fetchall():
        cur.execute("INSERT INTO log_usuarios(id_usuario,accion,descripcion,resultado) VALUES(%s,'ROL_ELIMINADO',%s,'OK')",
                    (id_usuario, f"El rol Inventario fue eliminado: el usuario {nombre} pasó a Cajero"))
    cur.execute("UPDATE usuarios SET id_rol=%s, etapa_asignada=NULL WHERE id_rol=%s", (cajero, viejo[0]))
    cur.execute("DELETE FROM roles WHERE id_rol=%s", (viejo[0],))


def init_db():
    """Prepara exclusivamente instalacion_limpia sin tocar bases anteriores."""
    c = mysql.connector.connect(**CFG)
    cur = c.cursor()
    try:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        c.database = DB
        nc_existia = _tabla_existe(cur, "productos_no_conformes")
        for sentencia in SCHEMA:
            cur.execute(sentencia)
        _migrar_produccion(cur, nc_existia)
        _asegurar_triggers_stock(cur)
        for sentencia in SEMILLAS:
            cur.execute(sentencia)
        _retirar_rol_inventario(cur)
        c.commit()
        cur.execute("SELECT COUNT(*) FROM usuarios")
        if cur.fetchone()[0] == 0:
            for usuario, clave, rol in [("admin", "admin123", "Administrador"), ("cajero", "cajero123", "Cajero")]:
                cur.execute("INSERT INTO usuarios(id_rol,nombre_usuario,clave_hash) "
                            "SELECT id_rol,%s,%s FROM roles WHERE nombre_rol=%s",
                            (usuario, hash_clave(clave), rol))
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        cur.close()
        c.close()
