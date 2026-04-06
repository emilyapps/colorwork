"""
pattern_core.py — shared logic for the colorwork pattern generator.

No tkinter, no GUI dependencies.  Both pattern_generator.py (tkinter desktop)
and app.py (Shiny web) import from here.

Public surface
--------------
Constants      : PADDING, NUM_W, NUM_H, STRIP_BG, STRIP_LINE
Orbit / groups : c1_orbit … d4_orbit, ORBIT_FNS, GROUP_NAMES, GROUP_TO_PARAMS
Color utils    : cmyk_to_hex, hex_to_cmyk, _hex_to_rgb, _rgb_to_hsl,
                 _hsl_to_hex, _relative_luminance, _contrast_ratio,
                 _harmony_colors
Pattern logic  : compute_fundamental_domain, generate_pattern
Tiling logic   : transformed_tile, build_tiling_grid
Layout         : tile_canvas_size, get_tile_descriptors, get_tiling_descriptors
SVG renderers  : render_grid_svg, render_tiling_svg
"""

import random

# ---------------------------------------------------------------------------
# Layout constants (shared by tkinter and SVG renderers)
# ---------------------------------------------------------------------------

PADDING    = 20   # px margin around tile on all sides
NUM_W      = 26   # extra right margin for row numbers
NUM_H      = 16   # extra bottom margin for col numbers
STRIP_BG   = "#e8e8e8"
STRIP_LINE = "#aaaaaa"


# ---------------------------------------------------------------------------
# Symmetry orbit functions  (r, c, H, W) → set of equivalent cells
# ---------------------------------------------------------------------------

def c1_orbit(r, c, H, W): return {(r, c)}
def d1_orbit(r, c, H, W): return {(r, c), (r, W-1-c)}
def c2_orbit(r, c, H, W): return {(r, c), (H-1-r, W-1-c)}
def d2_orbit(r, c, H, W): return {(r,c),(H-1-r,W-1-c),(r,W-1-c),(H-1-r,c)}

def c4_orbit(r, c, H, W):
    N = H  # H == W for 4× symmetry
    return {(r,c),(c,N-1-r),(N-1-r,N-1-c),(N-1-c,r)}

def d4_orbit(r, c, H, W):
    N = H
    return {
        (r,c),(c,N-1-r),(N-1-r,N-1-c),(N-1-c,r),
        (r,N-1-c),(N-1-r,c),(c,r),(N-1-c,N-1-r),
    }

ORBIT_FNS = {
    (1, False): c1_orbit, (1, True): d1_orbit,
    (2, False): c2_orbit, (2, True): d2_orbit,
    (4, False): c4_orbit, (4, True): d4_orbit,
}
GROUP_NAMES = {
    (1,False):"C1",(1,True):"D1",
    (2,False):"C2",(2,True):"D2",
    (4,False):"C4",(4,True):"D4",
}
GROUP_TO_PARAMS = {v: k for k, v in GROUP_NAMES.items()}


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

def cmyk_to_hex(c, m, y, k):
    r = round(255 * (1 - c/100) * (1 - k/100))
    g = round(255 * (1 - m/100) * (1 - k/100))
    b = round(255 * (1 - y/100) * (1 - k/100))
    return f"#{r:02x}{g:02x}{b:02x}"

def hex_to_cmyk(hex_str):
    hex_str = hex_str.strip().lstrip("#")
    if len(hex_str) != 6:
        return None
    try:
        r, g, b = int(hex_str[0:2],16), int(hex_str[2:4],16), int(hex_str[4:6],16)
    except ValueError:
        return None
    r_, g_, b_ = r/255, g/255, b/255
    k_ = 1 - max(r_, g_, b_)
    if k_ == 1:
        return (0, 0, 0, 100)
    c_ = (1 - r_ - k_) / (1 - k_)
    m_ = (1 - g_ - k_) / (1 - k_)
    y_ = (1 - b_ - k_) / (1 - k_)
    return (round(c_*100), round(m_*100), round(y_*100), round(k_*100))

def _hex_to_rgb(hex_str):
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

def _rgb_to_hsl(r, g, b):
    r, g, b = r/255, g/255, b/255
    cmax, cmin = max(r,g,b), min(r,g,b)
    delta = cmax - cmin
    l = (cmax + cmin) / 2
    s = 0.0 if delta == 0 else delta / (1 - abs(2*l - 1))
    if delta == 0:
        h = 0.0
    elif cmax == r:
        h = 60 * (((g - b) / delta) % 6)
    elif cmax == g:
        h = 60 * ((b - r) / delta + 2)
    else:
        h = 60 * ((r - g) / delta + 4)
    return h % 360, s, l

def _hsl_to_hex(h, s, l):
    h = h % 360
    c = (1 - abs(2*l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    if   h < 60:  r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:         r, g, b = c, 0, x
    return f"#{int((r+m)*255):02x}{int((g+m)*255):02x}{int((b+m)*255):02x}"

def _relative_luminance(hex_str):
    r, g, b = _hex_to_rgb(hex_str)
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b)

def _contrast_ratio(hex1, hex2):
    l1, l2 = _relative_luminance(hex1), _relative_luminance(hex2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)

def _harmony_colors(fill_hex):
    """Return 7 harmony colours: complement, 2× split, 2× analogous, 2× triad.
    Shifted strongly in lightness for contrast with the fill."""
    try:
        r, g, b = _hex_to_rgb(fill_hex)
    except Exception:
        return ["#888888"] * 7
    h, s, l = _rgb_to_hsl(r, g, b)
    s_harm = max(0.30, s * 0.85)
    if l > 0.55:
        l_harm = max(0.10, l - 0.50)
    else:
        l_harm = min(0.92, l + 0.45)
    return [_hsl_to_hex((h + off) % 360, s_harm, l_harm)
            for off in (180, 150, 210, 30, 330, 120, 240)]


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------

def compute_fundamental_domain(H, W, orbit_fn):
    """Return one canonical cell per orbit (first in raster order)."""
    visited, domain = set(), []
    for r in range(H):
        for c in range(W):
            if (r, c) not in visited:
                orbit = orbit_fn(r, c, H, W)
                visited |= orbit
                domain.append((r, c))
    return domain


def generate_pattern(H, W, orbit_fn, density):
    """Return (grid, domain) with random fills respecting the symmetry group."""
    grid   = [[False]*W for _ in range(H)]
    domain = compute_fundamental_domain(H, W, orbit_fn)
    for (r, c) in domain:
        filled = random.random() < density
        for (dr, dc) in orbit_fn(r, c, H, W):
            grid[dr][dc] = filled
    return grid, domain


# ---------------------------------------------------------------------------
# Tiling helpers
# ---------------------------------------------------------------------------

def transformed_tile(tile, H, W, h_type, v_type, hi, vi):
    """Return the tile transformed for repeat position (col hi, row vi)."""
    flip_r = flip_c = False
    if h_type == "reflection" and hi % 2 == 1:
        flip_c = not flip_c
    elif h_type == "rotation" and hi % 2 == 1:
        flip_r = not flip_r; flip_c = not flip_c
    if v_type == "reflection" and vi % 2 == 1:
        flip_r = not flip_r
    elif v_type == "rotation" and vi % 2 == 1:
        flip_r = not flip_r; flip_c = not flip_c
    if not flip_r and not flip_c:
        return tile
    result = [[False]*W for _ in range(H)]
    for r in range(H):
        for c in range(W):
            result[r][c] = tile[H-1-r if flip_r else r][W-1-c if flip_c else c]
    return result


def build_tiling_grid(tile, H, W, col_strip, row_strip, corner,
                       h_repeat, v_repeat, strip_width, h_type, v_type,
                       n_h=3, n_v=3, row_offset=0, col_offset=0):
    """Assemble a full tiling as a 2-D bool grid."""
    sw = strip_width
    nh = n_h if h_repeat else 1
    nv = n_v if v_repeat else 1
    uw = W + (sw if h_repeat else 0)
    uh = H + (sw if v_repeat else 0)
    total_w = nh * uw
    total_h = nv * uh
    result = [[False]*total_w for _ in range(total_h)]

    def _get(arr, r, c):
        try:    return arr[r][c]
        except: return False

    def _set(y, x, val):
        if 0 <= y < total_h and 0 <= x < total_w:
            result[y][x] = val

    hi_range = range(-1, nh + 1) if row_offset else range(nh)
    vi_range = range(-1, nv + 1) if col_offset else range(nv)

    for vi in vi_range:
        for hi in hi_range:
            x0 = hi * uw + (vi * row_offset) % uw
            y0 = vi * uh + (hi * col_offset) % uh
            if x0 >= total_w or x0 + uw <= 0: continue
            if y0 >= total_h or y0 + uh <= 0: continue
            t = transformed_tile(tile, H, W, h_type, v_type, hi, vi)
            for r in range(H):
                for c in range(W):
                    _set(y0+r, x0+c, t[r][c])
            if h_repeat and sw > 0:
                for r in range(H):
                    for sc in range(sw):
                        _set(y0+r, x0+W+sc, _get(col_strip, r, sc))
            if v_repeat and sw > 0:
                for sr in range(sw):
                    for c in range(W):
                        _set(y0+H+sr, x0+c, _get(row_strip, sr, c))
            if h_repeat and v_repeat and sw > 0:
                for sr in range(sw):
                    for sc in range(sw):
                        _set(y0+H+sr, x0+W+sc, _get(corner, sr, sc))
    return result


# ---------------------------------------------------------------------------
# Layout arithmetic — renderer-independent descriptors
#
# Each descriptor is a plain dict with a "type" key:
#   {"type": "rect",  "x", "y", "w", "h", "fill", "outline", "outline_width",
#                     "row", "col", "region"}   ← row/col/region for click routing
#   {"type": "text",  "x", "y", "text", "font_size", "fill"}
#   {"type": "line",  "x1","y1","x2","y2", "fill", "width"}
# ---------------------------------------------------------------------------

def tile_canvas_size(H, W, cell_size, h_on, v_on, strip_width):
    """Return (total_width, total_height) of the tile canvas in pixels."""
    ex_c = strip_width if h_on else 0
    ex_r = strip_width if v_on else 0
    total_w = (W + ex_c) * cell_size + 2 * PADDING + NUM_W
    total_h = (H + ex_r) * cell_size + 2 * PADDING + NUM_H
    return total_w, total_h


def get_tile_descriptors(
    grid, H, W, cell_size,
    fill_color, bg_color,
    domain_cells, show_domain,
    col_strip, row_strip, corner,
    h_on, v_on, strip_width,
):
    """Return drawing descriptors for the tile view (cells, strips, numbers).

    Uses module-level PADDING / NUM_W / NUM_H for margins so both the tkinter
    renderer and SVG renderer produce identical layouts.
    """
    cs  = cell_size
    sw  = strip_width
    out = []

    def _safe(arr, r, c):
        try:    return arr[r][c]
        except: return False

    # --- Tile cells ---------------------------------------------------------
    for r in range(H):
        for c in range(W):
            x0 = PADDING + c * cs
            y0 = PADDING + r * cs
            fill = fill_color if grid[r][c] else bg_color
            if show_domain and (r, c) in domain_cells:
                ol, ow = "#e63946", 2
            else:
                ol, ow = "#cccccc", 1
            out.append({"type":"rect", "x":x0, "y":y0, "w":cs, "h":cs,
                         "fill":fill, "outline":ol, "outline_width":ow,
                         "row":r, "col":c, "region":"tile"})

    # --- Col strip (right of tile) ------------------------------------------
    if h_on:
        for r in range(H):
            for sc in range(sw):
                x0 = PADDING + (W + sc) * cs
                y0 = PADDING + r * cs
                fill = fill_color if _safe(col_strip, r, sc) else STRIP_BG
                out.append({"type":"rect", "x":x0, "y":y0, "w":cs, "h":cs,
                             "fill":fill, "outline":STRIP_LINE, "outline_width":1,
                             "row":r, "col":sc, "region":"col_strip"})

    # --- Row strip (below tile) ---------------------------------------------
    if v_on:
        for sr in range(sw):
            for c in range(W):
                x0 = PADDING + c * cs
                y0 = PADDING + (H + sr) * cs
                fill = fill_color if _safe(row_strip, sr, c) else STRIP_BG
                out.append({"type":"rect", "x":x0, "y":y0, "w":cs, "h":cs,
                             "fill":fill, "outline":STRIP_LINE, "outline_width":1,
                             "row":sr, "col":c, "region":"row_strip"})

    # --- Corner -------------------------------------------------------------
    if h_on and v_on:
        for sr in range(sw):
            for sc in range(sw):
                x0 = PADDING + (W + sc) * cs
                y0 = PADDING + (H + sr) * cs
                fill = fill_color if _safe(corner, sr, sc) else STRIP_BG
                out.append({"type":"rect", "x":x0, "y":y0, "w":cs, "h":cs,
                             "fill":fill, "outline":STRIP_LINE, "outline_width":1,
                             "row":sr, "col":sc, "region":"corner"})

    # --- Numbers ------------------------------------------------------------
    ex_c       = sw if h_on else 0
    ex_r       = sw if v_on else 0
    total_cols = W + ex_c
    total_rows = H + ex_r
    num_size   = max(7, min(10, cs // 4))

    # Column numbers in the bottom margin
    num_y = PADDING + total_rows * cs + NUM_H // 2 + 1
    for c in range(W):
        out.append({"type":"text",
                    "x": PADDING + c * cs + cs // 2, "y": num_y,
                    "text": str(total_cols - c),
                    "font_size": num_size, "fill": "#777777"})
    for sc in range(ex_c):
        out.append({"type":"text",
                    "x": PADDING + (W + sc) * cs + cs // 2, "y": num_y,
                    "text": str(ex_c - sc),
                    "font_size": num_size, "fill": "#777777"})

    # Row numbers in the right margin
    num_x = PADDING + total_cols * cs + NUM_W // 2 + 1
    for r in range(H):
        out.append({"type":"text",
                    "x": num_x, "y": PADDING + r * cs + cs // 2,
                    "text": str(total_rows - r),
                    "font_size": num_size, "fill": "#777777"})
    for sr in range(ex_r):
        out.append({"type":"text",
                    "x": num_x, "y": PADDING + (H + sr) * cs + cs // 2,
                    "text": str(ex_r - sr),
                    "font_size": num_size, "fill": "#777777"})

    return out


def get_tiling_descriptors(
    grid, H, W, cell_size,
    fill_color, bg_color,
    h_repeat, v_repeat, strip_width,
    h_type, v_type,
    col_strip, row_strip, corner,
    n_copies=3, row_offset=0, col_offset=0,
    padding=1,
):
    """Return (descriptors, rows, cols) for the tiling preview."""
    cs = cell_size
    tgrid = build_tiling_grid(
        tile=grid, H=H, W=W,
        col_strip=col_strip, row_strip=row_strip, corner=corner,
        h_repeat=h_repeat, v_repeat=v_repeat, strip_width=strip_width,
        h_type=h_type, v_type=v_type,
        n_h=n_copies, n_v=n_copies,
        row_offset=row_offset, col_offset=col_offset,
    )
    rows = len(tgrid)
    cols = len(tgrid[0]) if rows else 0
    out  = []

    for r in range(rows):
        for c in range(cols):
            x0 = padding + c * cs
            y0 = padding + r * cs
            fill = fill_color if tgrid[r][c] else bg_color
            out.append({"type":"rect", "x":x0, "y":y0, "w":cs, "h":cs,
                         "fill":fill, "outline":"#cccccc", "outline_width":1})

    # Boundary lines between repeat units (only without brick offset)
    if not row_offset and not col_offset:
        sw     = strip_width
        nh     = n_copies if h_repeat else 1
        nv     = n_copies if v_repeat else 1
        unit_w = W + (sw if h_repeat else 0)
        unit_h = H + (sw if v_repeat else 0)
        total_w = cols * cs + 2 * padding
        total_h = rows * cs + 2 * padding
        for hi in range(1, nh):
            lx = padding + hi * unit_w * cs
            out.append({"type":"line",
                         "x1":lx, "y1":0, "x2":lx, "y2":total_h,
                         "fill":"#888888", "width":1})
        for vi in range(1, nv):
            ly = padding + vi * unit_h * cs
            out.append({"type":"line",
                         "x1":0, "y1":ly, "x2":total_w, "y2":ly,
                         "fill":"#888888", "width":1})

    return out, rows, cols


# ---------------------------------------------------------------------------
# SVG renderers (used by the Shiny app)
# ---------------------------------------------------------------------------

def render_grid_svg(descriptors, total_w, total_h, responsive=False):
    """Convert tile descriptors to an SVG string with clickable grid cells.

    responsive=True adds a viewBox and sets width="100%" so the SVG scales
    to fill its container (used by the Shiny web app).
    """
    if responsive:
        size = (f'viewBox="0 0 {total_w} {total_h}" width="100%" '
                f'style="display:block"')
    else:
        size = f'width="{total_w}" height="{total_h}" style="display:block"'
    parts = [f'<svg {size} xmlns="http://www.w3.org/2000/svg">']
    for d in descriptors:
        if d["type"] == "rect":
            attrs = (f'x="{d["x"]}" y="{d["y"]}" '
                     f'width="{d["w"]}" height="{d["h"]}" '
                     f'fill="{d["fill"]}" '
                     f'stroke="{d["outline"]}" stroke-width="{d["outline_width"]}" '
                     f'vector-effect="non-scaling-stroke"')
            if "region" in d:
                attrs += (f' class="grid-cell"'
                          f' data-region="{d["region"]}"'
                          f' data-row="{d["row"]}"'
                          f' data-col="{d["col"]}"'
                          f' style="cursor:pointer"')
            parts.append(f'  <rect {attrs}/>')
        elif d["type"] == "text":
            parts.append(
                f'  <text x="{d["x"]}" y="{d["y"]}" '
                f'font-size="{d["font_size"]}" fill="{d["fill"]}" '
                f'text-anchor="middle" dominant-baseline="middle">'
                f'{d["text"]}</text>'
            )
    parts.append('</svg>')
    return "\n".join(parts)


def render_tiling_svg(descriptors, rows, cols, cell_size, padding=1,
                       responsive=False):
    """Convert tiling descriptors to an SVG string."""
    total_w = cols * cell_size + 2 * padding
    total_h = rows * cell_size + 2 * padding
    if responsive:
        size = (f'viewBox="0 0 {total_w} {total_h}" width="100%" '
                f'style="display:block"')
    else:
        size = f'width="{total_w}" height="{total_h}" style="display:block"'
    nss = 'vector-effect="non-scaling-stroke"'
    parts = [f'<svg {size} xmlns="http://www.w3.org/2000/svg">']
    for d in descriptors:
        if d["type"] == "rect":
            parts.append(
                f'  <rect x="{d["x"]}" y="{d["y"]}" '
                f'width="{d["w"]}" height="{d["h"]}" '
                f'fill="{d["fill"]}" stroke="{d["outline"]}" '
                f'stroke-width="{d["outline_width"]}" {nss}/>'
            )
        elif d["type"] == "line":
            parts.append(
                f'  <line x1="{d["x1"]}" y1="{d["y1"]}" '
                f'x2="{d["x2"]}" y2="{d["y2"]}" '
                f'stroke="{d["fill"]}" stroke-width="{d["width"]}" {nss}/>'
            )
    parts.append('</svg>')
    return "\n".join(parts)
