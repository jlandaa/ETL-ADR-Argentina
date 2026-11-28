# 📊 ADRs Argentinos: End-to-End Data Pipeline & Dashboard

[![CI Quality](https://github.com/jlandaa/ETL-ADR-Argentina/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/jlandaa/ETL-ADR-Argentina/actions/workflows/ci.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://jml-dashboard-adr.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)

## 📌 Visión General del Proyecto

Este proyecto implementa un ciclo completo de **Data Analysis** y **Data Engineering** para monitorear y analizar los **ADRs (American Depositary Receipts)** de empresas argentinas que cotizan en el NYSE.

El objetivo es automatizar la recolección, validación, transformación y visualización de activos financieros para facilitar la toma de decisiones. La herramienta permite analizar la volatilidad, los retornos diarios, la correlación sectorial y el **rendimiento ajustado por riesgo** mediante un pipeline ETL defensivo y un motor analítico desacoplado y testeado en CI.

## 🛠️ Stack Tecnológico

* **Lenguaje:** Python (Pandas y NumPy para estadística financiera).
* **Extracción:** API de Yahoo Finance (`yfinance`).
* **Almacenamiento:** SQLite con SQLAlchemy.
* **Visualización:** Streamlit y Plotly (UI/UX corporativa con Sidebar).
* **Reportes e Integraciones:** `fpdf2` y `Matplotlib` (PDF Tear Sheets), `requests` (Webhooks HTTP POST con control de *timeout*).
* **Observabilidad:** Módulo `logging` nativo para auditoría de procesos en backend.
* **Calidad & CI/CD:** GitHub Actions, **Ruff** (linter & formatter) y **Pytest**.
* **Despliegue:** Streamlit Community Cloud.

## 🏗️ Arquitectura del Pipeline (ETL & Analytics)

El sistema separa las responsabilidades en cuatro etapas (pipeline ETL + motor analítico) respaldadas por observabilidad continua:

1. **Extract (`ETL_ADR_Argentina.py`):** Descarga automatizada de precios de cierre ajustados para tickers clave (`GGAL`, `YPF`, `BMA`, `PAM`, `CEPU`) y activos locales para el cálculo de brecha cambiaria.
2. **Transform & Data Quality Gate (`ETL_ADR_Argentina.py`):** Limpieza defensiva orientada a celdas, normalización de series temporales, cálculo de **Retornos Diarios** porcentuales, generación de metadatos (`timestamp`) y validación previa de integridad antes de persistir.
3. **Load (`ETL_ADR_Argentina.py`):** Persistencia parametrizada (`db_url`) en una base relacional SQLite (`.db`) para garantizar velocidad de consulta y permitir pruebas aisladas en CI sin afectar archivos productivos.
4. **Motor Cuantitativo Desacoplado (`analytics.py`):** Aísla la matemática financiera (Sharpe, VaR, Maximum Drawdown, simulaciones *What-If*, Monte Carlo / Markowitz y CCL implícito) en funciones puras, facilitando la cobertura con tests unitarios.

* **Observabilidad (Capa Transversal):** Registro silencioso de eventos (`etl_process.log`) para monitorear el estado de ejecución y detectar fallos de red sin interrumpir la experiencia del usuario.

## ✨ Análisis Cuantitativo y Funcionalidades

* **🔔 Sistema de Alertas Empresariales (Slack):** Monitorea umbrales de volatilidad definidos por el usuario. Si un activo rompe el límite de estrés, dispara un *payload* JSON estructurado vía Webhook (con *timeout* explícito), reportando el precio ajustado y la variación diaria en tiempo real.
* **📄 Generación de Reportes PDF (Tear Sheets):** Exportación de la simulación "What-If" a un documento ejecutivo. Combina métricas clave con curvas de rendimiento en Matplotlib, aplicando liberación de memoria (`plt.close()`) y limpieza garantizada de archivos PNG temporales.
* **Optimizador de Portafolios (Markowitz):** Motor de simulación estocástica (Monte Carlo) con ordenamiento consistente de tickers que grafica la **Frontera Eficiente**, identifica la cartera de Máximo Ratio de Sharpe y sugiere la distribución óptima de capital.
* **Análisis Cuantitativo "What-If":** Simulador interactivo donde el usuario asigna capital y pesos porcentuales mediante *sliders*. Normaliza automáticamente las proporciones base 100 y calcula la curva de *equity* histórica con vectorización en Pandas.
* **Integración Macroeconómica Sintética:** Cruce de activos locales (BYMA) e internacionales (NYSE) para calcular el **Dólar CCL implícito** y la brecha cambiaria, con *toggle* para deflactar precios en tiempo real.
* **Métricas de Riesgo Institucional:** Cálculo en tiempo real de Ratio de Sharpe anualizado, **VaR (Value at Risk al 95%)** y **Maximum Drawdown**.
* **Auto-Healing ETL & Data Quality:** Detecta autónomamente si falta la base de datos y la regenera. Aplica limpieza segura mediante `.dropna()` orientado a celdas y *Forward Fill* (`.ffill()`) para resolver desincronizaciones de feriados entre mercados.
* **Análisis de Riesgo y Volatilidad:** Histogramas y Box-plots superpuestos con recorte estadístico de percentiles 1% y 99% (*Outlier Mitigation*).
* **Matriz de Correlación:** Mapa de calor (*Heatmap*) interactivo para evaluar movimientos conjuntos y diversificación.
* **UI/UX Corporativa y Performance Optimizada:** Filtros temporales dinámicos en Sidebar, gestión segura de conexiones SQLite y caché en RAM (`@st.cache_data`) con TTL para respuestas instantáneas.

## 📂 Estructura del Proyecto

```text
📦 ETL-ADR-Argentina
 ┣ 📂 .devcontainer          # Configuración reproducible para Dev Containers
 ┣ 📂 .github/workflows
 ┃ ┗ 📜 ci.yml               # Pipeline de CI (Ruff check/format + Pytest)
 ┣ 📂 .streamlit             # Configuración de tema y servidor Streamlit
 ┣ 📂 tests
 ┃ ┗ 📜 test_etl_adr.py      # Tests unitarios del ETL, Data Quality Gate y analytics
 ┣ 📜 ETL_ADR_Argentina.py   # Pipeline ETL con Data Quality Gate y db_url parametrizado
 ┣ 📜 analytics.py           # Lógica cuantitativa pura (Markowitz, VaR, Drawdown, What-If)
 ┣ 📜 dashboard_adr.py       # Interfaz Streamlit, alertas Slack y exportación de Tear Sheets
 ┣ 📜 pyproject.toml         # Configuración de Ruff y Pytest
 ┣ 📜 requirements.txt       # Dependencias del proyecto
 ┣ 📜 LICENSE                # Licencia MIT
 ┗ 📜 README.md              # Documentación técnica
```

## 🚀 Despliegue y Ejecución

### Opción A: Entorno de Producción (Cloud)

El dashboard analítico está desplegado y accesible públicamente, consumiendo el pipeline de datos automatizado en el backend.

👉 **[Acceder al Dashboard Financiero (Streamlit)](https://jml-dashboard-adr.streamlit.app/)**

### Opción B: Ejecución Local (Desarrollo)

1. **Clonar el repositorio e ingresar a la carpeta:**

```bash
git clone [https://github.com/jlandaa/ETL-ADR-Argentina.git](https://github.com/jlandaa/ETL-ADR-Argentina.git)
cd ETL-ADR-Argentina
```

2. **Crear y activar un entorno virtual (Recomendado):**

```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias:**

```bash
pip install -r requirements.txt
```

4. **Ejecutar la aplicación:**

```bash
streamlit run dashboard_adr.py
```

## 🧪 Calidad de Código y Testing Automatizado (CI/CD)

Cada *push* y *pull request* hacia `main` dispara `ci.yml` en **GitHub Actions**, ejecutando linting, verificación de formato y la suite de pruebas unitarias en `tests/test_etl_adr.py`. Para correr las mismas validaciones en local:

```bash
ruff check .
ruff format --check .
pytest -v
```

---

👨‍💻 **Juan Manuel Landa** — *Computer Engineer | Data Analyst & BI Consultant*  
🔗 [LinkedIn](https://ar.linkedin.com/in/juan-manuel-landa/en) • 🌐 [Portfolio](https://juan-manuel-landa.netlify.app/) • ✉️ [Contacto](mailto:jmlanda93@gmail.com)
