import streamlit as st
import snowflake.connector
import pandas as pd
import plotly.graph_objects as go
import numpy as np

def obter_autonomia(porte):
    if porte == 'small' or porte == 'medium':
        return consumo_leves
    elif porte == 'large':
        return consumo_pesados
    else:
        return 1  # valor padrão para evitar divisão por zero ou erro

st.title("Eventos de Risco")
st.divider()  # Linha horizontal separadora

intervalo_alertas = st.sidebar.slider('Diferença em minutos entre eventos (Maior ou igual):', min_value=0, max_value=60, value=0, step=1)
consumo_leves = st.sidebar.number_input("Consumo Veículos Leves (KM/L):", min_value=1, max_value=365, value= 10, step=1)
consumo_pesados = st.sidebar.number_input("Consumo Veículos Pesados (KM/L):", min_value=1, max_value=365, value= 5, step=1)
preco_gasolina = st.sidebar.number_input("Preço Gasolina:", value=6.0, step=0.1, format="%.2f")
preco_disel = st.sidebar.number_input("Preço Disel:", value=6.0, step=0.1, format="%.2f")


if "df_eventos_de_risco" in st.session_state:
    df = st.session_state["df_eventos_de_risco"]
    df_v = st.session_state["df_eventos_de_velocidade"]
    df_trips = st.session_state["df_trips"]
    df_stops = st.session_state["df_stops"]

    veículos_analisados = st.sidebar.number_input("Veículos analisados:", min_value=1, max_value=365, value= df['VEHICLE_LICENSE_PLATE'].nunique(), step=1)

    # Lógica para os menus suspensos de seleção de porte dos veículos ------------------------------------
    referencia_porte = (df_v[['VEHICLE_LICENSE_PLATE', 'VEHICLE_SIZE']]
                        .sort_values(by='VEHICLE_SIZE', na_position='last')  # garante que valores não-nulos venham primeiro
                        .drop_duplicates(subset='VEHICLE_LICENSE_PLATE', keep='first'))  # mantém o primeiro valor com SIZE válido

    opcoes = ['small', 'medium', 'large', 'Preecher']
    porte_usuario = {}
    porte_selecionado = {}

    with st.sidebar.expander("Porte dos veículos", expanded=False):
        for index, row in referencia_porte.iterrows():
            placa = row ['VEHICLE_LICENSE_PLATE']
            porte_padrao = row['VEHICLE_SIZE']

            mapa_porte = {'small': 0, 'medium': 1, 'large': 2}

            valor_numerico = mapa_porte.get(porte_padrao, 3)  # 0 se o valor não estiver no dicionário

            selecao = st.selectbox(f"Porte para {placa}",options=opcoes, index=valor_numerico, key=placa)  # Garante que cada selectbox tenha uma chave única

            porte_selecionado[placa] = selecao

    # Converte o dicionário para DataFrame
    df_portes_atualizados = pd.DataFrame.from_dict(porte_selecionado, orient='index').reset_index()
    df_portes_atualizados.columns = ['VEHICLE_LICENSE_PLATE', 'VEHICLE_SIZE']


    #Filtro para normalização de eventos de segurança muito próximos -----------------------------------
    df = df[df['Delta_min'] >= intervalo_alertas]

    # Gráfico em cascata se a coluna TYPE existir e houver dados----------------------------------------
    if not df.empty and 'TYPE' in df.columns:
        event_counts = df['TYPE'].value_counts().sort_values(ascending=False)
        x = event_counts.index.tolist()
        y = event_counts.values.tolist()

        # Adiciona barra de total
        x.append("Total")
        y.append(sum(y))
        measure = ["relative"] * (len(x) - 1) + ["total"]

        # Cria gráfico de cascata
        fig = go.Figure(go.Waterfall(
            name="Eventos",
            orientation="v",
            measure=measure,
            x=x,
            y=y,
            text=[f"{v}" for v in y],
            textposition="outside",
            connector={"line": {"color": "orange"}}
        ))
        #Atualiza Layout grafico cascata
        fig.update_layout(
            title="Gráfico em Cascata – Tipos de Eventos de Risco",
            xaxis_title="Tipo de Evento",
            waterfallgap=0.3,
            yaxis=dict(
                showticklabels=False,  # remove os números do eixo Y
                showgrid=False,        # remove as linhas de grade
                zeroline=False         # remove a linha do zero
            )
        )

        st.plotly_chart(fig, use_container_width=True)

        #Calculo percentual de tempo dirigido fora do limite------------------------------------------------------
        tempo_total_dirigido = df_trips.groupby("VEHICLE_LICENSE_PLATE")["DURATION_IN_MILLISECONDS"].sum()
        df_resultado_dentro = tempo_total_dirigido.reset_index()

        tempo_acima_limite = df_v.groupby("LICENSE_PLATE")["DURATION_ABOVE_IN_MILLIS"].sum()
        df_resultado_fora = tempo_acima_limite.reset_index()
        df_resultado_fora= df_resultado_fora.rename(columns={'LICENSE_PLATE': 'VEHICLE_LICENSE_PLATE'})

        # Unir os dois DataFrames pela placa
        df_percentual_fora_limite = pd.merge(df_resultado_dentro, df_resultado_fora, on='VEHICLE_LICENSE_PLATE', how='inner')
        df_percentual_fora_limite.columns = ['VEHICLE_LICENSE_PLATE', 'TEMPO_TOTAL', 'TEMPO_FORA_DO_LIMITE']

        # Agora calcula os percentuais
        df_percentual_fora_limite['% FORA DO LIMITE'] = (df_percentual_fora_limite['TEMPO_FORA_DO_LIMITE'] / df_percentual_fora_limite['TEMPO_TOTAL']) * 100
        df_percentual_fora_limite['% FORA DO LIMITE'] = df_percentual_fora_limite['% FORA DO LIMITE'].round(2)
        df_percentual_fora_limite['% DENTRO DO LIMITE'] = 100 - df_percentual_fora_limite['% FORA DO LIMITE']

        #Grafico percentual de tempo acima do limite de velocidade---------------------------------------------------------
        fig = go.Figure(data=[
            # Barra para % DENTRO (negativa para empilhar para baixo)
            go.Bar(
                name='% Tempo com Velocidade Dentro do Limite',
                x=df_percentual_fora_limite['VEHICLE_LICENSE_PLATE'],
                y=-df_percentual_fora_limite['% DENTRO DO LIMITE'],
                text=[f"-{v:.1f}%" for v in df_percentual_fora_limite['% DENTRO DO LIMITE']],
                textposition='outside',
                marker_color='rgb(58, 115, 172)'
            ),
            # Barra para % fora (positiva para empilhar para cima)
            go.Bar(
                name='% Tempo com Velocidade Fora do Limite',
                x=df_percentual_fora_limite['VEHICLE_LICENSE_PLATE'],
                y=df_percentual_fora_limite['% FORA DO LIMITE'],
                text=[f"{v:.1f}%" for v in df_percentual_fora_limite['% FORA DO LIMITE']],
                textposition='outside',
                marker_color='rgb(214, 100, 83)')])

        fig.update_layout(
                barmode='relative',
                title='Distribuição de Tempo em Velocidade Dentro e Fora do Limite por Veículo',
                yaxis=dict(title='% de Tempo', ticksuffix='%'),
                xaxis=dict(title='Placa do Veículo'),
                height=500,
                

                # Coloca a legenda no topo, centralizada
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=1.1,
                    xanchor="center",
                    x=0.5),
            )


        st.plotly_chart(fig)

        #adiciona as informações de porte ao df de velocidade-------------------------------------------------------------
        dicionario_portes = dict(zip(df_portes_atualizados['VEHICLE_LICENSE_PLATE'], df_portes_atualizados['VEHICLE_SIZE']))
        df_v['VEHICLE_SIZE'] = df_v['VEHICLE_LICENSE_PLATE'].map(dicionario_portes)

        #Calculo de gasto de gasolina padrão
        df_v['Gasto_gasolina_padrão_L'] = df_v.apply(
            lambda row: row['distancia_acima_limite_KM'] / obter_autonomia(row['VEHICLE_SIZE']),
            axis=1
        )

        #Calculo de gasto de gasolina com fator de penalidade de 7% a mais de gasto a cada 8km/h a mais que 80km/h
        df_v['Gasto_gasolina_real_L'] = df_v.apply(
            lambda row: (((row['MEDIAN_SPEED_IN_KMH'] - 80) / 8) * 0.07 + 1) * row['Gasto_gasolina_padrão_L']
            if row['MEDIAN_SPEED_IN_KMH'] > 80 
            else row['Gasto_gasolina_padrão_L'],
            axis=1
        )

        st.markdown("Projeção de Economia de Combustível - Por Excesso de Velocidade")
        st.divider()  # Linha horizontal separadora

        percentual_reducao_combustivel_excesso_velocidade = st.slider('Redução % de combustivel dos excessos de velocidade:', min_value=0, max_value=100, value=50, step=5)

        #Criação de tabela para análise de Projeção de Economia de Combustível - Por Excesso de Velocidade-----------------
        pre_df = [['Gasto de Combustível Padrão durante Eventos de Velocidade (L)', 0.0],
                    ['Gasto de Combustível Real (L)', 0.0], 
                    ['Combustível extra consumido (L)', 0.0],
                    ['Combustível extra consumido no ano e total frota (L)', 0.0],
                    ['Preço Combustível', 0.0],
                    ['Gasto Extra com Combustível', 0.0] ,
                    [f'Redução de {percentual_reducao_combustivel_excesso_velocidade}%', 0.0]]
        economia_combustivel_excesso_velociddade = pd.DataFrame(pre_df, columns=['Descritivo', 'Valor']).set_index('Descritivo')

        #Carrega dados da página principal para análise
        num_dias_analise = st.session_state["num_dias_analise"]
        num_dias_ano = st.session_state["num_dias_ano"]
        frota_total = st.session_state["frota_total"]

        economia_combustivel_excesso_velociddade.loc['Gasto de Combustível Padrão durante Eventos de Velocidade (L)', 'Valor'] = df_v['Gasto_gasolina_padrão_L'].sum().round(2)
        economia_combustivel_excesso_velociddade.loc['Gasto de Combustível Real (L)', 'Valor'] = df_v['Gasto_gasolina_real_L'].sum().round(2)
        economia_combustivel_excesso_velociddade.loc['Combustível extra consumido (L)', 'Valor'] = df_v['Gasto_gasolina_real_L'].sum().round(2) - df_v['Gasto_gasolina_padrão_L'].sum().round(2)
        economia_combustivel_excesso_velociddade.loc['Combustível extra consumido no ano e total frota (L)', 'Valor'] = (economia_combustivel_excesso_velociddade.loc['Combustível extra consumido (L)', 'Valor']/veículos_analisados)/num_dias_analise
        economia_combustivel_excesso_velociddade.loc['Combustível extra consumido no ano e total frota (L)', 'Valor'] = economia_combustivel_excesso_velociddade.loc['Combustível extra consumido no ano e total frota (L)', 'Valor'] * num_dias_ano * frota_total
        economia_combustivel_excesso_velociddade.loc['Preço Combustível', 'Valor'] = preco_gasolina
        economia_combustivel_excesso_velociddade.loc['Gasto Extra com Combustível', 'Valor'] = economia_combustivel_excesso_velociddade.loc['Combustível extra consumido no ano e total frota (L)', 'Valor'] * preco_gasolina
        economia_combustivel_excesso_velociddade.loc[f'Redução de {percentual_reducao_combustivel_excesso_velocidade}%'] = economia_combustivel_excesso_velociddade.loc['Gasto Extra com Combustível', 'Valor'] * (1 - percentual_reducao_combustivel_excesso_velocidade/100)

        economia_combustivel_excesso_velociddade

        df_v



else:
    st.warning("⚠️ Os dados ainda não foram carregados.")