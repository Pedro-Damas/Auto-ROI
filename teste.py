import streamlit as st
import snowflake.connector
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import numpy as np

st.title("AUTO ROI")

# Inputs do usuário
fleet_id_input = st.text_input("Informe o Fleet ID:", value="688c2321-9274-4703-920c-3277e83c39ef")

# Data inicial e final para o período da análise
col1, col2 = st.columns(2)
with col1:
    data_inicial = st.date_input("Data inicial", value=date(2025, 1, 1))
with col2:
    data_final = st.date_input("Data final", value=date(2025, 12, 31))

#Lógica para calculo de diferença de dias e identifcação de dias úteis
diferenca_dias = (data_final - data_inicial).days + 1
dias_uteis = np.busday_count(data_inicial.strftime('%Y-%m-%d'), data_final.strftime('%Y-%m-%d'))
if np.is_busday(data_final):
    dias_uteis += 1

# Campo para número de dias analisados, preenchido por padrão com valores calculados
num_dias_analise = col1.number_input("Número de dias analisados:", min_value=1, max_value=365, value=diferenca_dias, step=1)
num_dias_uteis_analise = col2.number_input("Número de dias úteis analisados:", min_value=1, max_value=365, value=int(dias_uteis), step=1)
num_dias_ano = col1.number_input("Número de dias ano:", min_value=1, max_value=365, value=365, step=1)
num_dias_uteis_ano = col2.number_input("Número de dias úteis ano:", min_value=1, max_value=365, value= 240, step=1)
frota_total = st.number_input("Frota total do cliente:", min_value=1, max_value=365, value= 1, step=1)


#Lógica para consulta dos dados
if st.button("Autenticar e carregar dados"):
    if not fleet_id_input:
        st.warning("⚠️ Por favor, insira um Fleet ID válido.")
    else:
        try:
            # Conecta com autenticação via navegador (SSO Google)
            conn = snowflake.connector.connect(
                account="DL50892-GAA90132",
                user="pedro.damasceno@cobli.co",
                authenticator="externalbrowser",
                role="READONLY_ANALYSIS_ROLE_DPV2",
                warehouse="DATA_PLATFORM_ANALYSIS",
                database="DATA_PLATFORM",
                schema="GOLD"
            )

            st.success("✅ Conexão bem-sucedida!")

            # Constrói e executa a consulta com filtro de data para SAFETY_EVENTS --------------------------------------------------------
            cursor = conn.cursor()
            query1 = f"""
                SELECT *
                FROM DATA_PLATFORM.GOLD.SAFETY_EVENTS
                WHERE fleet_id = '{fleet_id_input}'
                AND EVENT_TIME BETWEEN '{data_inicial}' AND '{data_final}'
            """
            cursor.execute(query1)
            df = cursor.fetch_pandas_all()

            # Tradução dos tipos de evento
            mapeamento_tipos = {
                'distracted_driving': 'Direção Distraída',
                'phone_usage': 'Uso de Celular',
                'hardBreak': 'Frenagem Brusca',
                'smoking': 'Fumando',
                'eyes_closed': 'Olhos Fechados',
                'speedyTurn': 'Curva Agressiva',
                'tailgating': 'Distância Insegura',
                'road_speed_event': 'Excesso de Velocidade',
                'yawn': 'Fadiga'
            }
            df['TYPE'] = df['TYPE'].replace(mapeamento_tipos)

            # Tratamento de datas
            df['EVENT_TIME'] = pd.to_datetime(df['EVENT_TIME'])
            df = df.sort_values('EVENT_TIME').reset_index(drop=True)
            df['Delta_min'] = df['EVENT_TIME'].diff().dt.total_seconds() / 60

            # Criação df de eventos de velocidade-------------------------------------------------------------------------------------------
            df_v = df[df["TYPE"] == 'Excesso de Velocidade'].copy()

            #Velocidade acima do limite
            df_v['velocidade_acima_limite'] = df_v["MEDIAN_SPEED_IN_KMH"] - df_v["SPEED_LIMIT_IN_KMH"]

            #Distância acima do limite
            df_v['distancia_acima_limite_KM'] = (df_v["DURATION_ABOVE_IN_MILLIS"] / (1000 * 60 * 60)) * df_v["MEDIAN_SPEED_IN_KMH"]


            # Constrói e executa a consulta com filtro de data a query para obter PATHS ---------------------------------------------------
            cursor = conn.cursor()
            query2 = f"""
                SELECT *
                FROM DATA_PLATFORM.GOLD.PATHS
                WHERE fleet_id = '{fleet_id_input}'
                AND START_ADDRESS_DATETIME BETWEEN '{data_inicial}' AND '{data_final}'
            """
            cursor.execute(query2)
            df_paths = cursor.fetch_pandas_all()

            df_trips = df_paths[df_paths['TYPE'] == 'trips']
            df_stops = df_paths[df_paths['TYPE'] == 'stops']


            # Armazena em session state ---------------------------------------------------------------------------------------------------
            st.session_state["df_eventos_de_risco"] = df
            st.session_state["df_eventos_de_velocidade"] = df_v
            st.session_state["df_trips"] = df_trips
            st.session_state["df_stops"] = df_stops
            st.session_state["num_dias_analise"] = num_dias_analise
            st.session_state["num_dias_uteis_analise"] = num_dias_uteis_analise
            st.session_state["num_dias_ano"] = num_dias_ano
            st.session_state["num_dias_uteis_ano"] = num_dias_uteis_ano
            st.session_state["frota_total"] = frota_total

            #conclui a consulta
            cursor.close()
            conn.close()




        except Exception as e:
            st.error(f"❌ Falha na conexão ou consulta: {e}")
