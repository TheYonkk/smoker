"""
Visualize calibration readings to help generate a conversion function
"""
import logging
import sys
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from numpy.polynomial import Chebyshev, Polynomial

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)

file = "initial_cal.xlsx"

df = pd.read_excel(file)
df = df[df["ADC"] > 175]

fit = Polynomial.fit(df["ADC"], df["Temp"], deg=2)
logger.info(fit)
line_data = fit.linspace(100, (df["ADC"].min(), df["ADC"].max()))

logger.info(df.head())

fig = go.Figure()
fig.add_trace(go.Scatter(x=df["ADC"], y=df["Temp"], mode='markers'))
fig.add_trace(go.Scatter(x=line_data[0], y=line_data[1], mode='lines'))
fig.show()
