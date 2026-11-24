import logging
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

DEFAULT_DB_URL = "sqlite:///adr_argentina.db"
TICKERS_ETL = ["GGAL", "GGAL.BA", "YPF", "BMA", "PAM", "CEPU", "ARS=X", "^TNX"]
REQUIRED_RAW_COLUMNS = {"GGAL", "GGAL.BA", "ARS=X", "^TNX"}
EXPECTED_OUTPUT_COLUMNS = {
    "Date",
    "Dolar_CCL",
    "Dolar_Oficial",
    "Risk_Free_Rate",
    "Brecha_Cambiaria",
    "Ticker",
    "Price_USD",
    "Daily_Return",
    "processed_at",
}


def configurar_logging() -> None:
    """Configura formato de logs con timestamp y nivel."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def extract(period: str = "1y") -> dict[str, pd.DataFrame] | None:
    logger.info("Iniciando extracción consolidada desde Yahoo Finance...")
    yf_data = yf.download(TICKERS_ETL, period=period, interval="1d", auto_adjust=True)

    if yf_data is None or yf_data.empty:
        logger.error("No se pudieron descargar datos de Yahoo Finance.")
        return None

    df_yf = yf_data["Close"]
    return {"yf": df_yf}


def transform(raw_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    logger.info("Iniciando transformación financiera y macroeconómica...")
    df = raw_data["yf"].copy()

    faltantes = REQUIRED_RAW_COLUMNS - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas requeridas para la transformación: {sorted(faltantes)}")

    # Normalización de fechas sin zona horaria
    df.index = pd.to_datetime(df.index).normalize()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = "Date"

    # Consolidar fechas duplicadas por mezcla de husos horarios o datos intradiarios
    df = df.groupby(level=0).last()

    # Renombramos columnas macro antes de procesarlas
    df = df.rename(columns={"ARS=X": "Dolar_Oficial", "^TNX": "Risk_Free_Rate"})
    df = df.reset_index()

    # 1. Cálculo del Dólar CCL sintético (1 ADR GGAL = 10 acciones locales)
    ggal_valido = df["GGAL"].replace(0, np.nan)
    df["Dolar_CCL"] = (df["GGAL.BA"] / ggal_valido) * 10
    df["Dolar_CCL"] = df["Dolar_CCL"].replace([np.inf, -np.inf], np.nan)

    # 2. Tratamiento de feriados macroeconómicos
    for col in ("Dolar_CCL", "Dolar_Oficial", "Risk_Free_Rate"):
        df[col] = df[col].ffill().bfill()

    # 3. Brecha Cambiaria en %
    dolar_oficial_valido = df["Dolar_Oficial"].replace(0, np.nan)
    df["Brecha_Cambiaria"] = ((df["Dolar_CCL"] / dolar_oficial_valido) - 1) * 100
    df["Brecha_Cambiaria"] = df["Brecha_Cambiaria"].replace([np.inf, -np.inf], np.nan)

    # 4. Descartamos la acción local para conservar solo ADRs en USD
    df = df.drop(columns=["GGAL.BA"])

    # 5. Formato 'Long'
    df_melted = df.melt(
        id_vars=["Date", "Dolar_CCL", "Dolar_Oficial", "Risk_Free_Rate", "Brecha_Cambiaria"],
        var_name="Ticker",
        value_name="Price_USD",
    )

    # 6. Limpieza y cálculos finales
    df_melted = df_melted.dropna(subset=["Price_USD"])
    df_melted = df_melted[df_melted["Price_USD"] > 0]
    df_melted = (
        df_melted.sort_values(by=["Ticker", "Date"])
        .drop_duplicates(subset=["Ticker", "Date"], keep="last")
        .reset_index(drop=True)
    )
    df_melted["Daily_Return"] = df_melted.groupby("Ticker")["Price_USD"].pct_change()
    df_melted["processed_at"] = datetime.now()

    return df_melted


def validar_datos_etl(df: pd.DataFrame) -> tuple[bool, list[str]]:
    """Data Quality Gate previo a sobrescribir SQLite."""
    errores: list[str] = []

    if df.empty:
        return False, ["El dataset transformado está vacío."]

    columnas_faltantes = EXPECTED_OUTPUT_COLUMNS - set(df.columns)
    if columnas_faltantes:
        return False, [f"Faltan columnas esperadas: {sorted(columnas_faltantes)}"]

    if df.duplicated(subset=["Ticker", "Date"]).any():
        errores.append("Se detectaron filas duplicadas para la misma combinación (Ticker, Date).")

    if (df["Price_USD"] <= 0).any():
        errores.append("Se detectaron precios en USD menores o iguales a cero.")

    for col_macro in ("Dolar_CCL", "Dolar_Oficial"):
        if df[col_macro].isna().any() or (df[col_macro] <= 0).any():
            errores.append(f"Valores nulos o inválidos detectados en {col_macro}.")

    return len(errores) == 0, errores


def load(df: pd.DataFrame, db_url: str = DEFAULT_DB_URL) -> None:
    logger.info("Iniciando carga en SQLite (%s)...", db_url)
    engine = create_engine(db_url)
    try:
        df.to_sql("market_data", con=engine, if_exists="replace", index=False)
        logger.info("Datos cargados exitosamente: %d filas en market_data.", len(df))
    finally:
        engine.dispose()


if __name__ == "__main__":
    configurar_logging()
    raw_data = extract()
    if raw_data is None:
        sys.exit(1)

    transformed_data = transform(raw_data)
    es_valido, errores_calidad = validar_datos_etl(transformed_data)
    if not es_valido:
        for err in errores_calidad:
            logger.error("Data Quality Gate rechazado: %s", err)
        sys.exit(1)

    load(transformed_data)
