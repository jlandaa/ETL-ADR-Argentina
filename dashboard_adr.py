import logging
import os
import tempfile

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from fpdf import FPDF
from sqlalchemy import create_engine, text

import analytics
import ETL_ADR_Argentina as etl

logging.basicConfig(
    filename="etl_process.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 0rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# 1. Configuración de Base de Datos
DB_FILE = "adr_argentina.db"
engine = create_engine(f"sqlite:///{DB_FILE}")


# 2. Lógica de Control de Datos (Auto-ETL) con Logging
def check_and_run_etl() -> None:
    table_exists = False
    if os.path.exists(DB_FILE):
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='market_data'")
            )
            table_exists = result.fetchone() is not None

    if not table_exists:
        st.warning("📊 Generando base de datos financiera por primera vez...")
        logging.info("Iniciando proceso ETL automático: no se detectó la base local.")

        raw = etl.extract()
        if raw is not None:
            transformed = etl.transform(raw)
            es_valido, errores = etl.validar_datos_etl(transformed)
            if not es_valido:
                st.error(f"Error de calidad de datos: {'; '.join(errores)}")
                logging.error("Data Quality Gate fallido: %s", errores)
                st.stop()
            etl.load(transformed)
            st.success("✅ Datos procesados y cargados.")
            logging.info("Proceso ETL finalizado con éxito. Datos cargados en SQLite.")
        else:
            st.error("No se pudieron obtener datos de la API.")
            logging.error("Fallo crítico: no se pudieron extraer datos desde Yahoo Finance.")
            st.stop()
    else:
        logging.info("Verificación de DB exitosa. Inicializando Dashboard.")


check_and_run_etl()


# 3. Función de carga protegida
@st.cache_data(ttl=3600)
def load_data() -> pd.DataFrame:
    query = "SELECT * FROM market_data"
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


@st.cache_data
def convert_df(df_in: pd.DataFrame) -> bytes:
    return df_in.to_csv(index=False).encode("utf-8")


@st.cache_data
def generar_tear_sheet(
    tickers_list: list[str],
    capital: float,
    rentabilidad: float,
    df_plot: pd.DataFrame,
    moneda: str,
) -> bytes:
    pdf = FPDF()
    pdf.add_page()

    pdf.set_font("helvetica", "B", 16)
    pdf.cell(
        0,
        10,
        "Tear Sheet - Portafolio ADRs Argentinos",
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(5)

    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 8, f"Activos analizados: {', '.join(tickers_list)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Moneda de análisis: {moneda}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Capital Inicial Simulado: ${capital:,.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Rentabilidad Acumulada: {rentabilidad:.2f}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    col_capital = f"Capital ({moneda})"
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df_plot["Date"], df_plot[col_capital], color="#00b4d8", linewidth=2)
    ax.fill_between(df_plot["Date"], df_plot[col_capital], color="#00b4d8", alpha=0.3)
    ax.set_title(f"Evolución del Capital en {moneda}", fontsize=10, loc="left")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
        tmp_path = tmpfile.name

    try:
        fig.savefig(tmp_path, format="png", bbox_inches="tight")
        pdf.image(tmp_path, x=15, w=180)
    finally:
        plt.close(fig)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return bytes(pdf.output())


# --- INTERFAZ DEL DASHBOARD ---
st.title("📊 Análisis de ADRs Argentinos")

df = load_data()
df["Date"] = pd.to_datetime(df["Date"])

# --- CONTROLES EN EL SIDEBAR ---
st.sidebar.header("⚙️ Filtros del Dashboard")
st.sidebar.subheader("📅 Período de Análisis")

time_filter = st.sidebar.radio(
    "Selecciona el rango de tiempo:",
    options=["1 Mes", "3 Meses", "6 Meses", "YTD", "1 Año", "Máximo"],
    index=4,
)

df = analytics.filtrar_por_periodo(df, time_filter)

st.sidebar.markdown("---")
st.sidebar.subheader("🏢 Activos")

opciones_tickers = df["Ticker"].unique().tolist()
valores_deseados = ["GGAL", "YPF"]
defaults_validos = [ticker for ticker in valores_deseados if ticker in opciones_tickers]

tickers = st.sidebar.multiselect(
    "Selecciona los ADRs a comparar:",
    options=opciones_tickers,
    default=defaults_validos,
)

if tickers:
    df_subset = df[df["Ticker"].isin(tickers)].copy()

    st.sidebar.markdown("---")
    st.sidebar.subheader("🇦🇷 Contexto Macroeconómico")
    show_in_ars = st.sidebar.toggle("💸 Ver precios en Pesos (Efecto CCL)", value=False)

    df_filtered, currency = analytics.aplicar_moneda_y_retornos(df_subset, show_in_ars)

    # --- EXPORTACIÓN CSV ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("📥 Exportar Datos")
    st.sidebar.download_button(
        label="Descargar datos en CSV",
        data=convert_df(df_filtered),
        file_name="adrs_argentinos_filtrados.csv",
        mime="text/csv",
    )

    # --- SISTEMA DE ALERTAS (WEBHOOK) ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔔 Alertas de Volatilidad")

    umbral_volatilidad = st.sidebar.number_input(
        "Umbral de Alerta Diaria (%)", min_value=1.0, value=5.0, step=0.5
    )
    webhook_url = st.sidebar.text_input(
        "URL del Webhook (Discord/Slack)",
        type="password",
        help="Pega aquí la URL de integración de tu canal.",
    )

    if st.sidebar.button("🚀 Simular y Enviar Alertas"):
        if not webhook_url:
            st.sidebar.error("⚠️ Ingresa una URL de Webhook válida.")
        else:
            alertas = analytics.construir_alertas_volatilidad(
                df_filtered, umbral_volatilidad, currency
            )
            alertas_enviadas = 0
            for alerta in alertas:
                try:
                    response = requests.post(webhook_url, json=alerta["payload"], timeout=10)
                    if response.status_code in (200, 204):
                        alertas_enviadas += 1
                    else:
                        st.sidebar.error(
                            f"Fallo al enviar {alerta['ticker']}. Código HTTP: "
                            f"{response.status_code}"
                        )
                except requests.exceptions.RequestException as exc:
                    st.sidebar.error(f"Error de conexión: {exc}")

            if alertas_enviadas > 0:
                st.sidebar.success(f"✅ {alertas_enviadas} alerta(s) disparada(s) exitosamente.")
            else:
                st.sidebar.info(
                    "Tranquilidad en el mercado hoy. Ningún activo superó el umbral de estrés."
                )

    # --- MÉTRICAS DE RENDIMIENTO ---
    st.markdown("### 📈 Métricas de Rendimiento")
    cols = st.columns(len(tickers))

    for i, ticker in enumerate(tickers):
        t_data = df_filtered[df_filtered["Ticker"] == ticker].sort_values("Date")
        metricas = analytics.calcular_metricas_activo(
            t_data["Price_Active"], t_data["Active_Return"]
        )
        sharpe = metricas["sharpe_ratio"]
        sharpe_str = f"{sharpe:.4f}" if abs(sharpe) < 0.01 and sharpe != 0 else f"{sharpe:.2f}"
        total_ret = metricas["total_return_pct"]

        with cols[i]:
            st.metric(
                label=f"{ticker} (Sharpe: {sharpe_str})",
                value=f"{total_ret:.1f}%",
                delta="- Retorno Total" if total_ret < 0 else "Retorno Total",
            )
            risk_metrics_html = f"""
            <div style="font-size: 0.75em; color: #808495; line-height: 1.4;">
                <span style="white-space: nowrap;">
                    🔻 VaR (95%): {metricas["var_95_pct"]:.2f}%
                </span><br>
                <span style="white-space: nowrap;">
                    📉 Max Drawdown: {metricas["max_drawdown_pct"]:.2f}%
                </span>
            </div>
            """
            st.markdown(risk_metrics_html, unsafe_allow_html=True)

    # --- GRÁFICO DE PRECIOS ---
    fig_price = px.line(
        df_filtered,
        x="Date",
        y="Price_Active",
        color="Ticker",
        title=f"Evolución de Precios en {currency}",
    )
    st.plotly_chart(fig_price, use_container_width=True)

    # --- DISTRIBUCIÓN DE RETORNOS ---
    min_val = df_filtered["Active_Return"].quantile(0.01)
    max_val = df_filtered["Active_Return"].quantile(0.99)

    fig_ret = px.histogram(
        df_filtered,
        x="Active_Return",
        color="Ticker",
        marginal="box",
        title=f"Distribución de Retornos Diarios en {currency} (Zoom 98%)",
        nbins=100,
        range_x=[min_val, max_val],
    )
    fig_ret.update_layout(barmode="overlay")
    fig_ret.update_traces(opacity=0.75)
    st.plotly_chart(fig_ret, use_container_width=True)

    # --- MATRIZ DE CORRELACIÓN ---
    st.markdown("---")
    st.subheader(f"🔗 Matriz de Correlación de Retornos ({currency})")
    df_pivot = df_filtered.pivot(index="Date", columns="Ticker", values="Active_Return")
    corr_matrix = df_pivot.corr()
    fig_corr = px.imshow(
        corr_matrix,
        text_auto=".2f",
        aspect="auto",
        color_continuous_scale="RdBu_r",
        zmin=-1,
        zmax=1,
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    # --- OPTIMIZADOR DE MARKOWITZ ---
    st.markdown("---")
    st.subheader("🧠 Optimizador de Portafolios (Markowitz)")

    if len(tickers) > 1:
        current_rf = float(df_filtered["Risk_Free_Rate"].dropna().iloc[-1])
        risk_free_rate = current_rf / 100
        st.caption(
            f"🏦 Tasa Libre de Riesgo utilizada (US Treasury 10Y actual): **{current_rf:.2f}%**"
        )

        opt = analytics.optimizar_portafolio_markowitz(
            returns_pivot=df_pivot,
            risk_free_rate=risk_free_rate,
            num_portfolios=5000,
        )
        results = opt["results"]

        fig_ef = px.scatter(
            x=results[1, :],
            y=results[0, :],
            color=results[2, :],
            labels={
                "x": "Riesgo (Volatilidad)",
                "y": "Retorno Esperado",
                "color": "Sharpe Ratio",
            },
            title="Frontera Eficiente (5000 Simulaciones)",
            color_continuous_scale="Viridis",
        )
        fig_ef.add_scatter(
            x=[opt["opt_vol"]],
            y=[opt["opt_ret"]],
            mode="markers",
            marker={"color": "red", "size": 14, "symbol": "star"},
            name="Máximo Sharpe",
            hoverinfo="skip",
        )
        st.plotly_chart(fig_ef, use_container_width=True)

        st.write("**Distribución Sugerida de Capital (Para Maximizar el Ratio de Sharpe):**")
        weights_df = pd.DataFrame(
            {
                "Activo": opt["tickers"],
                "Asignación Sugerida": [f"{w * 100:.1f}%" for w in opt["opt_weights"]],
            }
        )
        st.dataframe(weights_df, hide_index=True)
    else:
        st.info(
            "💡 Selecciona al menos dos activos en el menú lateral "
            "para habilitar el simulador de portafolios."
        )

    # --- BRECHA CAMBIARIA ---
    st.markdown("---")
    st.subheader("🔥 Riesgo Macro: Evolución de la Brecha Cambiaria")
    st.write(
        "La brecha entre el Dólar CCL y el Dólar Oficial funciona como un termómetro directo "
        "del riesgo y estrés financiero en Argentina."
    )

    df_macro = (
        df_filtered[["Date", "Brecha_Cambiaria", "Dolar_CCL", "Dolar_Oficial"]]
        .drop_duplicates()
        .dropna()
    )

    if not df_macro.empty:
        fig_brecha = px.area(
            df_macro,
            x="Date",
            y="Brecha_Cambiaria",
            title="Brecha Cambiaria (CCL vs Oficial)",
            labels={"Brecha_Cambiaria": "Brecha (%)"},
            color_discrete_sequence=["#ff4b4b"],
        )
        fig_brecha.update_traces(fillcolor="rgba(255, 75, 75, 0.2)")
        st.plotly_chart(fig_brecha, use_container_width=True)

        brecha_actual = float(df_macro["Brecha_Cambiaria"].iloc[-1])
        st.metric(label="Brecha Cambiaria Actual", value=f"{brecha_actual:.1f}%")

    # --- ANÁLISIS WHAT-IF ---
    st.markdown("---")
    st.subheader("🎛️ Análisis 'What-If': Construye tu propio Portafolio")
    st.write(
        "¿Qué hubiera pasado si invertías tu propio capital con una distribución personalizada?"
    )

    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown("#### 1. Configura tu Inversión")
        initial_capital = st.number_input(
            "Capital Inicial (USD):",
            min_value=100.0,
            value=10000.0,
            step=1000.0,
        )

        st.markdown("**Asigna el peso a cada activo:**")
        custom_weights: dict[str, float] = {}
        for ticker in tickers:
            custom_weights[ticker] = st.slider(f"{ticker} (%)", 0, 100, int(100 / len(tickers)))

        total_weight = sum(custom_weights.values())
        if total_weight == 0:
            st.error("⚠️ La suma de los pesos no puede ser 0%.")
            valid_portfolio = False
        else:
            if total_weight != 100:
                st.warning(f"Suma: {total_weight}%. Se normalizará matemáticamente al 100%.")
            valid_portfolio = True

    with col2:
        st.markdown("#### 2. Evolución de tu Capital")
        if valid_portfolio:
            df_portfolio, final_value, total_ret_whatif = analytics.simular_portafolio_whatif(
                returns_pivot=df_pivot,
                weights_dict=custom_weights,
                initial_capital=initial_capital,
                currency=currency,
            )

            col_capital = f"Capital ({currency})"
            fig_whatif = px.line(
                df_portfolio,
                x="Date",
                y=col_capital,
                title=f"Proyección de un portafolio de ${initial_capital:,.2f} {currency}",
            )
            fig_whatif.update_traces(fill="tozeroy", line_color="#00b4d8")
            st.plotly_chart(fig_whatif, use_container_width=True)

            st.metric(
                label=f"Valor Final del Portafolio ({currency})",
                value=f"${final_value:,.2f}",
                delta=f"{total_ret_whatif:.2f}% de Rentabilidad Acumulada",
            )

            pdf_bytes = generar_tear_sheet(
                tickers_list=tickers,
                capital=initial_capital,
                rentabilidad=total_ret_whatif,
                df_plot=df_portfolio,
                moneda=currency,
            )

            with col1:
                st.markdown("---")
                st.markdown("**📄 Exportar Simulación**")
                st.download_button(
                    label="📥 Descargar Reporte (PDF)",
                    data=pdf_bytes,
                    file_name="Reporte_WhatIf_ADRs.pdf",
                    mime="application/pdf",
                )
else:
    st.warning("Selecciona al menos un ticker para visualizar los datos.")
