"""Plotly chart builders for the 24/7 Agent section cards.

Each builder produces a compact dark-themed Plotly figure suitable for
embedding inside an agent card. Charts show price action with EMA overlays,
volume, nearest support / resistance horizontals, and (optionally) entry,
stop, and target lines from an attached trade plan.

Conventions
-----------
- Dark theme matches the rest of the app: ``plotly_dark`` template with a
  ``#06121f`` plot background and a transparent paper background so the
  chart sits cleanly on the card surface.
- Candle colours follow the Binance-style palette already used elsewhere
  in the app (``#34c759`` up / ``#ff6b5b`` down).
- EMA column conventions mirror the rest of the codebase
  (``ema_fast`` ≈ EMA20, ``ema_slow`` ≈ EMA50, ``ema_trend`` ≈ EMA200).
  Builders also accept literal ``ema20`` / ``ema50`` / ``ema200`` columns
  if those happen to be present.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Theme constants — keep in sync with the rest of the app
# ---------------------------------------------------------------------------
PLOT_BG = "#06121f"
PAPER_BG = "rgba(0,0,0,0)"
GRID_COLOR = "rgba(255,255,255,0.05)"
TEXT_COLOR = "#cfd6e0"

UP_COLOR = "#34c759"
DOWN_COLOR = "#ff6b5b"

EMA_COLORS = {
    "ema20": "#f5a623",   # warm orange
    "ema50": "#4a90d9",   # blue
    "ema200": "#e056fd",  # magenta
}

SUPPORT_COLOR = "#2ed47a"
RESISTANCE_COLOR = "#ff6b5b"

ENTRY_COLOR = "#4a90d9"
STOP_COLOR = "#ff5c5c"
TARGET_COLOR = "#2ed47a"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _resolve_ema_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map logical EMA name → actual column name present on df.

    Accepts either the literal names ``ema20`` / ``ema50`` / ``ema200`` or
    the project's conventional aliases ``ema_fast`` / ``ema_slow`` /
    ``ema_trend``.
    """
    cols = set(df.columns)
    mapping: dict[str, str] = {}
    for logical, candidates in (
        ("ema20", ("ema20", "ema_fast")),
        ("ema50", ("ema50", "ema_slow")),
        ("ema200", ("ema200", "ema_trend")),
    ):
        for cand in candidates:
            if cand in cols:
                mapping[logical] = cand
                break
    return mapping


def _apply_dark_theme(fig: go.Figure, height: int,
                      enable_zoom_controls: bool = True) -> None:
    """Apply the shared dark-theme look-and-feel.

    enable_zoom_controls: when True (default), adds:
      - dragmode='pan' (more intuitive than 'zoom' on touch + scroll)
      - mouse-wheel zoom (via xaxis fixedrange=False)
      - crosshair spikes that follow the cursor
      - clean hover tooltip
    """
    fig.update_layout(
        template="plotly_dark",
        height=height,
        margin=dict(l=8, r=8, t=22, b=8),
        plot_bgcolor=PLOT_BG,
        paper_bgcolor=PAPER_BG,
        font=dict(color=TEXT_COLOR, size=11),
        showlegend=False,
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        # User-friendly zoom: drag pans, scroll zooms, double-click resets.
        dragmode="pan" if enable_zoom_controls else "zoom",
    )
    # Crosshair spikes — visible vertical/horizontal cursor lines that make
    # reading the chart at a specific time / price natural.
    x_kwargs = dict(
        gridcolor=GRID_COLOR, zeroline=False,
        showline=False, fixedrange=False)
    y_kwargs = dict(
        gridcolor=GRID_COLOR, zeroline=False,
        showline=False, fixedrange=False, side="right")
    if enable_zoom_controls:
        x_kwargs.update(
            showspikes=True, spikemode="across", spikesnap="cursor",
            spikecolor="#5b8eff", spikethickness=1, spikedash="dot")
        y_kwargs.update(
            showspikes=True, spikemode="across", spikesnap="cursor",
            spikecolor="#5b8eff", spikethickness=1, spikedash="dot")
    fig.update_xaxes(**x_kwargs)
    fig.update_yaxes(**y_kwargs)


def _add_hline(
    fig: go.Figure,
    y: float,
    *,
    color: str,
    dash: str = "dash",
    width: float = 1.0,
    label: str | None = None,
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Add a horizontal line with consistent styling and optional label."""
    kwargs: dict[str, Any] = dict(
        y=y, line=dict(color=color, width=width, dash=dash),
        opacity=0.85)
    if label:
        kwargs["annotation_text"] = label
        kwargs["annotation_position"] = "top right"
        kwargs["annotation_font"] = dict(color=color, size=10)
    if row is not None and col is not None:
        kwargs["row"] = row
        kwargs["col"] = col
    fig.add_hline(**kwargs)


def _zone_price(zone: Any) -> float | None:
    """Pull a numeric price out of an S/R zone dict / number / object."""
    if zone is None:
        return None
    if isinstance(zone, (int, float)):
        try:
            v = float(zone)
        except (TypeError, ValueError):
            return None
        return v if v > 0 else None
    if isinstance(zone, dict):
        for key in ("price", "level", "value", "center"):
            v = zone.get(key)
            if v is not None:
                try:
                    f = float(v)
                except (TypeError, ValueError):
                    continue
                if f > 0:
                    return f
        return None
    # Allow bare attribute objects as a courtesy.
    for key in ("price", "level", "value", "center"):
        v = getattr(zone, key, None)
        if v is not None:
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f > 0:
                return f
    return None


def _normalize_sr_zones(sr_zones: Any) -> tuple[list[float], list[float]]:
    """Convert the various S/R-zone shapes used in the codebase to two
    plain lists of price levels (supports, resistances).

    Accepted shapes:
      * dict with ``supports`` / ``resistances`` (the
        :func:`support_resistance.find_sr_zones` return value).
      * dict with ``support`` / ``resistance`` singular variants.
      * tuple/list of two iterables ``(supports, resistances)``.
      * flat iterable of zone dicts / floats (treated as mixed — split
        at price_now is not available here, so we just plot them all in
        a neutral colour by assigning to supports).
    """
    supports: list[float] = []
    resistances: list[float] = []
    if sr_zones is None:
        return supports, resistances

    if isinstance(sr_zones, dict):
        sup_iter = (sr_zones.get("supports") or sr_zones.get("support")
                    or [])
        res_iter = (sr_zones.get("resistances") or sr_zones.get("resistance")
                    or [])
    elif isinstance(sr_zones, (list, tuple)) and len(sr_zones) == 2 \
            and all(isinstance(x, (list, tuple)) for x in sr_zones):
        sup_iter, res_iter = sr_zones[0], sr_zones[1]
    else:
        # Flat iterable — best effort.
        sup_iter, res_iter = sr_zones, []

    for z in sup_iter or []:
        p = _zone_price(z)
        if p is not None:
            supports.append(p)
    for z in res_iter or []:
        p = _zone_price(z)
        if p is not None:
            resistances.append(p)
    return supports, resistances


def _empty_figure(message: str, height: int) -> go.Figure:
    """Return a dark-themed placeholder figure with a centred message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message, x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(color="#8e8e93", size=12))
    _apply_dark_theme(fig, height)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _trade_plan_levels(trade_plan: dict) -> dict[str, float]:
    """Extract entry / stop / target levels from a trade-plan dict.

    Supports both the new schema (``entry``, ``stop_loss``,
    ``take_profit`` / ``take_profit_2`` / ``take_profit_3``) and the
    legacy schema (``stop``, ``target``, ``target_2``, ``target_3``).
    """
    out: dict[str, float] = {}

    def _grab(*keys: str) -> float | None:
        for k in keys:
            v = trade_plan.get(k)
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f > 0:
                return f
        return None

    entry = _grab("entry", "entry_price")
    if entry is not None:
        out["entry"] = entry
    stop = _grab("stop_loss", "stop", "sl")
    if stop is not None:
        out["stop"] = stop
    t1 = _grab("take_profit", "target", "tp", "target_1", "tp1")
    if t1 is not None:
        out["target"] = t1
    t2 = _grab("take_profit_2", "target_2", "tp2")
    if t2 is not None:
        out["target_2"] = t2
    t3 = _grab("take_profit_3", "target_3", "tp3")
    if t3 is not None:
        out["target_3"] = t3
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_compact_chart(
    df: pd.DataFrame,
    trade_plan: dict | None = None,
    sr_zones: Any = None,
    height: int = 220,
) -> go.Figure:
    """Build a compact candlestick chart for an agent card.

    The chart is two stacked panels:
      * Price panel (≈ 80% of the height) with candles, EMA20/50/200
        overlays, support / resistance horizontals, and — if
        ``trade_plan`` is provided — entry / stop / target dashed lines.
      * Volume panel (≈ 20%) coloured up/down.

    Parameters
    ----------
    df:
        OHLCV DataFrame indexed by timestamp. Must contain the columns
        ``open``, ``high``, ``low``, ``close``, ``volume``. EMA columns
        (``ema_fast`` / ``ema_slow`` / ``ema_trend`` or the literal
        ``ema20`` / ``ema50`` / ``ema200``) are overlaid when present.
    trade_plan:
        Optional plan dict in the project's standard schema. When
        supplied, entry, stop and (up to three) targets are drawn as
        dashed horizontal lines with right-aligned labels.
    sr_zones:
        Optional support / resistance zones. Accepts the return value of
        :func:`support_resistance.find_sr_zones` (a dict with
        ``supports`` / ``resistances``) or any of the related shapes
        described in :func:`_normalize_sr_zones`.
    height:
        Total figure height in pixels.
    """
    if df is None or len(df) == 0:
        return _empty_figure("no data", height)

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        missing = ", ".join(sorted(required - set(df.columns)))
        return _empty_figure(f"missing columns: {missing}", height)

    # Use the most recent bars only — compact card view.
    plot = df.tail(120)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.78, 0.22], vertical_spacing=0.02)

    # Candles
    fig.add_trace(
        go.Candlestick(
            x=plot.index,
            open=plot["open"], high=plot["high"],
            low=plot["low"], close=plot["close"],
            increasing_line_color=UP_COLOR,
            decreasing_line_color=DOWN_COLOR,
            increasing_fillcolor=UP_COLOR,
            decreasing_fillcolor=DOWN_COLOR,
            line=dict(width=1),
            name="Price",
            showlegend=False),
        row=1, col=1)

    # EMA overlays (only those actually present on the frame)
    ema_map = _resolve_ema_columns(plot)
    for logical, color in EMA_COLORS.items():
        col_name = ema_map.get(logical)
        if not col_name:
            continue
        series = plot[col_name]
        if series.isna().all():
            continue
        fig.add_trace(
            go.Scatter(
                x=plot.index, y=series, mode="lines",
                name=logical.upper(),
                line=dict(color=color, width=1.1),
                hovertemplate=f"{logical.upper()}: %{{y:.4f}}<extra></extra>"),
            row=1, col=1)

    # S/R horizontal zones
    supports, resistances = _normalize_sr_zones(sr_zones)
    for i, level in enumerate(supports[:3]):
        _add_hline(
            fig, level, color=SUPPORT_COLOR, dash="dot", width=1.0,
            label=f"S{i + 1} {level:g}" if i == 0 else None,
            row=1, col=1)
    for i, level in enumerate(resistances[:3]):
        _add_hline(
            fig, level, color=RESISTANCE_COLOR, dash="dot", width=1.0,
            label=f"R{i + 1} {level:g}" if i == 0 else None,
            row=1, col=1)

    # Trade-plan entry / stop / target
    if isinstance(trade_plan, dict):
        levels = _trade_plan_levels(trade_plan)
        if "entry" in levels:
            _add_hline(
                fig, levels["entry"], color=ENTRY_COLOR, dash="dash",
                width=1.4, label=f"Entry {levels['entry']:g}",
                row=1, col=1)
        if "stop" in levels:
            _add_hline(
                fig, levels["stop"], color=STOP_COLOR, dash="dash",
                width=1.4, label=f"Stop {levels['stop']:g}",
                row=1, col=1)
        for key, lbl in (("target", "T1"), ("target_2", "T2"),
                         ("target_3", "T3")):
            if key in levels:
                _add_hline(
                    fig, levels[key], color=TARGET_COLOR, dash="dash",
                    width=1.2,
                    label=f"{lbl} {levels[key]:g}",
                    row=1, col=1)

    # Volume bars
    vol_colors = [
        UP_COLOR if c >= o else DOWN_COLOR
        for c, o in zip(plot["close"], plot["open"])]
    fig.add_trace(
        go.Bar(
            x=plot.index, y=plot["volume"], name="Volume",
            marker_color=vol_colors, marker_line_width=0,
            opacity=0.7, showlegend=False),
        row=2, col=1)

    _apply_dark_theme(fig, height)
    # Hide y-axis title clutter on the tiny volume panel.
    fig.update_yaxes(showticklabels=True, row=1, col=1)
    fig.update_yaxes(showticklabels=False, row=2, col=1)
    return fig


def build_multi_tf_chart(
    symbol: str,
    dfs_by_tf: dict[str, pd.DataFrame],
    height: int = 300,
) -> go.Figure:
    """Build a 4-panel mini-candlestick chart across 15m / 1h / 4h / 1d.

    Each panel shows the last ~80 candles for the corresponding
    timeframe with a faint EMA50 overlay. Panels are titled with the
    timeframe label. Missing or empty frames are tolerated — the
    corresponding panel simply shows a "no data" annotation.

    Parameters
    ----------
    symbol:
        Symbol label, e.g. ``"BTCUSDT"``. Used in the figure title.
    dfs_by_tf:
        Mapping of timeframe → OHLCV DataFrame. Recognised keys are
        ``"15m"``, ``"1h"``, ``"4h"``, ``"1d"`` (any extras are ignored;
        any missing key renders an empty panel).
    height:
        Total figure height in pixels.
    """
    tfs = ["15m", "1h", "4h", "1d"]

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=tfs,
        shared_xaxes=False, shared_yaxes=False,
        horizontal_spacing=0.06, vertical_spacing=0.14)

    cell_for_idx = [(1, 1), (1, 2), (2, 1), (2, 2)]

    dfs_by_tf = dfs_by_tf or {}
    for idx, tf in enumerate(tfs):
        row, col = cell_for_idx[idx]
        df = dfs_by_tf.get(tf)

        if df is None or len(df) == 0 or not {
                "open", "high", "low", "close"}.issubset(df.columns):
            fig.add_annotation(
                text="no data",
                xref=f"x{idx + 1} domain" if idx > 0 else "x domain",
                yref=f"y{idx + 1} domain" if idx > 0 else "y domain",
                x=0.5, y=0.5, showarrow=False,
                font=dict(color="#8e8e93", size=11))
            continue

        plot = df.tail(80)
        fig.add_trace(
            go.Candlestick(
                x=plot.index,
                open=plot["open"], high=plot["high"],
                low=plot["low"], close=plot["close"],
                increasing_line_color=UP_COLOR,
                decreasing_line_color=DOWN_COLOR,
                increasing_fillcolor=UP_COLOR,
                decreasing_fillcolor=DOWN_COLOR,
                line=dict(width=0.9),
                showlegend=False, name=tf),
            row=row, col=col)

        # Faint EMA50 (or ema_slow) overlay if available.
        ema_map = _resolve_ema_columns(plot)
        ema_col = ema_map.get("ema50") or ema_map.get("ema20")
        if ema_col and not plot[ema_col].isna().all():
            fig.add_trace(
                go.Scatter(
                    x=plot.index, y=plot[ema_col], mode="lines",
                    line=dict(color="#4a90d9", width=1.0),
                    opacity=0.85, showlegend=False,
                    hovertemplate="EMA: %{y:.4f}<extra></extra>"),
                row=row, col=col)

    _apply_dark_theme(fig, height)
    # Per-panel rangesliders off, and tighter subplot title styling.
    for i in range(1, 5):
        x_key = "xaxis" if i == 1 else f"xaxis{i}"
        fig.layout[x_key].update(rangeslider=dict(visible=False))
    fig.update_annotations(font=dict(color=TEXT_COLOR, size=11))

    title = f"{symbol} — 15m · 1h · 4h · 1d" if symbol else None
    if title:
        fig.update_layout(
            title=dict(text=title, x=0.01, xanchor="left",
                       font=dict(size=12, color=TEXT_COLOR)))
    return fig
