"""Readable charts with original units, visible gaps and explicit comparisons."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from bluenexus.catalog import signal_info

NAVY, BLUE, AMBER, RED = "#002e52", "#1688aa", "#a15c00", "#b53737"
COLORS=[NAVY,BLUE,AMBER,"#7259a2"]

def style(fig, height=330):
    fig.update_layout(template="plotly_white",font=dict(family="Montserrat, sans-serif",size=12,color=NAVY),
                      margin=dict(l=15,r=20,t=35,b=20),height=height,hovermode="x unified",
                      legend=dict(orientation="h",y=1.15,x=0),paper_bgcolor="rgba(0,0,0,0)",plot_bgcolor="white")
    fig.update_xaxes(title=None,gridcolor="#edf2f6")
    fig.update_yaxes(gridcolor="#e6edf2",zerolinecolor="#d0dce5")
    return fig

def lines(frame, keys, ylabel=None):
    fig=go.Figure()
    for i,key in enumerate(keys):
        if key not in frame or not frame[key].notna().any():
            continue
        name,unit,scale=signal_info(key)
        # Explicit calendar gaps prevent a missing day from appearing interpolated.
        ordered=frame.sort_values("date").set_index("date")
        if ordered.empty:
            continue
        ordered=ordered.reindex(pd.date_range(ordered.index.min(),ordered.index.max()))
        fig.add_scatter(x=ordered.index,y=ordered[key]*scale,name=name,connectgaps=False,
                        mode="lines+markers",marker=dict(size=4),line=dict(color=COLORS[i%len(COLORS)],width=2,dash="solid" if i==0 else "dot"),
                        hovertemplate="%{x|%d %b %Y}<br>%{y:,.3f}<extra>%{fullData.name}</extra>")
    fig.update_yaxes(title=ylabel or (signal_info(keys[0])[1] if keys else ""))
    return style(fig)

def equipment_chart(screened, info, markers=None, high=None):
    fig=go.Figure()
    fig.add_scatter(x=screened.date,y=screened.lower_fence,line=dict(width=0),showlegend=False,hoverinfo="skip")
    fig.add_scatter(x=screened.date,y=screened.upper_fence,line=dict(width=0),fill="tonexty",fillcolor="rgba(22,136,170,.12)",name="Prior statistical band",hoverinfo="skip")
    fig.add_scatter(x=screened.date,y=screened.value,name=info["label"],mode="lines+markers",line=dict(color=NAVY),marker=dict(size=4),connectgaps=False)
    flags=screened.loc[screened.flag]
    fig.add_scatter(x=flags.date,y=flags.value,name="Statistical deviation",mode="markers",marker=dict(color=AMBER,size=8,symbol="circle-open"))
    if markers is not None and len(markers):
        fig.add_scatter(x=markers.date,y=markers.value,name="Investigation rule",mode="markers",marker=dict(color=RED,size=8,symbol="diamond"))
    if high is not None:
        fig.add_hline(y=high,line_dash="dash",line_color=RED,annotation_text="Review only if °C confirmed",annotation_position="top left")
    fig.update_yaxes(title=info["unit"])
    return style(fig,380)

def display(value,digits=1):
    if value is None or isinstance(value,(float,np.floating)) and not np.isfinite(value):
        return "Unavailable"
    return f"{value:,.{digits}f}" if isinstance(value,(int,float,np.number)) else str(value)
