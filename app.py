import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Configuración inicial de la página
st.set_page_config(page_title="Control de Stock y Simulación", layout="wide")

# Inicializar variables en sesión para la simulación manual
if 'simulacion_compras' not in st.session_state:
    st.session_state.simulacion_compras = pd.DataFrame(columns=["Código", "Semana_Llegada", "Kilos_Simulados"])

if 'simulacion_proyectos' not in st.session_state:
    st.session_state.simulacion_proyectos = pd.DataFrame(columns=["Código", "Semana_Consumo", "Kilos_Requeridos"])

# ==========================================
# 1. MOTOR DE DATOS Y CÁLCULOS (PANDAS)
# ==========================================

@st.cache_data
def cargar_datos_base():
    """
    Simula la extracción desde Google Cloud (GCP) y SQL.
    Aquí deberías usar pd.read_gbq() para GCP y pd.read_sql() para SQL.
    """
    # Simulación de extracción desde GCP (Stock y Consumo)
    data = {
        "Código": ["MEFEAN143A202", "MEFEAN143K221", "MEFEAN143A227", "MEFEAN143K37100"],
        "Material": ["ANG LAMIN A572 100X100X10", "ANG LAMIN A572 100X100X10 G50", "ANG LAMIN A572 65X65X5", "ANG LAMIN A572 70X70X6"],
        "Clase": ["1.1 ALTA", "1.1 ALTA", "1.1 ALTA", "1.1 ALTA"],
        "Stock_Barra_12M": [54380, 0, 12167, 94672], #[cite: 1]
        "Stock_Despunte": [3855, 0, 183, 659], #[cite: 1]
        "Consumo_Semanal_Promedio": [2500, 1500, 2094, 3000] #[cite: 1, 3]
    }
    df_maestro = pd.DataFrame(data)

    # Simulación de extracción desde SQL (Reservas Efectivas)
    reservas = {"Código": ["MEFEAN143A202", "MEFEAN143A227"], "Reservas_Efectivas": [66249, 37148]} #[cite: 1, 3]
    df_reservas = pd.DataFrame(reservas)

    # Simulación del programa de importación (Tránsito/En Proceso)
    llegadas = {
        "Código": ["MEFEAN143A227", "MEFEAN143A202"],
        "Semana_Llegada": ["2026-50", "2026-48"], #[cite: 2, 3]
        "Kilos_Llegada": [11151, 20000] #[cite: 3]
    }
    df_llegadas = pd.DataFrame(llegadas)

    return df_maestro, df_reservas, df_llegadas

def calcular_kpis(df_maestro, df_reservas):
    """Cruza los datos y calcula Stock Disponible y KPIs de semanas."""
    # Unir maestro con reservas
    df = pd.merge(df_maestro, df_reservas, on="Código", how="left").fillna(0)
    
    # Cálculos de stock actual
    df["Total_Stock_Actual"] = df["Stock_Barra_12M"] + df["Stock_Despunte"] #[cite: 1]
    df["Stock_Disponible"] = df["Total_Stock_Actual"] - df["Reservas_Efectivas"] #[cite: 1, 3]
    
    # Cálculos de políticas de inventario según consumo promedio
    df["Stock_Critico_7Sem"] = df["Consumo_Semanal_Promedio"] * 7 #[cite: 3]
    df["Stock_Seguridad_14Sem"] = df["Consumo_Semanal_Promedio"] * 14 #[cite: 3]
    df["Stock_Max_20Sem"] = df["Consumo_Semanal_Promedio"] * 20 #[cite: 3]
    
    # Calcular Exceso o Déficit
    df["Exceso_Stock"] = np.where(df["Total_Stock_Actual"] > df["Stock_Max_20Sem"], df["Total_Stock_Actual"] - df["Stock_Max_20Sem"], 0) #[cite: 3]
    
    return df

def proyectar_evolucion(sku, df_kpi, df_llegadas, semanas_proyeccion=15):
    """Calcula la evolución del inventario semana a semana para un SKU."""
    datos_sku = df_kpi[df_kpi["Código"] == sku].iloc[0]
    
    # Generar lista de semanas futuras (ej: 2026-47, 2026-48...)
    año_actual, semana_actual, _ = datetime.now().isocalendar()
    semanas = [f"{año_actual + (semana_actual + i)//52}-{(semana_actual + i)%52 or 52}" for i in range(semanas_proyeccion)] #[cite: 3]
    
    # Filtrar llegadas y simulaciones para este SKU
    llegadas_sku = df_llegadas[df_llegadas["Código"] == sku]
    sim_compras_sku = st.session_state.simulacion_compras[st.session_state.simulacion_compras["Código"] == sku]
    
    evolucion = []
    stock_iterativo = datos_sku["Stock_Disponible"] #[cite: 1, 3]
    stock_sin_simulacion = datos_sku["Stock_Disponible"]

    for sem in semanas:
        # Sumar llegadas reales confirmadas
        llegada_real = llegadas_sku[llegadas_sku["Semana_Llegada"] == sem]["Kilos_Llegada"].sum() if not llegadas_sku.empty else 0
        
        # Sumar llegadas simuladas (Módulo What-If)
        llegada_simulada = sim_compras_sku[sim_compras_sku["Semana_Llegada"] == sem]["Kilos_Simulados"].sum() if not sim_compras_sku.empty else 0
        
        # Restar consumo promedio como forecast base
        consumo_base = datos_sku["Consumo_Semanal_Promedio"]
        
        # Cálculo del periodo
        stock_iterativo = stock_iterativo + llegada_real + llegada_simulada - consumo_base
        stock_sin_simulacion = stock_sin_simulacion + llegada_real - consumo_base
        
        evolucion.append({
            "Semana": sem,
            "Llegadas_Reales": llegada_real, #[cite: 3]
            "Llegada_Simulada": llegada_simulada, #[cite: 3]
            "Proyección": stock_iterativo, #[cite: 3]
            "Proyección_Sin_Simulacion": stock_sin_simulacion #[cite: 3]
        })
        
    return pd.DataFrame(evolucion), datos_sku

# Cargar y procesar
df_maestro, df_reservas, df_llegadas = cargar_datos_base()
df_kpi = calcular_kpis(df_maestro, df_reservas)


# ==========================================
# 2. ESQUELETO VISUAL (STREAMLIT)
# ==========================================

st.title("📦 Modelo de Control de Stock y Simulación")

# Navegación lateral
menu = st.sidebar.radio("Navegación", ["1. Dashboard General", "2. Gestor de Simulación", "3. Evolución por SKU"])

# --- MÓDULO 1: DASHBOARD GENERAL ---
if menu == "1. Dashboard General":
    st.header("Resumen de Inventario (GCP + SQL)")
    
    # Mostrar tabla principal con formato
    st.dataframe(
        df_kpi[["Código", "Material", "Total_Stock_Actual", "Reservas_Efectivas", "Stock_Disponible", "Stock_Critico_7Sem"]].style.highlight_min(subset=['Stock_Disponible'], color='lightcoral'), #[cite: 1, 3]
        use_container_width=True
    )

# --- MÓDULO 2: GESTOR DE SIMULACIÓN ---
elif menu == "2. Gestor de Simulación":
    st.header("Simulación de Compras (What-If)")
    st.write("Agrega compras hipotéticas para evaluar su impacto en la proyección antes de crear la OC en SAP.")
    
    with st.form("form_compras"):
        col1, col2, col3 = st.columns(3)
        with col1:
            sku_seleccionado = st.selectbox("Material a Comprar", df_kpi["Código"].unique())
        with col2:
            cantidad = st.number_input("Cantidad (Kilos)", min_value=0, step=1000)
        with col3:
            # Entrada de semana formato Año-Sem (Ej: 2026-50)
            semana_req = st.text_input("Semana de Llegada (Año-Sem)", "2026-50") 
            
        submit_compra = st.form_submit_button("Añadir a Simulación")
        
        if submit_compra:
            nueva_simulacion = pd.DataFrame({"Código": [sku_seleccionado], "Semana_Llegada": [semana_req], "Kilos_Simulados": [cantidad]})
            st.session_state.simulacion_compras = pd.concat([st.session_state.simulacion_compras, nueva_simulacion], ignore_index=True)
            st.success(f"Simulación guardada: {cantidad} kg de {sku_seleccionado} para {semana_req}.")

    st.subheader("Compras Simuladas Activas")
    st.dataframe(st.session_state.simulacion_compras, use_container_width=True)
    if st.button("Limpiar Simulaciones"):
        st.session_state.simulacion_compras = pd.DataFrame(columns=["Código", "Semana_Llegada", "Kilos_Simulados"])
        st.rerun()

# --- MÓDULO 3: EVOLUCIÓN POR SKU ---
elif menu == "3. Evolución por SKU":
    st.header("Análisis Semanal y Gráfico de Evolución")
    
    sku_analisis = st.selectbox("Seleccione Código SAP", df_kpi["Código"].unique())
    
    df_evolucion, datos_sku = proyectar_evolucion(sku_analisis, df_kpi, df_llegadas)
    
    # KPIs Rápidos en tarjetas
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stock Actual", f"{datos_sku['Total_Stock_Actual']:,.0f}") #[cite: 1]
    c2.metric("Stock Disponible", f"{datos_sku['Stock_Disponible']:,.0f}") #[cite: 1, 3]
    c3.metric("Consumo Promedio", f"{datos_sku['Consumo_Semanal_Promedio']:,.0f}") #[cite: 3]
    c4.metric("Stock Crítico", f"{datos_sku['Stock_Critico_7Sem']:,.0f}") #[cite: 3]

    st.markdown("---")
    
    # Gráfico con Plotly
    fig = go.Figure()
    
    # Línea Proyección con Simulación
    fig.add_trace(go.Scatter(x=df_evolucion["Semana"], y=df_evolucion["Proyección"], mode='lines+markers', name='Proyección con Simulación', line=dict(color='blue', width=3))) #[cite: 3]
    
    # Línea Proyección Base (Sin Simulación)
    fig.add_trace(go.Scatter(x=df_evolucion["Semana"], y=df_evolucion["Proyección_Sin_Simulacion"], mode='lines', name='Proyección Sin Simulación', line=dict(color='orange', dash='dash'))) #[cite: 3]
    
    # Líneas estáticas de políticas de inventario
    fig.add_trace(go.Scatter(x=df_evolucion["Semana"], y=[datos_sku["Stock_Critico_7Sem"]]*len(df_evolucion), mode='lines', name='Stock Crítico 7 Sem', line=dict(color='red'))) #[cite: 3]
    fig.add_trace(go.Scatter(x=df_evolucion["Semana"], y=[datos_sku["Stock_Seguridad_14Sem"]]*len(df_evolucion), mode='lines', name='Stock Seguridad 14 Sem', line=dict(color='yellow'))) #[cite: 3]
    fig.add_trace(go.Scatter(x=df_evolucion["Semana"], y=[datos_sku["Stock_Max_20Sem"]]*len(df_evolucion), mode='lines', name='Stock Max. 20 Sem', line=dict(color='green'))) #[cite: 3]

    fig.update_layout(title=f"Evolución de Stock: {sku_analisis}", xaxis_title="Semana", yaxis_title="Kilos", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
    
    # Tabla de detalle inferior
    st.subheader("Detalle Semanal")
    st.dataframe(df_evolucion.T, use_container_width=True) # Transpuesta para parecerse a la imagen de Excel[cite: 3]
