import os
import time
import requests
import pandas as pd
import urllib3
from datetime import datetime

# Silenciar las advertencias amarillas de seguridad (InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === 1. TUS CREDENCIALES DE CISCO ===
CLIENT_ID = "eawtheb6j64q3whehv2aj7rb"
CLIENT_SECRET = "5zD9CUUDVCYW2sBxkpazNpEh"
CUSTOMER_ID = "Zz17LnLF5r8xQpI"

# === 2. PLANTILLA OFICIAL DE 26 COLUMNAS ===
COLUMNAS_ESPERADAS = [
    'Telemetry', 'Name', 'Product ID', 'Product Description', 'Advisories', 
    'Critical Security Advisories', 'Location', 'Coverage Status', 'Software Type', 
    'Software Release', 'IP Address', 'Asset Groups', 'Contract Number', 'Managed By', 
    'Coverage End Date', 'Support Coverage', 'CX Level', 'Last Date of Support', 
    'End of Software maintenance', 'Last Scan', 'Product Family', 'Product Type', 
    'Role', 'Serial Number', 'Asset Type', 'Sales Order Number'
]

def pausar(paso):
    """Detiene la ejecución para mantener control absoluto sobre el flujo."""
    input(f"\n[CONTROL] Pausa activa. Presiona ENTER para iniciar {paso}...")

def obtener_token():
    print("\n" + "="*50)
    print(" PASO 1: Autenticación con Cisco")
    print("="*50)
    print("[LOG] Iniciando solicitud de Token OAuth2...")
    url = "https://id.cisco.com/oauth2/default/v1/token"
    payload = {'grant_type': 'client_credentials'}
    try:
        res = requests.post(url, data=payload, auth=(CLIENT_ID, CLIENT_SECRET), verify=False)
        res.raise_for_status()
        print("[ÉXITO] Token de acceso generado correctamente.")
        return res.json()['access_token']
    except Exception as e:
        print(f"[ERROR CRÍTICO] Autenticación falló: {e}")
        return None

def descargar_paginado(endpoint, token, nombre_modulo):
    """Descarga datos de forma iterativa controlando la paginación de la API v2."""
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
            print(f"[AVISO] Módulo {nombre_modulo} omitido o sin registros: {e}")
            break

    print(f"[ÉXITO] {len(activos_totales)} registros obtenidos de {nombre_modulo}.")
    return activos_totales

def fusionar_y_guardar_csv(hw_data, ne_data, contract_data, sa_data, sab_data, eol_data, eolb_data):
    print("\n" + "="*50)
    print(" PASO 3: Fusión Avanzada de 7 Vías y Guardado de CSV")
    print("="*50)
    print("[LOG] Procesando y cruzando tablas en memoria...")

    # Convertir descargas en DataFrames de Pandas
    df_hw = pd.DataFrame(hw_data) if hw_data else pd.DataFrame()
    df_ne = pd.DataFrame(ne_data) if ne_data else pd.DataFrame()
    df_co = pd.DataFrame(contract_data) if contract_data else pd.DataFrame()
    df_sa = pd.DataFrame(sa_data) if sa_data else pd.DataFrame()
    df_sab = pd.DataFrame(sab_data) if sab_data else pd.DataFrame()
    df_eol = pd.DataFrame(eol_data) if eol_data else pd.DataFrame()
    df_eolb = pd.DataFrame(eolb_data) if eolb_data else pd.DataFrame()

    if 'serialNumber' not in df_hw.columns:
        print("[ERROR CRÍTICO] La tabla base de Hardware no contiene 'serialNumber'. Abortando.")
        return

    # 1. Filtrar y limpiar datos lógicos de Redes y Contratos
    if not df_ne.empty and 'neInstanceId' in df_ne.columns:
        cols_ne = [c for c in ['neInstanceId', 'ipAddress', 'hostname', 'sysName', 'swType', 'swVersion', 'collectorId', 'sysLocation'] if c in df_ne.columns]
        df_ne = df_ne[cols_ne].drop_duplicates('neInstanceId')
    
    if not df_co.empty and 'serialNumber' in df_co.columns:
        cols_co = [c for c in ['serialNumber', 'contractNumber', 'coverageEndDate', 'coverageStatus', 'serviceLevel', 'serviceProgram'] if c in df_co.columns]
        df_co = df_co[cols_co].drop_duplicates('serialNumber')

    # 2. Procesar Alertas de Seguridad (Contar totales y críticas por dispositivo)
    df_adv_counts = pd.DataFrame(columns=['neInstanceId', 'Advisories', 'Critical Security Advisories'])
    if not df_sa.empty and not df_sab.empty and 'securityAdvisoryInstanceId' in df_sa.columns:
        df_sa_full = df_sa.merge(df_sab[['securityAdvisoryInstanceId', 'securityImpactRating']], on='securityAdvisoryInstanceId', how='left')
        adv_totales = df_sa_full.groupby('neInstanceId').size().reset_index(name='Advisories')
        adv_criticas = df_sa_full[df_sa_full['securityImpactRating'] == 'Critical'].groupby('neInstanceId').size().reset_index(name='Critical Security Advisories')
        df_adv_counts = adv_totales.merge(adv_criticas, on='neInstanceId', how='left').fillna(0)

    # 3. Procesar Fechas de Fin de Vida (EoL)
    df_eol_final = pd.DataFrame(columns=['hwInstanceId', 'lastDateOfSupport', 'eoSwMaintenanceReleasesDate'])
    if not df_eol.empty and not df_eolb.empty and 'hwEolInstanceId' in df_eol.columns:
        cols_eolb = [c for c in ['hwEolInstanceId', 'lastDateOfSupport', 'eoSwMaintenanceReleasesDate'] if c in df_eolb.columns]
        df_eol_full = df_eol.merge(df_eolb[cols_eolb], on='hwEolInstanceId', how='left')
        df_eol_final = df_eol_full[['hwInstanceId', 'lastDateOfSupport', 'eoSwMaintenanceReleasesDate']].drop_duplicates('hwInstanceId')

    # 4. Fusión Maestra Dinámica (LEFT JOIN usando llaves arquitectónicas de Cisco)
    print("[LOG] Ejecutando cruces relacionales...")
    df_master = df_hw.copy()
    if not df_ne.empty:
        df_master = df_master.merge(df_ne, on='neInstanceId', how='left')
    if not df_co.empty:
        df_master = df_master.merge(df_co, on='serialNumber', how='left')
    if not df_adv_counts.empty:
        df_master = df_master.merge(df_adv_counts, on='neInstanceId', how='left')
    if not df_eol_final.empty:
        df_master = df_master.merge(df_eol_final, on='hwInstanceId', how='left')

    # 5. Mapeo estructural hacia el formato del Dashboard original
    datos_formateados = []
    for item in df_master.to_dict('records'):
        # Validación de hostnames
        nombre_equipo = item.get('hostname') if pd.notna(item.get('hostname')) and item.get('hostname') else item.get('sysName', '')
        
        # Formatear números de alertas para evitar la aparición de decimales flotantes (.0)
        advisories = int(item.get('Advisories')) if pd.notna(item.get('Advisories')) else ''
        critical_adv = int(item.get('Critical Security Advisories')) if pd.notna(item.get('Critical Security Advisories')) else ''

        fila = {
            'Telemetry': 'Connected', 
            'Name': nombre_equipo, 
            'Product ID': item.get('productId', item.get('basePid', '')),
            'Product Description': item.get('productDescription', ''), 
            'Advisories': advisories, 
            'Critical Security Advisories': critical_adv, 
            'Location': item.get('sysLocation', ''), 
            'Coverage Status': item.get('coverageStatus', ''), 
            'Software Type': item.get('swType', ''),       
            'Software Release': item.get('swVersion', ''), 
            'IP Address': item.get('ipAddress', ''), 
            'Asset Groups': '', # Campos obsoletos en API v2 pública
            'Contract Number': item.get('contractNumber', ''), 
            'Managed By': item.get('collectorId', ''), 
            'Coverage End Date': item.get('coverageEndDate', ''), 
            'Support Coverage': item.get('serviceLevel', ''), 
            'CX Level': item.get('serviceProgram', ''), 
            'Last Date of Support': item.get('lastDateOfSupport', ''), 
            'End of Software maintenance': item.get('eoSwMaintenanceReleasesDate', ''), 
            'Last Scan': '', # Campos obsoletos en API v2 pública
            'Product Family': item.get('productFamily', ''),
            'Product Type': item.get('productType', ''),
            'Role': '', # Campos obsoletos en API v2 pública
            'Serial Number': item.get('serialNumber', ''),
            'Asset Type': 'Hardware',
            'Sales Order Number': '' # Campos obsoletos en API v2 pública
        }
        datos_formateados.append(fila)

    try:
        # 6. Construir DataFrame final con orden exacto de columnas y guardar
        df_final = pd.DataFrame(datos_formateados, columns=COLUMNAS_ESPERADAS)
        
        ruta_descargas = os.path.join(os.path.expanduser("~"), "Downloads")
        fecha_hora = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_archivo = f"{fecha_hora}_CX_CLOUD.csv"
        ruta_final = os.path.join(ruta_descargas, nombre_archivo)

        df_final.to_csv(ruta_final, index=False, encoding='utf-8')
        
        print(f"\n[ÉXITO TOTAL] El archivo con formato idéntico se ha generado.")
        print(f"[UBICACIÓN] -> {ruta_final}")
        print(f"[REGISTROS] Se procesaron exitosamente {len(df_final)} equipos de red.")
        
    except Exception as e:
        print(f"\n[ERROR CRÍTICO] Error al estructurar o guardar el archivo local: {e}")

# === FLUJO DE EJECUCIÓN MAESTRO ===
if __name__ == "__main__":
    print("=== INICIANDO EXTRACCIÓN AVANZADA DE 7 ENDPOINTS ===")
    
    token = obtener_token()
    if token:
        pausar("PASO 2 (Descarga Masiva de Datos de Cisco)")
        
        # Ejecución secuencial de los 7 endpoints documentados en tu OpenAPI YAML
        hw_datos = descargar_paginado("inventory/hardware", token, "HARDWARE [1/7]")
        ne_datos = descargar_paginado("inventory/network-elements", token, "REDES E IPs [2/7]")
        co_datos = descargar_paginado("contracts/coverage", token, "CONTRATOS [3/7]")
        sa_datos = descargar_paginado("product-alerts/security-advisories", token, "ALERTAS [4/7]")
        sab_datos = descargar_paginado("product-alerts/security-advisory-bulletins", token, "SEVERIDADES [5/7]")
        eol_datos = descargar_paginado("product-alerts/hardware-eol", token, "FIN DE VIDA [6/7]")
        eolb_datos = descargar_paginado("product-alerts/hardware-eol-bulletins", token, "FECHAS SOPORTE [7/7]")
        
        if hw_datos:
            pausar("PASO 3 (Fusión y Escritura del Archivo .CSV)")
            fusionar_y_guardar_csv(hw_datos, ne_datos, co_datos, sa_datos, sab_datos, eol_datos, eolb_datos)
        else:
            print("\n[AVISO] No se pudo obtener la información base de Hardware. Proceso abortado.")