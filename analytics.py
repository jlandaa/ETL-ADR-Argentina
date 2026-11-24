import numpy as np
import pandas as pd


def filtrar_por_periodo(df: pd.DataFrame, time_filter: str) -> pd.DataFrame:
    """Filtra el DataFrame por ventana temporal respecto a la última fecha disponible."""
    if df.empty:
        return df.copy()

    max_date = df["Date"].max()
    if time_filter == "1 Mes":
        start_date = max_date - pd.DateOffset(months=1)
    elif time_filter == "3 Meses":
        start_date = max_date - pd.DateOffset(months=3)
    elif time_filter == "6 Meses":
        start_date = max_date - pd.DateOffset(months=6)
    elif time_filter == "YTD":
        start_date = pd.to_datetime(f"{max_date.year}-01-01")
    elif time_filter == "1 Año":
        start_date = max_date - pd.DateOffset(years=1)
    else:
        start_date = df["Date"].min()

    return df[df["Date"] >= start_date].copy()


def aplicar_moneda_y_retornos(df: pd.DataFrame, show_in_ars: bool) -> tuple[pd.DataFrame, str]:
    """Convierte precios a ARS (vía Dólar CCL) o USD y recalcula retornos diarios."""
    df_out = df.copy()
    if show_in_ars:
        df_out["Price_Active"] = df_out["Price_USD"] * df_out["Dolar_CCL"]
        currency = "ARS (Pesos)"
    else:
        df_out["Price_Active"] = df_out["Price_USD"]
        currency = "USD"

    df_out = df_out.sort_values(by=["Ticker", "Date"])
    df_out = df_out.drop_duplicates(subset=["Ticker", "Date"], keep="last")
    df_out["Active_Return"] = df_out.groupby("Ticker")["Price_Active"].pct_change()
    return df_out, currency


def calcular_metricas_activo(prices: pd.Series, returns: pd.Series) -> dict[str, float]:
    """Calcula retorno total, Ratio de Sharpe anualizado, VaR 95% y Max Drawdown."""
    clean_returns = returns.dropna()
    clean_prices = prices.dropna()

    if clean_returns.empty or clean_prices.empty:
        return {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "var_95_pct": 0.0,
            "max_drawdown_pct": 0.0,
        }

    std_dev = float(clean_returns.std())
    sharpe_ratio = float((clean_returns.mean() / std_dev) * (252**0.5)) if std_dev > 0 else 0.0

    first_price = float(clean_prices.iloc[0])
    total_return_pct = (
        float((clean_prices.iloc[-1] / first_price - 1) * 100) if first_price > 0 else 0.0
    )

    var_95_pct = float(clean_returns.quantile(0.05) * 100)

    cumulative_returns = (1 + clean_returns).cumprod()
    peak = cumulative_returns.cummax()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown_pct = float(drawdown.min() * 100)

    return {
        "total_return_pct": total_return_pct,
        "sharpe_ratio": sharpe_ratio,
        "var_95_pct": var_95_pct,
        "max_drawdown_pct": max_drawdown_pct,
    }


def optimizar_portafolio_markowitz(
    returns_pivot: pd.DataFrame,
    risk_free_rate: float,
    num_portfolios: int = 5000,
    seed: int | None = None,
) -> dict:
    """Ejecuta Monte Carlo y devuelve pesos alineados al orden real de columnas del pivot."""
    clean_pivot = returns_pivot.dropna()
    if clean_pivot.empty or clean_pivot.shape[1] < 2:
        raise ValueError("Se necesitan al menos dos activos con retornos válidos.")

    tickers_ordenados = list(clean_pivot.columns)
    mean_returns = clean_pivot.mean() * 252
    cov_matrix = clean_pivot.cov() * 252

    rng = np.random.default_rng(seed)
    results = np.zeros((3, num_portfolios))
    weights_record: list[np.ndarray] = []

    for i in range(num_portfolios):
        weights = rng.random(len(tickers_ordenados))
        weights /= np.sum(weights)
        weights_record.append(weights)

        portfolio_return = float(np.sum(mean_returns * weights))
        portfolio_std_dev = float(np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights))))

        results[0, i] = portfolio_return
        results[1, i] = portfolio_std_dev
        results[2, i] = (
            (portfolio_return - risk_free_rate) / portfolio_std_dev
            if portfolio_std_dev > 0
            else 0.0
        )

    max_sharpe_idx = int(np.argmax(results[2]))
    return {
        "results": results,
        "opt_ret": float(results[0, max_sharpe_idx]),
        "opt_vol": float(results[1, max_sharpe_idx]),
        "opt_weights": weights_record[max_sharpe_idx],
        "tickers": tickers_ordenados,
    }


def simular_portafolio_whatif(
    returns_pivot: pd.DataFrame,
    weights_dict: dict[str, float],
    initial_capital: float,
    currency: str,
) -> tuple[pd.DataFrame, float, float]:
    """Proyecta la curva de capital normalizando los pesos personalizados al 100%."""
    total_weight = sum(weights_dict.values())
    if total_weight <= 0:
        raise ValueError("La suma de los pesos debe ser mayor a 0.")

    tickers = list(weights_dict.keys())
    normalized_weights = np.array([weights_dict[t] / total_weight for t in tickers])

    clean_pivot = returns_pivot[tickers].dropna()
    if clean_pivot.empty:
        raise ValueError("No hay fechas con datos completos para simular el portafolio.")

    port_daily_returns = clean_pivot.dot(normalized_weights)
    cumulative_returns = (1 + port_daily_returns).cumprod()
    portfolio_value_series = initial_capital * cumulative_returns

    col_capital = f"Capital ({currency})"
    df_portfolio = pd.DataFrame({col_capital: portfolio_value_series}).reset_index()

    final_value = float(portfolio_value_series.iloc[-1])
    total_return_pct = float((final_value / initial_capital - 1) * 100)
    return df_portfolio, final_value, total_return_pct


def construir_alertas_volatilidad(
    df_filtered: pd.DataFrame,
    umbral_volatilidad: float,
    currency: str,
) -> list[dict]:
    """Genera payloads compatibles con Discord y Slack para variaciones sobre el umbral."""
    if df_filtered.empty:
        return []

    last_date = df_filtered["Date"].max()
    latest_data = df_filtered[df_filtered["Date"] == last_date]
    alertas: list[dict] = []

    for _, row in latest_data.iterrows():
        if pd.isna(row["Active_Return"]):
            continue

        retorno_diario = float(row["Active_Return"] * 100)
        if abs(retorno_diario) >= umbral_volatilidad:
            icono = "🚀" if retorno_diario > 0 else "🩸"
            mensaje = (
                f"⚠️ **ALERTA DE MERCADO** ⚠️\n"
                f"**Activo:** {row['Ticker']}\n"
                f"**Fecha:** {last_date.strftime('%Y-%m-%d')}\n"
                f"**Variación:** {icono} {retorno_diario:.2f}%\n"
                f"**Precio (Cierre Ajustado):** ${row['Price_Active']:.2f} {currency}"
            )
            alertas.append(
                {
                    "ticker": row["Ticker"],
                    "retorno_diario": retorno_diario,
                    "payload": {"content": mensaje, "text": mensaje},
                }
            )

    return alertas
