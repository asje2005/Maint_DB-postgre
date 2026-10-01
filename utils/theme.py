"""
Central design system for the Manufacturing Operation Database — DATUM EDITION.

Drop-in replacement for utils/theme.py. The public API is unchanged
(PALETTE / RGB / TOKENS / GRADIENT_* / DEPARTMENT_COLORS / metric_card / badge /
value_gradient / get_css), so the rest of the app keeps working — only the
*values* change. Because static/styles.css references everything through
var(--token), swapping this file reskins the entire app to Datum:

  - Deep teal + teal-tinted graphite palette ("Deep & Refined" signal set)
  - Space Grotesk (UI) + Space Mono (codes/IDs) via a Google Fonts @import
  - Tighter machined radii, graphite-tinted shadows
  - Header/metric "gradient" tokens flattened to a subtle teal (no more
    teal->blue gradient text)

See handoff/IMPLEMENTATION.md for the optional follow-ups (emoji -> Bootstrap
icons, sidebar wordmark).
"""
import html
from functools import lru_cache
from pathlib import Path

# ── Colour tokens (Datum) ─────────────────────────────────────────────────────
# Keys are unchanged from the original so existing CSS keeps resolving.
PALETTE = {
    # Brand / primary (teal)
    "primary":        "#0d7a70",
    "primary-dark":   "#0a5d55",
    "primary-bright": "#15a094",   # vivid teal — gradient endpoint + logo mark
    "primary-light":  "#eef6f4",   # tint / hover background
    "primary-soft":   "#d3ece8",   # badge background
    "primary-border": "#b6ddd6",   # badge / accent border

    # Info / secondary (steel blue)
    "info":           "#2f86b3",
    "info-dark":      "#1f6791",
    "info-accent":    "#3a97c4",   # brighter accent (drafts, Swiss dept)
    "info-light":     "#e4f0f6",   # badge background
    "info-border":    "#b9d8e8",   # badge border
    "secondary":      "#2f86b3",   # alias of --info

    # Success (emerald)
    "success":        "#1c8a6e",
    "success-dark":   "#16715a",
    "success-light":  "#e2f2ec",
    "success-border": "#b3ddcd",

    # Danger (raspberry)
    "danger":         "#cf3a4b",
    "danger-dark":    "#b32f3f",

    # Neutral / slate (teal-tinted graphite)
    "ink":            "#102a2a",   # deep teal-graphite — logo backplate
    "bg":             "#f5f7f6",
    "surface":        "#ffffff",
    "bg-muted":       "#e9eeec",
    "border":         "#e2e7e5",
    "border-soft":    "#cbd3d0",
    "text":           "#14211f",
    "text-strong":    "#33433f",
    "text-muted":     "#5a6b66",
    "text-subtle":    "#8a9994",

    # Departments / equipment categories
    "dept-lathe":     "#6d5bd0",
    "dept-mill":      "#0d7a70",   # == primary
    "dept-swiss":     "#2f86b3",   # == info
}


def _rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}"


RGB = {
    "primary-rgb":     _rgb(PALETTE["primary"]),
    "info-rgb":        _rgb(PALETTE["info"]),
    "info-accent-rgb": _rgb(PALETTE["info-accent"]),
    "success-rgb":     _rgb(PALETTE["success"]),
    "danger-rgb":      _rgb(PALETTE["danger"]),
}

# ── Gradients ─────────────────────────────────────────────────────────────────
# Datum flattens header/metric text: a *subtle* same-hue teal instead of the old
# teal->blue. Danger/success keep a faint same-hue gradient for value_gradient().
GRADIENT_PRIMARY = f"linear-gradient(135deg, {PALETTE['primary']} 0%, {PALETTE['primary-bright']} 100%)"
GRADIENT_DANGER  = f"linear-gradient(135deg, {PALETTE['danger']} 0%, {PALETTE['danger-dark']} 100%)"
GRADIENT_SUCCESS = f"linear-gradient(135deg, {PALETTE['success']} 0%, {PALETTE['success-dark']} 100%)"

# ── Non-colour design tokens ──────────────────────────────────────────────────
TOKENS = {
    "gradient":     GRADIENT_PRIMARY,
    "font":         "'Space Grotesk', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "font-mono":    "'Space Mono', ui-monospace, Menlo, monospace",
    "shadow-xs":    "0 1px 2px rgba(16,42,42,0.05)",
    "shadow":       "0 1px 3px rgba(16,42,42,0.07), 0 1px 2px rgba(16,42,42,0.04)",
    "shadow-md":    "0 4px 12px rgba(16,42,42,0.08), 0 2px 4px rgba(16,42,42,0.04)",
    "shadow-lg":    "0 12px 28px rgba(16,42,42,0.10), 0 4px 8px rgba(16,42,42,0.05)",
    "transition":   "all 0.16s cubic-bezier(0.4,0,0.2,1)",
    "radius-sm":    "4px",
    "radius":       "6px",
    "radius-lg":    "10px",
    "input-height": "40px",
}

# ── Department / equipment-category colours (Plotly needs literal hex) ─────────
DEPARTMENT_COLORS = {
    "Lathe": PALETTE["dept-lathe"],
    "Mill":  PALETTE["dept-mill"],
    "Swiss": PALETTE["dept-swiss"],
}


def department_color(dept: str) -> str:
    return DEPARTMENT_COLORS.get(dept, PALETTE["dept-lathe"])


# Ordered brand palette for any chart that colours by an open-ended category
# (and for single-series charts, which take the first colour). Wiring this into
# ``px.defaults.color_discrete_sequence`` keeps every untyped chart on-brand
# instead of falling back to Plotly's / Streamlit's default blues.
CHART_SEQUENCE = [
    PALETTE["primary"],        # teal
    PALETTE["info"],           # steel blue
    PALETTE["dept-lathe"],     # violet
    PALETTE["success"],        # emerald
    PALETTE["danger"],         # raspberry
    PALETTE["info-accent"],    # bright blue
    PALETTE["primary-bright"], # bright teal
    PALETTE["text-muted"],     # slate
]


def style_fig(fig):
    """Apply the Datum look to a Plotly figure so charts match the rest of the app:
    the brand font, a transparent panel (the page surface shows through), and
    tokenised axis / grid / tick colours. Plotly renders to SVG, so colours are
    literal hex from PALETTE (CSS vars don't resolve inside the chart). Returns the
    same figure for inline use: ``st.plotly_chart(style_fig(fig))``. Axis updates
    are no-ops on charts without cartesian axes (e.g. pies), so this is safe for
    every figure type."""
    fig.update_layout(
        font=dict(family=TOKENS["font"], color=PALETTE["text"], size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title_font=dict(color=PALETTE["text-strong"]),
        # Legend titles ("Dept", "Category", …) duplicate the chart heading /
        # axis labels — drop them everywhere for a cleaner, consistent legend.
        legend=dict(font=dict(color=PALETTE["text-muted"]), title_text=""),
    )
    # Streamlit 1.50 + Plotly 6 render the literal string "undefined" where a
    # chart title would go when none is set. Every chart here is titled by an
    # st.subheader above the figure, so default untitled figures to an empty
    # title string to suppress the stray "undefined".
    if not (fig.layout.title and fig.layout.title.text):
        fig.update_layout(title_text="")
    _axis = dict(
        gridcolor=PALETTE["border"],
        zerolinecolor=PALETTE["border-soft"],
        linecolor=PALETTE["border-soft"],
        tickfont=dict(color=PALETTE["text-muted"]),
        title_font=dict(color=PALETTE["text-muted"]),
    )
    fig.update_xaxes(**_axis)
    fig.update_yaxes(**_axis)
    return fig


def value_gradient(kind: str) -> str:
    grad = {
        "primary": GRADIENT_PRIMARY,
        "danger":  GRADIENT_DANGER,
        "success": GRADIENT_SUCCESS,
    }[kind]
    return (
        f"background: {grad}; "
        "-webkit-background-clip: text; background-clip: text; "
        "-webkit-text-fill-color: transparent;"
    )


# ── HTML component helpers (unchanged) ────────────────────────────────────────
def metric_card(title: str, value, card_style: str = "", value_style: str = "", footer: str = "") -> str:
    card_attr  = f' style="{card_style}"' if card_style else ""
    value_attr = f' style="{value_style}"' if value_style else ""
    footer_html = (
        f'<div style="margin-top:10px;font-size:0.85rem;color:var(--text-muted);">{footer}</div>'
        if footer else ""
    )
    return (
        f'<div class="dashboard-card"{card_attr}>'
        f'<div class="metric-title">{title}</div>'
        f'<div class="metric-value"{value_attr}>{value}</div>'
        f'{footer_html}'
        f'</div>'
    )


def badge(text, kind: str = "info") -> str:
    # Escape the (often user-supplied) text; ``kind`` is always a trusted literal
    # used as a CSS class, so it is left as-is.
    return f'<span class="asset-badge badge-{kind}">{html.escape(str(text))}</span>'


# ── Stylesheet assembly ───────────────────────────────────────────────────────
_CSS_PATH = Path(__file__).resolve().parent.parent / "static" / "styles.css"

# Datum webfonts. @import must be the first rule in the <style> block.
_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap');"
)


def _root_block() -> str:
    rows = [f"        --{name}: {value};" for name, value in {**PALETTE, **RGB, **TOKENS}.items()]
    return "    :root {\n" + "\n".join(rows) + "\n    }"


@lru_cache(maxsize=1)
def get_css() -> str:
    body = _CSS_PATH.read_text(encoding="utf-8")
    return f"<style>\n{_FONT_IMPORT}\n{_root_block()}\n{body}\n</style>"
