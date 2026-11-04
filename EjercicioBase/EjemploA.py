import json
import math

def distancia_manhattan(p1, p2):
    """Calcula la distancia Manhattan entre dos puntos (x, y)."""
    return abs(p1['x'] - p2['x']) + abs(p1['y'] - p2['y'])

def cargar_datos(ruta_mundo, ruta_pedidos, ruta_vehiculos):
    """Lee los tres archivos JSON del dataset."""
    with open(ruta_mundo, 'r', encoding='utf-8') as f:
        mundo = json.load(f)
    with open(ruta_pedidos, 'r', encoding='utf-8') as f:
        pedidos = json.load(f)
    with open(ruta_vehiculos, 'r', encoding='utf-8') as f:
        vehiculos = json.load(f)
    return mundo, pedidos, vehiculos

# ==========================================
# MÓDULO 1: RUTEO INTERNO Y OPTIMIZACIÓN 2-OPT
# ==========================================
def optimizar_ruta_2opt(ruta, deposito):
    """
    Toma una lista de pedidos de un vehículo y aplica el algoritmo 2-Opt 
    para desatar cruces y reducir la distancia total recorrida.
    """
    if len(ruta) <= 2:
        return ruta

    def longitud_ruta(p_list):
        dist = distancia_manhattan(deposito, p_list[0])
        for i in range(len(p_list) - 1):
            dist += distancia_manhattan(p_list[i], p_list[i+1])
        dist += distancia_manhattan(p_list[-1], deposito)
        return dist

    mejor_ruta = ruta.copy()
    mejora = True
    
    while mejora:
        mejora = False
        for i in range(len(mejor_ruta) - 1):
            for j in range(i + 1, len(mejor_ruta)):
                # Invertir el segmento [i:j+1]
                nueva_ruta = mejor_ruta[:i] + mejor_ruta[i:j+1][::-1] + mejor_ruta[j+1:]
                if longitud_ruta(nueva_ruta) < longitud_ruta(mejor_ruta):
                    mejor_ruta = nueva_ruta
                    mejora = True
                    break
            if mejora:
                break
    return mejor_ruta

def rutar_vecino_cercano(pedidos_grupo, deposito):
    """Ordena los pedidos de un grupo saliendo del depósito hacia el más cercano."""
    if not pedidos_grupo:
        return []
    
    pendientes = pedidos_grupo.copy()
    pos_actual = deposito
    ruta_ordenada = []

    while pendientes:
        siguiente = min(pendientes, key=lambda p: distancia_manhattan(pos_actual, p))
        ruta_ordenada.append(siguiente)
        pos_actual = siguiente
        pendientes.remove(siguiente)

    # Refinar la ruta generada con 2-Opt
    return optimizar_ruta_2opt(ruta_ordenada, deposito)

# ==========================================
# MÓDULO 2: ASIGNACIÓN Y CLUSTERING (ZONIFICACIÓN)
# ==========================================
def agrupar_pedidos_k_vehiculos(pedidos, k, deposito):
    """
    Agrupa los pedidos en K zonas contiguas usando el ángulo con el depósito
    y distribución equitativa para balancear el tiempo (makespan).
    """
    # Ordenar pedidos angularmente desde el depósito
    pedidos_ordenados = sorted(
        pedidos, 
        key=lambda p: math.atan2(p['y'] - deposito['y'], p['x'] - deposito['x'])
    )
    
    # Dividir secuencialmente para hacer zonas contiguas
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
# MÓDULO 3: SIMULADOR INTERNO DE COSTO
# ==========================================
def calcular_costo_plan(rutas, mundo, total_pedidos):
    """Calcula el costo exacto del plan según las fórmulas oficiales."""
    deposito = {'x': mundo['deposito_x'], 'y': mundo['deposito_y']}
    costo_por_cuadra = mundo['costo_por_cuadra']
    costo_por_vehiculo = mundo['costo_por_vehiculo']
    costo_por_minuto_total = mundo['costo_por_minuto_total']
    costo_por_falla = mundo['costo_por_falla']
    
    min_por_cuadra = mundo['min_por_cuadra']
    tiempo_servicio = mundo['tiempo_servicio']
    tiempo_carga = mundo['tiempo_carga']
    
    distancia_total = 0
    vehiculos_usados = len(rutas)
    tiempos_retorno = []
    pedidos_entregados = set()

    for ruta in rutas:
        pos_actual = deposito
        tiempo_vehiculo = 0
        
        for parada in ruta:
            if parada == "DEPOSITO":
                dist = distancia_manhattan(pos_actual, deposito)
                distancia_total += dist
                tiempo_vehiculo += dist * min_por_cuadra + tiempo_carga
                pos_actual = deposito
            else:
                dist = distancia_manhattan(pos_actual, parada)
                distancia_total += dist
                tiempo_vehiculo += dist * min_por_cuadra + tiempo_servicio
                pos_actual = parada
                pedidos_entregados.add(parada['id'])
                
        # Regreso final al depósito
        dist_vuelta = distancia_manhattan(pos_actual, deposito)
        distancia_total += dist_vuelta
        tiempo_vehiculo += dist_vuelta * min_por_cuadra
        
        tiempos_retorno.append(tiempo_vehiculo)

    makespan = max(tiempos_retorno) if tiempos_retorno else 0
    fallas = total_pedidos - len(pedidos_entregados)

    costo_total = (
        (costo_por_cuadra * distancia_total) +
        (costo_por_vehiculo * vehiculos_usados) +
        (costo_por_minuto_total * makespan) +
        (costo_por_falla * fallas)
    )
    return costo_total

# ==========================================
# MÓDULO PRINCIPAL: OPTIMIZACIÓN Y SELECCIÓN
# ==========================================
def optimizar_plan(mundo, pedidos, vehiculos):
    """Evalúa usar de 1 a N vehículos y selecciona la mejor configuración."""
    deposito = {'x': mundo['deposito_x'], 'y': mundo['deposito_y']}
    total_vehiculos_disponibles = len(vehiculos)
    total_pedidos = len(pedidos)
    
    mejor_costo = float('inf')
    mejor_plan_formateado = None
    mejor_k = 0

    for k in range(1, total_vehiculos_disponibles + 1):
        # 1. Asignación (Clustering)
        grupos = agrupar_pedidos_k_vehiculos(pedidos, k, deposito)
        
        # 2. Ruteo individual (Vecino Cercano + 2-Opt)
        rutas_objetos = []
        for g in grupos:
            if g:
                ruta_v = rutar_vecino_cercano(g, deposito)
                rutas_objetos.append(ruta_v)
        
        # 3. Evaluador de Costos
        costo = calcular_costo_plan(rutas_objetos, mundo, total_pedidos)
        
        if costo < mejor_costo:
            mejor_costo = costo
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

    print(f"--- RESULTADO DE OPTIMIZACIÓN ---")
    print(f"Vehículos Óptimos a Utilizar: {mejor_k} de {total_vehiculos_disponibles}")
    print(f"Mejor Costo Estimado: {mejor_costo} puntos")
    return mejor_plan_formateado

# --- EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    ruta_mundo = "otrosdatasets/Base A/mundo.json"
    ruta_pedidos = "otrosdatasets/Base A/pedidos.json"
    ruta_vehiculos = "otrosdatasets/Base A/vehiculos.json"
    
    mundo, pedidos, vehiculos = cargar_datos(ruta_mundo, ruta_pedidos, ruta_vehiculos)
    plan_optimo = optimizar_plan(mundo, pedidos, vehiculos)
    
    with open("plan_salidaA.json", "w", encoding="utf-8") as f:
        json.dump(plan_optimo, f, indent=2)
        
    print("Plan guardado exitosamente en 'plan_salida.json'")
