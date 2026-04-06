"""
app.py — Shiny for Python web interface for the colorwork pattern generator.

Run with:  shiny run app.py
           shiny run app.py --reload   (auto-reloads on file changes)

All pattern logic lives in pattern_core.py (shared with the tkinter desktop app).
Database access uses db.py.  SQLite works fine locally; on shinyapps.io the
filesystem is ephemeral so saves will be lost on redeploy.
"""

from shiny import App, reactive, render, ui, req
import pattern_core
import db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contrast_fg(hex_color):
    """Return '#000000' or '#ffffff' whichever contrasts better with hex_color."""
    try:
        r, g, b = pattern_core._hex_to_rgb(hex_color)
        lum = 0.299*r + 0.587*g + 0.114*b
        return "#000000" if lum > 140 else "#ffffff"
    except Exception:
        return "#000000"


def _color_swatch_html(hex_color, label):
    fg = _contrast_fg(hex_color)
    return (f'<div style="display:inline-block;background:{hex_color};'
            f'color:{fg};padding:4px 10px;border-radius:4px;'
            f'font-weight:bold;font-size:13px">{label}</div>')


def _gradient_svg(fill_hex, bg_hex, width=280, height=20):
    try:
        r1, g1, b1 = pattern_core._hex_to_rgb(fill_hex)
        r2, g2, b2 = pattern_core._hex_to_rgb(bg_hex)
    except Exception:
        return ""
    steps = 60
    rects = []
    for i in range(steps):
        t  = i / (steps - 1)
        rc = int(r1 + t*(r2-r1))
        gc = int(g1 + t*(g2-g1))
        bc = int(b1 + t*(b2-b1))
        x  = int(i * width / steps)
        x2 = int((i+1) * width / steps)
        rects.append(f'<rect x="{x}" y="0" width="{x2-x}" height="{height}" '
                     f'fill="#{rc:02x}{gc:02x}{bc:02x}"/>')
    return (f'<svg width="{width}" height="{height}" '
            f'xmlns="http://www.w3.org/2000/svg">{"".join(rects)}</svg>')


def _contrast_html(fill_hex, bg_hex):
    try:
        ratio = pattern_core._contrast_ratio(fill_hex, bg_hex)
        if ratio >= 7.0:   rating, color = "Excellent", "#1a6e1a"
        elif ratio >= 4.5: rating, color = "Good",      "#2a762a"
        elif ratio >= 3.0: rating, color = "Fair",      "#a06000"
        else:              rating, color = "Low",        "#bb2222"
        return (f'<span style="color:{color};font-size:13px">'
                f'Contrast {ratio:.1f}:1 — {rating}</span>')
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

HARMONY_LABELS = ["Comp", "Split", "Split", "Analog", "Analog", "Triad", "Triad"]

# Shared CSS
_CSS = """
body { font-family: system-ui, sans-serif; }

/* compact sidebar labels */
.ctrl-label { font-weight:600; font-size:12px; color:#444;
              margin-top:10px; margin-bottom:2px; }
.shiny-input-container { margin-bottom: 4px !important; }
.shiny-input-container label { font-size: 12px; margin-bottom: 1px; }

/* tighter sliders */
.irs { margin-top:2px !important; }
.irs--shiny .irs-bar { height:3px; }
.irs--shiny .irs-handle { top:22px; width:14px; height:14px; }

/* harmony swatches */
.harmony-swatch {
    display:inline-block; width:38px; height:24px;
    border:1px solid #ccc; border-radius:3px;
    cursor:pointer; margin:2px; vertical-align:middle;
    transition: transform .1s;
}
.harmony-swatch:hover { transform: scale(1.15); }

/* pattern/tiling container: fills available width */
.grid-wrap { overflow-x:auto; overflow-y:auto; padding:4px 0; }

/* color sliders — compact */
.color-sliders .shiny-input-container { margin-bottom:2px !important; }
.color-sliders .irs { min-width:80px; }

/* sidebar tab nav — compact */
.bslib-sidebar-layout > .sidebar > .sidebar-content .nav-link {
    font-size: 12px; padding: 4px 8px;
}
/* sidebar nav fills width */
.bslib-sidebar-layout > .sidebar > .sidebar-content .nav-tabs {
    flex-wrap: nowrap;
}
"""

def _color_card(prefix, init_hex, init_k):
    """Build a fill or background color card with hex + CMYK accordion + HSL accordion."""
    label_id  = f"{prefix}_label_ui"
    is_fill   = prefix == "fill"
    title     = "Fill" if is_fill else "Background"
    return ui.card(
        ui.card_header(ui.output_ui(label_id)),
        # hex entry
        ui.div(
            ui.tags.span("Hex", style="font-size:11px;color:#666;margin-right:6px"),
            ui.input_text(f"{prefix}_hex", None,
                          value=init_hex, width="100px"),
            style="display:flex;align-items:center;margin-bottom:6px",
        ),
        # CMYK accordion
        ui.accordion(
            ui.accordion_panel(
                "CMYK",
                ui.div(
                    ui.input_slider(f"{prefix}_c", "C", 0, 100, 0,       step=1),
                    ui.input_slider(f"{prefix}_m", "M", 0, 100, 0,       step=1),
                    ui.input_slider(f"{prefix}_y", "Y", 0, 100, 0,       step=1),
                    ui.input_slider(f"{prefix}_k", "K", 0, 100, init_k,  step=1),
                    class_="color-sliders",
                ),
            ),
            id=f"{prefix}_cmyk_acc", open=False,
        ),
        # HSL accordion
        ui.accordion(
            ui.accordion_panel(
                "HSL",
                ui.div(
                    ui.input_slider(f"{prefix}_hsl_h", "H", 0, 360, 0,   step=1),
                    ui.input_slider(f"{prefix}_hsl_s", "S", 0, 100, 0,   step=1),
                    ui.input_slider(f"{prefix}_hsl_l", "L", 0, 100,
                                    0 if is_fill else 100,                step=1),
                    class_="color-sliders",
                ),
            ),
            id=f"{prefix}_hsl_acc", open=False,
        ),
        full_screen=False,
    )


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.script(src="grid_click.js"),
        ui.tags.style(_CSS),
    ),

    ui.panel_title("Colorwork Pattern Generator"),

    ui.layout_sidebar(
        # ----------------------------------------------------------------
        # Sidebar — tabbed controls
        # ----------------------------------------------------------------
        ui.sidebar(
            ui.navset_tab(

                # ----------------------------------------------------------
                # Tab 1: Pattern controls
                # ----------------------------------------------------------
                ui.nav_panel("Pattern",
                    ui.div("Rotation", class_="ctrl-label"),
                    ui.input_radio_buttons(
                        "rotation", None,
                        choices={"1":"1×","2":"2×","4":"4×"},
                        selected="4", inline=True,
                    ),
                    ui.input_checkbox("reflect", "Mirror axes", value=True),
                    ui.output_ui("group_label_ui"),

                    ui.div("Grid Size", class_="ctrl-label"),
                    ui.panel_conditional(
                        "input.rotation !== '4'",
                        ui.input_slider("grid_w", "W", 2, 25, 8, step=1),
                        ui.input_slider("grid_h", "H", 2, 25, 8, step=1),
                    ),
                    ui.panel_conditional(
                        "input.rotation === '4'",
                        ui.input_slider("grid_n", "N", 2, 25, 8, step=1),
                    ),

                    ui.div("Fill Density", class_="ctrl-label"),
                    ui.input_slider("density", None, 0.05, 0.95, 0.50, step=0.05),

                    ui.div(style="height:8px"),
                    ui.layout_columns(
                        ui.input_action_button("btn_generate", "Generate",
                                               class_="btn-primary btn-sm w-100"),
                        ui.input_action_button("btn_clear", "Clear",
                                               class_="btn-outline-secondary btn-sm w-100"),
                        col_widths=[6, 6],
                    ),

                    ui.tags.hr(style="margin:10px 0"),
                    ui.div("Cell Size", class_="ctrl-label"),
                    ui.input_slider("cell_size", None, 8, 48, 20, step=2),
                    ui.input_checkbox("show_domain", "Highlight domain", value=False),
                ),

                # ----------------------------------------------------------
                # Tab 2: Tiling controls
                # ----------------------------------------------------------
                ui.nav_panel("Tiling",
                    ui.div("Repeat", class_="ctrl-label"),
                    ui.input_checkbox("h_repeat", "Horizontal", value=False),
                    ui.input_checkbox("v_repeat", "Vertical",   value=False),

                    ui.div("Strip Width", class_="ctrl-label"),
                    ui.input_slider("strip_width", None, 0, 9, 1, step=1),
                    ui.input_checkbox("strip_h_reflect", "↕ reflect", value=False),
                    ui.input_checkbox("strip_v_reflect", "↔ reflect", value=False),

                    ui.div("H Type", class_="ctrl-label"),
                    ui.input_radio_buttons(
                        "h_type", None,
                        choices={"translation":"Transl.",
                                 "reflection":"Reflect.",
                                 "rotation":"180°"},
                        selected="translation",
                    ),

                    ui.div("V Type", class_="ctrl-label"),
                    ui.input_radio_buttons(
                        "v_type", None,
                        choices={"translation":"Transl.",
                                 "reflection":"Reflect.",
                                 "rotation":"180°"},
                        selected="translation",
                    ),

                    ui.div("Brick Offset", class_="ctrl-label"),
                    ui.input_slider("row_offset", "Row →", 0, 25, 0, step=1),
                    ui.input_slider("col_offset", "Col ↓", 0, 25, 0, step=1),

                    ui.div("Preview", class_="ctrl-label"),
                    ui.input_radio_buttons(
                        "preview_copies", None,
                        choices={"2":"2","3":"3","4":"4","5":"5"},
                        selected="3", inline=True,
                    ),
                    ui.input_slider("preview_cell_size", "Cell px", 4, 20, 8, step=2),
                ),

                # ----------------------------------------------------------
                # Tab 3: Colors
                # ----------------------------------------------------------
                ui.nav_panel("Colors",
                    _color_card("fill", "#000000", init_k=100),
                    _color_card("bg",   "#ffffff", init_k=0),
                    ui.div(
                        ui.output_ui("color_compare_ui"),
                        style="margin-top:8px",
                    ),
                ),

                # ----------------------------------------------------------
                # Tab 4: Save / Load (nested Patterns / Projects)
                # ----------------------------------------------------------
                ui.nav_panel("Save/Load",
                    ui.navset_pill(

                        ui.nav_panel("Patterns",
                            ui.output_ui("pattern_list_ui"),
                            ui.div(style="height:6px"),
                            ui.input_text("save_name_p", None,
                                          placeholder="name…"),
                            ui.layout_columns(
                                ui.input_action_button(
                                    "btn_save_pattern", "Save",
                                    class_="btn-success btn-sm w-100"),
                                ui.input_action_button(
                                    "btn_load_pattern", "Load",
                                    class_="btn-primary btn-sm w-100"),
                                ui.input_action_button(
                                    "btn_delete_p", "Del",
                                    class_="btn-outline-danger btn-sm w-100"),
                                col_widths=[4, 4, 4],
                            ),
                            ui.output_ui("save_status_ui"),
                            ui.output_ui("load_status_p_ui"),
                        ),

                        ui.nav_panel("Projects",
                            ui.output_ui("project_list_ui"),
                            ui.div(style="height:6px"),
                            ui.input_text("save_name_proj", None,
                                          placeholder="name…"),
                            ui.layout_columns(
                                ui.input_action_button(
                                    "btn_save_project", "Save",
                                    class_="btn-success btn-sm w-100"),
                                ui.input_action_button(
                                    "btn_load_project", "Load",
                                    class_="btn-primary btn-sm w-100"),
                                ui.input_action_button(
                                    "btn_delete_proj", "Del",
                                    class_="btn-outline-danger btn-sm w-100"),
                                col_widths=[4, 4, 4],
                            ),
                            ui.output_ui("save_status_proj_ui"),
                            ui.output_ui("load_status_proj_ui"),
                        ),

                    ),
                ),

            ),  # end navset_tab
            width=290,
        ),

        # ----------------------------------------------------------------
        # Main content — Pattern and Tiling always side by side
        # ----------------------------------------------------------------
        ui.layout_columns(
            ui.div(
                ui.tags.p("Pattern",
                          style="font-weight:600;font-size:13px;margin:0 0 4px"),
                ui.div(ui.output_ui("grid_output"), class_="grid-wrap"),
            ),
            ui.div(
                ui.tags.p("Tiling Preview",
                          style="font-weight:600;font-size:13px;margin:0 0 4px"),
                ui.div(ui.output_ui("tiling_output"), class_="grid-wrap"),
            ),
            col_widths=[6, 6],
        ),
    ),  # end layout_sidebar
)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def server(input, output, session):

    # ----------------------------------------------------------------
    # Mutable state (cf. PatternApp attributes in pattern_generator.py)
    # ----------------------------------------------------------------
    H_rv               = reactive.Value(8)
    W_rv               = reactive.Value(8)
    grid_rv            = reactive.Value([[False]*8 for _ in range(8)])
    domain_cells_rv    = reactive.Value(set())
    cell_to_can_rv     = reactive.Value({})
    col_strip_rv       = reactive.Value([])
    row_strip_rv       = reactive.Value([])
    corner_rv          = reactive.Value([])
    fill_hex_rv        = reactive.Value("#000000")
    bg_hex_rv          = reactive.Value("#ffffff")
    save_msg_rv        = reactive.Value("")
    load_msg_rv        = reactive.Value("")
    selected_id_rv     = reactive.Value(None)   # selected row in load list

    # ----------------------------------------------------------------
    # Helpers: orbit function and domain from current inputs
    # ----------------------------------------------------------------
    def _orbit_fn():
        return pattern_core.ORBIT_FNS[
            (int(input.rotation()), bool(input.reflect()))
        ]

    def _dims():
        rot = int(input.rotation())
        if rot == 4:
            n = input.grid_n()
            return n, n
        return input.grid_h(), input.grid_w()

    def _resize_strips(H, W, sw):
        def _resize(old, rows, cols):
            new = [[False]*cols for _ in range(rows)]
            for r in range(min(rows, len(old))):
                for c in range(min(cols,
                                   len(old[r]) if r < len(old) else 0)):
                    new[r][c] = old[r][c]
            return new
        col_strip_rv.set(_resize(col_strip_rv.get(), H,  sw))
        row_strip_rv.set(_resize(row_strip_rv.get(), sw, W))
        corner_rv.set(   _resize(corner_rv.get(),    sw, sw))

    def _rebuild_domain(H, W, orbit_fn):
        domain = pattern_core.compute_fundamental_domain(H, W, orbit_fn)
        domain_cells_rv.set(set(domain))
        ctc = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, H, W):
                ctc[(dr, dc)] = (r, c)
        cell_to_can_rv.set(ctc)

    # ----------------------------------------------------------------
    # Generate
    # ----------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.btn_generate)
    def _generate():
        H, W = _dims()
        H_rv.set(H); W_rv.set(W)
        sw = input.strip_width()
        _resize_strips(H, W, sw)
        orbit_fn = _orbit_fn()
        grid, domain = pattern_core.generate_pattern(
            H, W, orbit_fn, input.density()
        )
        grid_rv.set(grid)
        domain_cells_rv.set(set(domain))
        ctc = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, H, W):
                ctc[(dr, dc)] = (r, c)
        cell_to_can_rv.set(ctc)

    # Run once on startup
    @reactive.effect
    def _initial_generate():
        H, W = _dims()
        H_rv.set(H); W_rv.set(W)
        sw = input.strip_width()
        _resize_strips(H, W, sw)
        orbit_fn = _orbit_fn()
        grid, domain = pattern_core.generate_pattern(H, W, orbit_fn, 0.5)
        grid_rv.set(grid)
        domain_cells_rv.set(set(domain))
        ctc = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, H, W):
                ctc[(dr, dc)] = (r, c)
        cell_to_can_rv.set(ctc)
        _initial_generate.destroy()

    # ----------------------------------------------------------------
    # Clear
    # ----------------------------------------------------------------
    @reactive.effect
    @reactive.event(input.btn_clear)
    def _clear():
        H, W = H_rv.get(), W_rv.get()
        sw   = input.strip_width()
        grid_rv.set([[False]*W for _ in range(H)])
        col_strip_rv.set([[False]*sw for _ in range(H)])
        row_strip_rv.set([[False]*W  for _ in range(sw)])
        corner_rv.set(   [[False]*sw for _ in range(sw)])
        domain_cells_rv.set(set())

    # ----------------------------------------------------------------
    # Cell click  (cf. PatternApp._on_click)
    # ----------------------------------------------------------------
    @reactive.effect
    def _on_cell_click():
        click = input.cell_click()
        req(click)
        with reactive.isolate():
            r, c, region = click["row"], click["col"], click["region"]
            H, W = H_rv.get(), W_rv.get()
            sw   = input.strip_width()
            h_on = input.h_repeat() and sw > 0
            v_on = input.v_repeat() and sw > 0

            if region == "tile":
                canonical = cell_to_can_rv.get().get((r, c))
                if canonical is None: return
                r0, c0  = canonical
                g       = [row[:] for row in grid_rv.get()]
                new_val = not g[r0][c0]
                orbit_fn = _orbit_fn()
                for (dr, dc) in orbit_fn(r0, c0, H, W):
                    g[dr][dc] = new_val
                grid_rv.set(g)

            elif region == "col_strip" and h_on:
                sc  = c
                col = [row[:] for row in col_strip_rv.get()]
                new_val = not col[r][sc]
                rows_to_set = {r, H-1-r} if input.strip_h_reflect() else {r}
                cols_to_set = {sc, sw-1-sc} if input.strip_v_reflect() else {sc}
                for rr in rows_to_set:
                    for cc in cols_to_set:
                        if 0 <= rr < len(col) and 0 <= cc < len(col[rr]):
                            col[rr][cc] = new_val
                col_strip_rv.set(col)

            elif region == "row_strip" and v_on:
                sr  = r
                row = [row[:] for row in row_strip_rv.get()]
                new_val = not row[sr][c]
                rows_to_set = {sr, sw-1-sr} if input.strip_h_reflect() else {sr}
                cols_to_set = {c,  W-1-c}   if input.strip_v_reflect() else {c}
                for rr in rows_to_set:
                    for cc in cols_to_set:
                        if 0 <= rr < len(row) and 0 <= cc < len(row[rr]):
                            row[rr][cc] = new_val
                row_strip_rv.set(row)

            elif region == "corner" and h_on and v_on:
                sr, sc = r, c
                corn   = [row[:] for row in corner_rv.get()]
                new_val = not corn[sr][sc]
                rows_to_set = {sr, sw-1-sr} if input.strip_h_reflect() else {sr}
                cols_to_set = {sc, sw-1-sc} if input.strip_v_reflect() else {sc}
                for rr in rows_to_set:
                    for cc in cols_to_set:
                        if 0 <= rr < len(corn) and 0 <= cc < len(corn[rr]):
                            corn[rr][cc] = new_val
                corner_rv.set(corn)

    # ----------------------------------------------------------------
    # Color sync — single source of truth per color: fill_hex_rv / bg_hex_rv
    # Changing any CMYK, HSL, or hex input updates the rv; the rv drives all
    # other controls (cf. the _updating flag in ColorPicker).
    # ----------------------------------------------------------------
    _color_syncing = {"fill": False, "bg": False}

    def _sync_fill_from_hex(hex_str):
        fill_hex_rv.set(hex_str)
        result = pattern_core.hex_to_cmyk(hex_str)
        if result:
            c, m, y, k = result
            ui.update_slider("fill_c", value=c, session=session)
            ui.update_slider("fill_m", value=m, session=session)
            ui.update_slider("fill_y", value=y, session=session)
            ui.update_slider("fill_k", value=k, session=session)
        try:
            r, g, b = pattern_core._hex_to_rgb(hex_str)
            h, s, l = pattern_core._rgb_to_hsl(r, g, b)
            ui.update_slider("fill_hsl_h", value=round(h),     session=session)
            ui.update_slider("fill_hsl_s", value=round(s*100), session=session)
            ui.update_slider("fill_hsl_l", value=round(l*100), session=session)
        except Exception:
            pass
        ui.update_text("fill_hex", value=hex_str, session=session)

    def _sync_bg_from_hex(hex_str):
        bg_hex_rv.set(hex_str)
        result = pattern_core.hex_to_cmyk(hex_str)
        if result:
            c, m, y, k = result
            ui.update_slider("bg_c", value=c, session=session)
            ui.update_slider("bg_m", value=m, session=session)
            ui.update_slider("bg_y", value=y, session=session)
            ui.update_slider("bg_k", value=k, session=session)
        try:
            r, g, b = pattern_core._hex_to_rgb(hex_str)
            h, s, l = pattern_core._rgb_to_hsl(r, g, b)
            ui.update_slider("bg_hsl_h", value=round(h),     session=session)
            ui.update_slider("bg_hsl_s", value=round(s*100), session=session)
            ui.update_slider("bg_hsl_l", value=round(l*100), session=session)
        except Exception:
            pass
        ui.update_text("bg_hex", value=hex_str, session=session)

    @reactive.effect
    @reactive.event(input.fill_c, input.fill_m, input.fill_y, input.fill_k)
    def _fill_from_cmyk():
        if _color_syncing["fill"]: return
        _color_syncing["fill"] = True
        try:
            hex_str = pattern_core.cmyk_to_hex(
                input.fill_c(), input.fill_m(),
                input.fill_y(), input.fill_k()
            )
            _sync_fill_from_hex(hex_str)
        finally:
            _color_syncing["fill"] = False

    @reactive.effect
    @reactive.event(input.fill_hsl_h, input.fill_hsl_s, input.fill_hsl_l)
    def _fill_from_hsl():
        if _color_syncing["fill"]: return
        _color_syncing["fill"] = True
        try:
            hex_str = pattern_core._hsl_to_hex(
                input.fill_hsl_h(),
                input.fill_hsl_s() / 100.0,
                input.fill_hsl_l() / 100.0,
            )
            _sync_fill_from_hex(hex_str)
        finally:
            _color_syncing["fill"] = False

    @reactive.effect
    @reactive.event(input.fill_hex)
    def _fill_from_hex():
        if _color_syncing["fill"]: return
        _color_syncing["fill"] = True
        try:
            raw = input.fill_hex().strip()
            hex_str = raw if raw.startswith("#") else "#" + raw
            if pattern_core.hex_to_cmyk(hex_str):
                _sync_fill_from_hex(hex_str)
        finally:
            _color_syncing["fill"] = False

    @reactive.effect
    @reactive.event(input.bg_c, input.bg_m, input.bg_y, input.bg_k)
    def _bg_from_cmyk():
        if _color_syncing["bg"]: return
        _color_syncing["bg"] = True
        try:
            hex_str = pattern_core.cmyk_to_hex(
                input.bg_c(), input.bg_m(),
                input.bg_y(), input.bg_k()
            )
            _sync_bg_from_hex(hex_str)
        finally:
            _color_syncing["bg"] = False

    @reactive.effect
    @reactive.event(input.bg_hsl_h, input.bg_hsl_s, input.bg_hsl_l)
    def _bg_from_hsl():
        if _color_syncing["bg"]: return
        _color_syncing["bg"] = True
        try:
            hex_str = pattern_core._hsl_to_hex(
                input.bg_hsl_h(),
                input.bg_hsl_s() / 100.0,
                input.bg_hsl_l() / 100.0,
            )
            _sync_bg_from_hex(hex_str)
        finally:
            _color_syncing["bg"] = False

    @reactive.effect
    @reactive.event(input.bg_hex)
    def _bg_from_hex():
        if _color_syncing["bg"]: return
        _color_syncing["bg"] = True
        try:
            raw = input.bg_hex().strip()
            hex_str = raw if raw.startswith("#") else "#" + raw
            if pattern_core.hex_to_cmyk(hex_str):
                _sync_bg_from_hex(hex_str)
        finally:
            _color_syncing["bg"] = False

    # ----------------------------------------------------------------
    # Outputs — Pattern tab
    # ----------------------------------------------------------------
    @render.ui
    def group_label_ui():
        key = (int(input.rotation()), bool(input.reflect()))
        name = pattern_core.GROUP_NAMES.get(key, "")
        return ui.span(f"Group: {name}", style="color:#555;font-size:12px")

    @render.ui
    def grid_output():
        H, W = H_rv.get(), W_rv.get()
        sw   = input.strip_width()
        h_on = input.h_repeat() and sw > 0
        v_on = input.v_repeat() and sw > 0
        cs   = input.cell_size()
        descriptors = pattern_core.get_tile_descriptors(
            grid=grid_rv.get(), H=H, W=W, cell_size=cs,
            fill_color=fill_hex_rv.get(),
            bg_color=bg_hex_rv.get(),
            domain_cells=domain_cells_rv.get(),
            show_domain=input.show_domain(),
            col_strip=col_strip_rv.get(),
            row_strip=row_strip_rv.get(),
            corner=corner_rv.get(),
            h_on=h_on, v_on=v_on, strip_width=sw,
        )
        cw, ch = pattern_core.tile_canvas_size(H, W, cs, h_on, v_on, sw)
        svg = pattern_core.render_grid_svg(descriptors, cw, ch, responsive=True)
        return ui.HTML(svg)

    # ----------------------------------------------------------------
    # Outputs — Colors tab
    # ----------------------------------------------------------------
    @render.ui
    def fill_label_ui():
        return ui.HTML(_color_swatch_html(fill_hex_rv.get(), "Fill"))

    @render.ui
    def bg_label_ui():
        return ui.HTML(_color_swatch_html(bg_hex_rv.get(), "Background"))

    @render.ui
    def color_compare_ui():
        fill = fill_hex_rv.get()
        bg   = bg_hex_rv.get()
        harmonies = pattern_core._harmony_colors(fill)

        swatch_html = ""
        for label, hx in zip(HARMONY_LABELS, harmonies):
            swatch_html += (
                f'<span title="{label}: {hx}" '
                f'class="harmony-swatch" style="background:{hx}" '
                f'onclick="Shiny.setInputValue(\'harmony_click\','
                f'{{hex:\'{hx}\',nonce:Math.random()}},{{priority:\'event\'}})">'
                f'</span>'
            )

        return ui.HTML(
            f'<div style="margin-bottom:8px">'
            f'  <span style="font-size:11px;color:#888">Fill</span>'
            f'  {_gradient_svg(fill, bg)}'
            f'  <span style="font-size:11px;color:#888">Background</span>'
            f'</div>'
            f'<div style="margin-bottom:10px">{_contrast_html(fill, bg)}</div>'
            f'<div><span style="font-size:11px;color:#888">Harmonies → </span>'
            f'{swatch_html}</div>'
        )

    # Clicking a harmony swatch sets the background color
    @reactive.effect
    def _harmony_click():
        click = input.harmony_click()
        req(click)
        _sync_bg_from_hex(click["hex"])

    # ----------------------------------------------------------------
    # Outputs — Tiling tab
    # ----------------------------------------------------------------
    @render.ui
    def tiling_output():
        H, W = H_rv.get(), W_rv.get()
        cs   = input.preview_cell_size()
        descriptors, rows, cols = pattern_core.get_tiling_descriptors(
            grid=grid_rv.get(), H=H, W=W, cell_size=cs,
            fill_color=fill_hex_rv.get(),
            bg_color=bg_hex_rv.get(),
            h_repeat=input.h_repeat(),
            v_repeat=input.v_repeat(),
            strip_width=input.strip_width(),
            h_type=input.h_type(),
            v_type=input.v_type(),
            col_strip=col_strip_rv.get(),
            row_strip=row_strip_rv.get(),
            corner=corner_rv.get(),
            n_copies=int(input.preview_copies()),
            row_offset=input.row_offset(),
            col_offset=input.col_offset(),
        )
        svg = pattern_core.render_tiling_svg(descriptors, rows, cols, cs, responsive=True)
        return ui.HTML(svg)

    # ----------------------------------------------------------------
    # Outputs — Save / Load tab
    # ----------------------------------------------------------------
    save_msg_proj_rv = reactive.Value("")
    load_msg_p_rv    = reactive.Value("")
    load_msg_proj_rv = reactive.Value("")
    db_rev_rv        = reactive.Value(0)   # bumped after any save or delete

    @render.ui
    def save_status_ui():
        msg = save_msg_rv.get()
        if not msg: return ui.span()
        return ui.div(msg, style="margin-top:6px;font-size:12px;color:#1a6e1a")

    @render.ui
    def save_status_proj_ui():
        msg = save_msg_proj_rv.get()
        if not msg: return ui.span()
        return ui.div(msg, style="margin-top:6px;font-size:12px;color:#1a6e1a")

    @render.ui
    def load_status_p_ui():
        msg = load_msg_p_rv.get()
        if not msg: return ui.span()
        return ui.div(msg, style="margin-top:6px;font-size:12px;color:#bb2222")

    @render.ui
    def load_status_proj_ui():
        msg = load_msg_proj_rv.get()
        if not msg: return ui.span()
        return ui.div(msg, style="margin-top:6px;font-size:12px;color:#bb2222")

    def _list_row(rid, name, detail, selected_id):
        selected = (rid == selected_id)
        bg = "background:#cce5ff" if selected else ""
        return ui.tags.tr(
            ui.tags.td(
                ui.span(name, style="font-weight:600"), ui.tags.br(),
                ui.span(detail, style="font-size:11px;color:#666"),
                style="padding:4px 6px",
            ),
            style=f"cursor:pointer;{bg};border-bottom:1px solid #eee",
            onclick=(
                f"Shiny.setInputValue('list_select',"
                f"{{id:'{rid}',nonce:Math.random()}},"
                f"{{priority:'event'}})"
            ),
        )

    @render.ui
    def pattern_list_ui():
        db_rev_rv.get()          # reactive dependency — re-renders after save/delete
        patterns = db.list_patterns()
        sel = selected_id_rv.get()
        if not patterns:
            return ui.p("No saved patterns.", style="color:#888;font-size:12px")
        rows = [
            _list_row(
                f"p_{p['id']}", p["name"],
                f"{p['created_at'][:16]} · {p['grid_w']}×{p['grid_h']} · {p['symmetry_group']}",
                sel,
            )
            for p in patterns
        ]
        return ui.tags.table(*rows,
            style="width:100%;border-collapse:collapse;font-size:13px")

    @render.ui
    def project_list_ui():
        db_rev_rv.get()          # reactive dependency — re-renders after save/delete
        projects = db.list_projects()
        sel = selected_id_rv.get()
        if not projects:
            return ui.p("No saved projects.", style="color:#888;font-size:12px")
        rows = [
            _list_row(
                f"proj_{p['id']}", p["name"],
                p["created_at"][:16],
                sel,
            )
            for p in projects
        ]
        return ui.tags.table(*rows,
            style="width:100%;border-collapse:collapse;font-size:13px")

    @reactive.effect
    def _list_select():
        sel = input.list_select()
        req(sel)
        selected_id_rv.set(sel["id"])

    def _restore_project(data):
        tile   = data["tile"]
        strips = data["strips"]
        tiling = data["tiling"]
        H, W   = tile["grid_h"], tile["grid_w"]
        H_rv.set(H); W_rv.set(W)
        rotation, reflect = pattern_core.GROUP_TO_PARAMS[tile["symmetry_group"]]
        ui.update_radio_buttons("rotation",  selected=str(rotation), session=session)
        ui.update_checkbox("reflect",        value=reflect,          session=session)
        ui.update_slider("grid_w",           value=W,                session=session)
        ui.update_slider("grid_h",           value=H,                session=session)
        ui.update_slider("grid_n",           value=W,                session=session)
        ui.update_slider("cell_size",        value=tile.get("cell_size", 20),
                                                                      session=session)
        _sync_fill_from_hex(tile["fill_color"])
        _sync_bg_from_hex(tile["bg_color"])
        ui.update_slider("density", value=tile["fill_density"], session=session)
        grid_rv.set(tile["grid"])
        orbit_fn = pattern_core.ORBIT_FNS[(rotation, reflect)]
        _rebuild_domain(H, W, orbit_fn)

        sw = strips["width"]
        ui.update_slider("strip_width",     value=sw,                 session=session)
        ui.update_checkbox("strip_h_reflect", value=strips["h_reflect"],session=session)
        ui.update_checkbox("strip_v_reflect", value=strips["v_reflect"],session=session)
        col_strip_rv.set(strips["col_strip"])
        row_strip_rv.set(strips["row_strip"])
        corner_rv.set(   strips["corner"])

        ui.update_checkbox("h_repeat", value=tiling["h_repeat"], session=session)
        ui.update_checkbox("v_repeat", value=tiling["v_repeat"], session=session)
        ui.update_radio_buttons("h_type", selected=tiling["h_type"], session=session)
        ui.update_radio_buttons("v_type", selected=tiling["v_type"], session=session)
        ui.update_slider("row_offset", value=tiling.get("row_offset", 0),
                                                                    session=session)
        ui.update_slider("col_offset", value=tiling.get("col_offset", 0),
                                                                    session=session)

    @reactive.effect
    @reactive.event(input.btn_save_pattern)
    def _save_pattern():
        name = input.save_name_p().strip()
        if not name:
            save_msg_rv.set("Enter a name first.")
            return
        H, W = H_rv.get(), W_rv.get()
        key  = (int(input.rotation()), bool(input.reflect()))
        try:
            pid = db.save_pattern(
                name=name, grid_w=W, grid_h=H,
                symmetry_group=pattern_core.GROUP_NAMES[key],
                fill_color=fill_hex_rv.get(),
                bg_color=bg_hex_rv.get(),
                fill_density=input.density(),
                grid=grid_rv.get(),
            )
            save_msg_rv.set(f"Pattern saved (id {pid}).")
            ui.update_text("save_name_p", value="", session=session)
            db_rev_rv.set(db_rev_rv.get() + 1)
        except Exception as e:
            save_msg_rv.set(f"Error: {e}")

    @reactive.effect
    @reactive.event(input.btn_save_project)
    def _save_project():
        name = input.save_name_proj().strip()
        if not name:
            save_msg_proj_rv.set("Enter a name first.")
            return
        key  = (int(input.rotation()), bool(input.reflect()))
        data = {
            "tile": {
                "grid_w": W_rv.get(), "grid_h": H_rv.get(),
                "symmetry_group": pattern_core.GROUP_NAMES[key],
                "fill_color": fill_hex_rv.get(),
                "bg_color":   bg_hex_rv.get(),
                "fill_density": input.density(),
                "cell_size":    input.cell_size(),
                "grid":         grid_rv.get(),
            },
            "strips": {
                "width":     input.strip_width(),
                "h_reflect": input.strip_h_reflect(),
                "v_reflect": input.strip_v_reflect(),
                "col_strip": col_strip_rv.get(),
                "row_strip": row_strip_rv.get(),
                "corner":    corner_rv.get(),
            },
            "tiling": {
                "h_repeat":   input.h_repeat(),
                "v_repeat":   input.v_repeat(),
                "h_type":     input.h_type(),
                "v_type":     input.v_type(),
                "row_offset": input.row_offset(),
                "col_offset": input.col_offset(),
            },
        }
        try:
            pid = db.save_project(name, data)
            save_msg_proj_rv.set(f"Project saved (id {pid}).")
            ui.update_text("save_name_proj", value="", session=session)
            db_rev_rv.set(db_rev_rv.get() + 1)
        except Exception as e:
            save_msg_proj_rv.set(f"Error: {e}")

    @reactive.effect
    @reactive.event(input.btn_load_pattern)
    def _load_pattern():
        sel = selected_id_rv.get()
        if not sel or not sel.startswith("p_"):
            load_msg_p_rv.set("Select a pattern first.")
            return
        pid  = int(sel[2:])
        data = db.load_pattern(pid)
        if data is None:
            load_msg_p_rv.set("Pattern not found.")
            return
        H, W = data["grid_h"], data["grid_w"]
        H_rv.set(H); W_rv.set(W)
        rotation, reflect = pattern_core.GROUP_TO_PARAMS[data["symmetry_group"]]
        ui.update_radio_buttons("rotation", selected=str(rotation), session=session)
        ui.update_checkbox("reflect",       value=reflect,          session=session)
        ui.update_slider("grid_w",          value=W,                session=session)
        ui.update_slider("grid_h",          value=H,                session=session)
        ui.update_slider("grid_n",          value=W,                session=session)
        _sync_fill_from_hex(data["fill_color"])
        _sync_bg_from_hex(data["bg_color"])
        ui.update_slider("density", value=data["fill_density"], session=session)
        grid_rv.set(data["grid"])
        orbit_fn = pattern_core.ORBIT_FNS[(rotation, reflect)]
        _rebuild_domain(H, W, orbit_fn)
        _resize_strips(H, W, input.strip_width())
        load_msg_p_rv.set("")

    @reactive.effect
    @reactive.event(input.btn_load_project)
    def _load_project():
        sel = selected_id_rv.get()
        if not sel or not sel.startswith("proj_"):
            load_msg_proj_rv.set("Select a project first.")
            return
        pid = int(sel[5:])
        row = db.load_project(pid)
        if row is None:
            load_msg_proj_rv.set("Project not found.")
            return
        _restore_project(row["data"])
        load_msg_proj_rv.set("")

    @reactive.effect
    @reactive.event(input.btn_delete_p)
    def _delete_p():
        sel = selected_id_rv.get()
        if not sel or not sel.startswith("p_"):
            load_msg_p_rv.set("Select a pattern first.")
            return
        try:
            db.delete_pattern(int(sel[2:]))
            selected_id_rv.set(None)
            db_rev_rv.set(db_rev_rv.get() + 1)
            load_msg_p_rv.set("Deleted.")
        except Exception as e:
            load_msg_p_rv.set(f"Error: {e}")

    @reactive.effect
    @reactive.event(input.btn_delete_proj)
    def _delete_proj():
        sel = selected_id_rv.get()
        if not sel or not sel.startswith("proj_"):
            load_msg_proj_rv.set("Select a project first.")
            return
        try:
            db.delete_project(int(sel[5:]))
            selected_id_rv.set(None)
            db_rev_rv.set(db_rev_rv.get() + 1)
            load_msg_proj_rv.set("Deleted.")
        except Exception as e:
            load_msg_proj_rv.set(f"Error: {e}")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

import os as _os
app = App(app_ui, server,
          static_assets=_os.path.join(_os.path.dirname(__file__), "www"))
