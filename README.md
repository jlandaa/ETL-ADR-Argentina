# 📊 ADRs Argentinos: End-to-End Data Pipeline & Dashboard
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://jml-dashboard-adr.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io/)

## 📌 Visión General del Proyecto
Este proyecto implementa un ciclo completo de **Data Analysis** y **Data Engineering** para monitorear y analizar los **ADRs (American Depositary Receipts)** de empresas argentinas que cotizan en el NYSE.
El objetivo es automatizar la recolección, transformación y visualización de activos financieros para facilitar la toma de decisiones. La herramienta permite analizar la volatilidad, los retornos diarios, la correlación sectorial y el **rendimiento ajustado por riesgo** en tiempo real mediante un pipeline de datos robusto.

## 🛠️ Stack Tecnológico
* **Lenguaje:** Python (Pandas y NumPy para estadística financiera).
* **Extracción:** API de Yahoo Finance (`yfinance`).
* **Almacenamiento:** SQLite con SQLAlchemy (ORM).
* **Visualización:** Streamlit y Plotly (UI/UX corporativa con Sidebar).
* **Reportes e Integraciones:** `fpdf2` y `Matplotlib` (PDF Tear Sheets), `requests` (Webhooks HTTP POST).
* **Observabilidad:** Módulo `logging` nativo para auditoría de procesos en backend.
* **Despliegue:** Streamlit Community Cloud.

## 🏗️ Arquitectura del Pipeline (ETL)
El sistema se divide en tres fases modulares (ETL) respaldadas por una capa continua de monitoreo para asegurar la robustez del flujo:

1.  **Extract:** Descarga automatizada de precios de cierre ajustados para tickers clave como `GGAL`, `YPF`, `BMA`, `PAM` y `CEPU`.
2.  **Transform:** Limpieza de datos y normalización de series temporales.
    * Cálculo de **Retornos Diarios** porcentuales.
    * Generación de metadatos de procesamiento (`timestamp`).
3.  **Load:** Persistencia de los datos en una base de datos relacional local (`.db`) para garantizar la integridad y velocidad de consulta desde el Dashboard.

* **Observabilidad (Capa Transversal):** Registro silencioso de eventos (`etl_process.log`) para monitorear el estado de ejecución y detectar fallos de red sin interrumpir la experiencia del usuario.
  
## ✨ Análisis Cuantitativo y Funcionalidades (Analytics)

* **🔔 Sistema de Alertas Empresariales (Slack):** Módulo proactivo que monitorea umbrales de volatilidad definidos por el usuario. Si un activo rompe el límite de estrés, dispara un *payload* JSON estructurado a canales corporativos vía Webhook, reportando el precio ajustado y la variación diaria en tiempo real.
* **📄 Generación de Reportes PDF (Tear Sheets):** Exportación de la simulación "What-If" a un documento ejecutivo de un solo vistazo. Combina métricas clave con curvas de rendimiento vectorizadas mediante Matplotlib, aplicando una estricta liberación de memoria en el servidor (`plt.close()`).
* **Optimizador de Portafolios (Markowitz):** Integración de un motor de simulación estocástica (Monte Carlo) que genera miles de combinaciones de activos en tiempo real para graficar la **Frontera Eficiente**. Identifica matemáticamente la cartera de Máximo Ratio de Sharpe y sugiere la distribución óptima de capital.
* **Análisis Cuantitativo "What-If":** Simulador dinámico e interactivo que permite al usuario asignar capital y pesos porcentuales personalizados mediante *sliders*. El sistema normaliza matemáticamente las proporciones base 100 y calcula la curva de *equity* histórica utilizando vectorización pura en Pandas.
* **Integración Macroeconómica Sintética:** Desarrollo de lógica cruzada de activos locales (BYMA) e internacionales (NYSE) para calcular en el backend el **Dólar CCL implícito**. Incluye un *toggle* en la interfaz para deflactar los precios en tiempo real y aislar el rendimiento genuino de la ilusión monetaria (inflación/devaluación).
* **Métricas de Riesgo Institucional:** Evolución de las tarjetas de KPIs clásicas hacia un análisis de riesgo profundo. Calcula en tiempo real el Ratio de Sharpe anualizado, el **VaR (Value at Risk al 95%)** y el **Maximum Drawdown**, métricas estándar en la industria de fondos de inversión.
* **Auto-Healing ETL & Data Quality:** Pipeline de datos defensivo. El sistema detecta autónomamente si falta la base de datos y la regenera. Implementa limpieza segura mediante `.dropna()` orientada a celdas para evitar el borrado masivo por fallos de API, y utiliza *Forward Fill* (`.ffill()`) para corregir desincronizaciones de feriados entre calendarios internacionales.
* **Análisis de Riesgo y Volatilidad:** Histogramas y Box-plots superpuestos con zoom estadístico automático filtrando los percentiles 1% y 99% (Outlier Mitigation) para asegurar la máxima legibilidad de la distribución.
* **Matriz de Correlación:** Mapa de calor (Heatmap) interactivo para identificar movimientos conjuntos de mercado y oportunidades de diversificación.
* **UI/UX Corporativa y Performance Optimizada:** Diseño *Data-Driven* con filtros temporales dinámicos en un Sidebar. Implementación de decoradores de memoria en RAM (`@st.cache_data`) con Time-To-Live (TTL), reduciendo el impacto en la base de datos a cero durante la interacción del usuario y garantizando respuestas en milisegundos.


## 🚀 Despliegue y Ejecución

### Opción A: Entorno de Producción (Cloud)
El dashboard analítico está desplegado y accesible públicamente, consumiendo el pipeline de datos automatizado en el backend.

👉 **[Acceder al Dashboard Financiero (Streamlit)](https://jml-dashboard-adr.streamlit.app/)**

### Opción B: Ejecución Local (Desarrollo)
Para replicar el entorno de modelado en local:
1. **Clonar el repositorio e ingresar a la carpeta:**
    ```bash
    git clone https://github.com/jlandaa/ETL-ADR-Argentina.git
    cd ETL-ADR-Argentina
    ```
2.  **Crear y activar un entorno virtual (Recomendado):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En Windows: venv\Scripts\activate
    ```
3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Ejecutar la aplicación:**
    ```bash
    streamlit run dashboard_adr.py
    ```

---
👨‍💻 **Juan Manuel Landa** — *Computer Engineer | Data Analyst & BI Consultant*  
🔗 [LinkedIn](https://ar.linkedin.com/in/juan-manuel-landa/en) • 🌐 [Portfolio](https://juan-manuel-landa.netlify.app/) • ✉️ [Contacto](mailto:jmlanda93@gmail.com)
