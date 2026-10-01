import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import html
import io
from datetime import datetime, date
from sqlalchemy import text

APP_VERSION = "1.2.0"

# Call set_page_config as the absolute FIRST Streamlit command
st.set_page_config(
    page_title="Manufacturing Operation Database",
    layout="wide",
    initial_sidebar_state="expanded"
)

from utils.db import (get_engine, ensure_schema, finalize_service_draft,
                      create_service_record, promote_issue)
from utils import theme
from utils import queries as q
from utils import jobboss
from utils.theme import metric_card as _metric_card


# Every Plotly Express chart that doesn't pass its own colours inherits the Datum
# brand palette (single-series charts take the first colour), so nothing falls
# back to Plotly's default blues.
px.defaults.color_discrete_sequence = theme.CHART_SEQUENCE


def _plot(fig, **kwargs):
    """Render a Plotly figure with the Datum chart theme (brand font, transparent
    panel, tokenised axes) applied — the single chart-rendering path for the app."""
    return st.plotly_chart(theme.style_fig(fig), **kwargs)

# -----------------------------------------------------------------------------
# DESIGN SYSTEM CSS
# -----------------------------------------------------------------------------
st.markdown(theme.get_css(), unsafe_allow_html=True)

# This app is brand-locked to the Datum "Custom Theme" defined in
# .streamlit/config.toml. Streamlit's built-in themes (Light/Dark/"use system
# setting") override config and would mis-colour native widgets — Dark turns
# canvas widgets unreadable, and built-in Light paints accents Streamlit-red
# (#FF4B4B) instead of Datum teal. config base="light" can't override a visitor's
# saved selection, so if any built-in theme is active we clear it, reverting to
# the configured Custom Theme, and reload. Self-terminating (after the reset the
# active theme is "Custom Theme") and a session flag caps it at one reload.
components.html(
    """
    <script>
    (function () {
      try {
        var w = window.top || window.parent;
        if (!w) return;
        var badKey = null;
        for (var i = 0; i < w.localStorage.length; i++) {
          var k = w.localStorage.key(i);
          if (k && k.indexOf('stActiveTheme') === 0) {
            var v = w.localStorage.getItem(k);
            try { if (v && JSON.parse(v).name !== 'Custom Theme') badKey = k; } catch (e) {}
          }
        }
        if (badKey && !w.sessionStorage.getItem('mdbThemeLock')) {
          w.sessionStorage.setItem('mdbThemeLock', '1');
          w.localStorage.removeItem(badKey);
          w.location.reload();
        }
      } catch (e) {}
    })();
    </script>
    """,
    height=0,
)

# -----------------------------------------------------------------------------
# APP ROUTING & NAVIGATION
# -----------------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "Home"

# Remember who you are across reloads via a ?u= URL param (zero-dependency device
# persistence): seed the session identity from the URL on the first load of a session.
if "current_user" not in st.session_state:
    _u_seed = st.query_params.get("u")
    if _u_seed:
        st.session_state["current_user"] = _u_seed

# Streamlined task-based menu: 5 everyday items. Power-user pages (ERP live board,
# Records Manager, Settings) live in the sidebar "Advanced" expander, and Add/Edit
# Asset are reached from inside the Assets page — none of them appear in this menu.
_NAV_LABELS  = ["Today", "Assets", "Service", "PM Schedule", "Insights"]
_NAV_ICONS   = ["speedometer2", "hdd-stack", "wrench-adjustable", "calendar-check", "bar-chart-line"]
_NAV_TO_PAGE = {
    "Today":       "Home",
    "Assets":      "View Assets",
    "Service":     "Service Reports",
    "PM Schedule": "PM Schedule",
    "Insights":    "Reporting",
}
# Every page (including hidden/Advanced ones) maps to the menu label highlighted
# while it is open. Hidden pages park the highlight on a parent menu item.
_PAGE_TO_NAV = {
    "Home":            "Today",
    "View Assets":     "Assets",
    "Add Asset":       "Assets",
    "Edit Asset":      "Assets",
    "Service Reports": "Service",
    "PM Schedule":     "PM Schedule",
    "Reporting":       "Insights",
    "ERP Dashboard":   "Today",   # Advanced pages park the menu highlight on Today
    "Records Manager": "Today",
    "Settings":        "Today",
}
# Pages that are NOT their own menu item. The nav guard must not let the menu's
# passive return value bounce the user off one of these back to its parent label.
_HIDDEN_PAGES = {"Add Asset", "Edit Asset", "ERP Dashboard", "Records Manager", "Settings"}


def _set_page(page_name):
    """Switch pages from a button and keep the sidebar navigation in sync."""
    st.session_state.page = page_name
    label = _PAGE_TO_NAV.get(page_name)
    if label is not None:
        st.session_state["_nav_jump"] = _NAV_LABELS.index(label)


with st.sidebar:
    st.markdown('''<div class="datum-brand">
      <svg width="32" height="32" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="48" height="48" rx="10" fill="var(--ink)"/>
        <rect x="11" y="14" width="26" height="14.5" rx="2.5" stroke="var(--primary-bright)" stroke-width="2.6"/>
        <circle cx="24" cy="21.25" r="2.7" fill="var(--primary-bright)"/>
        <path d="M24 28.5v3.8" stroke="var(--primary-bright)" stroke-width="2.6" stroke-linecap="round"/>
        <path d="M20 32.2h8L24 38.5z" fill="var(--primary-bright)"/>
        <rect x="15.5" y="39.6" width="17" height="2.5" rx="1.25" fill="var(--primary-bright)"/>
      </svg>
      <div class="datum-wm"><div class="datum-name">Datum</div><div class="datum-sub">MAINTENANCE REFERENCE</div></div>
    </div>''', unsafe_allow_html=True)

    # ── Identity: pick your name (or add a new one). Stamps created_by/verified_by
    #    everywhere and persists across reloads via the ?u= URL param. ──────────────
    _ADD_NEW = "➕ Add a new name…"
    try:
        _id_engine = get_engine()
        ensure_schema()  # make sure new tables exist before the sidebar queries them
        _names = q.employee_names(_id_engine)
    except Exception:
        _id_engine, _names = None, []

    if _id_engine is not None:
        _cur_user = q.current_user()
        # A persisted/URL identity that is not a current employee must not silently
        # stamp created_by/verified_by while the picker shows "unselected": clear it
        # so q.current_user() and the visible selection agree.
        if _cur_user and _cur_user not in _names:
            q.set_current_user("")
            if "u" in st.query_params:
                del st.query_params["u"]
            _cur_user = ""
        _id_opts  = ["— Select your name —"] + _names + [_ADD_NEW]
        _id_idx   = _id_opts.index(_cur_user) if _cur_user in _names else 0
        _id_rev   = st.session_state.get("identity_rev", 0)
        _picked   = st.selectbox("You are", _id_opts, index=_id_idx, key=f"identity_select_{_id_rev}")

        if _picked == _ADD_NEW:
            _new_name = st.text_input("New name", key="identity_new_name", placeholder="First Last")
            if st.button("Add & select", use_container_width=True, key="identity_add_btn"):
                _added = q.add_employee(_id_engine, _new_name)
                if _added:
                    q.set_current_user(_added)
                    st.query_params["u"] = _added
                    st.session_state["identity_rev"] = _id_rev + 1
                    st.rerun()
                else:
                    st.warning("Enter a name first.")
        elif _picked != "— Select your name —" and _picked != _cur_user:
            q.set_current_user(_picked)
            st.query_params["u"] = _picked
            st.rerun()

    current_label = _PAGE_TO_NAV.get(st.session_state.page, "Today")
    default_idx   = _NAV_LABELS.index(current_label)

    # Button-driven navigation can request a target label through _nav_jump.
    manual_sel = st.session_state.pop("_nav_jump", None)
    if isinstance(manual_sel, int) and 0 <= manual_sel < len(_NAV_LABELS):
        default_idx = manual_sel
    elif manual_sel in _NAV_LABELS:
        default_idx = _NAV_LABELS.index(manual_sel)

    selected = st.radio(
        "Main navigation",
        _NAV_LABELS,
        index=default_idx,
        key="main_nav",
        label_visibility="collapsed",
    )

    target_page = _NAV_TO_PAGE.get(selected, "Home")
    # Let the menu drive the page only when the user actually picks a different
    # item. While a hidden page (Edit Asset, Settings, ERP live board, …) is open
    # the menu parks on a parent label and keeps returning it; without this guard
    # that passive return would bounce the user straight back to the parent page.
    on_hidden = st.session_state.page in _HIDDEN_PAGES
    if not (on_hidden and selected == current_label):
        st.session_state.page = target_page

    # At-a-glance "what needs attention" strip, mirrored from the Today cockpit.
    try:
        _ac = q.attention_counts(get_engine(), q.get_config_int(get_engine(), "pm_due_soon_days", 14))
        _bits = []
        if _ac["overdue"]:     _bits.append(f"🔴 {_ac['overdue']} PM overdue")
        if _ac["due_soon"]:    _bits.append(f"🟠 {_ac['due_soon']} due soon")
        if _ac["down"]:        _bits.append(f"⛔ {_ac['down']} down")
        if _ac["open_drafts"]: _bits.append(f"📝 {_ac['open_drafts']} drafts")
        if _ac["open_issues"]: _bits.append(f"⚠️ {_ac['open_issues']} issues")
        st.divider()
        st.caption(" · ".join(_bits) if _bits else "✅ Nothing needs attention")
    except Exception:
        pass

    st.divider()
    st.caption("Quick Links")
    st.link_button("MSC Vending Portal", "https://vending.mscdirect.com/", use_container_width=True)
    st.link_button("DMG Mori Portal", "https://us.mydmgmori.com/en-US/#/portal/inquiry/list", use_container_width=True)

    with st.expander("Advanced"):
        if st.button("ERP Live Board", use_container_width=True, key="adv_erp"):
            _set_page("ERP Dashboard"); st.rerun()
        if st.button("Records Manager", use_container_width=True, key="adv_records"):
            _set_page("Records Manager"); st.rerun()
        if st.button("Settings", use_container_width=True, key="adv_settings"):
            _set_page("Settings"); st.rerun()

    st.divider()
    if st.button("Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"v{APP_VERSION}")

# -----------------------------------------------------------------------------
# SHARED HELPERS
# -----------------------------------------------------------------------------

# _metric_card is imported from utils.theme (aliased above) so the markup lives
# next to its CSS classes; all metric cards share one definition.


def _require_db():
    """Return the SQLAlchemy engine if the database is reachable and migrated; show
    an error and return None otherwise. Connectivity and schema migration are
    reported separately so a DDL-migration failure on a reachable database is not
    mislabeled as 'Cannot connect'."""
    try:
        eng = get_engine()
        with eng.connect() as _c:
            _c.execute(text("SELECT 1"))
    except Exception as e:
        st.error(f"Cannot connect to the database: {e}")
        return None
    try:
        ensure_schema()  # apply additive migrations once per process (idempotent)
    except Exception as e:
        st.error(f"Database schema migration failed: {e}")
        return None
    return eng

# -----------------------------------------------------------------------------
# PAGE 1: HOME / DASHBOARD
# -----------------------------------------------------------------------------
def render_home_page():
    st.markdown('<div class="gradient-header">Today</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    _user = q.current_user()
    st.caption(f"{date.today().strftime('%A, %d %B %Y')}"
               + (f" · signed in as **{_user}**" if _user else " · pick your name in the sidebar"))

    soon = q.get_config_int(engine, "pm_due_soon_days", 14)
    ac = q.attention_counts(engine, soon)
    with engine.connect() as _conn:
        asset_count   = _conn.execute(text("SELECT COUNT(*) FROM assets")).scalar()
        pm_configured = _conn.execute(text("SELECT COUNT(*) FROM assets WHERE planned_pm_interval_days > 0")).scalar()
        draft_rows = _conn.execute(text(
            "SELECT report_id, asset_code, service_type, problem_description, created_at "
            "FROM service_reports WHERE record_state = 'Draft' ORDER BY created_at DESC"
        )).mappings().fetchall()

    if asset_count == 0:
        _empty_state("No assets yet", "Register your first machine to get started.", icon="📦")
        if st.button("➕ Register an asset", use_container_width=True):
            _set_page("Add Asset"); st.rerun()
        return

    # ── Attention row: 4 clickable count cards, most-urgent first ──────────────
    pm_overdue  = "—" if not pm_configured else ac["overdue"]
    pm_due_soon = "—" if not pm_configured else ac["due_soon"]
    cards = [
        ("🔴 Overdue PM",  pm_overdue,        ac["overdue"] and pm_configured, "PM Schedule", None,
         "Set PM intervals to enable" if not pm_configured else "Past due date"),
        ("🟠 PM Due Soon", pm_due_soon,       False, "PM Schedule", None,
         f"within {soon} days"),
        ("📝 Open Drafts", ac["open_drafts"], False, "Service Reports", "Edit Existing Draft", "work in progress"),
        ("⚠️ Open Issues", ac["open_issues"], False, "Service Reports", "Issues", "reported, untriaged"),
    ]
    cols = st.columns(4)
    for col, (title, val, danger, pg, sub, foot) in zip(cols, cards):
        with col:
            style = theme.value_gradient("danger") if danger else ""
            st.markdown(_metric_card(title, val, value_style=style, footer=foot), unsafe_allow_html=True)
            if st.button("View", key=f"today_{title}", use_container_width=True):
                if sub:
                    st.session_state["service_page"] = sub
                _set_page(pg); st.rerun()

    st.markdown("---")

    # ── Floor status (f7) ─────────────────────────────────────────────────────
    st.subheader("Floor status")
    _render_floor_strip(engine)
    with st.expander("Full floor board"):
        _render_floor_board(engine, with_actions=True)

    st.markdown("---")

    left_col, right_col = st.columns([2, 1])
    with left_col:
        st.subheader("Work-in-progress drafts")
        if not draft_rows:
            _empty_state("No open drafts", "Finished and finalized — nothing in progress.", icon="✅")
        else:
            for dr in draft_rows:
                asset_code    = dr["asset_code"] or "Unknown"
                creation_time = dr["created_at"].strftime("%Y-%m-%d %H:%M") if dr["created_at"] else "Unknown"
                service_type  = dr["service_type"] or "Unknown"
                problem       = dr["problem_description"] or "No description provided."
                problem_disp  = problem[:150] + '...' if len(problem) > 150 else problem
                st.markdown(f"""
                <div class="asset-item" style="border-left-color: var(--info-accent); background-color: rgba(var(--info-accent-rgb), 0.04);">
                    <div style="float:right; color:var(--info); font-weight:600; font-size:0.875rem; letter-spacing: 0.05em; text-transform: uppercase;">Draft</div>
                    <div class="asset-title">Draft — {html.escape(asset_code)}</div>
                    <div>
                        {theme.badge(service_type, "info")}
                        <span style="color:var(--text-muted); font-size:0.85rem;">Last saved: {creation_time}</span>
                    </div>
                    <div style="margin-top:10px; color:var(--text-strong); font-size:0.9rem;">
                        <strong>Problem:</strong> {html.escape(problem_disp)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"Open draft — {asset_code}", key=f"today_draft_{dr['report_id']}", use_container_width=True):
                    st.session_state.selected_draft_id = int(dr["report_id"])
                    st.session_state.service_page = "Edit Existing Draft"
                    _set_page("Service Reports"); st.rerun()

    with right_col:
        st.subheader("Quick actions")
        if st.button("🛠 Quick Log a service", use_container_width=True):
            _start_quick_log()
        if st.button("⚠️ Report an issue", use_container_width=True):
            st.session_state.service_page = "Issues"
            _set_page("Service Reports"); st.rerun()
        if st.button("📋 New service draft", use_container_width=True):
            st.session_state.service_page = "Create Service Draft"
            _set_page("Service Reports"); st.rerun()
        if st.button("➕ New asset", use_container_width=True):
            _set_page("Add Asset"); st.rerun()

# -----------------------------------------------------------------------------
# PAGE 2: ADD NEW ASSET
# -----------------------------------------------------------------------------
# Department codes are a fixed set (schema documents department_code as L/M/S/Q/E).
# Shared by the Add-Asset selectbox and the asset-code validation so they never drift.
DEPARTMENT_CODES = ["L", "M", "S", "Q", "E"]


def render_add_asset_page():
    st.markdown('<div class="gradient-header">Register New Asset</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    # Add Asset is a hidden page that parks the menu on "Assets"; clicking that
    # already-highlighted item is a no-op, so give it an explicit way back.
    if st.button("← Back to Assets", key="add_asset_back"):
        _set_page("View Assets")
        st.rerun()

    department = st.selectbox(
        "Department Code",
        DEPARTMENT_CODES,
        help="L = Lathe, M = Mill, S = Swiss, Q = Quality Control, E = Utility/Support"
    )
    
    # Auto-generate suggestion dynamically
    with engine.connect() as _conn:
        _rows = _conn.execute(
            text("SELECT asset_code FROM assets WHERE department_code = :dept"),
            {"dept": department}
        ).fetchall()
    _numbers = [int(r[0][len(department):]) for r in _rows if r[0][len(department):].isdigit()]
    next_num = max(_numbers) + 1 if _numbers else 1
    suggested_code = f"{department}{str(next_num).zfill(3)}"
    
    st.info(f"The next available code in department **{department}** is **{suggested_code}**.")
    
    # We construct a form
    with st.form("new_asset_form", clear_on_submit=False):
        
        col1, col2 = st.columns(2)
        with col1:
            asset_code = st.text_input(
                "Asset Code",
                value=suggested_code,
                help="Consists of 1 department letter and 3 sequence digits (e.g. L001)"
            )
            equipment_category = st.selectbox(
                "Equipment Category",
                ["Lathe", "Mill", "Swiss", "QC", "Support", "Other"]
            )
        with col2:
            manufacturer = st.text_input("Manufacturer", placeholder="e.g. Haas, Doosan")
            model = st.text_input("Model Name/Number", placeholder="e.g. VF-2, Lynx 2100")
            
        st.markdown("---")
        st.subheader("Technical & Distributor Information")
        
        col3, col4 = st.columns(2)
        with col3:
            serial_number = st.text_input("Serial Number")
            control_type = st.text_input("Control Type", placeholder="e.g. Fanuc, Haas, Mitsubishi")
            build_year = st.number_input("Build Year", min_value=1900, max_value=2100,
                                         value=None, step=1, format="%d", placeholder="e.g. 2024")
        with col4:
            distributor = st.text_input("Distributor Name")
            distributor_email = st.text_input("Distributor Email(s)")
            distributor_phone = st.text_input("Distributor Phone")
            
        vendor_contacts = st.text_area("Vendor / Specialist Contacts", placeholder="Notes on support engineers, repair techs, etc.")
        
        st.markdown("---")
        
        # Sub-equipments in expander for clean visual separation
        with st.expander("Additional / Sub-Equipment details (Optional)"):
            col_eq1, col_eq2, col_eq3 = st.columns(3)
            with col_eq1:
                st.markdown("#### Sub-Equipment 1")
                eq1_name = st.text_input("Name", key="eq1_name")
                eq1_make = st.text_input("Make", key="eq1_make")
                eq1_model = st.text_input("Model", key="eq1_model")
                eq1_serial = st.text_input("Serial Number", key="eq1_serial")
            with col_eq2:
                st.markdown("#### Sub-Equipment 2")
                eq2_name = st.text_input("Name", key="eq2_name")
                eq2_make = st.text_input("Make", key="eq2_make")
                eq2_model = st.text_input("Model", key="eq2_model")
                eq2_serial = st.text_input("Serial Number", key="eq2_serial")
            with col_eq3:
                st.markdown("#### Sub-Equipment 3")
                eq3_name = st.text_input("Name", key="eq3_name")
                eq3_make = st.text_input("Make", key="eq3_make")
                eq3_model = st.text_input("Model", key="eq3_model")
                eq3_serial = st.text_input("Serial Number", key="eq3_serial")
                
        # Batteries in expander
        with st.expander("Backup Battery Configuration (Optional)"):
            col_bat1, col_bat2 = st.columns(2)
            with col_bat1:
                st.markdown("#### Battery 1")
                battery_1_desc = st.text_input("Description", placeholder="e.g. Fanuc CNC Memory backup")
                battery_1_part = st.text_input("Part Number")
                battery_1_interval = st.number_input("Replacement Interval (Days)", min_value=0, value=365, step=30)
            with col_bat2:
                st.markdown("#### Battery 2")
                battery_2_desc = st.text_input("Description", placeholder="e.g. Main drive encoder backup")
                battery_2_part = st.text_input("Part Number", key="bat2_part")
                battery_2_interval = st.number_input("Replacement Interval (Days)", min_value=0, value=0, step=30, key="bat2_interval")
                
        submit = st.form_submit_button("Register Asset", use_container_width=True)
        
    if submit:
        # Form Validation
        asset_code = asset_code.strip().upper()
        if not asset_code:
            st.error("Asset Code is required")
            st.stop()
            
        if len(asset_code) != 4 or asset_code[0] not in DEPARTMENT_CODES or not asset_code[1:].isdigit():
            st.error("Asset Code must be one of " + "/".join(DEPARTMENT_CODES) +
                     " followed by three numbers (e.g. L001, M002)")
            st.stop()
            
        model_clean = model.strip()
        short_name = f"{asset_code}-{model_clean}" if model_clean else asset_code

        # Check uniqueness
        with engine.connect() as _conn:
            _exists = _conn.execute(
                text("SELECT 1 FROM assets WHERE asset_code = :code"),
                {"code": asset_code}
            ).fetchone()
        if _exists:
            st.error(f"An asset with code {asset_code} already exists in the system!")
            st.stop()
            
        try:
            with engine.connect() as _conn:
                _conn.execute(text("""
                    INSERT INTO assets (
                        asset_id, asset_code, department_code, sequence_number,
                        display_name, short_name, equipment_category,
                        manufacturer, model, serial_number, control_type, build_year,
                        distributor, distributor_email, distributor_phone, vendor_contacts,
                        template_version, registry_creation_date
                    ) VALUES (
                        :asset_id, :asset_code, :dept_code, :seq_num,
                        :display_name, :short_name, :category,
                        :manufacturer, :model, :serial_number, :control_type, :build_year,
                        :distributor, :distributor_email, :distributor_phone, :vendor_contacts,
                        '1.0', NOW()
                    )
                """), {
                    "asset_id":        f"A-{asset_code}",
                    "asset_code":      asset_code,
                    "dept_code":       asset_code[0],
                    "seq_num":         asset_code[1:],
                    "display_name":    short_name,
                    "short_name":      short_name,
                    "category":        equipment_category,
                    "manufacturer":    manufacturer.strip(),
                    "model":           model.strip(),
                    "serial_number":   serial_number.strip(),
                    "control_type":    control_type.strip(),
                    "build_year":      int(build_year) if build_year is not None else None,
                    "distributor":     distributor.strip(),
                    "distributor_email": distributor_email.strip(),
                    "distributor_phone": distributor_phone.strip(),
                    "vendor_contacts": vendor_contacts.strip(),
                })

                for n, (desc, part, interval) in enumerate([
                    (battery_1_desc, battery_1_part, battery_1_interval),
                    (battery_2_desc, battery_2_part, battery_2_interval),
                ], start=1):
                    if desc or part:
                        _conn.execute(text("""
                            INSERT INTO asset_batteries
                                (asset_id, battery_number, description, part_number, replacement_interval_days)
                            VALUES (:aid, :n, :desc, :part, :interval)
                        """), {"aid": f"A-{asset_code}", "n": n, "desc": desc,
                               "part": part, "interval": interval or 0})

                for n, (name, make, mdl, serial) in enumerate([
                    (eq1_name, eq1_make, eq1_model, eq1_serial),
                    (eq2_name, eq2_make, eq2_model, eq2_serial),
                    (eq3_name, eq3_make, eq3_model, eq3_serial),
                ], start=1):
                    if name:
                        _conn.execute(text("""
                            INSERT INTO asset_peripheral_equipment
                                (asset_id, equip_number, name, make, model, serial_number)
                            VALUES (:aid, :n, :name, :make, :model, :serial)
                        """), {"aid": f"A-{asset_code}", "n": n, "name": name,
                               "make": make, "model": mdl, "serial": serial})

                _conn.commit()

            st.cache_data.clear()  # invalidate cached fleet aggregates (PM schedule, badges) after the write
            st.success(f"Asset **{short_name}** successfully created and saved to registry!")
            st.balloons()
            st.rerun()

        except Exception as e:
            st.error(f"Error creating asset: {e}")

# -----------------------------------------------------------------------------
# PAGE 3: VIEW ASSETS REGISTRY
# -----------------------------------------------------------------------------
def render_view_assets_page():
    st.markdown('<div class="gradient-header">Asset Registry</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    action_add, action_refresh, _ = st.columns([1.2, 1.2, 4])
    with action_add:
        if st.button("Add Asset", key="asset_add_top", use_container_width=True):
            _set_page("Add Asset")
            st.rerun()
    with action_refresh:
        if st.button("Refresh Assets", key="asset_refresh_top", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    assets_df = pd.read_sql_query("""
        SELECT a.asset_id, a.asset_code, a.manufacturer, a.model, a.serial_number,
               a.equipment_category, a.build_year, a.control_type, a.distributor,
               a.distributor_email, a.distributor_phone, a.vendor_contacts,
               a.known_quirks, a.special_tooling, a.installation_notes, a.reference_document,
               b.description          AS battery_1_desc,
               b.replacement_interval_days AS battery_1_interval,
               (SELECT COUNT(*) FROM asset_peripheral_equipment p WHERE p.asset_id = a.asset_id) AS eq_count,
               (SELECT COUNT(*) FROM service_reports sr WHERE sr.asset_id = a.asset_id AND sr.record_state = 'Final') AS report_count
        FROM assets a
        LEFT JOIN asset_batteries b ON a.asset_id = b.asset_id AND b.battery_number = 1
        ORDER BY a.asset_id
    """, engine)
    equip_df = pd.read_sql_query(
        "SELECT asset_id, equip_number, name, make, model, serial_number FROM asset_peripheral_equipment ORDER BY asset_id, equip_number",
        engine
    )

    if assets_df.empty:
        st.info("No registered assets found. Click **Add Asset** to register one.")
        return
    equip_by_asset = (
        {aid: grp.to_dict("records") for aid, grp in equip_df.groupby("asset_id")}
        if not equip_df.empty else {}
    )

    # Search bar & Filters
    col_search, col_filter = st.columns([2, 1])
    with col_search:
        search_query = st.text_input("Search Assets", placeholder="Search by Code, Manufacturer, Model, or Serial...")
    with col_filter:
        cat_filter = st.selectbox("Category Filter", ["All", "Lathe", "Mill", "Swiss", "QC", "Support", "Other"])

    filtered_assets = []
    for _, row in assets_df.iterrows():
        code         = row["asset_code"] or ""
        manufacturer = row["manufacturer"] or ""
        model_val    = row["model"] or ""
        serial       = row["serial_number"] or ""
        category     = row["equipment_category"] or "Other"
        build_year   = str(int(row["build_year"])) if pd.notna(row["build_year"]) else ""
        control      = row["control_type"] or ""
        distributor  = row["distributor"] or ""

        match_str = f"{code} {manufacturer} {model_val} {serial} {category} {control}".lower()
        if search_query.lower() in match_str:
            if cat_filter == "All" or category == cat_filter:
                b1_interval = row["battery_1_interval"]
                has_battery = bool(row["battery_1_desc"]) and pd.notna(b1_interval) and int(b1_interval) > 0
                filtered_assets.append({
                    "asset_id":         row["asset_id"],
                    "code":             code,
                    "manufacturer":     manufacturer,
                    "model":            model_val,
                    "serial":           serial,
                    "category":         category,
                    "build_year":       build_year,
                    "control":          control,
                    "distributor":      distributor,
                    "distributor_email": row["distributor_email"] or "N/A",
                    "distributor_phone": row["distributor_phone"] or "N/A",
                    "vendor_contacts":  row["vendor_contacts"] or "None",
                    "has_battery":      has_battery,
                    "battery_desc":     row["battery_1_desc"],
                    "battery_interval": b1_interval,
                    "has_eq":           row["eq_count"] > 0,
                    "equipment":        equip_by_asset.get(row["asset_id"], []),
                    "report_count":     row["report_count"],
                    "known_quirks":     row["known_quirks"],
                    "special_tooling":  row["special_tooling"],
                    "installation_notes": row["installation_notes"],
                    "reference_document": row["reference_document"],
                })

    st.write(f"Showing **{len(filtered_assets)}** of **{len(assets_df)}** registered assets:")
    
    # Display List
    for a in filtered_assets:
        final_reports_count = int(a["report_count"])
        
        # Determine battery replacement notice.
        # Keep this on a single line with no leading indentation: a blank/indented
        # line here would close the card's HTML block and Streamlit would render
        # the markup as an indented code block instead of styled HTML.
        battery_notice = ""
        if a["has_battery"]:
            battery_notice = (
                f'<div class="battery-alert"><strong>Battery Tracked:</strong> '
                f"{html.escape(str(a['battery_desc']))} (Interval: {a['battery_interval']} days)</div>"
            )

        st.markdown(f"""
        <div class="asset-item">
            <div style="float: right; color: var(--text-muted); font-weight: 500; font-size: 0.9rem;">
                {html.escape(a['category'])}
            </div>
            <div class="asset-title">{html.escape(a['manufacturer'])} {html.escape(a['model'])} ({html.escape(a['code'])})</div>
            <div>
                {theme.badge(f"SN: {a['serial']}", "info")}
                {theme.badge(f"Control: {a['control']}", "primary")}
                {theme.badge(f"Reports: {final_reports_count}", "success")}
            </div>
            {battery_notice}
        </div>
        """, unsafe_allow_html=True)

        action_edit, action_delete, _ = st.columns([1, 1, 5])
        with action_edit:
            if st.button("Edit Asset", key=f"edit_top_{a['asset_id']}", use_container_width=True):
                st.session_state.edit_asset_id = a["asset_id"]
                _set_page("Edit Asset")
                st.rerun()
        with action_delete:
            if st.button("Delete Asset", key=f"del_top_{a['asset_id']}", use_container_width=True):
                st.session_state.pending_delete_asset = a["asset_id"]
                st.rerun()
        
        # Expanding details drawer
        with st.expander(f"Show Detailed Specification for {a['code']}"):
            detail_col1, detail_col2 = st.columns(2)
            with detail_col1:
                st.markdown(f"""
                **Manufacturer:** {a['manufacturer']}
                **Model:** {a['model']}
                **Serial Number:** {a['serial']}
                **Build Year:** {a['build_year']}
                **Control System:** {a['control']}
                """)
            with detail_col2:
                st.markdown(f"""
                **Distributor:** {a['distributor']}
                **Distributor Email:** {a['distributor_email']}
                **Distributor Phone:** {a['distributor_phone']}
                **Vendor Contacts:** {a['vendor_contacts']}
                """)

            # Machine Knowledge card (f5): surface the tribal-knowledge fields that
            # are captured at registration but never shown on the read path.
            _render_knowledge_card(a)

            # Additional equipment sub-view
            if a["has_eq"]:
                st.markdown("---")
                st.markdown("**Sub-Equipment Linked:**")
                for eq in a["equipment"]:
                    st.markdown(f"- **{eq['name']}** | Make: {eq['make'] or 'N/A'} | Model: {eq['model'] or 'N/A'} | SN: {eq['serial_number'] or 'N/A'}")
                        
            # Service reports history from DB
            if final_reports_count > 0:
                st.markdown("---")
                st.markdown("**Finalized Maintenance History:**")
                rpts_df = pd.read_sql_query(
                    text("SELECT service_id, finalized_at FROM service_reports "
                         "WHERE asset_id = :aid AND record_state = 'Final' "
                         "ORDER BY finalized_at DESC"),
                    engine,
                    params={"aid": a["asset_id"]}
                )
                for _, rpt in rpts_df.iterrows():
                    fin_date = rpt["finalized_at"].strftime("%Y-%m-%d") if rpt["finalized_at"] is not None else "N/A"
                    st.markdown(f"`{rpt['service_id']}` (Date completed: {fin_date})")

            # Documents (f6): manuals / PM sheets / registries for this asset.
            _render_asset_documents(engine, a["asset_id"], a["code"])

        if st.session_state.get("pending_delete_asset") == a["asset_id"]:
            st.warning(f"Delete **{a['asset_id']}** permanently?")
            cc1, cc2 = st.columns(2)
            with cc1:
                if st.button("Yes, Delete", key=f"confirm_del_{a['asset_id']}"):
                    with engine.connect() as conn:
                        conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": a["asset_id"]})
                        conn.execute(text("DELETE FROM asset_batteries WHERE asset_id = :id"), {"id": a["asset_id"]})
                        conn.execute(text("DELETE FROM assets WHERE asset_id = :id"), {"id": a["asset_id"]})
                        conn.commit()
                    st.cache_data.clear()  # drop the deleted asset from cached aggregates
                    st.session_state.pop("pending_delete_asset", None)
                    st.rerun()
            with cc2:
                if st.button("Cancel", key=f"cancel_del_{a['asset_id']}"):
                    st.session_state.pop("pending_delete_asset", None)
                    st.rerun()

        st.markdown("<hr style='border-color: var(--bg-muted); margin: 8px 0;'>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# PAGE 4: SERVICE REPORTS (DRAFTS & FINALIZATION WORKFLOW)
# -----------------------------------------------------------------------------
def render_service_page():
    st.markdown('<div class="gradient-header">Service Reports Manager</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    # Sub navigation selector with default handling
    if "service_page" not in st.session_state:
        st.session_state.service_page = "Quick Log"
    options = ["Quick Log", "Dashboard Overview", "Create Service Draft",
               "Edit Existing Draft", "Finalize Service Draft", "Fix History", "Issues"]
    selected_index = 0
    if st.session_state.service_page in options:
        selected_index = options.index(st.session_state.service_page)
    st.session_state.service_page = st.selectbox(
        "Service Action",
        options,
        index=selected_index
    )

    subpage = st.session_state.service_page

    # Load registered assets from PostgreSQL (source of truth)
    with engine.connect() as _c:
        _asset_rows = _c.execute(
            text("SELECT asset_code, display_name FROM assets ORDER BY asset_code")
        ).fetchall()
    registered_assets = [
        {"code": r[0], "label": r[1] or r[0]}
        for r in _asset_rows
    ]

    # -------------------------------------
    # SUBPAGE: QUICK LOG  (one-screen capture; built in Phase 3)
    # -------------------------------------
    if subpage == "Quick Log":
        _render_quick_log(engine, registered_assets)

    # -------------------------------------
    # SUBPAGE A: SERVICE OVERVIEW
    # -------------------------------------
    elif subpage == "Dashboard Overview":
        with engine.connect() as _c:
            _draft_count = _c.execute(
                text("SELECT COUNT(*) FROM service_reports WHERE record_state = 'Draft'")
            ).scalar()
        st.markdown(_metric_card("Total Open Drafts", _draft_count, card_style="max-width: 320px"), unsafe_allow_html=True)

        drafts_df = pd.read_sql_query(
            "SELECT report_id, asset_code, service_type, created_at "
            "FROM service_reports WHERE record_state = 'Draft' ORDER BY created_at DESC",
            engine
        )
        if not drafts_df.empty:
            st.markdown("### Open Draft Records")
            for _, d in drafts_df.iterrows():
                stype = d["service_type"] or "Unknown type"
                col_d1, col_d2 = st.columns([4, 1])
                with col_d1:
                    st.markdown(f"**{d['asset_code']}** — {stype}")
                with col_d2:
                    if st.button("Edit", key=f"edit_dr_{int(d['report_id'])}"):
                        st.session_state.selected_draft_id = int(d["report_id"])
                        st.session_state.service_page = "Edit Existing Draft"
                        st.rerun()
        else:
            st.info("All drafts are finalized. Click 'Create Service Draft' to begin a new record!")

    # -------------------------------------
    # SUBPAGE B: CREATE DRAFT
    # -------------------------------------
    elif subpage == "Create Service Draft":
        st.subheader("Create New Service Draft")

        if not registered_assets:
            st.warning("You must register at least one asset before creating service drafts.")
            return

        selected_asset = st.selectbox(
            "Select Target Asset",
            registered_assets,
            format_func=lambda a: f"{a['code']} — {a['label']}"
        )

        service_type = st.selectbox(
            "Service Type / Classification",
            ["Preventive", "Corrective", "Emergency"]
        )

        asset_code = selected_asset["code"]

        if st.button("Create Draft Record", use_container_width=True):
            with engine.connect() as _c:
                existing = _c.execute(
                    text("SELECT 1 FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"),
                    {"code": asset_code}
                ).fetchone()
            if existing:
                st.error(f"A work draft already exists for asset '{asset_code}'! Edit the existing draft or finalize it.")
            else:
                try:
                    with engine.connect() as _c:
                        _c.execute(text("""
                            INSERT INTO service_reports
                                (asset_id, asset_code, record_state, service_type, created_by, entry_timestamp)
                            VALUES (:aid, :code, 'Draft', :stype, :cby, NOW())
                        """), {"aid": f"A-{asset_code}", "code": asset_code, "stype": service_type,
                               "cby": q.current_user() or None})
                        _c.commit()
                    st.cache_data.clear()  # new draft -> refresh cached attention badges
                    st.success(f"Created service draft for asset {asset_code}!")
                    st.session_state.service_page = "Edit Existing Draft"
                    st.rerun()
                except Exception as e:
                    _m = str(getattr(e, "orig", e)).lower()
                    if "uq_one_open_draft" in _m or "duplicate key" in _m or "unique" in _m:
                        st.error(f"A work draft already exists for asset '{asset_code}'! Edit the existing draft or finalize it.")
                    else:
                        st.error(f"Failed to create draft: {e}")

    # -------------------------------------
    # SUBPAGE C: EDIT DRAFT
    # -------------------------------------
    elif subpage == "Edit Existing Draft":
        st.subheader("Edit Work-in-Progress Service Draft")

        drafts_df = pd.read_sql_query(
            "SELECT report_id, asset_code, service_type, created_at "
            "FROM service_reports WHERE record_state = 'Draft' ORDER BY created_at DESC",
            engine
        )
        if drafts_df.empty:
            st.warning("No drafts are currently open.")
            return

        default_idx = 0
        sel_id = st.session_state.get("selected_draft_id")
        if sel_id:
            ids = drafts_df["report_id"].tolist()
            if sel_id in ids:
                default_idx = ids.index(sel_id)

        def _draft_label(row):
            ts = row["created_at"].strftime("%Y-%m-%d") if row["created_at"] is not None else "N/A"
            return f"{row['asset_code']} — {row['service_type'] or 'No type'} (created {ts})"

        options_list = [(int(row["report_id"]), _draft_label(row)) for _, row in drafts_df.iterrows()]
        selected_opt = st.selectbox(
            "Select Draft to Modify",
            options_list,
            index=default_idx,
            format_func=lambda x: x[1],
            key="draft_selector"
        )
        report_id = selected_opt[0]

        draft_df = pd.read_sql_query(
            "SELECT * FROM service_reports WHERE report_id = %(rid)s",
            engine,
            params={"rid": report_id}
        )
        if draft_df.empty:
            st.error("Draft not found.")
            return
        draft = draft_df.iloc[0]

        problem   = st.text_area("Problem / Fault Description",     value=draft["problem_description"] or "")
        work_done = st.text_area("Action Taken / Work Performed",    value=draft["work_performed"] or "")

        issue_opts = ["", "Mechanical", "Electrical", "Pneumatic", "Hydraulic",
                      "Software", "Operator / Process", "Other", "Unknown"]
        cause_opts = ["", "Wear", "Misalignment", "Contamination", "Electrical Fault",
                      "Software / Parameters", "Installation Error", "Damage", "Unknown"]

        col_cls1, col_cls2 = st.columns(2)
        with col_cls1:
            _ic_val   = draft.get("issue_category") or ""
            issue_idx = issue_opts.index(_ic_val) if _ic_val in issue_opts else 0
            issue_category = st.selectbox("Issue Category", issue_opts, index=issue_idx,
                                          format_func=lambda x: x or "— Not set —")
        with col_cls2:
            _rc_val   = draft.get("root_cause") or ""
            cause_idx = cause_opts.index(_rc_val) if _rc_val in cause_opts else 0
            root_cause = st.selectbox("Root Cause", cause_opts, index=cause_idx,
                                      format_func=lambda x: x or "— Not set —")

        col_inp1, col_inp2 = st.columns(2)
        with col_inp1:
            downtime_val = float(draft["downtime_hours"]) if draft["downtime_hours"] is not None else 0.0
            downtime = st.number_input("Downtime (Hours)", min_value=0.0, value=downtime_val, step=0.5)
            _rts_val = draft["return_to_service"]
            rts_idx  = {"Yes": 1, "No": 2}.get(_rts_val, 0)
            return_to_service = st.selectbox("Return To Service?", ["Pending", "Yes", "No"], index=rts_idx)
        with col_inp2:
            verified_by = st.text_input("Report Compiled / Verified By", value=draft["verified_by"] or "")

        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn1:
            if st.button("Save Changes to Draft", use_container_width=True):
                with engine.connect() as _c:
                    _c.execute(text("""
                        UPDATE service_reports SET
                            issue_category      = :ic,
                            root_cause          = :rc,
                            problem_description = :prob,
                            work_performed      = :work,
                            downtime_hours      = :dt,
                            return_to_service   = :rts,
                            verified_by         = :vb,
                            updated_at          = NOW()
                        WHERE report_id = :id
                    """), {
                        "ic":   issue_category or None,
                        "rc":   root_cause or None,
                        "prob": problem.strip(),
                        "work": work_done.strip(),
                        "dt":   downtime,
                        "rts":  return_to_service,
                        "vb":   verified_by.strip(),
                        "id":   report_id,
                    })
                    _c.commit()
                st.success("Draft saved successfully!")

        with col_btn2:
            if st.button("Finalize This Draft", use_container_width=True):
                st.session_state.service_page = "Finalize Service Draft"
                st.session_state.selected_draft_id = report_id
                st.rerun()

        with col_btn3:
            if st.button("Delete Draft", use_container_width=True, key="delete_draft_btn"):
                st.session_state.show_delete_confirmation = True

        if st.session_state.get("show_delete_confirmation", False):
            st.warning(f"You are about to delete this draft for **{draft['asset_code']}**. This cannot be undone.")
            col_confirm1, col_confirm2 = st.columns(2)
            with col_confirm1:
                if st.button("Delete Permanently", use_container_width=True, key="confirm_delete"):
                    try:
                        with engine.connect() as _c:
                            _c.execute(text("DELETE FROM service_reports WHERE report_id = :id"), {"id": report_id})
                            _c.commit()
                        st.cache_data.clear()  # draft removed -> refresh cached attention badges
                        st.session_state.show_delete_confirmation = False
                        st.session_state.selected_draft_id = None
                        st.success("Draft deleted successfully!")
                        st.session_state.service_page = "Dashboard Overview"
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting draft: {e}")
                        st.session_state.show_delete_confirmation = False
            with col_confirm2:
                if st.button("Cancel", use_container_width=True, key="cancel_delete"):
                    st.session_state.show_delete_confirmation = False
                    st.rerun()

        # ── Parts used on this draft ──────────────────────────────────────────
        st.divider()
        st.markdown("##### Parts Used")

        parts_df = pd.read_sql_query(
            "SELECT id, part_name, quantity, is_battery FROM service_parts "
            "WHERE report_id = %(rid)s ORDER BY id",
            engine,
            params={"rid": report_id}
        )
        if parts_df.empty:
            st.caption("No parts recorded for this draft yet.")
        else:
            for _, prow in parts_df.iterrows():
                pc1, pc2, pc3, pc4 = st.columns([5, 1, 2, 1])
                pc1.write(prow["part_name"])
                pc2.write(f"× {int(prow['quantity'])}")
                pc3.write("Battery" if prow["is_battery"] else "Part")
                if pc4.button("Remove", key=f"del_part_{int(prow['id'])}"):
                    with engine.connect() as _c:
                        _c.execute(text("DELETE FROM service_parts WHERE id = :pid"),
                                   {"pid": int(prow["id"])})
                        _c.commit()
                    st.rerun()

        with st.form(f"add_part_form_{report_id}", clear_on_submit=True):
            ap1, ap2, ap3 = st.columns([5, 1, 2])
            new_part_name = ap1.text_input("Part name")
            new_part_qty  = ap2.number_input("Qty", min_value=1, value=1, step=1)
            new_part_batt = ap3.checkbox("Battery replacement")
            if st.form_submit_button("Add Part", use_container_width=True):
                if new_part_name.strip():
                    with engine.connect() as _c:
                        _c.execute(text("""
                            INSERT INTO service_parts (report_id, part_name, quantity, is_battery)
                            VALUES (:rid, :name, :qty, :batt)
                        """), {
                            "rid":  report_id,
                            "name": new_part_name.strip(),
                            "qty":  int(new_part_qty),
                            "batt": bool(new_part_batt),
                        })
                        _c.commit()
                    st.rerun()
                else:
                    st.warning("Enter a part name before adding.")

    # -------------------------------------
    # SUBPAGE D: FINALIZE SERVICE REPORT
    # -------------------------------------
    elif subpage == "Finalize Service Draft":
        st.subheader("Lock & Finalize Service Record")

        drafts_df = pd.read_sql_query(
            "SELECT report_id, asset_code, service_type, created_at "
            "FROM service_reports WHERE record_state = 'Draft' ORDER BY created_at DESC",
            engine
        )
        if drafts_df.empty:
            st.warning("No drafts are currently open.")
            return

        default_idx = 0
        sel_id = st.session_state.get("selected_draft_id")
        if sel_id:
            ids = drafts_df["report_id"].tolist()
            if sel_id in ids:
                default_idx = ids.index(sel_id)

        options_list = [(int(row["report_id"]), f"{row['asset_code']} — {row['service_type'] or 'No type'}") for _, row in drafts_df.iterrows()]
        selected_opt = st.selectbox(
            "Select Draft to Finalize",
            options_list,
            index=default_idx,
            format_func=lambda x: x[1],
            key="finalize_draft_selector"
        )
        report_id = selected_opt[0]

        draft_df = pd.read_sql_query(
            "SELECT * FROM service_reports WHERE report_id = %(rid)s",
            engine,
            params={"rid": report_id}
        )
        if draft_df.empty:
            st.error("Draft not found.")
            return
        draft = draft_df.iloc[0]

        asset_code = draft["asset_code"] or ""
        prob       = draft["problem_description"] or ""
        work       = draft["work_performed"] or ""
        dt_val     = draft["downtime_hours"] or 0.0
        verifier   = draft["verified_by"] or ""
        issue_cat  = draft.get("issue_category") or "—"
        root_c     = draft.get("root_cause") or "—"

        st.info("Please review all service details. Finalization locks this record as an immutable historical record.")
        st.markdown(f"""
        **Review Details:**
        - **Asset Code:** `{asset_code}`
        - **Issue Category:** {issue_cat}
        - **Root Cause:** {root_c}
        - **Problem Description:** {prob}
        - **Work Performed:** {work}
        - **Downtime Hours:** {dt_val} hours
        - **Verified By:** {verifier}
        """)

        fin_parts = pd.read_sql_query(
            "SELECT part_name, quantity, is_battery FROM service_parts "
            "WHERE report_id = %(rid)s ORDER BY id",
            engine,
            params={"rid": report_id}
        )
        if not fin_parts.empty:
            parts_lines = "\n".join(
                f"- {pr['part_name']} × {int(pr['quantity'])}" + (" (battery)" if pr["is_battery"] else "")
                for _, pr in fin_parts.iterrows()
            )
            st.markdown(f"**Parts Used:**\n{parts_lines}")

        if not verifier.strip():
            st.warning("**Verified By** is a required field. Go back to 'Edit Existing Draft' and fill it in before finalization!")
            return

        if draft["return_to_service"] not in ("Yes", "No"):
            st.warning("**Return To Service** must be set to Yes or No. Go back to 'Edit Existing Draft' and set it before finalization!")
            return

        st.warning("**Warning**: Finalization is permanent and cannot be undone.")

        if st.button("Lock & Finalize Record", use_container_width=True):
            try:
                # Shared one-transaction finalize: generates the service_id, computes
                # the event cost from rates + parts, and flips the record to Final.
                final_id = finalize_service_draft(
                    engine, report_id,
                    created_by=q.current_user() or None,
                    verified_by=verifier,
                )
                st.success(f"Service finalized successfully! Record ID: `{final_id}`")
                st.balloons()
                st.session_state.service_page = "Dashboard Overview"
                st.session_state.selected_draft_id = None
                st.rerun()
            except ValueError as e:
                st.warning(str(e))
            except Exception as e:
                st.error(f"Error finalizing service report: {e}")

    # -------------------------------------
    # SUBPAGE: FIX HISTORY  (f3 — searchable cross-fleet repair history)
    # -------------------------------------
    elif subpage == "Fix History":
        _render_fix_history(engine)

    # -------------------------------------
    # SUBPAGE: ISSUES  (f8 — capture + triage inbox; built in Phase 3)
    # -------------------------------------
    elif subpage == "Issues":
        _render_issues_inbox(engine, registered_assets)


_ISSUE_CATEGORIES = ["Mechanical", "Electrical", "Pneumatic", "Hydraulic", "Software",
                     "Operator / Process", "Other", "Unknown"]
_ROOT_CAUSES = ["Wear", "Misalignment", "Contamination", "Electrical Fault",
                "Software / Parameters", "Installation Error", "Damage", "Unknown"]


def _render_quick_log(engine, registered_assets):
    """f9 — one-screen service capture: everything (incl. parts) on a single form,
    with two outcomes — save as a draft, or log & finalize in one atomic submit."""
    st.subheader("Quick Log a service event")
    st.caption("Capture a whole service event on one screen. Save it as a draft to "
               "finish later, or log & finalize immediately.")

    if not registered_assets:
        st.warning("Register at least one asset before logging service.")
        return

    prefill = st.session_state.get("ql_prefill") or {}
    codes = [a["code"] for a in registered_assets]
    pre_code = prefill.get("asset_code")
    a_idx = codes.index(pre_code) if pre_code in codes else 0
    pre_type = prefill.get("service_type") or "Corrective"
    t_idx = ["Preventive", "Corrective", "Emergency"].index(pre_type) if pre_type in ("Preventive", "Corrective", "Emergency") else 1

    asset = st.selectbox("Machine", registered_assets, index=a_idx,
                         format_func=lambda a: f"{a['code']} — {a['label']}")
    c1, c2 = st.columns(2)
    with c1:
        service_type = st.selectbox("Service type", ["Preventive", "Corrective", "Emergency"], index=t_idx)
        issue_category = st.selectbox("Issue category", _ISSUE_CATEGORIES, index=len(_ISSUE_CATEGORIES) - 1)
        downtime = st.number_input("Downtime (hours)", min_value=0.0, step=0.5, value=0.0)
    with c2:
        root_cause = st.selectbox("Root cause", _ROOT_CAUSES, index=len(_ROOT_CAUSES) - 1)
        return_to_service = st.selectbox("Returned to service?", ["Yes", "No"], index=0)
        verified_by = st.text_input("Verified by", value=q.current_user())

    problem = st.text_area("Problem / symptom", placeholder="What was wrong?")
    work = st.text_area("Work performed", placeholder="What did you do to fix it?")

    st.markdown("**Parts used** (optional)")
    parts_seed = pd.DataFrame([{"part_name": "", "quantity": 1, "is_battery": False, "unit_cost": None}])
    parts_edit = st.data_editor(
        parts_seed, num_rows="dynamic", use_container_width=True, key="ql_parts",
        column_config={
            "part_name": st.column_config.TextColumn("Part"),
            "quantity": st.column_config.NumberColumn("Qty", min_value=1, step=1),
            "is_battery": st.column_config.CheckboxColumn("Battery?"),
            "unit_cost": st.column_config.NumberColumn("Unit cost ($)", min_value=0.0, format="%.2f"),
        })
    parts = [p for p in parts_edit.to_dict("records") if (p.get("part_name") or "").strip()]

    fields = {
        "problem_description": problem.strip() or None,
        "work_performed": work.strip() or None,
        "downtime_hours": float(downtime),
        "return_to_service": return_to_service,
        "verified_by": verified_by.strip() or None,
        "issue_category": issue_category,
        "root_cause": root_cause,
    }

    b1, b2 = st.columns(2)
    with b1:
        save_draft = st.button("💾 Save as draft", use_container_width=True)
    with b2:
        log_final = st.button("✅ Log & finalize", use_container_width=True, type="primary")

    if save_draft or log_final:
        # Block a duplicate open draft for the same asset (DB enforces it too).
        with engine.connect() as _c:
            dup = _c.execute(text(
                "SELECT 1 FROM service_reports WHERE asset_code = :code AND record_state = 'Draft'"
            ), {"code": asset["code"]}).fetchone()
        if dup:
            st.error(f"An open draft already exists for {asset['code']}. Edit or finalize it first.")
            return
        if log_final and not verified_by.strip():
            st.warning("**Verified by** is required to finalize. Fill it in or save as a draft instead.")
            return
        try:
            rid, sid = create_service_record(
                engine, asset_code=asset["code"], service_type=service_type,
                fields=fields, parts=parts, finalize=bool(log_final),
                created_by=q.current_user() or None)
            st.cache_data.clear()
            st.session_state.pop("ql_prefill", None)
            st.session_state.pop("ql_parts", None)  # reset the parts grid so its rows don't carry into the next log
            if log_final:
                st.success(f"Logged & finalized — `{sid}`")
                st.balloons()
            else:
                st.success("Draft saved. Find it under **Edit Existing Draft**.")
                st.session_state.selected_draft_id = int(rid)
            st.rerun()
        except ValueError as e:
            st.warning(str(e))
        except Exception as e:
            st.error(f"Could not save: {e}")


def _promote_issue(engine, row):
    """UI wrapper around db.promote_issue: promote then jump to the draft editor."""
    try:
        rid = promote_issue(engine, int(row["id"]), created_by=q.current_user() or None)
        st.cache_data.clear()
        st.session_state.selected_draft_id = int(rid)
        st.session_state.service_page = "Edit Existing Draft"
        st.success("Promoted to a service draft.")
        st.rerun()
    except ValueError as e:
        st.warning(str(e))
    except Exception as e:
        st.error(f"Could not promote: {e}")


def _render_issues_inbox(engine, registered_assets):
    """f8 — fast personal 'noticed a problem' inbox: capture, triage, promote."""
    st.subheader("Issues — report & triage")

    with st.expander("➕ Report an issue", expanded=True):
        with st.form("new_issue_form", clear_on_submit=True):
            a = st.selectbox("Machine", registered_assets,
                             format_func=lambda a: f"{a['code']} — {a['label']}")
            note = st.text_area("What did you notice?",
                                placeholder="e.g. grinding noise from the spindle at high RPM")
            pri = st.selectbox("Priority", ["High", "Normal", "Low"], index=1)
            if st.form_submit_button("Log issue", use_container_width=True):
                if not note.strip():
                    st.warning("Describe the issue first.")
                else:
                    code = a["code"] if a else None
                    with engine.begin() as c:
                        c.execute(text("""
                            INSERT INTO machine_issues (asset_code, asset_id, note, priority, created_by)
                            VALUES (:code, :aid, :note, :pri, :by)
                        """), {"code": code, "aid": f"A-{code}" if code else None,
                               "note": note.strip(), "pri": pri, "by": q.current_user() or None})
                    st.cache_data.clear()
                    st.success("Issue logged.")
                    st.rerun()

    df = q.open_issues_df(engine)
    if df.empty:
        _empty_state("No open issues", "Nothing on the list. Use the form above when you spot a problem.")
        return

    st.markdown(f"**{len(df)}** open issue(s).")
    _pri_kind = {"High": "primary", "Normal": "info", "Low": "neutral"}
    for _, r in df.iterrows():
        created = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] is not None else ""
        who = f" · {html.escape(str(r['created_by']))}" if r["created_by"] else ""
        code_disp = html.escape(str(r['asset_code'])) if r['asset_code'] else 'Unassigned'
        note_disp = html.escape(str(r['note'] or '')).replace("\n", "<br>")
        st.markdown(f"""
        <div class="asset-item">
            <div style="float:right;color:var(--text-muted);font-size:0.82rem;">{created}{who}</div>
            <div class="asset-title">{code_disp}</div>
            <div style="margin:4px 0;">{theme.badge(r['priority'] or 'Normal', _pri_kind.get(r['priority'], 'info'))}</div>
            <div style="font-size:0.92rem;">{note_disp}</div>
        </div>
        """, unsafe_allow_html=True)
        cc1, cc2, _ = st.columns([1, 1, 3])
        with cc1:
            if st.button("Promote to draft", key=f"issue_promote_{r['id']}", use_container_width=True):
                _promote_issue(engine, r)
        with cc2:
            if st.button("Close", key=f"issue_close_{r['id']}", use_container_width=True):
                with engine.begin() as c:
                    c.execute(text("UPDATE machine_issues SET status = 'Closed', closed_at = NOW() WHERE id = :i"),
                              {"i": int(r["id"])})
                st.cache_data.clear()
                st.rerun()


def _render_fix_history(engine):
    """f3 — keyword + filter search over finalized repair records, so past fixes
    are findable across the whole fleet instead of trapped one asset at a time."""
    st.subheader("Fix History — search past repairs")
    st.caption("Search finalized service records by symptom, work performed, or asset. "
               "Great for \"how did we fix this last time?\"")

    q_text = st.text_input("Search", value=st.session_state.pop("fix_history_query", ""),
                           placeholder="e.g. spindle alarm, coolant leak, encoder…")
    f1, f2, f3 = st.columns(3)
    with f1:
        cats = st.multiselect("Category", ["Lathe", "Mill", "Swiss", "QC", "Support", "Other"])
    with f2:
        issues = st.multiselect("Issue", ["Mechanical", "Electrical", "Pneumatic", "Hydraulic",
                                           "Software", "Operator / Process", "Other", "Unknown"])
    with f3:
        rcs = st.multiselect("Root cause", ["Wear", "Misalignment", "Contamination", "Electrical Fault",
                                            "Software / Parameters", "Installation Error", "Damage", "Unknown"])

    df = q.fix_history_df(engine, q_text, cats, issues, rcs)
    if df.empty:
        _empty_state("No matching repairs",
                     "No finalized service records match your search yet. Try fewer "
                     "filters, or finalize some service events to build history.")
        return

    st.write(f"**{len(df)}** matching record(s).")
    for _, r in df.iterrows():
        fin = r["finalized_at"].strftime("%Y-%m-%d") if r["finalized_at"] is not None else "—"
        cat = r["equipment_category"] or "—"
        st.markdown(f"""
        <div class="asset-item">
            <div style="float:right;color:var(--text-muted);font-size:0.85rem;">{fin}</div>
            <div class="asset-title">{html.escape(str(r['asset_code'] or 'Unassigned'))} · {html.escape(str(cat))}</div>
            <div style="margin:4px 0;">
                {theme.badge(r['service_type'] or '—', 'info')}
                {theme.badge(r['issue_category'] or 'Unclassified', 'primary')}
                {theme.badge(r['root_cause'] or 'Unknown', 'neutral')}
            </div>
            <div style="font-size:0.9rem;"><strong>Problem:</strong> {html.escape(str(r['problem_description'] or '—'))}</div>
            <div style="font-size:0.9rem;"><strong>Fix:</strong> {html.escape(str(r['work_performed'] or '—'))}</div>
            {f'<div style="font-size:0.85rem;color:var(--text-muted);margin-top:4px;"><strong>Parts:</strong> {html.escape(str(r["parts"]))}</div>' if r['parts'] else ''}
        </div>
        """, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# PAGE 5: ERP SHOP DASHBOARD
# -----------------------------------------------------------------------------
def render_erp_dashboard_page():
    st.markdown('<div class="gradient-header">ERP Shop Dashboard</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    # Navigation tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Shop Floor Live View", 
        "Financial Job Costing", 
        "Capacity & Backlog", 
        "Scrap & Quality", 
        "SQL Integration Guide"
    ])
    
    # -----------------------------------------
    # TAB 1: LIVE VIEW
    # -----------------------------------------
    with tab1:
        st.subheader("CNC Machining Centers - Active Operations")
        
        df_live = pd.read_sql_query("""
            SELECT lt.ticket_id    AS "TicketID",
                   COALESCE(lt.job_no, '—')   AS "JobNo",
                   COALESCE(j.part_no, '—')   AS "PartNo",
                   COALESCE(j.customer, '—')  AS "Customer",
                   wc.machine_id   AS "MachineID",
                   wc.machine_name AS "MachineName",
                   wc.department   AS "Department",
                   COALESCE(emp.name, 'Unassigned') AS "OperatorName",
                   COALESCE(lt.op_code, '—')  AS "OpCode",
                   COALESCE(lt.op_desc, '—')  AS "OpDesc",
                   TO_CHAR(lt.time_in, 'YYYY-MM-DD HH24:MI:SS') AS "TimeIn"
            FROM labor_tickets lt
            JOIN work_centers wc ON lt.machine_id = wc.machine_id
            LEFT JOIN jobs j      ON lt.job_no      = j.job_no
            LEFT JOIN employees emp ON lt.employee_id = emp.employee_id
            WHERE lt.time_out IS NULL
        """, engine)
        
        if df_live.empty:
            st.info("No active check-ins on the shop floor right now.")
        else:
            col_live1, col_live2 = st.columns([3, 1])
            with col_live1:
                # Live grid of active machines
                cols = st.columns(3)
                for index, row in df_live.iterrows():
                    col_idx = index % 3
                    with cols[col_idx]:
                        # Glassmorphism Active Card
                        color_border = theme.department_color(row['Department'])
                        mid, mname, dept, jobno, partn, cust, opc, opd, oper, tin = (
                            html.escape(str(row[c])) for c in
                            ('MachineID', 'MachineName', 'Department', 'JobNo', 'PartNo',
                             'Customer', 'OpCode', 'OpDesc', 'OperatorName', 'TimeIn'))
                        st.markdown(f"""
                        <div class="asset-item" style="border-left-color: {color_border}; background-color: var(--surface);">
                            <div style="float: right;">
                                <span class="status-badge"><span class="status-pulse"></span>ACTIVE</span>
                            </div>
                            <div style="font-weight: 700; font-size: 1.1rem; color: var(--text);">{mid} - {mname}</div>
                            <div style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 12px; font-weight: 600; text-transform: uppercase;">{dept} Center</div>
                            <hr style="margin: 8px 0; border-color: var(--bg-muted);">
                            <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Job Number:</strong> <code style="background-color: var(--bg-muted); padding: 2px 6px; border-radius: 4px;">{jobno}</code></div>
                            <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Part Name:</strong> {partn}</div>
                            <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Customer:</strong> {cust}</div>
                            <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Op:</strong> {opc} - {opd}</div>
                            <div style="font-size: 0.9rem; margin-bottom: 4px;"><strong>Operator:</strong> {oper}</div>
                            <div style="font-size: 0.8rem; color: var(--text-subtle); margin-top: 8px;">Clocked In: {tin}</div>
                        </div>
                        """, unsafe_allow_html=True)
            with col_live2:
                # Derive the footer from the data so the sub-counts always reconcile
                # with the headline (QC/Support tickets fall into "Other").
                counts = df_live['Department'].value_counts()
                known = ['Lathe', 'Mill', 'Swiss']
                parts = [f"{d}s: {int(counts.get(d, 0))}" for d in known]
                other = int(len(df_live) - sum(int(counts.get(d, 0)) for d in known))
                if other:
                    parts.append(f"Other: {other}")
                st.markdown(_metric_card(
                    "Active Running CNCs", len(df_live),
                    footer=" | ".join(parts)
                ), unsafe_allow_html=True)
                
                st.subheader("Live Dispatch Board")
                st.dataframe(
                    df_live[['MachineID', 'JobNo', 'OperatorName', 'OpDesc', 'TimeIn']],
                    use_container_width=True,
                    hide_index=True
                )
                
    # -----------------------------------------
    # TAB 2: FINANCIAL JOB COSTING
    # -----------------------------------------
    with tab2:
        st.subheader("Financial Variance - Estimated vs Actual Labor Hours")
        
        df_cost = pd.read_sql_query("""
            SELECT j.job_no          AS "JobNo",
                   j.customer        AS "Customer",
                   j.part_no         AS "PartNo",
                   j.order_qty       AS "OrderQty",
                   j.due_date        AS "DueDate",
                   COALESCE(j.est_setup_hours, 0) AS "EstSetupHours",
                   COALESCE(j.est_run_hours, 0)   AS "EstRunHours",
                   j.status          AS "Status",
                   COALESCE(SUM(lt.setup_hours), 0) AS "ActSetupHours",
                   COALESCE(SUM(lt.run_hours),   0) AS "ActRunHours"
            FROM jobs j
            LEFT JOIN labor_tickets lt ON j.job_no = lt.job_no
            GROUP BY j.job_no, j.customer, j.part_no, j.order_qty, j.due_date,
                     j.est_setup_hours, j.est_run_hours, j.status
        """, engine)
        
        # Calculate derived columns
        df_cost['EstTotalHours'] = df_cost['EstSetupHours'] + df_cost['EstRunHours']
        df_cost['ActTotalHours'] = df_cost['ActSetupHours'] + df_cost['ActRunHours']
        df_cost['VarianceHours'] = df_cost['ActTotalHours'] - df_cost['EstTotalHours']
        df_cost['PctOverrun'] = (df_cost['ActTotalHours'] / df_cost['EstTotalHours'] - 1) * 100
        df_cost['PctOverrun'] = df_cost['PctOverrun'].replace([float('inf'), float('-inf')], 0).fillna(0)
        
        # User interactive filter threshold
        overrun_filter = st.slider("Filter: Highlight Job Overrun Threshold (%)", min_value=0, max_value=100, value=25)
        
        # Display cards
        total_overrun_jobs = len(df_cost[(df_cost['PctOverrun'] > overrun_filter) & (df_cost['Status'] == 'Completed')])
        
        total_est    = df_cost[df_cost['Status'] == 'Completed']['EstTotalHours'].sum()
        total_act    = df_cost[df_cost['Status'] == 'Completed']['ActTotalHours'].sum()
        net_variance = total_act - total_est

        col_c1, col_c2, col_c3 = st.columns(3)
        with col_c1:
            st.markdown(_metric_card("Jobs Completed", len(df_cost[df_cost['Status'] == 'Completed'])), unsafe_allow_html=True)
        with col_c2:
            alert_card  = "border-color: var(--danger)" if total_overrun_jobs > 0 else ""
            alert_value = theme.value_gradient("danger") if total_overrun_jobs > 0 else ""
            st.markdown(_metric_card("Critical Overrun Alerts", total_overrun_jobs, card_style=alert_card, value_style=alert_value), unsafe_allow_html=True)
        with col_c3:
            var_style = (
                theme.value_gradient("danger") if net_variance > 0
                else theme.value_gradient("success")
            )
            st.markdown(_metric_card("Net Hours Variance", f"{net_variance:+.1f} hrs", value_style=var_style), unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Split layout
        col_chart, col_table = st.columns([1, 1])
        
        with col_chart:
            st.subheader("Est. vs Act. Labor Hours Comparison")
            # Build horizontal side-by-side bar chart
            fig = go.Figure()
            completed_df = df_cost[df_cost['Status']=='Completed'].sort_values('JobNo')
            fig.add_trace(go.Bar(
                y=completed_df['JobNo'],
                x=completed_df['EstTotalHours'],
                name='Estimated Hours',
                orientation='h',
                marker_color=theme.PALETTE["border-soft"]
            ))
            fig.add_trace(go.Bar(
                y=completed_df['JobNo'],
                x=completed_df['ActTotalHours'],
                name='Actual Hours',
                orientation='h',
                marker_color=theme.PALETTE["info"]
            ))
            fig.update_layout(
                barmode='group',
                height=450,
                margin=dict(l=50, r=20, t=10, b=10),
                legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center")
            )
            _plot(fig, use_container_width=True)
            
        with col_table:
            st.subheader("Job Ledger Details")
            
            # Format and styled dataframe representation
            styled_df = df_cost[['JobNo', 'Customer', 'PartNo', 'EstTotalHours', 'ActTotalHours', 'VarianceHours', 'PctOverrun', 'Status']].copy()
            styled_df['EstTotalHours'] = styled_df['EstTotalHours'].round(1)
            styled_df['ActTotalHours'] = styled_df['ActTotalHours'].round(1)
            styled_df['VarianceHours'] = styled_df['VarianceHours'].round(1)
            styled_df['PctOverrun'] = styled_df['PctOverrun'].apply(lambda x: f"{x:+.0f}%" if x != 0 else "0%")
            
            st.dataframe(
                styled_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "VarianceHours": st.column_config.NumberColumn(
                        "Variance (Hrs)",
                        format="%+f"
                    ),
                    "PctOverrun": "Overrun %"
                }
            )
            
    # -----------------------------------------
    # TAB 3: CAPACITY & BACKLOG
    # -----------------------------------------
    with tab3:
        st.subheader("Machine Center Backlog Capacity")
        
        df_back = pd.read_sql_query("""
            SELECT COALESCE(wc.department, 'Unassigned')   AS "Department",
                   COALESCE(wc.machine_name, 'Unassigned') AS "MachineName",
                   SUM(COALESCE(j.est_setup_hours, 0) + COALESCE(j.est_run_hours, 0)) AS "BacklogHours",
                   COUNT(j.job_no) AS "JobCount"
            FROM jobs j
            LEFT JOIN work_centers wc ON wc.machine_id = (
               SELECT lt.machine_id FROM labor_tickets lt
               WHERE lt.job_no = j.job_no AND lt.op_code = '30' LIMIT 1
            )
            WHERE j.status IN ('Active', 'Scheduled')
            GROUP BY COALESCE(wc.machine_name, 'Unassigned'),
                     COALESCE(wc.department, 'Unassigned')
        """, engine)
        
        if df_back.empty:
            st.info("No active backlog scheduled on the floor.")
        else:
            col_b1, col_b2 = st.columns([1, 1])
            
            with col_b1:
                st.subheader("Hours Backlog by Machining Center")
                fig_back = px.bar(
                    df_back.sort_values('BacklogHours', ascending=False),
                    x='BacklogHours',
                    y='MachineName',
                    color='Department',
                    color_discrete_map=theme.DEPARTMENT_COLORS,
                    orientation='h',
                    labels={'BacklogHours': 'Queued Hours', 'MachineName': 'Machine'},
                    height=450
                )
                fig_back.update_layout(margin=dict(l=50, r=20, t=10, b=10))
                _plot(fig_back, use_container_width=True)
                
            with col_b2:
                st.subheader("Backlog Capacity Summary Table")
                st.dataframe(
                    df_back.sort_values('BacklogHours', ascending=False),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Dynamic backlog planning insight card
                total_hours = df_back['BacklogHours'].sum()
                fleet_size = pd.read_sql_query("SELECT COUNT(*) AS n FROM work_centers", engine)["n"].iloc[0]
                fleet_size = max(int(fleet_size), 1)
                st.markdown(f"""
                <div class="asset-item" style="border-left-color: var(--dept-lathe); background-color: var(--surface); margin-top: 25px;">
                    <div class="asset-title">Production Scheduling Insight</div>
                    <div style="font-size: 0.925rem; color: var(--text-strong); line-height: 1.5;">
                        Your shop floor is currently holding a total backlog of <strong>{total_hours:.1f} hours</strong> of estimated production. 
                        Assuming a standard <strong>1-shift 8-hour operation</strong> per machine day, this represents approximately 
                        <strong>{(total_hours / fleet_size / 8):.1f} days</strong> of load across your entire {fleet_size} CNC Work Center fleet.
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
    # -----------------------------------------
    # TAB 4: SCRAP & QUALITY
    # -----------------------------------------
    with tab4:
        st.subheader("Scrap Rate Analysis & First-Pass Yield (FPY)")
        
        df_scrap = pd.read_sql_query("""
            SELECT lt.machine_id   AS "MachineID",
                   wc.machine_name AS "MachineName",
                   wc.department   AS "Department",
                   SUM(lt.qty_good)  AS "TotalGood",
                   SUM(lt.qty_scrap) AS "TotalScrap"
            FROM labor_tickets lt
            JOIN work_centers wc ON lt.machine_id = wc.machine_id
            WHERE lt.op_code = '30'
            GROUP BY lt.machine_id, wc.machine_name, wc.department
        """, engine)
        
        if df_scrap.empty or df_scrap['TotalScrap'].sum() == 0:
            st.info("Excellent quality performance! There is no scrap recorded in this database cycle.")
        else:
            total_good = df_scrap['TotalGood'].sum()
            total_scrap = df_scrap['TotalScrap'].sum()
            overall_scrap_rate = (total_scrap / (total_good + total_scrap)) * 100
            fpy = 100 - overall_scrap_rate
            
            col_s1, col_s2, col_s3 = st.columns(3)
            with col_s1:
                st.markdown(_metric_card("Total Parts Produced", int(total_good + total_scrap)), unsafe_allow_html=True)
            with col_s2:
                st.markdown(_metric_card("Total Scrap Parts", int(total_scrap), value_style=theme.value_gradient("danger")), unsafe_allow_html=True)
            with col_s3:
                st.markdown(_metric_card("Shop First-Pass Yield (FPY)", f"{fpy:.1f}%", value_style=theme.value_gradient("success")), unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            col_sc1, col_sc2 = st.columns([1, 1])
            with col_sc1:
                st.subheader("Scrap Pieces by Machining Department")
                df_dept_scrap = df_scrap.groupby('Department')['TotalScrap'].sum().reset_index()
                fig_scrap_pie = px.pie(
                    df_dept_scrap,
                    values='TotalScrap',
                    names='Department',
                    color='Department',
                    color_discrete_map=theme.DEPARTMENT_COLORS,
                    hole=0.4
                )
                fig_scrap_pie.update_layout(margin=dict(l=20, r=20, t=10, b=10))
                _plot(fig_scrap_pie, use_container_width=True)
                
            with col_sc2:
                st.subheader("Scrap Rate List by Machine Center")
                df_scrap['ScrapRate'] = (df_scrap['TotalScrap'] / (df_scrap['TotalGood'] + df_scrap['TotalScrap'])) * 100
                st.dataframe(
                    df_scrap[['MachineName', 'Department', 'TotalGood', 'TotalScrap', 'ScrapRate']].sort_values('TotalScrap', ascending=False),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "ScrapRate": st.column_config.NumberColumn(
                            "Scrap Rate %",
                            format="%.1f%%"
                        )
                    }
                )
                
    # -----------------------------------------
    # TAB 5: SQL INTEGRATION GUIDE
    # -----------------------------------------
    with tab5:
        st.subheader("Connecting to on-premise ECI M1 / JobBoss SQL Server")
        st.markdown("""
        This app already ships a **built-in JobBoss sync** (`utils/jobboss.py`): it pulls
        employees, jobs, and labor into this database so every page keeps working even when
        JobBoss is offline. Configure it with environment variables — **never hardcode
        credentials** — and run it from **Advanced → Settings → "Sync from JobBoss"** or
        `python sync_jobboss.py`:

        ```bash
        pip install -r requirements-jobboss.txt          # optional pyodbc + ODBC driver
        export JOBBOSS_SERVER='<your_server>\\\\<INSTANCE>'
        export JOBBOSS_DB='<your_database>'
        export JOBBOSS_USER='<read_only_login>'
        export JOBBOSS_PASSWORD='<password>'
        ```

        The reference snippet below shows the underlying ODBC connection + query shape
        (the column names are a starting point — verify them against your instance):
        """)
        
        st.code("""
import pyodbc
import pandas as pd

def get_jobboss_connection():
    # Configure your on-premise SQL Server credentials
    conn_str = (
        "Driver={ODBC Driver 18 for SQL Server};"
        "Server=<your_server>\\\\<INSTANCE>;"  # your server name/IP & SQL instance
        "Database=<your_database>;"            # your production database
        "UID=<your_login>;"                    # use a read-only SQL Server login
        "PWD=<your_password>;"                 # supply via an env var; never commit a real password
        "Trusted_Connection=no;"
    )
    return pyodbc.connect(conn_str)

# Example function querying live check-ins directly from JobBoss
def get_live_labor_checkins():
    conn = get_jobboss_connection()
    
    # Example SQL Server schema for JobBoss/ECI M1 LaborTickets
    query = \"\"\"
    SELECT 
        lt.TICKET_ID as TicketID, 
        lt.JOB_NUMBER as JobNo, 
        j.PART_NUMBER as PartNo, 
        j.CUSTOMER_NAME as Customer, 
        wc.WORK_CENTER_ID as MachineID, 
        wc.DESCRIPTION as MachineName, 
        emp.FIRST_LAST_NAME as OperatorName, 
        lt.OP_CODE as OpCode, 
        lt.OP_DESCRIPTION as OpDesc, 
        lt.TIME_IN as TimeIn
    FROM LABOR_TICKET lt
    JOIN JOB_ORDER j ON lt.JOB_NUMBER = j.JOB_NUMBER
    JOIN WORK_CENTER wc ON lt.WORK_CENTER_ID = wc.WORK_CENTER_ID
    JOIN EMPLOYEE emp ON lt.EMPLOYEE_ID = emp.EMPLOYEE_ID
    WHERE lt.TIME_OUT IS NULL;
    \"\"\"
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df
        """, language="python")

# -----------------------------------------------------------------------------
# PAGE 6: REPORTING & ANALYTICS SUITE
# -----------------------------------------------------------------------------
# Real interactive reporting over the live base tables (no fact_reporting_production
# dependency). Replaces the old ETL/cookbook tabs. KPI rulings that bind every tab:
#   * Quality (parts / yield / scrap) filters op_code='30' — scrap is only logged
#     on the main machining op, so summing across ops would triple-count parts.
#   * Hours / utilization / labor-efficiency use ALL op_codes (setup + saw are
#     real labor).
#   * Every ratio guards its denominator with NULLIF -> renders "N/A", never inf.
#   * Maintenance analytics count record_state='Final' only and degrade to clean
#     empty-states while service_reports is unpopulated.

# QC / Support live only in work_centers (not in theme.DEPARTMENT_COLORS), so the
# map is extended here to keep them coloured in production charts.
_DEPT_MAP = {
    **theme.DEPARTMENT_COLORS,
    "QC":      theme.PALETTE["text-muted"],
    "Support": theme.PALETTE["text-subtle"],
}

# Export queries are shared between the per-view CSV buttons and the full
# workbook builder, so they live in one place.
_SQL_EXPORT = {
    "production_jobs": """
        SELECT j.job_no AS job, j.customer AS customer, j.part_no AS part,
               ROUND((COALESCE(j.est_setup_hours, 0) + COALESCE(j.est_run_hours, 0))::numeric, 1)           AS est_hrs,
               ROUND(COALESCE(SUM(lt.setup_hours + lt.run_hours), 0)::numeric, 1) AS act_hrs,
               ROUND(COALESCE(SUM(lt.setup_hours + lt.run_hours), 0)
                     - (COALESCE(j.est_setup_hours, 0) + COALESCE(j.est_run_hours, 0)), 1)                  AS var_hrs,
               CASE WHEN COALESCE(SUM(lt.setup_hours + lt.run_hours), 0) > 0
                    THEN ROUND(100.0 * (COALESCE(j.est_setup_hours, 0) + COALESCE(j.est_run_hours, 0))
                         / SUM(lt.setup_hours + lt.run_hours), 1)
               END                                                                AS efficiency
        FROM jobs j
        LEFT JOIN labor_tickets lt ON j.job_no = lt.job_no
        WHERE j.status = 'Completed'
        GROUP BY j.job_no, j.customer, j.part_no, j.est_setup_hours, j.est_run_hours
        ORDER BY efficiency ASC NULLS LAST
    """,
    "production_scrap": """
        SELECT wc.machine_name AS machine, wc.department AS department,
               COALESCE(SUM(lt.qty_good), 0)  AS good,
               COALESCE(SUM(lt.qty_scrap), 0) AS scrap,
               ROUND(100.0 * SUM(lt.qty_scrap)
                     / NULLIF(SUM(lt.qty_good) + SUM(lt.qty_scrap), 0), 1) AS scrap_pct
        FROM labor_tickets lt
        JOIN work_centers wc ON lt.machine_id = wc.machine_id
        WHERE lt.op_code = '30'
        GROUP BY wc.machine_name, wc.department
        ORDER BY scrap DESC
    """,
    "production_machine_load": """
        SELECT wc.machine_name AS machine, wc.department AS department,
               ROUND(COALESCE(SUM(lt.setup_hours), 0)::numeric, 1) AS setup_hrs,
               ROUND(COALESCE(SUM(lt.run_hours), 0)::numeric, 1)   AS run_hrs
        FROM labor_tickets lt
        JOIN work_centers wc ON lt.machine_id = wc.machine_id
        GROUP BY wc.machine_name, wc.department
        ORDER BY run_hrs DESC
    """,
    "service_reports_final": """
        SELECT service_id, asset_code, service_type, issue_category, root_cause,
               downtime_hours, return_to_service, verified_by, finalized_at
        FROM service_reports
        WHERE record_state = 'Final'
        ORDER BY finalized_at DESC NULLS LAST
    """,
    "service_parts": """
        SELECT sp.part_name, sp.quantity, sp.is_battery, sr.service_id, sr.asset_code
        FROM service_parts sp
        JOIN service_reports sr ON sp.report_id = sr.report_id
        WHERE sr.record_state = 'Final'
        ORDER BY sp.part_name
    """,
    "assets": """
        SELECT asset_code, equipment_category, department_code, display_name, manufacturer,
               model, serial_number, control_type, build_year, planned_pm_interval_days,
               asset_status, commission_date
        FROM assets
        ORDER BY asset_code
    """,
    "asset_batteries": """
        SELECT a.asset_code, b.battery_number, b.description, b.part_number,
               b.replacement_interval_days
        FROM asset_batteries b
        JOIN assets a ON a.asset_id = b.asset_id
        ORDER BY a.asset_code, b.battery_number
    """,
    "asset_peripherals": """
        SELECT a.asset_code, p.equip_number, p.name, p.make, p.model, p.serial_number
        FROM asset_peripheral_equipment p
        JOIN assets a ON a.asset_id = p.asset_id
        ORDER BY a.asset_code, p.equip_number
    """,
}

_SQL_SUMMARY = """
    SELECT
      (SELECT COALESCE(SUM(qty_good)  FILTER (WHERE op_code='30'), 0) FROM labor_tickets) AS good_op30,
      (SELECT COALESCE(SUM(qty_scrap) FILTER (WHERE op_code='30'), 0) FROM labor_tickets) AS scrap_op30,
      (SELECT ROUND(COALESCE(SUM(setup_hours + run_hours), 0)::numeric, 1) FROM labor_tickets) AS logged_hours,
      (SELECT COUNT(DISTINCT machine_id) FROM labor_tickets WHERE time_out IS NULL) AS active_machines,
      (SELECT COUNT(*) FROM service_reports WHERE record_state='Final') AS final_events,
      (SELECT COALESCE(SUM(downtime_hours), 0) FROM service_reports WHERE record_state='Final') AS total_downtime,
      (SELECT COUNT(*) FROM assets) AS total_assets,
      (SELECT COUNT(*) FILTER (WHERE planned_pm_interval_days IS NULL) FROM assets) AS assets_missing_pm
"""


# ── small shared helpers ──────────────────────────────────────────────────────
def _q(sql, engine, params=None):
    """Run a read query and return a DataFrame. Aggregation lives in SQL; pandas
    does only light shaping. Multiselect filters bind as Postgres arrays via
    ``col = ANY(:list)``, so an empty selection is coalesced to "all" first."""
    return pd.read_sql_query(text(sql), engine, params=params or {})


def _na(value, fmt="{:.1f}"):
    """Format a possibly-NULL/NaN numeric, or "N/A" when it is missing — used so a
    zero denominator never renders as a misleading 100% or ∞."""
    if value is None:
        return "N/A"
    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        pass
    return fmt.format(value)


def _empty_state(title, body, icon=""):
    """Branded empty-section card so an empty view reads as designed, not broken."""
    st.markdown(
        f'<div class="asset-item" style="border-left-color: var(--border-soft); '
        f'background-color: var(--surface);"><div class="asset-title">{icon} {title}</div>'
        f'<div style="font-size:0.925rem;color:var(--text-muted);line-height:1.5;">{body}</div></div>',
        unsafe_allow_html=True,
    )


def _insight_card(title, body_html, accent="var(--dept-lathe)", margin_top="0"):
    """Left-accented call-out card carrying the "so what" narrative under a section."""
    st.markdown(
        f'<div class="asset-item" style="border-left-color: {accent}; '
        f'background-color: var(--surface); margin-top: {margin_top};">'
        f'<div class="asset-title">{title}</div>'
        f'<div style="font-size:0.925rem;color:var(--text-strong);line-height:1.5;">{body_html}</div></div>',
        unsafe_allow_html=True,
    )


def _hr():
    st.markdown("<hr style='border-color:var(--border);margin:14px 0 18px;'>", unsafe_allow_html=True)


def _render_knowledge_card(a):
    """Machine Knowledge card (f5): show the captured-but-never-displayed quirks /
    tooling / install notes for an asset. Renders only when at least one is present;
    otherwise a gentle prompt so the empty state reads as designed, not broken."""
    import html as _html
    fields = [
        ("Known quirks",       a.get("known_quirks")),
        ("Special tooling",    a.get("special_tooling")),
        ("Installation notes", a.get("installation_notes")),
        ("Reference document", a.get("reference_document")),
    ]
    present = [(lbl, val) for lbl, val in fields if val and str(val).strip()]
    if not present:
        st.caption("No machine-specific notes captured yet — add quirks, special "
                   "tooling, or install notes via **Edit**.")
        return
    body = "".join(
        f'<div style="margin-top:6px;"><strong>{lbl}:</strong> '
        f'{_html.escape(str(val)).strip().replace(chr(10), "<br>")}</div>'
        for lbl, val in present
    )
    _insight_card("🔧 Machine Knowledge", body, accent="var(--primary)", margin_top="12px")


def _render_asset_documents(engine, asset_id, asset_code):
    """f6 — list / download / upload the on-disk manuals & PM sheets for an asset."""
    st.markdown("---")
    st.markdown("**Documents:**")
    docs = q.asset_documents_df(engine, asset_id)
    if docs.empty:
        st.caption("No documents indexed. Use **Scan asset documents** in Advanced → "
                   "Settings, or upload one below.")
    else:
        for _, d in docs.iterrows():
            dc1, dc2 = st.columns([4, 1])
            with dc1:
                st.markdown(f"{theme.badge(d['doc_type'] or 'Other', 'neutral')} {html.escape(str(d['file_name']))}",
                            unsafe_allow_html=True)
            with dc2:
                try:
                    st.download_button("Download", q.read_document(d["rel_path"]),
                                       file_name=d["file_name"],
                                       key=f"doc_dl_{asset_id}_{int(d['id'])}",
                                       use_container_width=True)
                except Exception:
                    st.caption("missing")
    up = st.file_uploader("Add a document", key=f"doc_up_{asset_id}",
                          label_visibility="collapsed")
    if up is not None:
        if st.button(f"Save {up.name}", key=f"doc_save_{asset_id}", use_container_width=True):
            q.save_document(engine, asset_id, up.name, up.getvalue(), added_by=q.current_user() or None)
            st.success(f"Saved {up.name}.")
            st.rerun()


def _start_quick_log(asset_code=None, service_type=None):
    """Smart-default hand-off: open the Service ▸ Quick Log tab prefilled with the
    asset and service type from whatever row launched it (a Down machine, a PM due
    row, an issue, …). The Quick Log tab reads ``ql_prefill`` on arrival."""
    st.session_state["ql_prefill"] = {"asset_code": asset_code, "service_type": service_type}
    st.session_state["service_page"] = "Quick Log"
    _set_page("Service Reports")
    st.rerun()


_FLOOR_META = {
    "DOWN":    ("⛔", "var(--danger)"),
    "RUNNING": ("🟢", "var(--success)"),
    "IDLE":    ("⚪", "var(--text-muted)"),
    "OFFLINE": ("⚫", "var(--text-muted)"),
}


def _render_floor_strip(engine):
    """f7 — compact 'is anything down right now' strip: one count card per status."""
    counts = q.floor_status_counts(engine)
    cols = st.columns(4)
    for col, status in zip(cols, ["DOWN", "RUNNING", "IDLE", "OFFLINE"]):
        icon, color = _FLOOR_META[status]
        style = theme.value_gradient("danger") if (status == "DOWN" and counts.get(status, 0)) else ""
        with col:
            st.markdown(_metric_card(f"{icon} {status.title()}", counts.get(status, 0),
                                     value_style=style), unsafe_allow_html=True)


def _render_floor_board(engine, with_actions=False):
    """Full per-machine floor board. DOWN machines surface first; when with_actions
    is set, each offers a one-click jump to log a corrective repair."""
    df = q.floor_status_df(engine)
    if df.empty:
        _empty_state("No work centers configured",
                     "Add machines in Advanced → Records Manager to see live floor status.")
        return
    down = df[df["status"] == "DOWN"]
    for _, r in down.iterrows():
        mid   = html.escape(str(r["machine_id"]))
        mname = html.escape(str(r.get("machine_name") or ""))
        dept  = html.escape(str(r.get("department") or ""))
        st.markdown(
            f'<div class="asset-item" style="border-left-color:var(--danger);">'
            f'<div style="float:right;color:var(--danger);font-weight:600;">DOWN</div>'
            f'<div class="asset-title">{mid} — {mname}</div>'
            f'<div style="color:var(--text-muted);font-size:0.85rem;">'
            f'{dept}</div></div>',
            unsafe_allow_html=True)
        if with_actions:
            if st.button(f"Log repair for {r['machine_id']}", key=f"floor_fix_{r['machine_id']}",
                         use_container_width=True):
                _start_quick_log(asset_code=r["machine_id"], service_type="Corrective")

    show = df[["machine_id", "machine_name", "department", "status",
               "job_no", "op_code", "emp_name"]].rename(columns={
        "machine_id": "Machine", "machine_name": "Name", "department": "Dept",
        "status": "Status", "job_no": "Job", "op_code": "Op", "emp_name": "Operator"})
    st.dataframe(show, use_container_width=True, hide_index=True)


def _pareto_fig(df, cat_col, val_col, y_title, bar_color):
    """Classic Pareto: bars sorted descending + cumulative-% line on a secondary axis."""
    d = df.copy()
    d[val_col] = pd.to_numeric(d[val_col])
    d = d.sort_values(val_col, ascending=False)
    total = float(d[val_col].sum())
    d["cum_pct"] = (d[val_col].cumsum() / total * 100) if total else 0.0
    fig = go.Figure()
    fig.add_trace(go.Bar(x=d[cat_col], y=d[val_col], marker_color=bar_color, name=y_title))
    fig.add_trace(go.Scatter(
        x=d[cat_col], y=d["cum_pct"], name="Cumulative %", yaxis="y2",
        mode="lines+markers", line=dict(color=theme.PALETTE["text-strong"])))
    fig.update_layout(
        height=400, margin=dict(l=40, r=50, t=30, b=60),
        legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
        yaxis=dict(title=y_title),
        yaxis2=dict(overlaying="y", side="right", range=[0, 100], ticksuffix="%", showgrid=False))
    return fig


def _excel_safe(df):
    """openpyxl cannot serialise timezone-aware datetimes (our TIMESTAMPTZ columns,
    e.g. service_reports.finalized_at, come back tz-aware). Drop the tz, keeping the
    local wall-clock, on any datetime column before writing to .xlsx."""
    out = df.copy()
    for col in out.columns:
        if isinstance(out[col].dtype, pd.DatetimeTZDtype):
            out[col] = out[col].dt.tz_localize(None)
    return out


def _build_full_report(engine, exports):
    """Assemble the multi-sheet .xlsx workbook in memory and return its bytes.

    ``exports`` is the pre-fetched {export-key: DataFrame} map the Export tab
    already built for its CSV buttons, so the eight dump queries run once per
    render rather than twice."""
    snap = _q(_SQL_SUMMARY, engine).iloc[0]
    good, scrap = float(snap["good_op30"]), float(snap["scrap_op30"])
    fpy = round(100 * good / (good + scrap), 1) if (good + scrap) else None
    summary = pd.DataFrame([
        {"Metric": "First-Pass Yield % (op 30)", "Value": fpy if fpy is not None else "N/A"},
        {"Metric": "Good parts (op 30)",          "Value": int(good)},
        {"Metric": "Scrap parts (op 30)",         "Value": int(scrap)},
        {"Metric": "Logged machine hours",        "Value": float(snap["logged_hours"])},
        {"Metric": "Active machines (now)",       "Value": int(snap["active_machines"])},
        {"Metric": "Finalized service events",    "Value": int(snap["final_events"])},
        {"Metric": "Total downtime hrs",          "Value": float(snap["total_downtime"])},
        {"Metric": "Registered assets",           "Value": int(snap["total_assets"])},
        {"Metric": "Assets missing PM interval",  "Value": int(snap["assets_missing_pm"])},
        {"Metric": "Report generated",            "Value": str(datetime.now())},
    ])
    sheets = {
        "Summary":            summary,
        "Production_Jobs":    exports["production_jobs"],
        "Scrap_By_Machine":   exports["production_scrap"],
        "Machine_Logged_Hrs": exports["production_machine_load"],
        "Service_Reports":    exports["service_reports_final"],
        "Service_Parts":      exports["service_parts"],
        "Assets":             exports["assets"],
        "Asset_Batteries":    exports["asset_batteries"],
        "Asset_Peripherals":  exports["asset_peripherals"],
    }
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            if df.empty:
                df = pd.DataFrame({"info": [f"No rows for {name} at export time."]})
            _excel_safe(df).to_excel(xw, sheet_name=name[:31], index=False)
    buf.seek(0)
    return buf.getvalue()


# ── TAB 1: PRODUCTION ─────────────────────────────────────────────────────────
def _render_production_tab(engine, data_lo, data_hi):
    st.subheader("Shop-floor output, yield & machine load")

    depts = _q("SELECT DISTINCT department FROM work_centers ORDER BY 1", engine)["department"].tolist()
    c1, c2 = st.columns([2, 2])
    with c1:
        sel_depts = st.multiselect("Department", depts, default=depts, key="prod_dept") or depts
    with c2:
        rng = st.date_input("Clock-in date range", value=(data_lo, data_hi),
                            min_value=data_lo, max_value=data_hi, key="prod_dates")
    lo, hi = rng if isinstance(rng, (list, tuple)) and len(rng) == 2 else (data_lo, data_hi)
    P = {"depts": list(sel_depts), "lo": lo, "hi": hi}
    _hr()

    # KPI row
    k = _q("""
        SELECT
          COALESCE(SUM(lt.qty_good)  FILTER (WHERE lt.op_code='30'), 0) AS good,
          COALESCE(SUM(lt.qty_scrap) FILTER (WHERE lt.op_code='30'), 0) AS scrap,
          COUNT(DISTINCT lt.machine_id) AS machines,
          CASE WHEN SUM(lt.qty_good)  FILTER (WHERE lt.op_code='30')
                  + SUM(lt.qty_scrap) FILTER (WHERE lt.op_code='30') > 0
               THEN ROUND(100.0 * SUM(lt.qty_good) FILTER (WHERE lt.op_code='30')
                    / (SUM(lt.qty_good)  FILTER (WHERE lt.op_code='30')
                     + SUM(lt.qty_scrap) FILTER (WHERE lt.op_code='30')), 1)
          END AS fpy_pct
        FROM labor_tickets lt
        JOIN work_centers wc ON lt.machine_id = wc.machine_id
        WHERE wc.department = ANY(:depts) AND lt.time_in::date BETWEEN :lo AND :hi
    """, engine, P).iloc[0]
    active = int(_q("SELECT COUNT(DISTINCT machine_id) AS n FROM labor_tickets WHERE time_out IS NULL",
                    engine)["n"].iloc[0])
    good, scrap, machines = int(k["good"]), int(k["scrap"]), int(k["machines"])
    fpy = None if pd.isna(k["fpy_pct"]) else float(k["fpy_pct"])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(_metric_card("Total Parts Produced", f"{good + scrap:,}",
                    footer=f"{good:,} good · {scrap:,} scrap (op 30)"), unsafe_allow_html=True)
    with m2:
        st.markdown(_metric_card("Total Scrap", f"{scrap:,}",
                    value_style=theme.value_gradient("danger") if scrap > 0 else ""),
                    unsafe_allow_html=True)
    with m3:
        fpy_style = "" if fpy is None else theme.value_gradient("success" if fpy >= 98 else "danger")
        st.markdown(_metric_card("First-Pass Yield", _na(fpy, "{:.1f}%"),
                    value_style=fpy_style, footer="Main run op (30)"), unsafe_allow_html=True)
    with m4:
        st.markdown(_metric_card("Active Machines", f"{active}",
                    value_style=theme.value_gradient("primary"),
                    footer=f"clocked in now · {machines} machines logged in range"),
                    unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section A — quality & scrap
    a1, a2 = st.columns([1, 1])
    with a1:
        st.subheader("Scrap by machine (op 30)")
        scrap_df = _q("""
            SELECT wc.machine_name AS machine, wc.department AS department,
                   COALESCE(SUM(lt.qty_good), 0)  AS good,
                   COALESCE(SUM(lt.qty_scrap), 0) AS scrap,
                   ROUND(100.0 * SUM(lt.qty_scrap)
                         / NULLIF(SUM(lt.qty_good) + SUM(lt.qty_scrap), 0), 1) AS scrap_pct
            FROM labor_tickets lt
            JOIN work_centers wc ON lt.machine_id = wc.machine_id
            WHERE lt.op_code = '30' AND wc.department = ANY(:depts)
              AND lt.time_in::date BETWEEN :lo AND :hi
            GROUP BY wc.machine_name, wc.department
            HAVING SUM(lt.qty_scrap) > 0
            ORDER BY scrap DESC
        """, engine, P)
        if scrap_df.empty:
            _empty_state("No scrap in this range",
                         "Every machining (op 30) part passed first-pass inspection for the selected scope.",
                         icon="")
        else:
            scrap_df["scrap"] = pd.to_numeric(scrap_df["scrap"])
            fig = px.bar(scrap_df, x="scrap", y="machine", color="department", orientation="h",
                         color_discrete_map=_DEPT_MAP, height=440,
                         labels={"scrap": "Scrap pieces", "machine": "Machine", "department": "Dept"})
            fig.update_layout(margin=dict(l=120, r=20, t=48, b=10), bargap=0.35,
                              legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
                              yaxis=dict(autorange="reversed"))
            _plot(fig, use_container_width=True)
    with a2:
        st.subheader("First-pass yield by department")
        fpy_df = _q("""
            SELECT wc.department AS department,
                   COALESCE(SUM(lt.qty_good), 0)  AS good,
                   COALESCE(SUM(lt.qty_scrap), 0) AS scrap
            FROM labor_tickets lt
            JOIN work_centers wc ON lt.machine_id = wc.machine_id
            WHERE lt.op_code = '30' AND wc.department = ANY(:depts)
              AND lt.time_in::date BETWEEN :lo AND :hi
            GROUP BY wc.department
            HAVING SUM(lt.qty_good) + SUM(lt.qty_scrap) > 0
        """, engine, P)
        if fpy_df.empty:
            _empty_state("No production yet", "No op-30 parts logged for the selected scope.")
        else:
            fpy_df["good"] = pd.to_numeric(fpy_df["good"])
            fpy_df["scrap"] = pd.to_numeric(fpy_df["scrap"])
            fpy_df["fpy"] = 100 * fpy_df["good"] / (fpy_df["good"] + fpy_df["scrap"])
            fpy_df = fpy_df.sort_values("fpy")
            fig = px.bar(fpy_df, x="fpy", y="department", orientation="h", color="department",
                         color_discrete_map=_DEPT_MAP, height=440,
                         labels={"fpy": "First-pass yield %", "department": "Dept"})
            lo_x = min(90.0, float(fpy_df["fpy"].min()) - 2)
            # Axis starts near the data (not 0) to separate near-100% departments,
            # so label each bar with its exact value — otherwise they read as
            # identical full blocks.
            fig.update_traces(texttemplate="%{x:.1f}%", textposition="inside",
                              insidetextanchor="end", textfont=dict(color="white", size=13))
            fig.update_layout(margin=dict(l=80, r=20, t=48, b=10), showlegend=False,
                              bargap=0.45, xaxis=dict(range=[lo_x, 100]))
            _plot(fig, use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section B — machine load & utilization
    load_df = _q("""
        SELECT wc.machine_name AS machine, wc.department AS department,
               ROUND(COALESCE(SUM(lt.setup_hours), 0)::numeric, 1) AS setup_hrs,
               ROUND(COALESCE(SUM(lt.run_hours), 0)::numeric, 1)   AS run_hrs,
               ROUND(COALESCE(SUM(EXTRACT(EPOCH FROM (lt.time_out - lt.time_in)) / 3600.0)
                              FILTER (WHERE lt.time_out IS NOT NULL), 0)::numeric, 1) AS clocked_span_hrs
        FROM labor_tickets lt
        JOIN work_centers wc ON lt.machine_id = wc.machine_id
        WHERE wc.department = ANY(:depts) AND lt.time_in::date BETWEEN :lo AND :hi
        GROUP BY wc.machine_name, wc.department
        HAVING SUM(COALESCE(lt.setup_hours, 0) + COALESCE(lt.run_hours, 0)) > 0
        ORDER BY SUM(COALESCE(lt.setup_hours, 0) + COALESCE(lt.run_hours, 0)) DESC
    """, engine, P)
    for col in ("setup_hrs", "run_hrs", "clocked_span_hrs"):
        if col in load_df.columns:
            load_df[col] = pd.to_numeric(load_df[col])
    b1, b2 = st.columns([2, 1])
    with b1:
        st.subheader("Logged hours by machine")
        if load_df.empty:
            _empty_state("No logged hours", "No labor was booked in the selected scope.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(y=load_df["machine"], x=load_df["setup_hrs"], name="Setup",
                                 orientation="h", marker_color=theme.PALETTE["border-soft"]))
            fig.add_trace(go.Bar(y=load_df["machine"], x=load_df["run_hrs"], name="Run",
                                 orientation="h", marker_color=theme.PALETTE["primary"]))
            fig.update_layout(barmode="stack", height=440, xaxis_title="Logged hours",
                              margin=dict(l=120, r=20, t=48, b=10),
                              legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"),
                              yaxis=dict(autorange="reversed"))
            _plot(fig, use_container_width=True)
            st.caption("Logged hours = setup + run time booked to each machine in range — a relative load "
                       "indicator (no shift calendar available).")
    with b2:
        st.subheader("Run-hour productivity")
        if load_df.empty:
            _empty_state("Awaiting hours", "Productivity appears once labor is booked.", icon="")
        else:
            run_total = float(load_df["run_hrs"].sum())
            span_total = float(load_df["clocked_span_hrs"].sum())
            prod = 100 * run_total / span_total if span_total else None
            st.markdown(_metric_card("Run-Hour Productivity", _na(prod, "{:.0f}%"),
                        value_style=theme.value_gradient("success") if prod is not None else "",
                        footer="Run time ÷ clocked span (closed tickets)"), unsafe_allow_html=True)
            _insight_card("Utilization basis",
                "Shown as <strong>productive run time</strong> ÷ total <strong>clocked span</strong> over "
                "<strong>closed</strong> tickets only. No fabricated capacity denominator: the dataset has no "
                "shift calendar, so absolute machine utilization cannot be computed without an assumption.",
                accent="var(--info)", margin_top="14px")
    st.markdown("<br>", unsafe_allow_html=True)

    # Section C — department logged-hours mix
    st.subheader("Department logged-hours mix")
    mix_df = _q("""
        SELECT wc.department AS department,
               ROUND(COALESCE(SUM(lt.setup_hours + lt.run_hours), 0)::numeric, 1) AS logged_hours
        FROM labor_tickets lt
        JOIN work_centers wc ON lt.machine_id = wc.machine_id
        WHERE wc.department = ANY(:depts) AND lt.time_in::date BETWEEN :lo AND :hi
        GROUP BY wc.department
        HAVING COALESCE(SUM(lt.setup_hours + lt.run_hours), 0) > 0
        ORDER BY logged_hours DESC
    """, engine, P)
    if mix_df.empty:
        _empty_state("No logged hours", "Nothing booked in the selected scope.")
    else:
        mix_df["logged_hours"] = pd.to_numeric(mix_df["logged_hours"])
        cpie, cside = st.columns([1, 1])
        with cpie:
            fig = px.pie(mix_df, values="logged_hours", names="department", color="department",
                         color_discrete_map=_DEPT_MAP, hole=0.45, height=320)
            # Keep slice labels inside the ring — Plotly drops the ones too small
            # to fit instead of scattering overlapping leader lines; the legend
            # and the breakdown table beside it carry the small departments.
            fig.update_traces(textposition="inside", insidetextorientation="horizontal")
            fig.update_layout(margin=dict(l=20, r=20, t=10, b=10), uniformtext_minsize=11,
                              uniformtext_mode="hide",
                              legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
            _plot(fig, use_container_width=True)
        with cside:
            total_hrs = float(mix_df["logged_hours"].sum())
            lead = mix_df.iloc[0]
            share = 100 * float(lead["logged_hours"]) / total_hrs if total_hrs else 0
            _insight_card("Where the hours go",
                f"<strong>{html.escape(str(lead['department']))}</strong> carries the most logged time — "
                f"{float(lead['logged_hours']):.0f} hrs ({share:.0f}%) of {total_hrs:,.0f} hrs booked across "
                f"{len(mix_df)} department(s) in range.", accent="var(--primary)")
            st.dataframe(
                mix_df.rename(columns={"department": "Department", "logged_hours": "Logged hrs"}),
                use_container_width=True, hide_index=True,
                column_config={"Logged hrs": st.column_config.NumberColumn("Logged hrs", format="%.1f")})
    st.markdown("<br>", unsafe_allow_html=True)

    # Section D — labor efficiency (completed jobs; filter-independent)
    st.subheader("Labor efficiency — completed jobs")
    st.caption("Across all completed jobs — spans each job's full life, so it ignores the filters above.")
    eff_df = _q(_SQL_EXPORT["production_jobs"], engine)
    if eff_df.empty:
        _empty_state("No completed jobs", "Labor efficiency appears once jobs reach Completed status.")
    else:
        for col in ("est_hrs", "act_hrs", "var_hrs", "efficiency"):
            eff_df[col] = pd.to_numeric(eff_df[col])
        d1, d2 = st.columns([1, 1])
        with d1:
            bars = eff_df.sort_values("var_hrs")
            colors = [theme.PALETTE["danger"] if v > 0 else theme.PALETTE["success"] for v in bars["var_hrs"]]
            fig = go.Figure(go.Bar(x=bars["var_hrs"], y=bars["job"], orientation="h", marker_color=colors))
            fig.update_layout(height=440, margin=dict(l=70, r=20, t=10, b=10),
                              xaxis_title="Hours vs estimate  (+over / −under)")
            fig.add_vline(x=0, line_width=1, line_color=theme.PALETTE["text-muted"])
            _plot(fig, use_container_width=True)
        with d2:
            st.dataframe(eff_df, use_container_width=True, hide_index=True, column_config={
                "job": "Job", "customer": "Customer", "part": "Part",
                "est_hrs": st.column_config.NumberColumn("Est Hrs", format="%.1f"),
                "act_hrs": st.column_config.NumberColumn("Act Hrs", format="%.1f"),
                "var_hrs": st.column_config.NumberColumn("Variance Hrs", format="%+.1f"),
                "efficiency": st.column_config.NumberColumn("Efficiency % (>100 = beat est.)", format="%.1f%%"),
            })

    # Insight — the "so what"
    bits = []
    if fpy is not None:
        bits.append(f"Shop first-pass yield is <strong>{fpy:.1f}%</strong> on {good + scrap:,} op-30 parts.")
    if not scrap_df.empty:
        rates = pd.to_numeric(scrap_df["scrap_pct"], errors="coerce")
        if rates.notna().any():
            w = scrap_df.loc[rates.idxmax()]
            wp = float(rates.loc[rates.idxmax()])
            if wp > 5:
                bits.append(f"<strong>{w['machine']}</strong> ({w['department']}) has the highest scrap rate "
                            f"at <strong>{wp:.1f}%</strong>.")
    if not eff_df.empty:
        overruns = int((pd.to_numeric(eff_df["var_hrs"]) > 0).sum())
        if overruns:
            bits.append(f"<strong>{overruns} of {len(eff_df)}</strong> completed jobs overran their labor estimate.")
    _insight_card("What to act on", " ".join(bits) or "No production in the selected window.",
                  margin_top="6px")


# ── TAB 2: MAINTENANCE & SERVICE ──────────────────────────────────────────────
def _maint_battery_pm(engine):
    """Forward-looking battery PM cadence (real registry data — useful even before
    any service report exists)."""
    st.subheader("Planned battery replacement cadence")
    st.caption("Forward-looking PM from the asset registry. Service history populates as reports are finalized.")
    bat = _q("""
        SELECT a.display_name AS "Asset", b.description AS "Battery",
               b.part_number AS "PartNumber", b.replacement_interval_days AS "IntervalDays"
        FROM asset_batteries b
        JOIN assets a ON b.asset_id = a.asset_id
        ORDER BY b.replacement_interval_days ASC NULLS LAST, a.display_name
    """, engine)
    if bat.empty:
        _empty_state("No battery records", "No batteries are registered against assets yet.")
    else:
        st.dataframe(bat, use_container_width=True, hide_index=True, column_config={
            "IntervalDays": st.column_config.NumberColumn("Interval (days)", format="%d"),
        })


def _render_maintenance_tab(engine):
    st.subheader("Service events, downtime & parts (finalized records only)")

    gate = _q("""
        SELECT COUNT(*) FILTER (WHERE record_state='Final') AS n_final,
               COUNT(*) FILTER (WHERE record_state='Draft') AS n_draft
        FROM service_reports
    """, engine).iloc[0]
    n_final, n_draft = int(gate["n_final"]), int(gate["n_draft"])

    if n_final == 0:
        _empty_state("No finalized service reports yet",
            "Maintenance analytics activate automatically once reports are finalized "
            "(record_state = Final). Drafts are excluded so KPIs reflect verified work only. "
            f"Drafts in progress: <strong>{n_draft}</strong>. When data arrives this tab shows downtime "
            "totals, a downtime-by-asset Pareto, issue-category and root-cause breakdowns, service-type mix, "
            "parts consumed, and MTBF.", icon="")
        ph = st.columns(4)
        for col, title in zip(ph, ["Finalized Events", "Total Downtime", "Avg Downtime", "Parts Consumed"]):
            with col:
                st.markdown(_metric_card(title, "—"), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        _maint_battery_pm(engine)
        return

    # Derive service types from the data (COALESCE NULL -> 'Unknown') rather than a
    # hardcoded list: service_type is nullable and ingested verbatim, so a NULL or
    # non-canonical value must still be selectable or its events vanish from every
    # chart while still counting toward the n_final gate above (reconciliation gap).
    types = _q("SELECT DISTINCT COALESCE(service_type,'Unknown') AS t FROM service_reports "
               "WHERE record_state='Final' ORDER BY 1", engine)["t"].tolist()
    cats = _q("SELECT DISTINCT COALESCE(issue_category,'Unknown') AS c FROM service_reports "
              "WHERE record_state='Final' ORDER BY 1", engine)["c"].tolist()
    c1, c2 = st.columns([2, 2])
    with c1:
        sel_types = st.multiselect("Service type", types, default=types, key="maint_type") or types
    with c2:
        sel_cats = st.multiselect("Issue category", cats, default=cats, key="maint_cat") or cats
    M = {"types": list(sel_types), "cats": list(sel_cats)}
    _hr()

    k = _q("""
        SELECT COUNT(*)                                                          AS events,
               ROUND(COALESCE(SUM(downtime_hours), 0)::numeric, 1)               AS total_dt,
               ROUND(COALESCE(AVG(downtime_hours), 0)::numeric, 1)               AS avg_dt,
               COUNT(*) FILTER (WHERE service_type IN ('Corrective','Emergency')) AS unplanned,
               COUNT(*) FILTER (WHERE service_type='Emergency')                  AS emergency,
               COUNT(DISTINCT asset_id)                                          AS assets_serviced
        FROM service_reports
        WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
          AND COALESCE(issue_category,'Unknown') = ANY(:cats)
    """, engine, M).iloc[0]
    pk = _q("""
        SELECT COALESCE(SUM(sp.quantity), 0)                              AS parts_qty,
               COALESCE(SUM(sp.quantity) FILTER (WHERE sp.is_battery), 0) AS batt_qty
        FROM service_parts sp
        JOIN service_reports sr ON sp.report_id = sr.report_id
        WHERE sr.record_state='Final' AND COALESCE(sr.service_type,'Unknown') = ANY(:types)
          AND COALESCE(sr.issue_category,'Unknown') = ANY(:cats)
    """, engine, M).iloc[0]
    events = int(k["events"])
    total_dt, avg_dt = float(k["total_dt"]), float(k["avg_dt"])
    assets_serviced = int(k["assets_serviced"])
    parts_qty, batt_qty = int(pk["parts_qty"]), int(pk["batt_qty"])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(_metric_card("Finalized Events", f"{events}",
                    value_style=theme.value_gradient("primary"),
                    footer=f"{assets_serviced} assets"), unsafe_allow_html=True)
    with m2:
        st.markdown(_metric_card("Total Downtime (hrs)", f"{total_dt:.1f}",
                    value_style=theme.value_gradient("danger") if total_dt > 0 else ""),
                    unsafe_allow_html=True)
    with m3:
        st.markdown(_metric_card("Avg Downtime / Event", f"{avg_dt:.1f}"), unsafe_allow_html=True)
    with m4:
        st.markdown(_metric_card("Parts Consumed", f"{parts_qty}",
                    footer=f"of which {batt_qty} batteries"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section A — downtime Pareto by asset
    a1, a2 = st.columns([2, 1])
    dt_df = _q("""
        SELECT COALESCE(a.display_name, sr.asset_code, 'Unknown') AS asset,
               a.equipment_category                              AS category,
               ROUND(COALESCE(SUM(sr.downtime_hours), 0)::numeric, 1) AS downtime_hrs,
               COUNT(*)                                          AS events
        FROM service_reports sr
        LEFT JOIN assets a ON sr.asset_id = a.asset_id
        WHERE sr.record_state='Final' AND COALESCE(sr.service_type,'Unknown') = ANY(:types)
          AND COALESCE(sr.issue_category,'Unknown') = ANY(:cats)
        GROUP BY COALESCE(a.display_name, sr.asset_code, 'Unknown'), a.equipment_category
        ORDER BY downtime_hrs DESC
        LIMIT 15
    """, engine, M)
    with a1:
        st.subheader("Downtime by asset")
        if dt_df.empty or pd.to_numeric(dt_df["downtime_hrs"]).sum() == 0:
            _empty_state("No downtime recorded", "Finalized reports in scope logged zero downtime.", icon="")
        else:
            dt_df["downtime_hrs"] = pd.to_numeric(dt_df["downtime_hrs"])
            fig = px.bar(dt_df.sort_values("downtime_hrs"), x="downtime_hrs", y="asset",
                         orientation="h", height=440, color_discrete_sequence=[theme.PALETTE["danger"]],
                         labels={"downtime_hrs": "Downtime hours", "asset": "Asset"})
            fig.update_layout(margin=dict(l=140, r=20, t=10, b=10))
            _plot(fig, use_container_width=True)
    with a2:
        st.subheader("Top drivers")
        if not dt_df.empty and pd.to_numeric(dt_df["downtime_hrs"]).sum() > 0:
            total = float(pd.to_numeric(dt_df["downtime_hrs"]).sum())
            top = dt_df.iloc[0]
            _insight_card("Biggest downtime driver",
                          f"<strong>{html.escape(str(top['asset']))}</strong> accounts for {float(top['downtime_hrs']):.1f} hrs "
                          f"({100 * float(top['downtime_hrs']) / total:.0f}%) of finalized downtime across "
                          f"{int(top['events'])} event(s).", accent="var(--danger)")
            st.dataframe(dt_df[["asset", "events", "downtime_hrs"]], use_container_width=True, hide_index=True,
                         column_config={"asset": "Asset", "events": "Events",
                                        "downtime_hrs": st.column_config.NumberColumn("Downtime (hrs)", format="%.1f")})
    st.markdown("<br>", unsafe_allow_html=True)

    # Section B — issue-category & root-cause Paretos
    b1, b2 = st.columns([1, 1])
    with b1:
        st.subheader("Issue categories")
        iss_df = _q("""
            SELECT COALESCE(issue_category,'Unknown') AS category,
                   COUNT(*) AS events,
                   ROUND(COALESCE(SUM(downtime_hours), 0)::numeric, 1) AS downtime_hrs
            FROM service_reports
            WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
              AND COALESCE(issue_category,'Unknown') = ANY(:cats)
            GROUP BY COALESCE(issue_category,'Unknown')
            ORDER BY downtime_hrs DESC
        """, engine, M)
        if iss_df.empty or pd.to_numeric(iss_df["downtime_hrs"]).sum() == 0:
            _empty_state("No downtime to chart", "No finalized events with logged downtime match the current filters.")
        else:
            _plot(_pareto_fig(iss_df, "category", "downtime_hrs", "Downtime hrs",
                                        theme.PALETTE["info"]), use_container_width=True)
    with b2:
        st.subheader("Root causes")
        rc_df = _q("""
            SELECT COALESCE(root_cause,'Unknown') AS root_cause,
                   COUNT(*) AS events,
                   ROUND(COALESCE(SUM(downtime_hours), 0)::numeric, 1) AS downtime_hrs
            FROM service_reports
            WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
              AND COALESCE(issue_category,'Unknown') = ANY(:cats)
            GROUP BY COALESCE(root_cause,'Unknown')
            ORDER BY events DESC
        """, engine, M)
        if rc_df.empty:
            _empty_state("No causes to chart", "No finalized events match the current filters.")
        else:
            _plot(_pareto_fig(rc_df, "root_cause", "events", "Events",
                                        theme.PALETTE["dept-lathe"]), use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section C — service-type mix + MTBF
    c1c, c2c = st.columns([1, 1])
    with c1c:
        st.subheader("Service-type mix")
        mix_df = _q("""
            SELECT COALESCE(service_type,'Unknown') AS type, COUNT(*) AS events
            FROM service_reports
            WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
              AND COALESCE(issue_category,'Unknown') = ANY(:cats)
            GROUP BY COALESCE(service_type,'Unknown')
        """, engine, M)
        if mix_df.empty:
            _empty_state("No events", "Nothing to chart for the current filters.")
        else:
            fig = px.pie(mix_df, values="events", names="type", hole=0.45, height=320, color="type",
                         color_discrete_map={"Preventive": theme.PALETTE["success"],
                                             "Corrective": theme.PALETTE["info"],
                                             "Emergency": theme.PALETTE["danger"],
                                             "Unknown": theme.PALETTE["text-muted"]})
            fig.update_layout(margin=dict(l=20, r=20, t=10, b=10),
                              legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
            _plot(fig, use_container_width=True)
    with c2c:
        st.subheader("Mean time between failures")
        # Both numerator (span) and denominator must reference ONLY unplanned
        # events: spanning across Preventive events would inflate the failure
        # interval. MTBF = calendar span of unplanned failures ÷ (failures − 1)
        # gaps between them (the guard below guarantees failures ≥ 2 → denom ≥ 1).
        mt = _q("""
            SELECT COUNT(*) FILTER (WHERE service_type IN ('Corrective','Emergency')
                                          AND finalized_at IS NOT NULL) AS unplanned,
                   EXTRACT(EPOCH FROM (
                       MAX(finalized_at) FILTER (WHERE service_type IN ('Corrective','Emergency'))
                     - MIN(finalized_at) FILTER (WHERE service_type IN ('Corrective','Emergency'))
                   )) / 86400.0 AS window_days
            FROM service_reports
            WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
              AND COALESCE(issue_category,'Unknown') = ANY(:cats)
        """, engine, M).iloc[0]
        unplanned = int(mt["unplanned"])
        window_days = None if pd.isna(mt["window_days"]) else float(mt["window_days"])
        if unplanned < 2 or not window_days:
            _empty_state("MTBF not computable",
                         "MTBF needs at least two finalized Corrective/Emergency events spanning time. "
                         "Too few recorded.", icon="")
        else:
            mtbf = window_days / (unplanned - 1)
            st.markdown(_metric_card("Mean Time Between Failures", f"{mtbf:.1f} days",
                        value_style=theme.value_gradient("success"),
                        footer="Avg gap between unplanned failures"), unsafe_allow_html=True)
            _insight_card("MTBF basis",
                          "Mean calendar days between consecutive unplanned (Corrective/Emergency) finalized "
                          "failures — span of those failures ÷ the gaps between them. No machine run-clock exists, "
                          "so calendar span is the defensible basis.", accent="var(--info)")
    st.markdown("<br>", unsafe_allow_html=True)

    # Finalized service log
    st.subheader("Finalized service log")
    log_df = _q("""
        SELECT service_id AS "ServiceID", asset_code AS "Asset", service_type AS "Type",
               issue_category AS "Issue", root_cause AS "RootCause",
               downtime_hours AS "DowntimeHrs", return_to_service AS "Returned",
               verified_by AS "VerifiedBy", TO_CHAR(finalized_at,'YYYY-MM-DD') AS "Finalized"
        FROM service_reports
        WHERE record_state='Final' AND COALESCE(service_type,'Unknown') = ANY(:types)
          AND COALESCE(issue_category,'Unknown') = ANY(:cats)
        ORDER BY finalized_at DESC NULLS LAST
    """, engine, M)
    if log_df.empty:
        _empty_state("No finalized reports match", "Widen the filters above to see service history.")
    else:
        st.dataframe(log_df, use_container_width=True, hide_index=True, column_config={
            "DowntimeHrs": st.column_config.NumberColumn("Downtime (hrs)", format="%.1f")})

    st.markdown("<br>", unsafe_allow_html=True)
    _maint_battery_pm(engine)


# ── TAB 3: ASSET REGISTRY ─────────────────────────────────────────────────────
def _render_asset_tab(engine):
    st.subheader("Fleet composition, age & data quality")

    cats = _q("SELECT DISTINCT COALESCE(equipment_category,'Unknown') AS equipment_category FROM assets ORDER BY 1",
              engine)["equipment_category"].tolist()
    yb = _q("SELECT MIN(build_year) AS lo, MAX(build_year) AS hi FROM assets", engine).iloc[0]
    if pd.isna(yb["lo"]):
        y_lo, y_hi = 1990, date.today().year
    else:
        y_lo, y_hi = int(yb["lo"]), int(yb["hi"])
    if y_lo >= y_hi:
        y_lo = y_hi - 1
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        sel_cats = st.multiselect("Equipment category", cats, default=cats, key="asset_cat") or cats
    with c2:
        y0, y1 = st.slider("Build year", y_lo, y_hi, (y_lo, y_hi), key="asset_years")
    with c3:
        incl_null = st.checkbox("Include unknown build year", value=True, key="asset_incl_null")
    A = {"cats": list(sel_cats), "y0": y0, "y1": y1, "incl_null": incl_null}
    _hr()

    k = _q("""
        SELECT COUNT(*)                                                      AS total,
               COUNT(*) FILTER (WHERE build_year IS NULL)                    AS missing_year,
               COUNT(*) FILTER (WHERE asset_status IS NULL)                  AS missing_status,
               COUNT(*) FILTER (WHERE planned_pm_interval_days IS NULL)      AS missing_pm,
               ROUND(AVG(EXTRACT(YEAR FROM CURRENT_DATE) - build_year)
                     FILTER (WHERE build_year IS NOT NULL), 1)               AS avg_age
        FROM assets
        WHERE COALESCE(equipment_category,'Unknown') = ANY(:cats)
          AND ((build_year BETWEEN :y0 AND :y1) OR (:incl_null AND build_year IS NULL))
    """, engine, A).iloc[0]
    total = int(k["total"]); missing_year = int(k["missing_year"])
    missing_pm = int(k["missing_pm"])
    avg_age = None if pd.isna(k["avg_age"]) else float(k["avg_age"])

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(_metric_card("Assets in Fleet", f"{total}",
                    value_style=theme.value_gradient("primary")), unsafe_allow_html=True)
    with m2:
        age_style = theme.value_gradient("danger") if (avg_age is not None and avg_age > 20) else ""
        st.markdown(_metric_card("Avg Equipment Age", _na(avg_age, "{:.0f} yrs"),
                    value_style=age_style, footer="CURRENT_DATE − build_year"), unsafe_allow_html=True)
    with m3:
        st.markdown(_metric_card("Missing Build Year", f"{missing_year}",
                    value_style=theme.value_gradient("danger") if missing_year > 0 else "",
                    footer=f"{missing_year}/{total} assets"), unsafe_allow_html=True)
    with m4:
        st.markdown(_metric_card("PM Interval Not Set", f"{missing_pm}",
                    value_style=theme.value_gradient("danger") if missing_pm > 0 else "",
                    footer="can't compute overdue PM"), unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section A — fleet composition
    s1, s2 = st.columns([1, 1])
    with s1:
        st.subheader("By equipment category")
        cat_df = _q("""
            SELECT COALESCE(equipment_category,'Unknown') AS category, COUNT(*) AS count
            FROM assets
            WHERE COALESCE(equipment_category,'Unknown') = ANY(:cats)
              AND ((build_year BETWEEN :y0 AND :y1) OR (:incl_null AND build_year IS NULL))
            GROUP BY COALESCE(equipment_category,'Unknown') ORDER BY count DESC
        """, engine, A)
        if cat_df.empty:
            _empty_state("No assets match filters", "Widen the category or build-year range.")
        else:
            fig = px.pie(cat_df, values="count", names="category", color="category",
                         color_discrete_map=theme.DEPARTMENT_COLORS, hole=0.45, height=400)
            fig.update_layout(margin=dict(l=20, r=20, t=10, b=10),
                              legend=dict(orientation="h", y=-0.1, x=0.5, xanchor="center"))
            _plot(fig, use_container_width=True)
    with s2:
        st.subheader("By department")
        dep_df = _q("""
            SELECT CASE department_code WHEN 'L' THEN 'Lathe' WHEN 'M' THEN 'Mill'
                     WHEN 'S' THEN 'Swiss' ELSE COALESCE(department_code,'Unknown') END AS department,
                   COUNT(*) AS count
            FROM assets
            WHERE COALESCE(equipment_category,'Unknown') = ANY(:cats)
              AND ((build_year BETWEEN :y0 AND :y1) OR (:incl_null AND build_year IS NULL))
            GROUP BY 1 ORDER BY count DESC
        """, engine, A)
        if dep_df.empty:
            _empty_state("No assets match filters", "Widen the category or build-year range.")
        else:
            fig = px.bar(dep_df, x="department", y="count", color="department",
                         color_discrete_map=theme.DEPARTMENT_COLORS, height=400,
                         labels={"department": "Department", "count": "Assets"})
            fig.update_layout(margin=dict(l=40, r=20, t=10, b=10), showlegend=False)
            _plot(fig, use_container_width=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section B — equipment age distribution
    e1, e2 = st.columns([2, 1])
    age_df = _q("""
        SELECT CASE
                 WHEN build_year IS NULL THEN 'Unknown'
                 WHEN EXTRACT(YEAR FROM CURRENT_DATE) - build_year < 5  THEN '0-4 yrs'
                 WHEN EXTRACT(YEAR FROM CURRENT_DATE) - build_year < 10 THEN '5-9 yrs'
                 WHEN EXTRACT(YEAR FROM CURRENT_DATE) - build_year < 20 THEN '10-19 yrs'
                 ELSE '20+ yrs'
               END AS age_band,
               COUNT(*) AS count
        FROM assets
        WHERE COALESCE(equipment_category,'Unknown') = ANY(:cats)
          AND ((build_year BETWEEN :y0 AND :y1) OR (:incl_null AND build_year IS NULL))
        GROUP BY 1
    """, engine, A)
    with e1:
        st.subheader("Equipment age distribution")
        order = ["0-4 yrs", "5-9 yrs", "10-19 yrs", "20+ yrs", "Unknown"]
        age_df = age_df.set_index("age_band").reindex(order, fill_value=0).reset_index()
        age_df.columns = ["age_band", "count"]
        bar_colors = []
        for band in age_df["age_band"]:
            if band == "20+ yrs":
                bar_colors.append(theme.PALETTE["danger"])
            elif band == "Unknown":
                bar_colors.append(theme.PALETTE["border-soft"])
            else:
                bar_colors.append(theme.PALETTE["info"])
        fig = go.Figure(go.Bar(x=age_df["age_band"], y=age_df["count"], marker_color=bar_colors))
        fig.update_layout(height=400, margin=dict(l=40, r=20, t=10, b=10),
                          xaxis_title="Age band", yaxis_title="Assets")
        _plot(fig, use_container_width=True)
    with e2:
        st.subheader("Age insight")
        n_old = int(age_df.loc[age_df["age_band"] == "20+ yrs", "count"].iloc[0])
        n_unknown = int(age_df.loc[age_df["age_band"] == "Unknown", "count"].iloc[0])
        _insight_card("Fleet age",
                      f"<strong>{n_old}</strong> asset(s) are 20+ yrs old (flag for capital-replacement review); "
                      f"<strong>{n_unknown}</strong> lack a build year and can't be aged.",
                      accent="var(--dept-lathe)")
    st.markdown("<br>", unsafe_allow_html=True)

    # Section C — battery & peripheral inventory
    i1, i2 = st.columns([1, 1])
    with i1:
        st.subheader("Battery replacement cadence")
        bat_df = _q("""
            SELECT b.replacement_interval_days AS interval_days, COUNT(*) AS batteries,
                   COUNT(DISTINCT b.asset_id) AS assets
            FROM asset_batteries b
            JOIN assets a ON b.asset_id = a.asset_id
            WHERE COALESCE(a.equipment_category,'Unknown') = ANY(:cats)
            GROUP BY b.replacement_interval_days ORDER BY b.replacement_interval_days
        """, engine, A)
        if bat_df.empty:
            _empty_state("No batteries", "No batteries registered for the selected categories.")
        else:
            bat_df["interval_days"] = bat_df["interval_days"].astype(str)
            fig = px.bar(bat_df, x="interval_days", y="batteries", height=360,
                         color_discrete_sequence=[theme.PALETTE["success"]],
                         labels={"interval_days": "Replacement interval (days)", "batteries": "Batteries"})
            fig.update_layout(margin=dict(l=40, r=20, t=10, b=10))
            _plot(fig, use_container_width=True)
            st.caption("Battery replacement cadence — drives spares planning.")
    with i2:
        st.subheader("Peripheral inventory")
        per_df = _q("""
            SELECT pe.name AS "Equipment", COALESCE(pe.make,'Unknown') AS "Make",
                   COUNT(*) AS "Units", COUNT(DISTINCT pe.asset_id) AS "OnAssets"
            FROM asset_peripheral_equipment pe
            JOIN assets a ON pe.asset_id = a.asset_id
            WHERE COALESCE(a.equipment_category,'Unknown') = ANY(:cats)
            GROUP BY pe.name, COALESCE(pe.make,'Unknown') ORDER BY "Units" DESC
        """, engine, A)
        if per_df.empty:
            _empty_state("No peripherals", "No peripheral equipment for the selected categories.")
        else:
            st.dataframe(per_df, use_container_width=True, hide_index=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # Section D — registry data quality (centerpiece)
    st.subheader("Registry data quality")
    _insight_card("Preventive-maintenance intervals not configured",
                  f"<strong>{missing_pm} of {total}</strong> in-scope assets have no planned PM interval, and "
                  "commission dates & asset status are also unpopulated. Overdue-PM tracking activates "
                  "automatically once intervals and commission/last-service dates are entered.",
                  accent="var(--danger)")
    flag_df = _q("""
        SELECT a.display_name AS "Asset", a.equipment_category AS "Category",
               CASE WHEN a.build_year IS NULL THEN '' ELSE '✓' END AS "BuildYear",
               CASE WHEN a.asset_status IS NULL THEN '' ELSE '✓' END AS "Status",
               CASE WHEN a.planned_pm_interval_days IS NULL THEN '' ELSE '✓' END AS "PMInterval",
               CASE WHEN a.commission_date IS NULL THEN '' ELSE '✓' END AS "Commissioned"
        FROM assets a
        WHERE COALESCE(a.equipment_category,'Unknown') = ANY(:cats)
          AND ((a.build_year BETWEEN :y0 AND :y1) OR (:incl_null AND a.build_year IS NULL))
        ORDER BY (a.build_year IS NULL) DESC, a.display_name
    """, engine, A)
    if flag_df.empty:
        _empty_state("No assets match filters", "Widen the category or build-year range.")
    else:
        st.dataframe(flag_df, use_container_width=True, hide_index=True)


# ── TAB 4: EXPORT ─────────────────────────────────────────────────────────────
def _render_export_tab(engine):
    st.subheader("Download reports")
    st.caption("CSV files mirror the tables shown in each tab (full datasets). The workbook bundles every "
               "view as a multi-sheet .xlsx.")
    _hr()

    n_final = int(_q("SELECT COUNT(*) AS n FROM service_reports WHERE record_state='Final'",
                     engine)["n"].iloc[0])
    # Fetch every export dataset once; reused by both the CSV buttons and the workbook.
    exports = {key: _q(sql, engine) for key, sql in _SQL_EXPORT.items()}
    left, right = st.columns([1, 1])
    with left:
        st.markdown("**Individual views (CSV)**")
        csv_buttons = [
            ("Production — Job Efficiency",        "production_jobs",         "production_jobs.csv"),
            ("Production — Scrap by Machine",      "production_scrap",        "production_scrap.csv"),
            ("Production — Logged Hours",          "production_machine_load", "production_machine_load.csv"),
            ("Maintenance — Finalized Reports",   "service_reports_final",   "service_reports_final.csv"),
            ("Maintenance — Service Parts",       "service_parts",           "service_parts.csv"),
            ("Asset Registry",                    "assets",                  "assets.csv"),
            ("Asset Batteries",                   "asset_batteries",         "asset_batteries.csv"),
            ("Asset Peripherals",                 "asset_peripherals",       "asset_peripherals.csv"),
        ]
        for label, key, fname in csv_buttons:
            st.download_button(label, data=exports[key].to_csv(index=False).encode("utf-8"),
                               file_name=fname, mime="text/csv",
                               use_container_width=True, key=f"csv_{key}")
        if n_final == 0:
            st.caption("Maintenance exports are header-only until reports are finalized.")
    with right:
        st.markdown("**Full report (Excel)**")
        xlsx_bytes = _build_full_report(engine, exports)
        st.download_button("Download Full Report (.xlsx)", data=xlsx_bytes,
            file_name=f"maintdb_report_{date.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key="dl_full_xlsx")
        _insight_card("Workbook contents",
            "9 sheets: Summary, Production_Jobs, Scrap_By_Machine, Machine_Logged_Hrs, Service_Reports, "
            "Service_Parts, Assets, Asset_Batteries, Asset_Peripherals. Maintenance sheets carry finalized "
            "reports only and are header-only until reports are finalized.", accent="var(--primary)",
            margin_top="14px")


def _render_reliability_tab(engine):
    """f2 — Bad-Actor scorecard: which machines cost the most downtime / breakdowns."""
    st.subheader("Reliability — Bad-Actor Scorecard")
    df = q.bad_actor_df(engine)
    if df.empty:
        _empty_state(
            "No finalized service reports yet",
            "Once you finalize service events, the machines with the most downtime "
            "and the most unplanned breakdowns rank here, worst first.")
        return

    total_dt = float(pd.to_numeric(df["total_downtime"]).sum())
    worst = df.iloc[0]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(_metric_card("Assets With History", len(df)), unsafe_allow_html=True)
    with c2:
        st.markdown(_metric_card("Total Downtime (hrs)", _na(total_dt)), unsafe_allow_html=True)
    with c3:
        st.markdown(_metric_card("Worst Actor", worst["asset_code"],
                                 footer=f"{_na(worst['total_downtime'])} hrs lost"),
                    unsafe_allow_html=True)

    top = df.head(12)
    st.subheader("Downtime by asset (worst first)")
    fig = px.bar(
        top, x="asset_code", y="total_downtime",
        color="equipment_category",
        labels={"total_downtime": "Downtime (hrs)", "asset_code": "Asset",
                "equipment_category": "Category"})
    fig.update_layout(height=380, margin=dict(l=40, r=20, t=48, b=40),
                      legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center"))
    _plot(fig, use_container_width=True)

    show = df.rename(columns={
        "asset_code": "Asset", "display_name": "Name", "equipment_category": "Category",
        "events": "Events", "total_downtime": "Downtime (hrs)",
        "emergencies": "Emerg.", "correctives": "Corr.", "mttr": "MTTR (hrs)",
        "last_event": "Last Event",
    })
    st.dataframe(show, use_container_width=True, hide_index=True)
    _insight_card(
        "How to read this",
        "Start at the top. These machines lose you the most production time and "
        "trigger the most unplanned repairs — they're where preventive maintenance "
        "and spares investment pay back fastest. Click an asset in the registry to "
        "see its full repair history.",
        accent="var(--danger)", margin_top="6px")


def _render_failure_modes_tab(engine):
    """f4 — Failure-mode Pareto: which root causes / issue categories dominate."""
    st.subheader("Failure Modes — Pareto Analysis")
    cdim, cmet = st.columns(2)
    with cdim:
        dim_label = st.radio("Break down by", ["Root cause", "Issue category"], horizontal=True)
    with cmet:
        metric = st.radio("Measure", ["Event count", "Downtime hours"], horizontal=True)
    dim = "root_cause" if dim_label == "Root cause" else "issue_category"
    val_col = "events" if metric == "Event count" else "downtime"

    df = q.pareto_df(engine, dim)
    if df.empty or float(pd.to_numeric(df[val_col]).sum()) == 0:
        _empty_state("No finalized service reports yet",
                     "Finalize service events to see which failure modes dominate. "
                     "Classifying each report's issue and root cause makes this sharper.")
        return

    fig = _pareto_fig(df, "category", val_col, metric, theme.PALETTE["primary"])
    _plot(fig, use_container_width=True)

    top = df.sort_values(val_col, ascending=False).iloc[0]
    _insight_card(
        "Your #1 failure mode",
        f"<strong>{top['category']}</strong> accounts for the most {metric.lower()}. "
        f"That's where prevention buys the biggest reliability gain.",
        accent="var(--primary)", margin_top="6px")
    st.dataframe(
        df.rename(columns={"category": "Category", "events": "Events", "downtime": "Downtime (hrs)"}),
        use_container_width=True, hide_index=True)


def _render_cost_tab(engine):
    """f10 — Maintenance cost: turn captured downtime + parts into dollars per
    event, per asset, and per month (the language management approves spend in)."""
    st.subheader("Maintenance Cost")
    by_asset = q.cost_by_asset_df(engine)
    if by_asset.empty or float(pd.to_numeric(by_asset["total_cost"]).sum()) == 0:
        _empty_state(
            "No costed events yet",
            "Finalize service events (with downtime and/or priced parts) to see cost "
            "per asset and per month. Set the labor and downtime rates in "
            "Advanced → Settings.")
        return

    labor = q.get_config_float(engine, "labor_rate_per_hour", 75.0)
    drate = q.get_config_float(engine, "downtime_rate_per_hour", 250.0)
    total = float(pd.to_numeric(by_asset["total_cost"]).sum())
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(_metric_card("Total Maintenance Cost", f"${total:,.0f}"), unsafe_allow_html=True)
    with c2:
        st.markdown(_metric_card("Finalized Events", int(by_asset["events"].sum())), unsafe_allow_html=True)
    with c3:
        st.markdown(_metric_card("Rate", f"${labor:.0f} + ${drate:.0f}/hr",
                                 footer="labor + downtime"), unsafe_allow_html=True)
    st.caption("Estimated. "
               "event cost = (labor + downtime rate) × downtime hours + Σ priced parts.")

    by_month = q.cost_by_month_df(engine)
    if not by_month.empty:
        st.subheader("Monthly maintenance spend")
        fig = px.bar(by_month, x="month", y="total_cost",
                     labels={"month": "Month", "total_cost": "Cost ($)"})
        fig.update_layout(height=320, margin=dict(l=40, r=20, t=10, b=40))
        _plot(fig, use_container_width=True)

    top = by_asset.head(15)
    st.subheader("Cost by asset (repair-vs-replace signal)")
    fig2 = px.bar(top, x="asset_code", y="total_cost",
                  labels={"asset_code": "Asset", "total_cost": "Cost ($)"})
    fig2.update_layout(height=340, margin=dict(l=40, r=20, t=10, b=40))
    _plot(fig2, use_container_width=True)

    st.dataframe(by_asset.rename(columns={
        "asset_code": "Asset", "display_name": "Name", "events": "Events",
        "total_cost": "Total Cost ($)", "total_downtime": "Downtime (hrs)"}),
        use_container_width=True, hide_index=True)


def render_reporting_suite_page():
    st.markdown('<div class="gradient-header">Reporting &amp; Analytics Suite</div>', unsafe_allow_html=True)

    engine = _require_db()
    if engine is None:
        return

    # Production data window, derived once (never hardcoded) and shared with Tab 1.
    win = _q("SELECT MIN(time_in)::date AS lo, MAX(time_in)::date AS hi FROM labor_tickets", engine)
    if win.empty or pd.isna(win["lo"].iloc[0]):
        data_lo = data_hi = date.today()
    else:
        data_lo = pd.to_datetime(win["lo"].iloc[0]).date()
        data_hi = pd.to_datetime(win["hi"].iloc[0]).date()
    st.caption(f"Production data window: {data_lo} → {data_hi} · Today: {date.today()}")

    (tab_prod, tab_maint, tab_rel, tab_fail,
     tab_cost, tab_asset, tab_export) = st.tabs([
        "Production",
        "Maintenance & Service",
        "Reliability",
        "Failure Modes",
        "Cost",
        "Asset Registry",
        "Export",
    ])
    with tab_prod:
        _render_production_tab(engine, data_lo, data_hi)
    with tab_maint:
        _render_maintenance_tab(engine)
    with tab_rel:
        _render_reliability_tab(engine)
    with tab_fail:
        _render_failure_modes_tab(engine)
    with tab_cost:
        _render_cost_tab(engine)
    with tab_asset:
        _render_asset_tab(engine)
    with tab_export:
        _render_export_tab(engine)

# -----------------------------------------------------------------------------
# PAGE: EDIT ASSET
# -----------------------------------------------------------------------------
def render_edit_asset_page():
    engine = _require_db()
    if engine is None:
        return
    asset_id = st.session_state.get("edit_asset_id")
    if not asset_id:
        _set_page("View Assets")
        st.rerun()

    df = pd.read_sql_query(
        text("SELECT * FROM assets WHERE asset_id = :id"), engine, params={"id": asset_id}
    )
    if df.empty:
        st.error(f"Asset {asset_id} not found.")
        return
    a = df.iloc[0]

    bat_df = pd.read_sql_query(
        text("SELECT * FROM asset_batteries WHERE asset_id = :id ORDER BY battery_number"),
        engine, params={"id": asset_id}
    )
    eq_df = pd.read_sql_query(
        text("SELECT * FROM asset_peripheral_equipment WHERE asset_id = :id ORDER BY equip_number"),
        engine, params={"id": asset_id}
    )

    st.markdown(f'<div class="gradient-header">Edit — {html.escape(str(a["display_name"] or asset_id))}</div>', unsafe_allow_html=True)

    col_back, col_del = st.columns([5, 1])
    with col_back:
        if st.button("← Back to Registry"):
            st.session_state.pop("edit_asset_id", None)
            st.session_state.pop("confirm_delete_asset", None)
            _set_page("View Assets")
            st.rerun()
    with col_del:
        if st.button("Delete Asset"):
            st.session_state.confirm_delete_asset = asset_id

    if st.session_state.get("confirm_delete_asset") == asset_id:
        st.error(f"Permanently delete **{asset_id}**? This cannot be undone.")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Yes, Delete Permanently", key="confirm_del_asset"):
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": asset_id})
                    conn.execute(text("DELETE FROM asset_batteries WHERE asset_id = :id"), {"id": asset_id})
                    conn.execute(text("DELETE FROM assets WHERE asset_id = :id"), {"id": asset_id})
                    conn.commit()
                st.cache_data.clear()  # drop the deleted asset from cached aggregates
                st.session_state.pop("confirm_delete_asset", None)
                st.session_state.pop("edit_asset_id", None)
                _set_page("View Assets")
                st.rerun()
        with c2:
            if st.button("Cancel", key="cancel_del_asset"):
                st.session_state.pop("confirm_delete_asset", None)
                st.rerun()
        return

    st.markdown("---")

    CATEGORIES   = ["Lathe", "Mill", "Swiss", "QC", "Support", "Other"]
    STATUS_OPTS  = ["Active", "Inactive", "Under Repair", "Decommissioned"]

    with st.form("edit_asset_form"):

        st.subheader("Identity & Classification")
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("Asset ID", value=asset_id, disabled=True)
            cat_idx = CATEGORIES.index(a["equipment_category"]) if a["equipment_category"] in CATEGORIES else 5
            equipment_category = st.selectbox("Equipment Category", CATEGORIES, index=cat_idx)
            primary_function   = st.text_input("Primary Function", value=a["primary_function"] or "")
            stat_idx = STATUS_OPTS.index(a["asset_status"]) if a["asset_status"] in STATUS_OPTS else 0
            asset_status = st.selectbox("Asset Status", STATUS_OPTS, index=stat_idx)
        with c2:
            display_name  = st.text_input("Display Name", value=a["display_name"] or "")
            facility      = st.text_input("Facility", value=a["facility"] or "")
            area_cell     = st.text_input("Area / Cell", value=a["area_cell"] or "")
            commission_date = st.date_input("Commission Date", value=a["commission_date"] or None)
            planned_pm    = st.number_input("Planned PM Interval (Days)",
                                            value=int(a["planned_pm_interval_days"]) if a["planned_pm_interval_days"] else 0,
                                            min_value=0, step=30)

        st.markdown("---")
        st.subheader("Technical Specifications")
        c3, c4 = st.columns(2)
        with c3:
            manufacturer  = st.text_input("Manufacturer",   value=a["manufacturer"]  or "")
            model         = st.text_input("Model",          value=a["model"]          or "")
            serial_number = st.text_input("Serial Number",  value=a["serial_number"] or "")
        with c4:
            control_type  = st.text_input("Control Type",   value=a["control_type"]  or "")
            build_year    = st.number_input("Build Year", min_value=1900, max_value=2100,
                                            value=int(a["build_year"]) if a["build_year"] else None, step=1, format="%d")

        st.markdown("---")
        st.subheader("Distributor & Contacts")
        c5, c6 = st.columns(2)
        with c5:
            distributor       = st.text_input("Distributor",       value=a["distributor"]       or "")
            distributor_email = st.text_input("Distributor Email", value=a["distributor_email"] or "")
            distributor_phone = st.text_input("Distributor Phone", value=a["distributor_phone"] or "")
        with c6:
            vendor_contacts = st.text_area("Vendor Contacts", value=a["vendor_contacts"] or "")

        st.markdown("---")
        st.subheader("Notes & Documentation")
        installation_notes = st.text_area("Installation Notes", value=a["installation_notes"] or "")
        known_quirks       = st.text_area("Known Quirks",       value=a["known_quirks"]       or "")
        c7, c8 = st.columns(2)
        with c7:
            special_tooling   = st.text_input("Special Tooling",   value=a["special_tooling"]   or "")
        with c8:
            reference_document = st.text_input("Reference Document", value=a["reference_document"] or "")

        st.markdown("---")
        st.subheader("Battery Configuration")
        bat_rows = bat_df.set_index("battery_number").to_dict("index") if not bat_df.empty else {}
        bat_cols = st.columns(3)
        battery_data = []
        for n in range(1, 4):
            b = bat_rows.get(n, {})
            with bat_cols[n - 1]:
                st.markdown(f"**Battery {n}**")
                bd = st.text_input("Description", value=b.get("description") or "", key=f"bat{n}d")
                bp = st.text_input("Part Number",  value=b.get("part_number") or "",  key=f"bat{n}p")
                bi = st.number_input("Interval (Days)", value=int(b.get("replacement_interval_days") or 0),
                                     min_value=0, step=30, key=f"bat{n}i")
            battery_data.append((n, bd, bp, bi))

        st.markdown("---")
        st.subheader("Peripheral Equipment")
        eq_rows = eq_df.set_index("equip_number").to_dict("index") if not eq_df.empty else {}
        eq_cols = st.columns(3)
        equipment_data = []
        for n in range(1, 4):
            e = eq_rows.get(n, {})
            with eq_cols[n - 1]:
                st.markdown(f"**Equipment {n}**")
                en   = st.text_input("Name",   value=e.get("name")          or "", key=f"eq{n}n")
                em   = st.text_input("Make",   value=e.get("make")          or "", key=f"eq{n}m")
                emdl = st.text_input("Model",  value=e.get("model")         or "", key=f"eq{n}mdl")
                es   = st.text_input("Serial", value=e.get("serial_number") or "", key=f"eq{n}s")
            equipment_data.append((n, en, em, emdl, es))

        saved = st.form_submit_button("Save All Changes", use_container_width=True)

    if saved:
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE assets SET
                        display_name             = :display_name,
                        short_name               = :display_name,
                        equipment_category       = :category,
                        primary_function         = :primary_function,
                        asset_status             = :asset_status,
                        facility                 = :facility,
                        area_cell                = :area_cell,
                        commission_date          = :commission_date,
                        planned_pm_interval_days = :pm_interval,
                        manufacturer             = :manufacturer,
                        model                    = :model,
                        serial_number            = :serial_number,
                        control_type             = :control_type,
                        build_year               = :build_year,
                        distributor              = :distributor,
                        distributor_email        = :distributor_email,
                        distributor_phone        = :distributor_phone,
                        vendor_contacts          = :vendor_contacts,
                        installation_notes       = :installation_notes,
                        known_quirks             = :known_quirks,
                        special_tooling          = :special_tooling,
                        reference_document       = :reference_document
                    WHERE asset_id = :asset_id
                """), {
                    "asset_id":          asset_id,
                    "display_name":      display_name.strip() or None,
                    "category":          equipment_category,
                    "primary_function":  primary_function.strip() or None,
                    "asset_status":      asset_status,
                    "facility":          facility.strip() or None,
                    "area_cell":         area_cell.strip() or None,
                    "commission_date":   commission_date,
                    "pm_interval":       planned_pm or None,
                    "manufacturer":      manufacturer.strip() or None,
                    "model":             model.strip() or None,
                    "serial_number":     serial_number.strip() or None,
                    "control_type":      control_type.strip() or None,
                    "build_year":        int(build_year) if build_year is not None else None,
                    "distributor":       distributor.strip() or None,
                    "distributor_email": distributor_email.strip() or None,
                    "distributor_phone": distributor_phone.strip() or None,
                    "vendor_contacts":   vendor_contacts.strip() or None,
                    "installation_notes": installation_notes.strip() or None,
                    "known_quirks":      known_quirks.strip() or None,
                    "special_tooling":   special_tooling.strip() or None,
                    "reference_document": reference_document.strip() or None,
                })

                conn.execute(text("DELETE FROM asset_batteries WHERE asset_id = :id"), {"id": asset_id})
                for n, desc, part, interval in battery_data:
                    if desc or part:
                        conn.execute(text("""
                            INSERT INTO asset_batteries (asset_id, battery_number, description, part_number, replacement_interval_days)
                            VALUES (:id, :n, :desc, :part, :interval)
                        """), {"id": asset_id, "n": n, "desc": desc or None,
                               "part": part or None, "interval": interval})

                conn.execute(text("DELETE FROM asset_peripheral_equipment WHERE asset_id = :id"), {"id": asset_id})
                for n, name, make, mdl, serial in equipment_data:
                    if name:
                        conn.execute(text("""
                            INSERT INTO asset_peripheral_equipment (asset_id, equip_number, name, make, model, serial_number)
                            VALUES (:id, :n, :name, :make, :model, :serial)
                        """), {"id": asset_id, "n": n, "name": name,
                               "make": make or None, "model": mdl or None, "serial": serial or None})

                conn.commit()
            st.cache_data.clear()  # refresh cached PM/floor/attention aggregates after the edit
            st.success(f"{asset_id} updated successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Error saving: {e}")


# -----------------------------------------------------------------------------
# PAGE: RECORDS MANAGER  (CRUD for ERP tables)
# -----------------------------------------------------------------------------
def _clean(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, str) and not val.strip():
        return None
    return val


def _save_crud(engine, original, edited, table, pk, pk_is_serial=False):
    with engine.connect() as conn:
        if pk_is_serial:
            existing = edited[edited[pk].notna()].copy()
            new_rows = edited[edited[pk].isna()].copy()
            # Drop the data_editor's bare ＋ rows (all non-PK cells blank) so a stray
            # click on ＋ then Save does not insert an all-NULL junk record. Genuine
            # partially-filled new rows are kept.
            non_pk = [c for c in edited.columns if c != pk]
            new_rows = new_rows[new_rows[non_pk].notna().any(axis=1)]
            orig_pks = set(original[pk].tolist())
            edit_pks = set(existing[pk].tolist())
        else:
            orig_pks = set(original[pk].tolist())
            edit_pks = set(edited[pk].tolist()) if not edited.empty else set()
            existing = edited[edited[pk].isin(orig_pks)]
            new_rows = edited[~edited[pk].isin(orig_pks)]
            # Ignore blank rows the data_editor's ＋ button leaves behind when the
            # PK column is locked — real inserts go through the dedicated Add form.
            new_rows = new_rows[
                new_rows[pk].notna() & (new_rows[pk].astype(str).str.strip() != "")
            ]

        # Deletes
        for pk_val in orig_pks - edit_pks:
            conn.execute(
                text(f"DELETE FROM {table} WHERE {pk} = :pk"),
                {"pk": int(pk_val) if pk_is_serial else pk_val}
            )

        # Updates
        non_pk_cols = [c for c in original.columns if c != pk]
        for _, row in existing.iterrows():
            orig_row = original[original[pk] == row[pk]]
            if orig_row.empty:
                continue
            params = {c: _clean(row[c]) for c in non_pk_cols}
            params[pk] = int(row[pk]) if pk_is_serial else row[pk]
            set_clause = ", ".join(f"{c} = :{c}" for c in non_pk_cols)
            conn.execute(text(f"UPDATE {table} SET {set_clause} WHERE {pk} = :{pk}"), params)

        # Inserts
        insert_cols = [c for c in edited.columns if not (pk_is_serial and c == pk)]
        for _, row in new_rows.iterrows():
            params = {c: _clean(row[c]) for c in insert_cols}
            col_list = ", ".join(insert_cols)
            val_list = ", ".join(f":{c}" for c in insert_cols)
            conn.execute(text(f"INSERT INTO {table} ({col_list}) VALUES ({val_list})"), params)

        conn.commit()
    st.cache_data.clear()  # ERP edits feed cached floor/attention/reporting reads


_CRUD_DEFAULT_CAPTION = "Add rows with the ＋ button. Click a cell to edit. Save when done."
_CRUD_LOCKED_CAPTION = (
    "IDs are locked once a record exists — edit the other fields in place and Save. "
    "Use the form below to add a record, or a row's to remove one."
)


def _friendly_db_error(e):
    """Turn a raw database error into a plain-language message, or None if unknown."""
    msg = str(getattr(e, "orig", e)).lower()
    if "foreign key" in msg:
        return ("This record is still used by other records (e.g. labor tickets). "
                "Reassign or remove those first, then try again.")
    if "duplicate key" in msg or "unique constraint" in msg:
        return "That ID already exists — pick a different one."
    return None


def _render_add_form(engine, key, table, add_fields):
    """Dedicated insert form for tables whose primary key is locked in the editor.
    add_fields: list of (column, label, kind, options) where kind is text/number/date/select.
    The first field is treated as the required primary key."""
    with st.expander("Add a new record"):
        with st.form(f"add_{key}", clear_on_submit=True):
            vals = {}
            for col, label, kind, options in add_fields:
                wkey = f"add_{key}_{col}"
                if kind == "select":
                    vals[col] = st.selectbox(label, options, key=wkey)
                elif kind == "number":
                    vals[col] = st.number_input(label, value=None, step=1.0, key=wkey)
                elif kind == "date":
                    vals[col] = st.date_input(label, value=None, key=wkey)
                else:
                    vals[col] = st.text_input(label, key=wkey)
            if st.form_submit_button("Add"):
                pk_col, pk_label = add_fields[0][0], add_fields[0][1]
                if not str(vals.get(pk_col) or "").strip():
                    st.warning(f"{pk_label} is required.")
                    return
                params = {c: _clean(v) for c, v in vals.items()}
                cols = ", ".join(vals.keys())
                ph = ", ".join(f":{c}" for c in vals.keys())
                try:
                    with engine.connect() as conn:
                        conn.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({ph})"), params)
                        conn.commit()
                    st.cache_data.clear()  # ERP inserts feed cached floor/attention/reporting reads
                    st.session_state.pop(f"records_{key}", None)
                    st.success("Added.")
                    st.rerun()
                except Exception as e:
                    st.error(_friendly_db_error(e) or f"Error: {e}")


def _crud_tab(engine, key, query, table, pk, column_config, pk_is_serial=False,
              caption=_CRUD_DEFAULT_CAPTION, add_fields=None):
    st.caption(caption)
    state_key = f"records_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = pd.read_sql_query(query, engine)

    edited = st.data_editor(
        st.session_state[state_key],
        num_rows="dynamic",
        use_container_width=True,
        column_config=column_config,
        key=f"editor_{key}",
        hide_index=True,
    )

    c1, c2, _ = st.columns([1, 1, 4])
    with c1:
        if st.button("Save", key=f"save_{key}", use_container_width=True):
            try:
                _save_crud(engine, st.session_state[state_key], edited, table, pk, pk_is_serial)
                del st.session_state[state_key]
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(_friendly_db_error(e) or f"Error: {e}")
    with c2:
        if st.button("Discard", key=f"discard_{key}", use_container_width=True):
            del st.session_state[state_key]
            st.rerun()

    if add_fields:
        _render_add_form(engine, key, table, add_fields)


def render_records_manager_page():
    st.markdown('<div class="gradient-header">Records Manager</div>', unsafe_allow_html=True)
    engine = _require_db()
    if engine is None:
        return

    tab_wc, tab_emp, tab_jobs, tab_lt = st.tabs([
        "Work Centers", "Employees", "Jobs", "Labor Tickets"
    ])

    with tab_wc:
        _crud_tab(
            engine, "wc",
            query="SELECT machine_id, machine_name, department FROM work_centers ORDER BY machine_id",
            table="work_centers", pk="machine_id",
            caption=_CRUD_LOCKED_CAPTION,
            column_config={
                "machine_id":   st.column_config.TextColumn("Machine ID", disabled=True),
                "machine_name": st.column_config.TextColumn("Machine Name", required=True),
                "department":   st.column_config.SelectboxColumn(
                    "Department", options=["Lathe", "Mill", "Swiss", "QC", "Support"], required=True
                ),
            },
            add_fields=[
                ("machine_id",   "Machine ID",   "text",   None),
                ("machine_name", "Machine Name", "text",   None),
                ("department",   "Department",   "select", ["Lathe", "Mill", "Swiss", "QC", "Support"]),
            ],
        )

    with tab_emp:
        _crud_tab(
            engine, "emp",
            query="SELECT employee_id, name, role FROM employees ORDER BY employee_id",
            table="employees", pk="employee_id",
            caption=_CRUD_LOCKED_CAPTION,
            column_config={
                "employee_id": st.column_config.TextColumn("Employee ID", disabled=True),
                "name":        st.column_config.TextColumn("Name", required=True),
                "role":        st.column_config.TextColumn("Role"),
            },
            add_fields=[
                ("employee_id", "Employee ID", "text", None),
                ("name",        "Name",        "text", None),
                ("role",        "Role",        "text", None),
            ],
        )

    with tab_jobs:
        _crud_tab(
            engine, "jobs",
            query="""
                SELECT job_no, part_no, customer, order_qty, due_date,
                       est_setup_hours, est_run_hours, status
                FROM jobs ORDER BY job_no
            """,
            table="jobs", pk="job_no",
            caption=_CRUD_LOCKED_CAPTION,
            column_config={
                "job_no":          st.column_config.TextColumn("Job #", disabled=True),
                "part_no":         st.column_config.TextColumn("Part No"),
                "customer":        st.column_config.TextColumn("Customer"),
                "order_qty":       st.column_config.NumberColumn("Order Qty", min_value=0, step=1),
                "due_date":        st.column_config.DateColumn("Due Date"),
                "est_setup_hours": st.column_config.NumberColumn("Est Setup Hrs", format="%.2f"),
                "est_run_hours":   st.column_config.NumberColumn("Est Run Hrs",   format="%.2f"),
                "status":          st.column_config.SelectboxColumn(
                    "Status", options=["Active", "Scheduled", "Completed", "On Hold"]
                ),
            },
            add_fields=[
                ("job_no",          "Job #",         "text",   None),
                ("part_no",         "Part No",       "text",   None),
                ("customer",        "Customer",      "text",   None),
                ("order_qty",       "Order Qty",     "number", None),
                ("due_date",        "Due Date",      "date",   None),
                ("est_setup_hours", "Est Setup Hrs", "number", None),
                ("est_run_hours",   "Est Run Hrs",   "number", None),
                ("status",          "Status",        "select", ["Active", "Scheduled", "Completed", "On Hold"]),
            ],
        )

    with tab_lt:
        _crud_tab(
            engine, "lt",
            caption="Ticket ID is auto-assigned on new rows. Add rows with the ＋ button.",
            query="""
                SELECT ticket_id, employee_id, job_no, machine_id, op_code, op_desc,
                       time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap
                FROM labor_tickets ORDER BY ticket_id
            """,
            table="labor_tickets", pk="ticket_id", pk_is_serial=True,
            column_config={
                "ticket_id":   st.column_config.NumberColumn("Ticket ID", disabled=True),
                "employee_id": st.column_config.TextColumn("Employee ID"),
                "job_no":      st.column_config.TextColumn("Job #"),
                "machine_id":  st.column_config.TextColumn("Machine ID"),
                "op_code":     st.column_config.TextColumn("Op Code"),
                "op_desc":     st.column_config.TextColumn("Op Description"),
                "time_in":     st.column_config.DatetimeColumn("Time In"),
                "time_out":    st.column_config.DatetimeColumn("Time Out"),
                "setup_hours": st.column_config.NumberColumn("Setup Hrs", format="%.2f"),
                "run_hours":   st.column_config.NumberColumn("Run Hrs",   format="%.2f"),
                "qty_good":    st.column_config.NumberColumn("Qty Good",  step=1),
                "qty_scrap":   st.column_config.NumberColumn("Qty Scrap", step=1),
            }
        )


# -----------------------------------------------------------------------------
# PAGE: PM SCHEDULE  (filled in Phase 2)
# -----------------------------------------------------------------------------
def render_pm_schedule_page():
    st.markdown('<div class="gradient-header">PM Schedule</div>', unsafe_allow_html=True)
    engine = _require_db()
    if engine is None:
        return

    soon = q.get_config_int(engine, "pm_due_soon_days", 14)
    st.caption(f"Preventive maintenance due dates. \"Due soon\" = within {soon} days "
               "(change in Advanced → Settings).")
    df = q.pm_schedule_df(engine, soon)
    if df.empty:
        _empty_state("No assets yet", "Register assets and set a PM interval to plan preventive maintenance.")
        return

    counts = df["status"].value_counts().to_dict()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(_metric_card("🔴 Overdue", counts.get("Overdue", 0),
                                 value_style=theme.value_gradient("danger") if counts.get("Overdue", 0) else ""),
                    unsafe_allow_html=True)
    with c2:
        st.markdown(_metric_card("🟠 Due Soon", counts.get("Due Soon", 0)), unsafe_allow_html=True)
    with c3:
        st.markdown(_metric_card("🟢 Scheduled", counts.get("Scheduled", 0)), unsafe_allow_html=True)
    with c4:
        st.markdown(_metric_card("— No interval", counts.get("No interval", 0),
                                 footer="set interval via Edit Asset"), unsafe_allow_html=True)

    if counts.get("No interval", 0) == len(df):
        _insight_card(
            "PM intervals not configured",
            "None of your assets have a planned PM interval yet, so nothing can be "
            "scheduled. Open an asset in the registry, click <strong>Edit</strong>, and "
            "set its planned PM interval (days) to start tracking due dates.",
            accent="var(--primary)", margin_top="6px")

    order = {"Overdue": 0, "Due Soon": 1, "Scheduled": 2, "No interval": 3}
    df = df.assign(_o=df["status"].map(order)).sort_values(["_o", "days_until"], na_position="last")

    accents = {"Overdue": "var(--danger)", "Due Soon": "var(--dept-mill)", "Scheduled": "var(--success)"}
    for bucket in ["Overdue", "Due Soon", "Scheduled"]:
        sub = df[df["status"] == bucket]
        if sub.empty:
            continue
        st.markdown(f"### {bucket} ({len(sub)})")
        for _, r in sub.iterrows():
            nd = pd.to_datetime(r["next_due"])
            nd_s = nd.strftime("%Y-%m-%d") if pd.notna(nd) else "—"
            du = r["days_until"]
            du_s = (f"{int(du)} days" if du >= 0 else f"{abs(int(du))} days ago") if pd.notna(du) else "—"
            interval = int(r["interval_days"]) if pd.notna(r["interval_days"]) else "—"
            cc1, cc2 = st.columns([4, 1])
            with cc1:
                st.markdown(
                    f'<div class="asset-item" style="border-left-color:{accents[bucket]};">'
                    f'<div class="asset-title">{html.escape(str(r["asset_code"]))} — {html.escape(str(r.get("display_name") or ""))}</div>'
                    f'<div style="font-size:0.88rem;color:var(--text-muted);">'
                    f'Next PM: <strong>{nd_s}</strong> ({du_s}) · every {interval} days</div></div>',
                    unsafe_allow_html=True)
            with cc2:
                if st.button("Log PM", key=f"pm_log_{r['asset_code']}", use_container_width=True):
                    _start_quick_log(asset_code=r["asset_code"], service_type="Preventive")


# -----------------------------------------------------------------------------
# PAGE: SETTINGS  (Advanced)
# -----------------------------------------------------------------------------
def render_settings_page():
    st.markdown('<div class="gradient-header">Settings</div>', unsafe_allow_html=True)
    engine = _require_db()
    if engine is None:
        return

    st.subheader("Rates & thresholds")
    st.caption("These drive the estimated service cost and the PM \"due soon\" window. "
               "Changes take effect immediately.")
    with st.form("settings_form"):
        labor = st.number_input(
            "Labor rate ($ / hour)", min_value=0.0, step=5.0,
            value=q.get_config_float(engine, "labor_rate_per_hour", 75.0))
        downtime = st.number_input(
            "Downtime cost ($ / hour)", min_value=0.0, step=10.0,
            value=q.get_config_float(engine, "downtime_rate_per_hour", 250.0))
        soon = st.number_input(
            "PM \"due soon\" window (days)", min_value=1, max_value=180, step=1,
            value=q.get_config_int(engine, "pm_due_soon_days", 14))
        if st.form_submit_button("Save settings", use_container_width=True):
            q.set_config(engine, "labor_rate_per_hour", round(float(labor), 2))
            q.set_config(engine, "downtime_rate_per_hour", round(float(downtime), 2))
            q.set_config(engine, "pm_due_soon_days", int(soon))
            st.success("Settings saved.")
            st.rerun()

    st.divider()
    st.subheader("Documents")
    st.caption("Index the manuals and PM sheets already on disk so they show on each "
               "asset's page. Safe to run repeatedly — it only adds new files.")
    if st.button("Scan asset documents", key="settings_doc_backfill"):
        n = q.backfill_documents(engine, added_by=q.current_user() or None)
        st.success(f"Indexed {n} new document(s).")

    st.divider()
    st.subheader("JobBoss sync")
    st.caption("Pull employees, jobs, and labor tickets from the JobBoss / ECI M1 "
               "system into this database. Read-only against JobBoss and safe to run "
               "repeatedly — existing rows are updated in place, never deleted.")
    st.caption(f"Status: {jobboss.status_text()}")
    if st.button("Sync from JobBoss", key="settings_jobboss_sync",
                 disabled=not jobboss.available()):
        with st.spinner("Syncing from JobBoss…"):
            res = jobboss.sync_to_postgres(engine)
        if res["ok"]:
            st.success(f"Synced — employees {res['employees']}, jobs {res['jobs']}, "
                       f"labor {res['labor']}.")
            st.rerun()
        else:
            st.warning(f"Nothing synced — {res['reason']}")

    st.divider()
    st.subheader("Identity")
    st.write(f"Signed in as: **{q.current_user() or '—'}**")
    if st.button("Clear my name", key="settings_clear_user"):
        q.set_current_user("")
        if "u" in st.query_params:   # also drop the ?u= seed, else identity re-seeds on reload
            del st.query_params["u"]
        st.rerun()


# -----------------------------------------------------------------------------
# MAIN APP ROUTER
# -----------------------------------------------------------------------------
page = st.session_state.page

if page == "Home":
    render_home_page()
elif page == "Add Asset":
    render_add_asset_page()
elif page == "View Assets":
    render_view_assets_page()
elif page == "Service Reports":
    render_service_page()
elif page == "ERP Dashboard":
    render_erp_dashboard_page()
elif page == "Reporting":
    render_reporting_suite_page()
elif page == "PM Schedule":
    render_pm_schedule_page()
elif page == "Settings":
    render_settings_page()
elif page == "Edit Asset":
    render_edit_asset_page()
elif page == "Records Manager":
    render_records_manager_page()
