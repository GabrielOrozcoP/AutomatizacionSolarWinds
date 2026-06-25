import os
import time
import requests
import pandas as pd
import urllib3
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === 1. TUS CREDENCIALES DE CISCO ===
CLIENT_ID = "eawtheb6j64q3whehv2aj7rb"
CLIENT_SECRET = "5zD9CUUDVCYW2sBxkpazNpEh"
CUSTOMER_ID = "Zz17LnLF5r8xQpI"

COLUMNAS_ESPERADAS = [
    'Telemetry', 'Name', 'Product ID', 'Product Description', 'Advisories', 
    'Critical Security Advisories', 'Location', 'Coverage Status', 'Software Type', 
    'Software Release', 'IP Address', 'Asset Groups', 'Contract Number', 'Managed By', 
    'Coverage End Date', 'Support Coverage', 'CX Level', 'Last Date of Support', 
    'End of Software maintenance', 'Last Scan', 'Product Family', 'Product Type', 
    'Role', 'Serial Number', 'Asset Type', 'Sales Order Number'
]

def pausar(paso):
    input(f"\n[CONTROL] Pausa activa. Presiona ENTER para iniciar {paso}...")

def obtener_token():
    print("\n[LOG] Autenticando con Cisco...")
    url = "https://id.cisco.com/oauth2/default/v1/token"
    payload = {'grant_type': 'client_credentials'}
    try:
        res = requests.post(url, data=payload, auth=(CLIENT_ID, CLIENT_SECRET), verify=False)
        res.raise_for_status()
        return res.json()['access_token']
    except Exception as e:
        print(f"[ERROR CRÍTICO] Autenticación falló: {e}")
        return None

def descargar_paginado(endpoint, token, nombre_modulo):
    print(f"\n--- Descargando módulo: {nombre_modulo} ---")
    activos_totales = []
    page = 1
    rows = 100
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    while True:
        url = f"https://apix.cisco.com/cs/api/v2/{endpoint}?customerId={CUSTOMER_ID}&page={page}&rows={rows}"
        print(f"[LOG] {nombre_modulo} -> Solicitando página {page}...")
        
        try:
            res = requests.get(url, headers=headers, verify=False, timeout=30)
            res.raise_for_status()
            
            respuesta_json = res.json()
            data = respuesta_json.get('data', [])
            
            if not data: break
            activos_totales.extend(data)
            
            total_pages = respuesta_json.get('pagination', {}).get('pages', 1)
            if page >= total_pages: break
            
            page += 1
            time.sleep(1)
        except Exception as e:
            print(f"[ERROR] Falló la descarga en {nombre_modulo}: {e}")
            break

    print(f"[ÉXITO] {len(activos_totales)} registros obtenidos de {nombre_modulo}.")
    return activos_totales

def fusionar_y_guardar(hw_data, ne_data, contract_data):
    print("\n" + "="*50)
    print(" PASO 3: Fusión de Datos Avanzada (Con Puente de IDs)")
    print("="*50)
    
    # 1. Convertir las listas en Tablas de Pandas
    df_hw = pd.DataFrame(hw_data) if hw_data else pd.DataFrame()
    df_ne = pd.DataFrame(ne_data) if ne_data else pd.DataFrame()
    df_co = pd.DataFrame(contract_data) if contract_data else pd.DataFrame()

    if 'serialNumber' not in df_hw.columns:
        print("[ERROR CRÍTICO] Hardware no tiene 'serialNumber'.")
        return

    print("[LOG] Construyendo puente de conexión (neInstanceId -> serialNumber)...")
    
    # 2. Crear el "Puente" usando Hardware y Contratos
    mapa_ids = pd.DataFrame(columns=['neInstanceId', 'serialNumber'])
    
    if 'neInstanceId' in df_hw.columns:
        mapa_ids = pd.concat([mapa_ids, df_hw[['neInstanceId', 'serialNumber']].dropna()])
    if not df_co.empty and 'neInstanceId' in df_co.columns and 'serialNumber' in df_co.columns:
        mapa_ids = pd.concat([mapa_ids, df_co[['neInstanceId', 'serialNumber']].dropna()])
        
    mapa_ids = mapa_ids.drop_duplicates(subset=['neInstanceId'])

    print("[LOG] Limpiando tablas de Redes y Contratos...")
    # 3. Limpieza y preparación de IPs
    if not df_ne.empty and 'neInstanceId' in df_ne.columns:
        # Extraemos IPs, nombres y ¡Versiones de software!
        cols_ne = [c for c in ['neInstanceId', 'ipAddress', 'hostname', 'sysName', 'swType', 'swVersion'] if c in df_ne.columns]
        df_ne = df_ne[cols_ne].drop_duplicates('neInstanceId')
        
        # Cruce mágico: Le pegamos el serialNumber a las IPs usando el puente
        if not mapa_ids.empty:
            df_ne = df_ne.merge(mapa_ids, on='neInstanceId', how='inner')
    else:
        df_ne = pd.DataFrame()

    # 4. Limpieza de Contratos
    if not df_co.empty and 'serialNumber' in df_co.columns:
        cols_co = [c for c in ['serialNumber', 'contractNumber', 'coverageEndDate', 'coverageStatus', 'serviceLevel'] if c in df_co.columns]
        df_co = df_co[cols_co].drop_duplicates('serialNumber')

    # 5. Fusión Maestra (Todo se une usando el serialNumber)
    print("[LOG] Cruzando Hardware con IPs y Hostnames...")
    df_master = df_hw.merge(df_ne, on='serialNumber', how='left') if not df_ne.empty and 'serialNumber' in df_ne.columns else df_hw
    
    print("[LOG] Cruzando con base de datos de Contratos...")
    df_master = df_master.merge(df_co, on='serialNumber', how='left') if not df_co.empty else df_master

    # 6. Mapear a tu plantilla exacta
    datos_formateados = []
    for item in df_master.to_dict('records'):
        # A veces el nombre viene en 'hostname', a veces en 'sysName'
        nombre_equipo = item.get('hostname') if pd.notna(item.get('hostname')) and item.get('hostname') else item.get('sysName', '')
        
        fila = {
            'Telemetry': 'Connected', 
            'Name': nombre_equipo, 
            'Product ID': item.get('basePid', item.get('productId', '')),
            'Product Description': item.get('itemDescription', ''),
            'Advisories': '', 
            'Critical Security Advisories': '', 
            'Location': '', 
            'Coverage Status': item.get('coverageStatus', ''), 
            'Software Type': item.get('swType', ''),       # ¡Agregado exitosamente!
            'Software Release': item.get('swVersion', ''), # ¡Agregado exitosamente!
            'IP Address': item.get('ipAddress', ''), 
            'Asset Groups': '',
            'Contract Number': item.get('contractNumber', ''), 
            'Managed By': '',
            'Coverage End Date': item.get('coverageEndDate', ''), 
            'Support Coverage': item.get('serviceLevel', ''), 
            'CX Level': '',
            'Last Date of Support': item.get('ldosDate', ''),
            'End of Software maintenance': item.get('eosmDate', ''),
            'Last Scan': '',
            'Product Family': item.get('productFamily', ''),
            'Product Type': item.get('productType', ''),
            'Role': '',
            'Serial Number': item.get('serialNumber', ''),
            'Asset Type': 'Hardware',
            'Sales Order Number': ''
        }
        datos_formateados.append(fila)

    try:
        # 7. Guardar el archivo
        df_final = pd.DataFrame(datos_formateados, columns=COLUMNAS_ESPERADAS)
        ruta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
        nombre_archivo = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_CX_CLOUD_FULL.csv"
        ruta_final = os.path.join(ruta_descargas, nombre_archivo)

        df_final.to_csv(ruta_final, index=False, encoding='utf-8')
        print(f"\n[ÉXITO TOTAL] Fusión completada. Archivo guardado en:\n-> {ruta_final}")
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] Error al guardar el archivo: {e}")

# === FLUJO DE EJECUCIÓN MAESTRO ===
if __name__ == "__main__":
    print("=== INICIANDO EXTRACCIÓN AVANZADA (HARDWARE + RED + CONTRATOS) ===")
    
    token = obtener_token()
    if token:
        pausar("PASO 2 (Descarga Masiva de Módulos)")
        
        hw_datos = descargar_paginado("inventory/hardware", token, "HARDWARE")
        ne_datos = descargar_paginado("inventory/network-elements", token, "IPs & HOSTNAMES")
        co_datos = descargar_paginado("contracts/coverage", token, "CONTRATOS")
        
        if hw_datos:
            pausar("PASO 3 (Fusión y Exportación)")
            fusionar_y_guardar(hw_datos, ne_datos, co_datos)
        else:
            print("\n[AVISO] No se pudo descargar el hardware base. Proceso abortado.")