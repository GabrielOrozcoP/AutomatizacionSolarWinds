import pyodbc

print("Iniciando prueba de conexión a Producción...")

# ==========================================
# 1. CONFIGURA TUS CREDENCIALES AQUÍ
# ==========================================
# Cambia estos valores por los reales de tu entorno
SERVIDOR = '192.168.111.40'          # Pon la IP de tu servidor de producción (PCCEAWA)
BASE_DE_DATOS = 'SolarWindsOrion'      # El nombre de tu base de datos de producción
USUARIO = 'User_Prueba'       # El usuario de SQL (idealmente el de solo lectura)
CONTRASENA = 'Tme031127fv1'    # La contraseña del usuario

# La cadena de conexión (Usa el Driver 17, que es el estándar moderno en Windows)
connection_string = f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVIDOR};DATABASE={BASE_DE_DATOS};UID={USUARIO};PWD={CONTRASENA}'

try:
    # ==========================================
    # 2. INTENTAR CONECTAR
    # ==========================================
    print(f"Intentando conectar a {SERVIDOR}...")
    conexion = pyodbc.connect(connection_string, timeout=5)
    print("✅ ¡CONEXIÓN EXITOSA!")
    
    # Crear un cursor para ejecutar comandos
    cursor = conexion.cursor()
    
    # ==========================================
    # 3. EJECUTAR CONSULTAS DE PRUEBA
    # ==========================================
    print("\nEjecutando consultas de prueba...")
    
    # Prueba A: ¿Quién soy y dónde estoy?
    cursor.execute("SELECT DB_NAME() AS BaseActual, SYSTEM_USER AS UsuarioActual")
    row = cursor.fetchone()
    print(f"-> Conectado a la Base de Datos: {row.BaseActual}")
    print(f"-> Sesión iniciada como: {row.UsuarioActual}")
    
    # Prueba B: Contar registros de una tabla ligera de Cisco (Skill_Group)
    # Esto confirma que tienes permisos de LECTURA en las tablas del Contact Center
    try:
        cursor.execute("SELECT COUNT(*) FROM Skill_Group")
        conteo = cursor.fetchone()[0]
        print(f"-> Permisos de lectura confirmados. La tabla Skill_Group tiene {conteo} registros.")
    except Exception as e:
        print(f"-> ⚠️ Conectó a la BD, pero hubo error al leer la tabla Skill_Group: {e}")

    # Cerrar la conexión
    cursor.close()
    conexion.close()
    print("\nConexión cerrada correctamente. ¡Todo está listo para trabajar!")

except pyodbc.OperationalError as e:
    print("\n❌ ERROR DE CONEXIÓN (Operacional):")
    print("Posibles causas: La IP está mal, el puerto 1433 está bloqueado por el Firewall o el servidor está apagado.")
    print(f"Detalle técnico: {e}")
    
except pyodbc.InterfaceError as e:
    print("\n❌ ERROR DE AUTENTICACIÓN:")
    print("Posibles causas: El usuario o la contraseña son incorrectos, o el usuario no tiene permiso para entrar a esa base de datos.")
    print(f"Detalle técnico: {e}")
    
except Exception as e:
    print(f"\n❌ ERROR INESPERADO:\n{e}")