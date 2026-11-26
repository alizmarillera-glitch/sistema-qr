# -*- coding: utf-8 -*-
"""Prueba independiente de conexión y autenticación para la Fase 2."""
from getpass import getpass
import conexion as db


def main():
    try:
        db.init_db()
        print(f"\nConexión correcta con la base de datos: {db.DB}")
        print("Tablas obligatorias y auxiliares: verificadas.")
        usuario = input("Usuario: ").strip()
        clave = getpass("Contraseña: ")
        try:
            perfil = db.autenticar_usuario(usuario, clave)
        except db.UsuarioDesactivado:
            print(f"Acceso rechazado: {db.MSG_USUARIO_DESACTIVADO}")
            return
        if not perfil:
            print("Acceso rechazado: usuario o contraseña incorrectos.")
            return
        print("\nAutenticación correcta.")
        print(f"Usuario: {perfil['nombre_usuario']}")
        print(f"Rol: {perfil['nombre_rol']}")
        print("Se registró el inicio de sesión en LOG_USUARIOS.")
    except Exception as exc:
        print("\nNo se pudo completar la prueba:")
        print(exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
