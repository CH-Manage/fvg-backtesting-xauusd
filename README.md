# fvg-backtesting-xauusd
FVG (Fair Value Gap) strategy backtesting on XAUUSD 4H — 260 trades, 43.8% win rate, profit factor 1.56, net P&amp;L +82R with 1:2 RR

# FVG Backtesting — XAUUSD 📈

Backtesting automatizado de la estrategia **Fair Value Gap (FVG)** sobre XAUUSD (Oro) en timeframe 4H, desarrollado como parte de un proyecto personal simulando el rol de Quant Analyst en J.P. Morgan.

---

## Resultados (1 año de datos, RR 1:2)

| Métrica | Resultado |
|---|---|
| Total operaciones | 260 |
| Operaciones ganadoras | 114 |
| Operaciones perdedoras | 146 |
| Win Rate | 43.8% |
| Profit Factor | 1.56 |
| Net P&L | +82R |
| Max Drawdown | -12R |

---

## ¿Qué es un Fair Value Gap?

Un FVG es un desequilibrio de precio formado por 3 velas consecutivas donde existe un gap entre la vela 1 y la vela 3:

- **FVG Alcista**: Low de vela 3 > High de vela 1 → entrada long en retroceso a la zona
- **FVG Bajista**: High de vela 3 < Low de vela 1 → entrada short en retroceso a la zona

---

## Lógica de la estrategia

- Entrada en el punto medio de la zona FVG cuando el precio retrocede
- Stop Loss en el extremo opuesto de la zona
- Take Profit con RR 1:2 configurable
- Timeframe: 4H
- Activo: XAUUSD (GC=F via Yahoo Finance)

---

## Tecnologías

| Herramienta | Uso |
|---|---|
| Python | Lenguaje principal |
| yfinance | Descarga de datos históricos |
| Streamlit | Dashboard interactivo |
| Plotly | Equity curve y gráficos |
| Pandas | Procesamiento de datos |

---

## Dashboard incluye

- Equity curve con drawdown shading
- Win/Loss pie chart
- Monthly P&L bar chart
- Trade log exportable en CSV
- Filtros por tipo de FVG (Bullish/Bearish)
- Ajuste de RR ratio y lookback period

---

*Proyecto personal con fines educativos. No constituye asesoramiento de inversión.*