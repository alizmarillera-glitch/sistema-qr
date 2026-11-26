-- INSTALACION LIMPIA DE SISTEMA_QR
-- Base de datos de destino: instalacion_limpia
-- Este script NO elimina bases de datos existentes ni modifica tesis_qr / tesis_qr_v2.
-- Las tablas complementarias existencias, tasa_factura, tasas_bcv y movimientos_inventario
-- conservan las funciones de inventario, historial y conversión BCV del programa.

SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS instalacion_limpia
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE instalacion_limpia;

CREATE TABLE IF NOT EXISTS roles (
  id_rol INT AUTO_INCREMENT PRIMARY KEY,
  nombre_rol VARCHAR(40) NOT NULL,
  descripcion VARCHAR(255) NULL,
  CONSTRAINT uq_roles_nombre UNIQUE (nombre_rol)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS usuarios (
  id_usuario INT AUTO_INCREMENT PRIMARY KEY,
  id_rol INT NOT NULL,
  nombre_usuario VARCHAR(40) NOT NULL,
  clave_hash VARCHAR(255) NOT NULL,
  estado TINYINT(1) NOT NULL DEFAULT 1,
  fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  etapa_asignada TINYINT NULL,          -- solo rol CONTROL: etapa de producción (1 a 9) que puede modificar
  CONSTRAINT uq_usuarios_nombre UNIQUE (nombre_usuario),
  CONSTRAINT fk_usuarios_roles FOREIGN KEY (id_rol) REFERENCES roles(id_rol)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS log_usuarios (
  id_log BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_usuario INT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  accion VARCHAR(100) NOT NULL,
  descripcion TEXT NULL,
  resultado VARCHAR(30) NULL,
  CONSTRAINT fk_log_usuarios FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario)
    ON UPDATE CASCADE ON DELETE SET NULL,
  INDEX idx_log_fecha (fecha_hora),
  INDEX idx_log_usuario (id_usuario)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS metodo_pago (
  id_metodo_pago INT AUTO_INCREMENT PRIMARY KEY,
  nombre_metodo VARCHAR(60) NOT NULL,
  estado TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT uq_metodo_pago_nombre UNIQUE (nombre_metodo)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS clientes (
  id_cliente INT AUTO_INCREMENT PRIMARY KEY,
  tipo_documento VARCHAR(15) NOT NULL,
  documento VARCHAR(40) NOT NULL,
  nombre_razon_social VARCHAR(150) NOT NULL,
  telefono VARCHAR(40) NULL,
  correo VARCHAR(150) NULL,
  direccion VARCHAR(255) NULL,
  fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  codigo_cliente VARCHAR(20) NULL,
  CONSTRAINT uq_clientes_documento UNIQUE (documento),
  CONSTRAINT uq_clientes_codigo UNIQUE (codigo_cliente)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pistones (
  id_piston INT AUTO_INCREMENT PRIMARY KEY,
  codigo_piston VARCHAR(40) NOT NULL,
  descripcion VARCHAR(180) NOT NULL,
  diametro_mm DECIMAL(10,3) NULL,
  sobremedida_mm DECIMAL(10,3) NULL,
  altura_compresion_mm DECIMAL(10,3) NULL,
  diametro_pasador_mm DECIMAL(10,3) NULL,
  especificacion_camara VARCHAR(180) NULL,
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
  CONSTRAINT uq_pistones_codigo UNIQUE (codigo_piston),
  CONSTRAINT chk_pistones_stock_minimo CHECK (stock_minimo >= 0),
  INDEX idx_pistones_descripcion (descripcion),
  INDEX idx_pistones_activo (activo)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS precios_pistones (
  id_precio INT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  precio_base DECIMAL(14,2) NOT NULL,
  moneda CHAR(3) NOT NULL DEFAULT 'USD',
  vigente_desde DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  vigente_hasta DATETIME NULL,
  CONSTRAINT chk_precio_base CHECK (precio_base >= 0),
  CONSTRAINT fk_precios_piston FOREIGN KEY (id_piston) REFERENCES pistones(id_piston),
  INDEX idx_precio_vigencia (id_piston, vigente_desde, vigente_hasta)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS codigos_qr (
  id_qr INT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  contenido_qr VARCHAR(600) NOT NULL,
  ruta_imagen VARCHAR(255) NULL,
  fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO',
  UNIQUE KEY uq_qr_contenido (contenido_qr(191)),
  CONSTRAINT fk_qr_piston FOREIGN KEY (id_piston) REFERENCES pistones(id_piston),
  INDEX idx_qr_piston (id_piston)
) ENGINE=InnoDB;

-- Existencias separadas del dato técnico «número de piezas».
CREATE TABLE IF NOT EXISTS existencias (
  id_piston INT NOT NULL PRIMARY KEY,
  stock INT NOT NULL DEFAULT 0,
  CONSTRAINT chk_existencias_stock CHECK (stock >= 0),
  CONSTRAINT fk_exist_pistones FOREIGN KEY (id_piston) REFERENCES pistones(id_piston)
) ENGINE=InnoDB;

-- stock_actual se mantiene sincronizado con existencias; existencias es la fuente operativa.
DROP TRIGGER IF EXISTS trg_existencias_ai;
DROP TRIGGER IF EXISTS trg_existencias_au;
DROP TRIGGER IF EXISTS trg_existencias_ad;
CREATE TRIGGER trg_existencias_ai AFTER INSERT ON existencias
FOR EACH ROW UPDATE pistones SET stock_actual=NEW.stock WHERE id_piston=NEW.id_piston;
CREATE TRIGGER trg_existencias_au AFTER UPDATE ON existencias
FOR EACH ROW UPDATE pistones SET stock_actual=NEW.stock WHERE id_piston=NEW.id_piston;
CREATE TRIGGER trg_existencias_ad AFTER DELETE ON existencias
FOR EACH ROW UPDATE pistones SET stock_actual=0 WHERE id_piston=OLD.id_piston;

CREATE TABLE IF NOT EXISTS facturas (
  id_factura INT AUTO_INCREMENT PRIMARY KEY,
  nro_factura VARCHAR(20) NOT NULL,
  id_cliente INT NOT NULL,
  id_usuario INT NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  subtotal DECIMAL(14,2) NOT NULL DEFAULT 0,
  monto_iva DECIMAL(14,2) NOT NULL DEFAULT 0,
  total DECIMAL(14,2) NOT NULL DEFAULT 0,
  estado VARCHAR(30) NOT NULL DEFAULT 'EMITIDA',
  tasa_bcv DECIMAL(14,6) NULL,
  fecha_tasa DATE NULL,
  subtotal_bs DECIMAL(16,2) NULL,
  iva_bs DECIMAL(16,2) NULL,
  total_bs DECIMAL(16,2) NULL,
  moneda_base CHAR(3) NOT NULL DEFAULT 'USD',
  observacion TEXT NULL,
  CONSTRAINT uq_facturas_numero UNIQUE (nro_factura),
  CONSTRAINT fk_facturas_cliente FOREIGN KEY (id_cliente) REFERENCES clientes(id_cliente),
  CONSTRAINT fk_facturas_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario),
  INDEX idx_facturas_fecha (fecha_hora),
  INDEX idx_facturas_cliente (id_cliente)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detalle_factura (
  id_detalle INT AUTO_INCREMENT PRIMARY KEY,
  id_factura INT NOT NULL,
  id_piston INT NOT NULL,
  cantidad INT NOT NULL,
  precio_unitario DECIMAL(14,2) NOT NULL,
  subtotal_linea DECIMAL(14,2) NOT NULL,
  CONSTRAINT chk_detalle_factura_cantidad CHECK (cantidad > 0),
  CONSTRAINT fk_detalle_factura_factura FOREIGN KEY (id_factura) REFERENCES facturas(id_factura),
  CONSTRAINT fk_detalle_factura_piston FOREIGN KEY (id_piston) REFERENCES pistones(id_piston),
  INDEX idx_detalle_factura_factura (id_factura),
  INDEX idx_detalle_factura_piston (id_piston)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tasa_factura (
  id_factura INT NOT NULL PRIMARY KEY,
  tasa_bcv DECIMAL(14,6) NOT NULL,
  fecha_tasa DATE NULL,
  subtotal_bs DECIMAL(16,2) NULL,
  monto_iva_bs DECIMAL(16,2) NULL,
  total_bs DECIMAL(16,2) NULL,
  CONSTRAINT fk_tasa_facturas FOREIGN KEY (id_factura) REFERENCES facturas(id_factura)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS pago (
  id_pago INT AUTO_INCREMENT PRIMARY KEY,
  id_factura INT NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  monto_total DECIMAL(14,2) NOT NULL DEFAULT 0,
  estado VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
  CONSTRAINT fk_pago_factura FOREIGN KEY (id_factura) REFERENCES facturas(id_factura),
  INDEX idx_pago_factura (id_factura)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detalle_pago (
  id_detalle_pago BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_pago INT NOT NULL,
  metodo_pago INT NOT NULL,
  monto DECIMAL(14,2) NOT NULL,
  referencia VARCHAR(120) NULL,
  fecha_pago DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  estado VARCHAR(30) NOT NULL DEFAULT 'REGISTRADO',
  moneda CHAR(3) NOT NULL DEFAULT 'USD',
  tasa_aplicada DECIMAL(14,6) NULL,
  observacion VARCHAR(255) NULL,
  CONSTRAINT chk_detalle_pago_monto CHECK (monto > 0),
  CONSTRAINT fk_detalle_pago_pago FOREIGN KEY (id_pago) REFERENCES pago(id_pago),
  CONSTRAINT fk_detalle_pago_metodo FOREIGN KEY (metodo_pago) REFERENCES metodo_pago(id_metodo_pago),
  INDEX idx_detalle_pago_pago (id_pago)
) ENGINE=InnoDB;

-- Historial de tasas USD -> Bs. (consultadas al BCV o ingresadas manualmente).
CREATE TABLE IF NOT EXISTS tasas_bcv (
  id_tasa INT AUTO_INCREMENT PRIMARY KEY,
  moneda_origen CHAR(3) NOT NULL DEFAULT 'USD',
  moneda_destino CHAR(3) NOT NULL DEFAULT 'VES',
  tasa DECIMAL(14,6) NOT NULL,
  fecha_efectiva DATE NOT NULL,
  fecha_consulta DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fuente VARCHAR(160) NOT NULL,
  validada TINYINT(1) NOT NULL DEFAULT 1,
  CONSTRAINT chk_tasas_bcv_tasa CHECK (tasa > 0),
  INDEX idx_tasas_consulta (fecha_consulta, id_tasa)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS movimientos_inventario (
  id_movimiento BIGINT AUTO_INCREMENT PRIMARY KEY,
  id_piston INT NOT NULL,
  tipo ENUM('APERTURA','ENTRADA','SALIDA','AJUSTE') NOT NULL,
  cantidad INT NOT NULL,
  motivo VARCHAR(255) NOT NULL,
  fecha_hora DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario INT NULL,
  id_factura INT NULL,
  stock_anterior INT NULL,
  stock_nuevo INT NULL,
  CONSTRAINT fk_mov_piston FOREIGN KEY (id_piston) REFERENCES pistones(id_piston),
  CONSTRAINT fk_mov_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE SET NULL,
  CONSTRAINT fk_mov_factura FOREIGN KEY (id_factura) REFERENCES facturas(id_factura) ON DELETE SET NULL,
  INDEX idx_mov_piston_fecha (id_piston, fecha_hora),
  INDEX idx_mov_factura (id_factura)
) ENGINE=InnoDB;

INSERT IGNORE INTO roles (nombre_rol, descripcion) VALUES
  ('Administrador', 'Acceso completo al sistema'),
  ('Cajero', 'Registro de ventas, facturas y pagos'),
  ('CONTROL', 'Responsable de una de las nueve etapas de producción');

INSERT IGNORE INTO metodo_pago (nombre_metodo, estado) VALUES
  ('Zelle', 1), ('Pago móvil', 1), ('Transferencia', 1), ('Bolívares', 1), ('Divisa', 1);

-- El programa crea admin y cajero al iniciar si todavía no existen.
-- Credenciales iniciales: admin / admin123 y cajero / cajero123.
