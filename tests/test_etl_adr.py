from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

import analytics
import ETL_ADR_Argentina as etl


def _crear_raw_mock() -> dict[str, pd.DataFrame]:
    fechas = pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "GGAL": [50.0, 52.0, 55.0, 50.0],
            "GGAL.BA": [6000.0, np.nan, 6600.0, 6250.0],
            "YPF": [30.0, 31.5, 30.0, 33.0],
            "ARS=X": [1000.0, 1000.0, np.nan, 1020.0],
            "^TNX": [4.2, 4.3, 4.3, np.nan],
        },
        index=fechas,
    )
    return {"yf": df}


def test_transform_calcula_ccl_brecha_feriados_y_long_format() -> None:
    df_out = etl.transform(_crear_raw_mock())

    # GGAL.BA debe quedar descartada y solo deben quedar los ADRs (GGAL, YPF)
    assert set(df_out["Ticker"].unique()) == {"GGAL", "YPF"}
    assert df_out["Date"].dt.tz is None
    assert df_out["Dolar_CCL"].isna().sum() == 0
    assert df_out["Dolar_Oficial"].isna().sum() == 0
    assert df_out["Risk_Free_Rate"].isna().sum() == 0

    # Día 1: CCL = (6000 / 50) * 10 = 1200; Brecha = ((1200 / 1000) - 1) * 100 = 20%
    fila_dia_1 = df_out[(df_out["Ticker"] == "GGAL") & (df_out["Date"] == "2026-01-01")].iloc[0]
    assert fila_dia_1["Dolar_CCL"] == pytest.approx(1200.0)
    assert fila_dia_1["Brecha_Cambiaria"] == pytest.approx(20.0)


def test_transform_falla_si_faltan_columnas_macro() -> None:
    df_incompleto = pd.DataFrame({"GGAL": [50.0]}, index=pd.date_range("2026-01-01", periods=1))
    with pytest.raises(ValueError, match="Faltan columnas requeridas"):
        etl.transform({"yf": df_incompleto})


def test_data_quality_gate_etl() -> None:
    df_ok = etl.transform(_crear_raw_mock())
    es_valido, errores = etl.validar_datos_etl(df_ok)
    assert es_valido is True
    assert errores == []

    es_valido_vacio, errores_vacio = etl.validar_datos_etl(pd.DataFrame())
    assert es_valido_vacio is False
    assert len(errores_vacio) == 1


def test_load_sqlite_en_directorio_temporal(tmp_path: Path) -> None:
    df_ok = etl.transform(_crear_raw_mock())
    db_url = f"sqlite:///{tmp_path / 'test_adr.db'}"

    etl.load(df_ok, db_url=db_url)

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM market_data")).scalar()
        assert count == len(df_ok)
    finally:
        engine.dispose()


def test_conversion_moneda_ccl_y_metricas_riesgo() -> None:
    df_ok = etl.transform(_crear_raw_mock())
    df_ars, moneda = analytics.aplicar_moneda_y_retornos(df_ok, show_in_ars=True)
    assert moneda == "ARS (Pesos)"

    ggal_ars = df_ars[df_ars["Ticker"] == "GGAL"].sort_values("Date")
    assert ggal_ars["Price_Active"].iloc[0] == pytest.approx(50.0 * 1200.0)

    metricas = analytics.calcular_metricas_activo(
        ggal_ars["Price_Active"], ggal_ars["Active_Return"]
    )
    assert metricas["max_drawdown_pct"] <= 0.0
    assert np.isfinite(metricas["sharpe_ratio"])

    # Caso borde: precio plano (std == 0) no debe producir inf ni NaN
    precios_planos = pd.Series([100.0, 100.0, 100.0])
    retornos_planos = precios_planos.pct_change()
    metricas_planas = analytics.calcular_metricas_activo(precios_planos, retornos_planos)
    assert metricas_planas["sharpe_ratio"] == 0.0


def test_markowitz_mantiene_orden_de_tickers_y_suma_uno() -> None:
    fechas = pd.date_range("2026-01-01", periods=6, freq="D")
    returns_pivot = pd.DataFrame(
        {
            "YPF": [0.02, -0.01, 0.03, 0.01, -0.02, 0.04],
            "GGAL": [0.01, 0.02, -0.01, 0.02, 0.01, 0.01],
        },
        index=fechas,
    )

    opt = analytics.optimizar_portafolio_markowitz(
        returns_pivot, risk_free_rate=0.04, num_portfolios=300, seed=42
    )
    assert opt["tickers"] == ["YPF", "GGAL"]
    assert float(np.sum(opt["opt_weights"])) == pytest.approx(1.0)
    assert opt["opt_vol"] > 0


def test_simulador_whatif_normaliza_pesos_y_valida_cero() -> None:
    fechas = pd.date_range("2026-01-01", periods=3, freq="D")
    returns_pivot = pd.DataFrame(
        {"GGAL": [0.10, 0.10, 0.0], "YPF": [0.10, 0.10, 0.0]},
        index=fechas,
    )
    returns_pivot.index.name = "Date"

    # Pesos 30/30 deben normalizarse a 50%/50%
    df_port, final_val, ret_pct = analytics.simular_portafolio_whatif(
        returns_pivot, {"GGAL": 30, "YPF": 30}, initial_capital=1000.0, currency="USD"
    )
    assert "Capital (USD)" in df_port.columns
    assert final_val == pytest.approx(1210.0)
    assert ret_pct == pytest.approx(21.0)

    with pytest.raises(ValueError, match="mayor a 0"):
        analytics.simular_portafolio_whatif(
            returns_pivot, {"GGAL": 0, "YPF": 0}, initial_capital=1000.0, currency="USD"
        )


def test_construir_alertas_volatilidad() -> None:
    df_ok = etl.transform(_crear_raw_mock())
    df_usd, currency = analytics.aplicar_moneda_y_retornos(df_ok, show_in_ars=False)

    # En la última fecha: GGAL cae -9.09% y YPF sube +10.00% -> ambos superan 5%
    alertas = analytics.construir_alertas_volatilidad(df_usd, umbral_volatilidad=5.0, currency=currency)
    assert len(alertas) == 2
    assert {a["ticker"] for a in alertas} == {"GGAL", "YPF"}
    assert "content" in alertas[0]["payload"]
    assert "text" in alertas[0]["payload"]
