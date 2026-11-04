import json
import math

def distancia_manhattan(p1, p2):
    """Calcula la distancia Manhattan entre dos puntos (x, y)."""
    return abs(p1['x'] - p2['x']) + abs(p1['y'] - p2['y'])

def es_premium(pedido):
    """Detecta si un pedido es premium soportando booleanos, enteros (1/0) y strings."""
    if not isinstance(pedido, dict):
        return False
    val = pedido.get('premium', False)
    if isinstance(val, str):
        return val.strip().lower() in ('true', '1', 'si', 'yes')
    if isinstance(val, (int, float)):
        return bool(val)
    return bool(val)

def cargar_datos(ruta_mundo, ruta_pedidos, ruta_vehiculos):
    """Lee los tres archivos JSON del dataset asegurando valores por defecto seguros."""
    with open(ruta_mundo, 'r', encoding='utf-8') as f:
        mundo = json.load(f)
    with open(ruta_pedidos, 'r', encoding='utf-8') as f:
        pedidos = json.load(f)
    with open(ruta_vehiculos, 'r', encoding='utf-8') as f:
        vehiculos = json.load(f)
        
    # Normalizar campo premium en cada pedido
    for p in pedidos:
        p['premium'] = es_premium(p)
        
    return mundo, pedidos, vehiculos

# ==========================================
# MÓDULO 1: COSTO Y EVALUACIÓN DE RUTAS
# ==========================================
def calcular_metricas_ruta(ruta, deposito, mundo):
    """
    Calcula distancia, tiempo final y minutos de espera para pedidos premium
    de una ruta individual.
    """
    min_por_cuadra = mundo.get('min_por_cuadra', 3)
    tiempo_servicio = mundo.get('tiempo_servicio', 5)
    tiempo_carga = mundo.get('tiempo_carga', 10)
    
    pos_actual = deposito
    tiempo_vehiculo = 0
    distancia = 0
    minutos_espera_premium = 0
    
    for parada in ruta:
        if parada == "DEPOSITO":
            dist = distancia_manhattan(pos_actual, deposito)
            distancia += dist
            tiempo_vehiculo += dist * min_por_cuadra + tiempo_carga
            pos_actual = deposito
        else:
            dist = distancia_manhattan(pos_actual, parada)
            distancia += dist
            # El tiempo de llegada es cuando empieza la entrega (según Evento 1)
            tiempo_llegada = tiempo_vehiculo + dist * min_por_cuadra
            if parada.get('premium', False):
                minutos_espera_premium += tiempo_llegada
                
            tiempo_vehiculo = tiempo_llegada + tiempo_servicio
            pos_actual = parada
            
    # Retorno final al depósito
    dist_retorno = distancia_manhattan(pos_actual, deposito)
    distancia += dist_retorno
    tiempo_vehiculo += dist_retorno * min_por_cuadra
    
    return {
        'distancia': distancia,
        'tiempo_retorno': tiempo_vehiculo,
        'minutos_espera_premium': minutos_espera_premium
    }

def costo_local_ruta(ruta, deposito, mundo):
    """Función de costo específica de una ruta para guiar la optimización interna."""
    metricas = calcular_metricas_ruta(ruta, deposito, mundo)
    costo_cuadra = mundo.get('costo_por_cuadra', 3)
    costo_premium = mundo.get('costo_por_minuto_premium', 1)
    
    return (
        metricas['distancia'] * costo_cuadra +
        metricas['minutos_espera_premium'] * costo_premium
    )

# ==========================================
# MÓDULO 2: RUTEO Y OPTIMIZACIÓN LOCAL
# ==========================================
def optimizar_ruta_evento1(ruta, deposito, mundo):
    """
    Optimiza la ruta usando 2-Opt y Relocate (reubicación),
    guiado por el costo real que considera la distancia y la espera premium.
    """
    if len(ruta) <= 2:
        return ruta

    mejor_ruta = ruta.copy()
    mejor_costo = costo_local_ruta(mejor_ruta, deposito, mundo)
    mejora = True
    
    while mejora:
        mejora = False
        n = len(mejor_ruta)
        
        # 1. Probar inversiones 2-Opt
        for i in range(n - 1):
            for j in range(i + 1, n):
                nueva = mejor_ruta[:i] + mejor_ruta[i:j+1][::-1] + mejor_ruta[j+1:]
                costo_nuevo = costo_local_ruta(nueva, deposito, mundo)
                if costo_nuevo < mejor_costo:
                    mejor_ruta = nueva
                    mejor_costo = costo_nuevo
                    mejora = True
                    break
            if mejora:
                break
                
        if mejora:
            continue
            
        # 2. Probar Relocate (adelantar o mover pedidos individuales)
        # Fundamental para pedidos premium que rinden más al inicio de la ruta
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                nueva = mejor_ruta.copy()
                parada = nueva.pop(i)
                nueva.insert(j, parada)
                costo_nuevo = costo_local_ruta(nueva, deposito, mundo)
                if costo_nuevo < mejor_costo:
                    mejor_ruta = nueva
                    mejor_costo = costo_nuevo
                    mejora = True
                    break
            if mejora:
                break
                
    return mejor_ruta

def rutar_grupo_con_prioridad_premium(pedidos_grupo, deposito, mundo):
    """
    Construye una ruta inicial priorizando pedidos premium al inicio,
    y luego refina con optimización local (2-Opt + Relocate).
    """
    if not pedidos_grupo:
        return []
    
    premiums = [p for p in pedidos_grupo if p.get('premium', False)]
    normales = [p for p in pedidos_grupo if not p.get('premium', False)]
    
    ruta_inicial = []
    pos_actual = deposito
    
    # 1. Atender primero a los clientes premium usando el más cercano
    pendientes_prem = premiums.copy()
    while pendientes_prem:
        siguiente = min(pendientes_prem, key=lambda p: distancia_manhattan(pos_actual, p))
        ruta_inicial.append(siguiente)
        pos_actual = siguiente
        pendientes_prem.remove(siguiente)
        
    # 2. Luego atender a los normales usando vecino más cercano
    pendientes_norm = normales.copy()
    while pendientes_norm:
        siguiente = min(pendientes_norm, key=lambda p: distancia_manhattan(pos_actual, p))
        ruta_inicial.append(siguiente)
        pos_actual = siguiente
        pendientes_norm.remove(siguiente)
        
    # 3. Refinar la ruta con optimización local guiada por costo
    return optimizar_ruta_evento1(ruta_inicial, deposito, mundo)

# ==========================================
# MÓDULO 3: ASIGNACIÓN Y CLUSTERING (ZONIFICACIÓN)
# ==========================================
def agrupar_pedidos_k_vehiculos(pedidos, k, deposito):
    """Agrupa pedidos en K zonas contiguas según su ángulo con el depósito."""
    pedidos_ordenados = sorted(
        pedidos, 
        key=lambda p: math.atan2(p['y'] - deposito['y'], p['x'] - deposito['x'])
    )
    n = len(pedidos_ordenados)
    tam_base = n // k
    resto = n % k
    
    grupos = []
    inicio = 0
    for i in range(k):
        tam_actual = tam_base + (1 if i < resto else 0)
        grupos.append(pedidos_ordenados[inicio:inicio + tam_actual])
        inicio += tam_actual
        
    return grupos

# ==========================================
# MÓDULO 4: SIMULADOR OFICIAL DE COSTO (CON EVENTO 1)
# ==========================================
def calcular_costo_plan(rutas, mundo, total_pedidos):
    """
    Calcula el costo total del plan incluyendo la penalización de Evento 1
    (minutos desde la hora_salida hasta la entrega de cada premium entregado).
    """
    deposito = {'x': mundo['deposito_x'], 'y': mundo['deposito_y']}
    costo_por_cuadra = mundo.get('costo_por_cuadra', 3)
    costo_por_vehiculo = mundo.get('costo_por_vehiculo', 60)
    costo_por_minuto_total = mundo.get('costo_por_minuto_total', 1)
    costo_por_falla = mundo.get('costo_por_falla', 200)
    costo_por_minuto_premium = mundo.get('costo_por_minuto_premium', 1)
    
    distancia_total = 0
    vehiculos_usados = len(rutas)
    tiempos_retorno = []
    minutos_espera_premium_total = 0
    pedidos_entregados = set()

    for ruta in rutas:
        metricas = calcular_metricas_ruta(ruta, deposito, mundo)
        distancia_total += metricas['distancia']
        tiempos_retorno.append(metricas['tiempo_retorno'])
        minutos_espera_premium_total += metricas['minutos_espera_premium']
        
        for parada in ruta:
            if isinstance(parada, dict) and 'id' in parada:
                pedidos_entregados.add(parada['id'])

    makespan = max(tiempos_retorno) if tiempos_retorno else 0
    fallas = total_pedidos - len(pedidos_entregados)

    costo_distancia = costo_por_cuadra * distancia_total
    costo_vehiculos = costo_por_vehiculo * vehiculos_usados
    costo_makespan = costo_por_minuto_total * makespan
    costo_fallas = costo_por_falla * fallas
    costo_premium = costo_por_minuto_premium * minutos_espera_premium_total

    costo_total = (
        costo_distancia +
        costo_vehiculos +
        costo_makespan +
        costo_fallas +
        costo_premium
    )
    
    desglose = {
        'costo_total': costo_total,
        'distancia_total': distancia_total,
        'costo_distancia': costo_distancia,
        'vehiculos_usados': vehiculos_usados,
        'costo_vehiculos': costo_vehiculos,
        'makespan': makespan,
        'costo_makespan': costo_makespan,
        'fallas': fallas,
        'costo_fallas': costo_fallas,
        'minutos_premium': minutos_espera_premium_total,
        'costo_premium': costo_premium
    }
    return costo_total, desglose

# ==========================================
# MÓDULO 5: OPTIMIZACIÓN Y SELECCIÓN DE FLOTA
# ==========================================
def optimizar_plan(mundo, pedidos, vehiculos):
    """
    Evalúa usar de 1 a N vehículos y selecciona la configuración
    que minimiza el costo total con las reglas de Evento 1.
    """
    deposito = {'x': mundo['deposito_x'], 'y': mundo['deposito_y']}
    total_vehiculos_disponibles = len(vehiculos)
    total_pedidos = len(pedidos)
    
    mejor_costo = float('inf')
    mejor_desglose = None
    mejor_plan_formateado = None
    mejor_k = 0

    print("--- EVALUANDO CONFIGURACIONES DE FLOTA (EVENTO 1) ---")
    for k in range(1, total_vehiculos_disponibles + 1):
        # 1. Asignación por zonas
        grupos = agrupar_pedidos_k_vehiculos(pedidos, k, deposito)
        
        # 2. Ruteo individual con prioridad de clientes premium
        rutas_objetos = []
        for g in grupos:
            if g:
                ruta_v = rutar_grupo_con_prioridad_premium(g, deposito, mundo)
                rutas_objetos.append(ruta_v)
        
        # 3. Evaluación de costo con fórmula oficial de Evento 1
        costo, desglose = calcular_costo_plan(rutas_objetos, mundo, total_pedidos)
        
        print(f"K = {k} autos | Distancia: {desglose['distancia_total']} | "
              f"Makespan: {desglose['makespan']}m | Espera Premium: {desglose['minutos_premium']}m | "
              f"Costo: {costo:.0f}")
        
        if costo < mejor_costo:
            mejor_costo = costo
            mejor_desglose = desglose
            mejor_k = len(rutas_objetos)
            
            # Formato de salida JSON oficial
            rutas_json = []
            for i, r in enumerate(rutas_objetos):
                id_vehiculo = vehiculos[i]['id']
                paradas_ids = [p['id'] if isinstance(p, dict) else p for p in r]
                rutas_json.append({
                    "vehiculo": id_vehiculo,
                    "paradas": paradas_ids
                })
            mejor_plan_formateado = {"rutas": rutas_json}

    print("\n--- RESULTADO FINAL DE OPTIMIZACIÓN ---")
    print(f"Vehículos Óptimos a Utilizar: {mejor_k} de {total_vehiculos_disponibles}")
    print(f"Costo Total: {mejor_costo:.0f} puntos")
    print(f"  - Costo Distancia ({mejor_desglose['distancia_total']} cuadras): ${mejor_desglose['costo_distancia']}")
    print(f"  - Costo Vehículos ({mejor_desglose['vehiculos_usados']} autos): ${mejor_desglose['costo_vehiculos']}")
    print(f"  - Costo Makespan ({mejor_desglose['makespan']} min): ${mejor_desglose['costo_makespan']}")
    print(f"  - Costo Clientes Premium ({mejor_desglose['minutos_premium']} min de espera): ${mejor_desglose['costo_premium']}")
    print(f"  - Costo Fallas ({mejor_desglose['fallas']} pedidos): ${mejor_desglose['costo_fallas']}")
    
    return mejor_plan_formateado

# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    ruta_mundo = "evento1/dataset/evento1C/mundo.json"
    ruta_pedidos = "evento1/dataset/evento1C/pedidos.json"
    ruta_vehiculos = "evento1/dataset/evento1C/vehiculos.json"
    # ruta_mundo = "evento1/dataset/evento1A/mundo.json"
    # ruta_mundo = "otrosdatasets/Base A/mundo.json"
    
    mundo, pedidos, vehiculos = cargar_datos(ruta_mundo, ruta_pedidos, ruta_vehiculos)
    plan_optimo = optimizar_plan(mundo, pedidos, vehiculos)
    
    with open("plan_salida_evento1C.json", "w", encoding="utf-8") as f:
        json.dump(plan_optimo, f, indent=2)
        
    print("\nPlan guardado exitosamente en 'plan_salida_evento1.json'")
