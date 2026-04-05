import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog
import random
import db

PADDING    = 20
NUM_W      = 26   # extra right margin reserved for row numbers
NUM_H      = 16   # extra bottom margin reserved for column numbers
STRIP_BG   = "#e8e8e8"
STRIP_LINE = "#aaaaaa"

# ---------------------------------------------------------------------------
# Slider + Entry helper
# ---------------------------------------------------------------------------

def make_slider_entry(parent, var, from_, to, resolution,
                       slider_length=160, entry_width=4, command=None):
    """Create a min-label + Scale + max-label + Entry widget group.

    Returns (frame, refresh_fn).  Call refresh_fn() after programmatic
    var.set() calls to keep the entry display in sync.
    """
    frame    = tk.Frame(parent)
    _syncing = [False]

    def _fmt(v):
        return f"{v:.2f}" if resolution < 1 else str(int(round(v)))

    def _sync_entry():
        entry.delete(0, tk.END)
        entry.insert(0, _fmt(var.get()))

    def _on_slider(val):
        if _syncing[0]:
            return
        _syncing[0] = True
        try:
            _sync_entry()
            if command:
                command()
        finally:
            _syncing[0] = False

    def _on_entry(event=None):
        if _syncing[0]:
            return
        _syncing[0] = True
        try:
            raw = entry.get().strip()
            v = float(raw) if resolution < 1 else int(raw)
            v = max(from_, min(to, v))
            if resolution >= 1:
                v = int(round(v / resolution) * resolution)
            old_v = var.get()
            var.set(v)
            _sync_entry()
            if command and v != old_v:
                command()
        except ValueError:
            _sync_entry()
        finally:
            _syncing[0] = False

    lbl_style = {"font": ("", 8), "fg": "#888888"}
    tk.Label(frame, text=_fmt(from_), **lbl_style).pack(side=tk.LEFT, padx=(0, 2))
    scale = tk.Scale(frame, variable=var, from_=from_, to=to, resolution=resolution,
                     orient=tk.HORIZONTAL, length=slider_length, showvalue=False,
                     command=_on_slider)
    scale.pack(side=tk.LEFT)
    tk.Label(frame, text=_fmt(to), **lbl_style).pack(side=tk.LEFT, padx=(2, 0))
    entry = tk.Entry(frame, width=entry_width, font=("Courier", 9))
    _sync_entry()
    entry.pack(side=tk.LEFT, padx=(8, 0))
    entry.bind("<Return>",   _on_entry)
    entry.bind("<FocusOut>", _on_entry)

    def refresh():
        _syncing[0] = True
        try:
            _sync_entry()
        finally:
            _syncing[0] = False

    return frame, refresh


# ---------------------------------------------------------------------------
# Symmetry orbit functions  (r, c, H, W)
# ---------------------------------------------------------------------------

def c1_orbit(r, c, H, W):
    return {(r, c)}

def d1_orbit(r, c, H, W):
    return {(r, c), (r, W-1-c)}

def c2_orbit(r, c, H, W):
    return {(r, c), (H-1-r, W-1-c)}

def d2_orbit(r, c, H, W):
    return {(r,c),(H-1-r,W-1-c),(r,W-1-c),(H-1-r,c)}

def c4_orbit(r, c, H, W):
    N = H  # H == W for 4× symmetry
    return {(r,c),(c,N-1-r),(N-1-r,N-1-c),(N-1-c,r)}

def d4_orbit(r, c, H, W):
    N = H  # H == W for 4× symmetry
    return {
        (r,c),(c,N-1-r),(N-1-r,N-1-c),(N-1-c,r),
        (r,N-1-c),(N-1-r,c),(c,r),(N-1-c,N-1-r),
    }

ORBIT_FNS = {
    (1, False): c1_orbit, (1, True): d1_orbit,
    (2, False): c2_orbit, (2, True): d2_orbit,
    (4, False): c4_orbit, (4, True): d4_orbit,
}
GROUP_NAMES     = {(1,False):"C1",(1,True):"D1",(2,False):"C2",
                   (2,True):"D2",(4,False):"C4",(4,True):"D4"}
GROUP_TO_PARAMS = {v: k for k, v in GROUP_NAMES.items()}


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def cmyk_to_hex(c, m, y, k):
    r = round(255 * (1 - c/100) * (1 - k/100))
    g = round(255 * (1 - m/100) * (1 - k/100))
    b = round(255 * (1 - y/100) * (1 - k/100))
    return f"#{r:02x}{g:02x}{b:02x}"

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
    """Return 7 harmony hex colours: complement, 2× split-complement, 2× analogous, 2× triad.
    Harmonies are shifted strongly in lightness so they contrast with the fill."""
    try:
        r, g, b = _hex_to_rgb(fill_hex)
    except Exception:
        return ["#888888"] * 7
    h, s, l = _rgb_to_hsl(r, g, b)
    s_harm = max(0.30, s * 0.85)          # keep saturation vivid
    if l > 0.55:                           # light fill → much darker harmonies
        l_harm = max(0.10, l - 0.50)
    else:                                  # dark/medium fill → much lighter harmonies
        l_harm = min(0.92, l + 0.45)
    return [_hsl_to_hex((h + off) % 360, s_harm, l_harm)
            for off in (180, 150, 210, 30, 330, 120, 240)]

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


class ColorPicker:
    """CMYK + HSL + hex color picker.  Call .get() for the current hex value."""

    def __init__(self, parent, label, initial_hex, on_change, slider_length=120):
        self._on_change = on_change
        self._updating  = False
        c0,m0,y0,k0 = hex_to_cmyk(initial_hex) or (0,0,0,100)
        self.c_var = tk.IntVar(value=c0)
        self.m_var = tk.IntVar(value=m0)
        self.y_var = tk.IntVar(value=y0)
        self.k_var = tk.IntVar(value=k0)
        r0,g0,b0   = _hex_to_rgb(initial_hex)
        h0,s0,l0   = _rgb_to_hsl(r0,g0,b0)
        self.h_var = tk.IntVar(value=round(h0))
        self.s_var = tk.IntVar(value=round(s0*100))
        self.l_var = tk.IntVar(value=round(l0*100))
        self._color = initial_hex
        self._cmyk_entries = {}
        self._hsl_entries  = {}

        # Section label coloured with the initial colour
        self._label = tk.Label(parent, text=f"  {label}  ",
                               font=("", 10, "bold"),
                               bg=initial_hex,
                               fg=self._contrast_fg(initial_hex),
                               relief="flat", padx=4, pady=3)
        self._label.pack(anchor=tk.W, pady=(0, 6))

        # Swatch + hex entry
        top = tk.Frame(parent)
        top.pack(anchor=tk.W, pady=(0, 6))
        self._swatch = tk.Label(top, bg=initial_hex, width=7, height=2,
                                relief="solid", borderwidth=1)
        self._swatch.pack(side=tk.LEFT, padx=(0, 10))
        hex_col = tk.Frame(top)
        hex_col.pack(side=tk.LEFT, anchor=tk.W)
        tk.Label(hex_col, text="Hex", font=("", 8), fg="#888888").pack(anchor=tk.W)
        self._hex_entry = tk.Entry(hex_col, width=9, font=("Courier", 10))
        self._hex_entry.insert(0, initial_hex)
        self._hex_entry.pack()
        self._hex_entry.bind("<Return>",   self._on_hex)
        self._hex_entry.bind("<FocusOut>", self._on_hex)

        # CMYK sliders with min/max labels and entry boxes
        lbl_style = {"font": ("", 8), "fg": "#888888"}
        for ch, var in [("C", self.c_var), ("M", self.m_var),
                        ("Y", self.y_var), ("K", self.k_var)]:
            row = tk.Frame(parent)
            row.pack(anchor=tk.W, pady=1)
            tk.Label(row, text=ch, width=2, font=("", 9, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text="0",   **lbl_style).pack(side=tk.LEFT, padx=(0, 2))
            tk.Scale(row, variable=var, from_=0, to=100, resolution=1,
                     orient=tk.HORIZONTAL, length=slider_length, showvalue=False,
                     command=self._on_cmyk).pack(side=tk.LEFT)
            tk.Label(row, text="100", **lbl_style).pack(side=tk.LEFT, padx=(2, 0))
            e = tk.Entry(row, width=4, font=("Courier", 9))
            e.insert(0, str(var.get()))
            e.pack(side=tk.LEFT, padx=(8, 0))
            e.bind("<Return>",   lambda ev, v=var: self._on_cmyk_entry(ev, v))
            e.bind("<FocusOut>", lambda ev, v=var: self._on_cmyk_entry(ev, v))
            self._cmyk_entries[ch] = e

        # HSL sliders
        sep = tk.Frame(parent, height=1, bg="#cccccc")
        sep.pack(fill=tk.X, pady=(6, 4))
        hsl_specs = [
            ("H", self.h_var, 0, 360),
            ("S", self.s_var, 0, 100),
            ("L", self.l_var, 0, 100),
        ]
        for ch, var, lo, hi in hsl_specs:
            row = tk.Frame(parent)
            row.pack(anchor=tk.W, pady=1)
            tk.Label(row, text=ch, width=2, font=("", 9, "bold")).pack(side=tk.LEFT)
            tk.Label(row, text=str(lo), **lbl_style).pack(side=tk.LEFT, padx=(0, 2))
            tk.Scale(row, variable=var, from_=lo, to=hi, resolution=1,
                     orient=tk.HORIZONTAL, length=slider_length, showvalue=False,
                     command=self._on_hsl).pack(side=tk.LEFT)
            tk.Label(row, text=str(hi), **lbl_style).pack(side=tk.LEFT, padx=(2, 0))
            e = tk.Entry(row, width=4, font=("Courier", 9))
            e.insert(0, str(var.get()))
            e.pack(side=tk.LEFT, padx=(8, 0))
            e.bind("<Return>",   lambda ev, v=var, lo=lo, hi=hi: self._on_hsl_entry(ev, v, lo, hi))
            e.bind("<FocusOut>", lambda ev, v=var, lo=lo, hi=hi: self._on_hsl_entry(ev, v, lo, hi))
            self._hsl_entries[ch] = e

    @staticmethod
    def _contrast_fg(hex_color):
        """Return black or white depending on which contrasts better with hex_color."""
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return "#000000"
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        luminance = 0.299*r + 0.587*g + 0.114*b
        return "#000000" if luminance > 140 else "#ffffff"

    def get(self): return self._color

    def set_color(self, hex_str):
        result = hex_to_cmyk(hex_str)
        if not result: return
        self._updating = True
        try:
            c,m,y,k = result
            self.c_var.set(c); self.m_var.set(m)
            self.y_var.set(y); self.k_var.set(k)
            self._color = hex_str
            self._hex_entry.delete(0, tk.END)
            self._hex_entry.insert(0, hex_str)
            self._swatch.config(bg=hex_str)
            self._label.config(bg=hex_str, fg=self._contrast_fg(hex_str))
            self._sync_cmyk_entries()
            self._update_hsl_from_hex()
        finally:
            self._updating = False

    def _sync_cmyk_entries(self):
        for ch, var in [("C", self.c_var), ("M", self.m_var),
                        ("Y", self.y_var), ("K", self.k_var)]:
            e = self._cmyk_entries.get(ch)
            if e:
                e.delete(0, tk.END)
                e.insert(0, str(var.get()))

    def _sync_hsl_entries(self):
        for ch, var in [("H", self.h_var), ("S", self.s_var), ("L", self.l_var)]:
            e = self._hsl_entries.get(ch)
            if e:
                e.delete(0, tk.END)
                e.insert(0, str(var.get()))

    def _update_hsl_from_hex(self):
        """Sync H/S/L vars (and entries) from the current self._color."""
        try:
            r, g, b = _hex_to_rgb(self._color)
            h, s, l = _rgb_to_hsl(r, g, b)
            self.h_var.set(round(h))
            self.s_var.set(round(s * 100))
            self.l_var.set(round(l * 100))
            self._sync_hsl_entries()
        except Exception:
            pass

    def _update_from_cmyk(self):
        """Recalculate hex from current CMYK vars and refresh all displays."""
        self._color = cmyk_to_hex(self.c_var.get(), self.m_var.get(),
                                   self.y_var.get(), self.k_var.get())
        self._hex_entry.delete(0, tk.END)
        self._hex_entry.insert(0, self._color)
        self._swatch.config(bg=self._color)
        self._label.config(bg=self._color, fg=self._contrast_fg(self._color))
        self._sync_cmyk_entries()
        self._update_hsl_from_hex()
        self._on_change()

    def _update_from_hsl(self):
        """Recalculate hex from current HSL vars and refresh all displays."""
        self._color = _hsl_to_hex(self.h_var.get(),
                                   self.s_var.get() / 100.0,
                                   self.l_var.get() / 100.0)
        self._hex_entry.delete(0, tk.END)
        self._hex_entry.insert(0, self._color)
        self._swatch.config(bg=self._color)
        self._label.config(bg=self._color, fg=self._contrast_fg(self._color))
        self._sync_hsl_entries()
        # Sync CMYK from new hex
        result = hex_to_cmyk(self._color)
        if result:
            c, m, y, k = result
            self.c_var.set(c); self.m_var.set(m)
            self.y_var.set(y); self.k_var.set(k)
            self._sync_cmyk_entries()
        self._on_change()

    def _on_cmyk(self, *_):
        if self._updating: return
        self._updating = True
        try:
            self._update_from_cmyk()
        finally:
            self._updating = False

    def _on_cmyk_entry(self, event, var):
        if self._updating: return
        self._updating = True
        try:
            v = max(0, min(100, int(event.widget.get().strip())))
            var.set(v)
            self._update_from_cmyk()
        except ValueError:
            self._sync_cmyk_entries()
        finally:
            self._updating = False

    def _on_hsl(self, *_):
        if self._updating: return
        self._updating = True
        try:
            self._update_from_hsl()
        finally:
            self._updating = False

    def _on_hsl_entry(self, event, var, lo, hi):
        if self._updating: return
        self._updating = True
        try:
            v = max(lo, min(hi, int(event.widget.get().strip())))
            var.set(v)
            self._update_from_hsl()
        except ValueError:
            self._sync_hsl_entries()
        finally:
            self._updating = False

    def _on_hex(self, event=None):
        if self._updating: return
        self._updating = True
        try:
            raw = self._hex_entry.get().strip()
            hex_str = raw if raw.startswith("#") else "#" + raw
            result = hex_to_cmyk(hex_str)
            if result:
                c,m,y,k = result
                self.c_var.set(c); self.m_var.set(m)
                self.y_var.set(y); self.k_var.set(k)
                self._color = hex_str
                self._swatch.config(bg=hex_str)
                self._label.config(bg=hex_str, fg=self._contrast_fg(hex_str))
                self._sync_cmyk_entries()
                self._update_hsl_from_hex()
                self._on_change()
        finally:
            self._updating = False


# ---------------------------------------------------------------------------
# Colour compare panel  (gradient + contrast + harmony)
# ---------------------------------------------------------------------------

class ColorComparePanel:
    _HARMONY_LABELS = ["Comp", "Split", "Split", "Analog", "Analog", "Triad", "Triad"]
    _GRAD_W = 290
    _GRAD_H = 22

    def __init__(self, parent, get_fill, get_bg, on_bg_click):
        self._get_fill    = get_fill
        self._get_bg      = get_bg
        self._on_bg_click = on_bg_click

        sep = tk.Frame(parent, height=1, bg="#cccccc")
        sep.pack(fill=tk.X, pady=(0, 10))

        # Gradient strip
        grad_row = tk.Frame(parent)
        grad_row.pack(anchor=tk.W, pady=(0, 4))
        tk.Label(grad_row, text="Fill", font=("",8), fg="#888888").pack(side=tk.LEFT, padx=(0,4))
        self._grad_canvas = tk.Canvas(grad_row, width=self._GRAD_W, height=self._GRAD_H,
                                       highlightthickness=1, highlightbackground="#cccccc")
        self._grad_canvas.pack(side=tk.LEFT)
        tk.Label(grad_row, text="Background", font=("",8), fg="#888888").pack(side=tk.LEFT, padx=(4,0))

        # Contrast ratio
        self._contrast_lbl = tk.Label(parent, text="", font=("",9), anchor=tk.W)
        self._contrast_lbl.pack(anchor=tk.W, pady=(0, 8))

        # Harmony swatches
        harm_row = tk.Frame(parent)
        harm_row.pack(anchor=tk.W)
        tk.Label(harm_row, text="Harmonies  →", font=("",8), fg="#888888").pack(side=tk.LEFT, padx=(0,8))
        self._swatches = []
        for lbl_text in self._HARMONY_LABELS:
            col_f = tk.Frame(harm_row)
            col_f.pack(side=tk.LEFT, padx=4)
            sw = tk.Label(col_f, width=4, height=1, relief="solid",
                          borderwidth=1, cursor="hand2")
            sw.pack()
            tk.Label(col_f, text=lbl_text, font=("",7), fg="#666666").pack()
            self._swatches.append(sw)

        self.refresh()

    def refresh(self):
        fill_hex = self._get_fill()
        bg_hex   = self._get_bg()

        # Gradient fill→bg
        self._grad_canvas.delete("all")
        try:
            r1,g1,b1 = _hex_to_rgb(fill_hex)
            r2,g2,b2 = _hex_to_rgb(bg_hex)
            steps = 96
            w, h = self._GRAD_W, self._GRAD_H
            for i in range(steps):
                t  = i / (steps - 1)
                rc = int(r1 + t*(r2-r1))
                gc = int(g1 + t*(g2-g1))
                bc = int(b1 + t*(b2-b1))
                x  = int(i * w / steps)
                x2 = int((i+1) * w / steps)
                self._grad_canvas.create_rectangle(x, 0, x2, h,
                    fill=f"#{rc:02x}{gc:02x}{bc:02x}", outline="")
        except Exception:
            pass

        # Contrast ratio
        try:
            ratio = _contrast_ratio(fill_hex, bg_hex)
            if ratio >= 7.0:
                rating, fg = "Excellent", "#1a6e1a"
            elif ratio >= 4.5:
                rating, fg = "Good",      "#2a762a"
            elif ratio >= 3.0:
                rating, fg = "Fair",      "#a06000"
            else:
                rating, fg = "Low",       "#bb2222"
            self._contrast_lbl.config(
                text=f"Contrast  {ratio:.1f} : 1  —  {rating}", fg=fg)
        except Exception:
            self._contrast_lbl.config(text="")

        # Harmony swatches — click sets background
        try:
            harmonies = _harmony_colors(fill_hex)
            for sw, hx in zip(self._swatches, harmonies):
                sw.config(bg=hx)
                sw.bind("<Button-1>", lambda e, c=hx: self._on_bg_click(c))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tiling helpers
# ---------------------------------------------------------------------------

def transformed_tile(tile, H, W, h_type, v_type, hi, vi):
    """Return the tile transformed for repeat position (col hi, row vi).

    Each direction contributes independent flips that are XOR-composed:
      translation  → no change
      reflection   → flip the axis-perpendicular dimension on odd copies
      rotation     → 180° (flip both axes) on odd copies
    """
    flip_r = flip_c = False

    if h_type == "reflection" and hi % 2 == 1:
        flip_c = not flip_c
    elif h_type == "rotation" and hi % 2 == 1:
        flip_r = not flip_r
        flip_c = not flip_c

    if v_type == "reflection" and vi % 2 == 1:
        flip_r = not flip_r
    elif v_type == "rotation" and vi % 2 == 1:
        flip_r = not flip_r
        flip_c = not flip_c

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
    """Assemble the full tiling as a 2-D bool grid for the preview.

    row_offset: each row of tiles is shifted right by this many cells relative
                to the row above it.
    col_offset: each column of tiles is shifted down by this many cells relative
                to the column to its left.
    Extra tiles are rendered outside the canvas range and silently clipped.
    """
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

    # Render one extra tile on each side to fill gaps created by the offset
    hi_range = range(-1, nh + 1) if row_offset else range(nh)
    vi_range = range(-1, nv + 1) if col_offset else range(nv)

    for vi in vi_range:
        for hi in hi_range:
            x0 = hi * uw + (vi * row_offset) % uw
            y0 = vi * uh + (hi * col_offset) % uh
            # Skip tiles entirely outside the canvas
            if x0 >= total_w or x0 + uw <= 0:
                continue
            if y0 >= total_h or y0 + uh <= 0:
                continue
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
# Domain helpers
# ---------------------------------------------------------------------------

def compute_fundamental_domain(H, W, orbit_fn):
    visited, domain = set(), []
    for r in range(H):
        for c in range(W):
            if (r, c) not in visited:
                orbit = orbit_fn(r, c, H, W)
                visited |= orbit
                domain.append((r, c))
    return domain


# ---------------------------------------------------------------------------
# Tiling settings window
# ---------------------------------------------------------------------------

class TilingWindow(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Tiling")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.withdraw()
        self._build_ui()

    def _build_ui(self):
        f = tk.Frame(self, padx=14, pady=14)
        f.pack(fill=tk.BOTH)

        tk.Label(f, text="Repeat Direction", font=("",10,"bold")).pack(anchor=tk.W)
        tk.Checkbutton(f, text="Horizontal", variable=self.app.h_repeat_var,
                       command=self._change).pack(anchor=tk.W)
        tk.Checkbutton(f, text="Vertical",   variable=self.app.v_repeat_var,
                       command=self._change).pack(anchor=tk.W)

        tk.Label(f, text="").pack()
        tk.Label(f, text="Strip Width", font=("",10,"bold")).pack(anchor=tk.W)
        frm, _ = make_slider_entry(f, self.app.strip_width_var, 0, 9, 1,
                                    slider_length=140, entry_width=3,
                                    command=self._change)
        frm.pack(anchor=tk.W)

        tk.Label(f, text="").pack()
        tk.Label(f, text="Strip Symmetry", font=("",10,"bold")).pack(anchor=tk.W)
        tk.Checkbutton(f, text="Reflect top ↔ bottom",
                       variable=self.app.strip_h_reflect_var).pack(anchor=tk.W)
        tk.Checkbutton(f, text="Reflect left ↔ right",
                       variable=self.app.strip_v_reflect_var).pack(anchor=tk.W)

        tk.Label(f, text="").pack()
        tk.Label(f, text="Brick Offset", font=("",10,"bold")).pack(anchor=tk.W)
        for lbl, var in [("Row shift (right per row ↓):", self.app.row_offset_var),
                         ("Col shift (down per col →):", self.app.col_offset_var)]:
            tk.Label(f, text=lbl, font=("",9)).pack(anchor=tk.W)
            frm, _ = make_slider_entry(f, var, 0, 25, 1,
                                        slider_length=140, entry_width=3,
                                        command=self._change)
            frm.pack(anchor=tk.W, pady=(0, 4))

        tk.Label(f, text="").pack()
        tk.Label(f, text="Repeat Type", font=("",10,"bold")).pack(anchor=tk.W)

        table = tk.Frame(f)
        table.pack(anchor=tk.W, pady=(4,0))
        types = [("Translation","translation"), ("Reflection","reflection"), ("180° Rot.","rotation")]

        for col, (label, _) in enumerate(types, start=1):
            tk.Label(table, text=label, font=("",9,"bold"), width=10,
                     anchor=tk.CENTER).grid(row=0, column=col, padx=2)

        tk.Label(table, text="Horizontal", anchor=tk.W).grid(row=1, column=0, sticky=tk.W, padx=(0,8))
        for col, (_, value) in enumerate(types, start=1):
            tk.Radiobutton(table, variable=self.app.h_repeat_type_var,
                           value=value, command=self._change).grid(row=1, column=col)

        tk.Label(table, text="Vertical", anchor=tk.W).grid(row=2, column=0, sticky=tk.W, padx=(0,8))
        for col, (_, value) in enumerate(types, start=1):
            tk.Radiobutton(table, variable=self.app.v_repeat_type_var,
                           value=value, command=self._change).grid(row=2, column=col)

    def _change(self):
        self.app._on_tiling_change()
        self.after(1, self.lift)


# ---------------------------------------------------------------------------
# Tiling preview window
# ---------------------------------------------------------------------------

class PreviewWindow(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title("Tiling Preview")
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self.withdraw()
        self.copies_var    = tk.IntVar(value=3)
        self.cell_size_var = tk.IntVar(value=8)
        self._build_ui()

    def _build_ui(self):
        ctrl = tk.Frame(self, padx=8, pady=6)
        ctrl.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Label(ctrl, text="Copies:").pack(side=tk.LEFT)
        for n in [2, 3, 4, 5]:
            tk.Radiobutton(ctrl, text=str(n), variable=self.copies_var,
                           value=n, command=self.refresh).pack(side=tk.LEFT)
        tk.Label(ctrl, text="   Cell px:").pack(side=tk.LEFT)
        tk.Scale(ctrl, variable=self.cell_size_var, from_=4, to=16, resolution=2,
                 orient=tk.HORIZONTAL, length=80, showvalue=True,
                 command=lambda _: self.refresh()).pack(side=tk.LEFT)
        hbar = tk.Scrollbar(self, orient=tk.HORIZONTAL)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar = tk.Scrollbar(self, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(self, bg="white",
                                xscrollcommand=hbar.set,
                                yscrollcommand=vbar.set)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=(8,0), pady=(8,0))
        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)

    def refresh(self):
        if not self.winfo_viewable():
            return
        app  = self.app
        n    = self.copies_var.get()
        row_off = app.row_offset_var.get()
        col_off = app.col_offset_var.get()
        grid = build_tiling_grid(
            tile=app.grid, H=app.H, W=app.W,
            col_strip=app.col_strip, row_strip=app.row_strip, corner=app.corner,
            h_repeat=app.h_repeat_var.get(), v_repeat=app.v_repeat_var.get(),
            strip_width=app.strip_width_var.get(),
            h_type=app.h_repeat_type_var.get(),
            v_type=app.v_repeat_type_var.get(),
            n_h=n, n_v=n,
            row_offset=row_off, col_offset=col_off,
        )
        cs   = self.cell_size_var.get()
        rows = len(grid)
        cols = len(grid[0]) if rows > 0 else 0
        cw, ch = cols*cs + 2, rows*cs + 2
        self.canvas.config(scrollregion=(0, 0, cw, ch))
        self.canvas.delete("all")

        fill_c = app.fill_picker.get()
        bg_c   = app.bg_picker.get()
        for r in range(rows):
            for c in range(cols):
                x0, y0 = 1 + c*cs, 1 + r*cs
                fill = fill_c if grid[r][c] else bg_c
                self.canvas.create_rectangle(x0, y0, x0+cs, y0+cs,
                                              fill=fill, outline="#cccccc", width=1)

        # Boundary lines between repeat units — only meaningful without brick offset
        if not row_off and not col_off:
            sw     = app.strip_width_var.get()
            unit_w = app.W + (sw if app.h_repeat_var.get() else 0)
            unit_h = app.H + (sw if app.v_repeat_var.get() else 0)
            nh = n if app.h_repeat_var.get() else 1
            nv = n if app.v_repeat_var.get() else 1
            for hi in range(1, nh):
                x = 1 + hi * unit_w * cs
                self.canvas.create_line(x, 0, x, ch, fill="#888888", width=1)
            for vi in range(1, nv):
                y = 1 + vi * unit_h * cs
                self.canvas.create_line(0, y, cw, y, fill="#888888", width=1)


# ---------------------------------------------------------------------------
# Load dialog
# ---------------------------------------------------------------------------

class LoadDialog(tk.Toplevel):
    def __init__(self, parent, on_load):
        super().__init__(parent)
        self.title("Load Pattern")
        self.resizable(False, False)
        self.grab_set()
        self._on_load  = on_load
        self._patterns = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        frame = tk.Frame(self, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text="Saved patterns", font=("",10,"bold")).pack(anchor=tk.W)
        lf = tk.Frame(frame)
        lf.pack(fill=tk.BOTH, expand=True, pady=(4,8))
        sb = tk.Scrollbar(lf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._lb = tk.Listbox(lf, width=58, height=12, yscrollcommand=sb.set,
                               font=("Courier",10), activestyle="dotbox")
        self._lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._lb.yview)
        self._lb.bind("<Double-Button-1>", lambda _: self._load())
        bf = tk.Frame(frame)
        bf.pack(fill=tk.X)
        tk.Button(bf, text="Load",   command=self._load,   width=10).pack(side=tk.LEFT, padx=(0,4))
        tk.Button(bf, text="Delete", command=self._delete, width=10).pack(side=tk.LEFT, padx=(0,4))
        tk.Button(bf, text="Cancel", command=self.destroy, width=10).pack(side=tk.LEFT)

    def _refresh(self):
        self._patterns = db.list_patterns()
        self._lb.delete(0, tk.END)
        for p in self._patterns:
            self._lb.insert(tk.END,
                f"{p['name']:<22}  {p['created_at'][:16]}"
                f"  {p['grid_w']:>2}×{p['grid_h']:<2}  {p['symmetry_group']}")

    def _selected_id(self):
        sel = self._lb.curselection()
        return self._patterns[sel[0]]["id"] if sel else None

    def _load(self):
        pid = self._selected_id()
        if pid is None: return
        data = db.load_pattern(pid)
        if data:
            self._on_load(data)
            self.destroy()

    def _delete(self):
        pid = self._selected_id()
        if pid is None: return
        name = self._patterns[self._lb.curselection()[0]]["name"]
        if messagebox.askyesno("Delete", f"Delete '{name}'?", parent=self):
            db.delete_pattern(pid)
            self._refresh()


# ---------------------------------------------------------------------------
# Load project dialog
# ---------------------------------------------------------------------------

class LoadProjectDialog(tk.Toplevel):
    def __init__(self, parent, on_load):
        super().__init__(parent)
        self.title("Load Project")
        self.resizable(False, False)
        self.grab_set()
        self._on_load  = on_load
        self._projects = []
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        frame = tk.Frame(self, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text="Saved projects", font=("",10,"bold")).pack(anchor=tk.W)
        lf = tk.Frame(frame)
        lf.pack(fill=tk.BOTH, expand=True, pady=(4,8))
        sb = tk.Scrollbar(lf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._lb = tk.Listbox(lf, width=52, height=12, yscrollcommand=sb.set,
                               font=("Courier",10), activestyle="dotbox")
        self._lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._lb.yview)
        self._lb.bind("<Double-Button-1>", lambda _: self._load())
        bf = tk.Frame(frame)
        bf.pack(fill=tk.X)
        tk.Button(bf, text="Load",   command=self._load,   width=10).pack(side=tk.LEFT, padx=(0,4))
        tk.Button(bf, text="Delete", command=self._delete, width=10).pack(side=tk.LEFT, padx=(0,4))
        tk.Button(bf, text="Cancel", command=self.destroy, width=10).pack(side=tk.LEFT)

    def _refresh(self):
        self._projects = db.list_projects()
        self._lb.delete(0, tk.END)
        for p in self._projects:
            self._lb.insert(tk.END, f"{p['name']:<28}  {p['created_at'][:16]}")

    def _selected_id(self):
        sel = self._lb.curselection()
        return self._projects[sel[0]]["id"] if sel else None

    def _load(self):
        pid = self._selected_id()
        if pid is None: return
        row = db.load_project(pid)
        if row:
            self._on_load(row["data"])
            self.destroy()

    def _delete(self):
        pid = self._selected_id()
        if pid is None: return
        name = self._projects[self._lb.curselection()[0]]["name"]
        if messagebox.askyesno("Delete", f"Delete project '{name}'?", parent=self):
            db.delete_project(pid)
            self._refresh()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class PatternApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Symmetrical Grid Pattern Generator")
        self.root.resizable(True, True)

        self.H = 8
        self.W = 8
        self.grid              = [[False]*self.W for _ in range(self.H)]
        self.domain_cells      = set()
        self.cell_to_canonical = {}

        # Symmetry
        self.rotation_var    = tk.IntVar(value=4)
        self.reflect_var     = tk.BooleanVar(value=True)

        # Grid size vars
        self.grid_w_var      = tk.IntVar(value=8)   # 1×/2×: width
        self.grid_h_var      = tk.IntVar(value=8)   # 1×/2×: height
        self.grid_n_var      = tk.IntVar(value=8)   # 4×: square side

        self.cell_size_var   = tk.IntVar(value=40)
        self.density_var     = tk.DoubleVar(value=0.5)
        self.show_domain_var = tk.BooleanVar(value=False)

        # Tiling
        self.h_repeat_var        = tk.BooleanVar(value=False)
        self.v_repeat_var        = tk.BooleanVar(value=False)
        self.strip_width_var     = tk.IntVar(value=1)
        self.h_repeat_type_var   = tk.StringVar(value="translation")
        self.v_repeat_type_var   = tk.StringVar(value="translation")
        self.strip_h_reflect_var = tk.BooleanVar(value=False)
        self.strip_v_reflect_var = tk.BooleanVar(value=False)
        self.row_offset_var      = tk.IntVar(value=0)
        self.col_offset_var      = tk.IntVar(value=0)
        self.col_strip = []
        self.row_strip = []
        self.corner    = []

        # Slider-entry refresh callbacks (set in _build_ui)
        self._grid_w_refresh    = None
        self._grid_h_refresh    = None
        self._grid_n_refresh    = None
        self._density_refresh   = None
        self._cell_size_refresh = None

        self._build_ui()
        self._build_color_window()
        self._build_tiling_window()
        self._build_preview_window()
        self.generate()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        menubar   = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Save Project…",  command=self._save_project,  accelerator="Command+S")
        file_menu.add_command(label="Load Project…",  command=self._load_project,  accelerator="Command+O")
        file_menu.add_separator()
        file_menu.add_command(label="Save Pattern…",  command=self._save_pattern,  accelerator="Command+Shift+S")
        file_menu.add_command(label="Load Pattern…",  command=self._load_pattern,  accelerator="Command+Shift+O")
        file_menu.add_separator()
        file_menu.add_separator()
        file_menu.add_command(label="Export PDF…", command=self._export_pdf, accelerator="Command+Shift+E")
        file_menu.add_separator()
        file_menu.add_command(label="Colors…",  command=self._show_colors,  accelerator="Command+K")
        file_menu.add_command(label="Tiling…",  command=self._show_tiling,  accelerator="Command+T")
        file_menu.add_command(label="Preview…", command=self._show_preview, accelerator="Command+P")
        menubar.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menubar)
        self.root.bind("<Command-s>",       lambda _: self._save_project())
        self.root.bind("<Command-o>",       lambda _: self._load_project())
        self.root.bind("<Command-S>",       lambda _: self._save_pattern())
        self.root.bind("<Command-O>",       lambda _: self._load_pattern())
        self.root.bind("<Command-E>",       lambda _: self._export_pdf())
        self.root.bind("<Command-k>", lambda _: self._show_colors())
        self.root.bind("<Command-t>", lambda _: self._show_tiling())
        self.root.bind("<Command-p>", lambda _: self._show_preview())

        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(side=tk.LEFT, padx=(PADDING,8), pady=PADDING)
        hbar = tk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar = tk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas = tk.Canvas(canvas_frame, bg="white", cursor="hand2",
                                xscrollcommand=hbar.set,
                                yscrollcommand=vbar.set)
        self.canvas.pack(side=tk.LEFT)
        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)
        self.canvas.bind("<Button-1>", self._on_click)

        ctrl = tk.Frame(self.root, padx=8, pady=PADDING)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)

        # Rotation
        tk.Label(ctrl, text="Rotation", font=("",10,"bold")).pack(anchor=tk.W)
        for label, value in [("1× (none)",1), ("2× (180°)",2), ("4× (90°…)",4)]:
            tk.Radiobutton(ctrl, text=label, variable=self.rotation_var,
                           value=value, command=self._on_rotation_change).pack(anchor=tk.W)
        tk.Label(ctrl, text="").pack()

        # Reflections
        tk.Label(ctrl, text="Reflections", font=("",10,"bold")).pack(anchor=tk.W)
        tk.Checkbutton(ctrl, text="Add mirror axes", variable=self.reflect_var,
                       command=self.generate).pack(anchor=tk.W)
        self.group_label = tk.Label(ctrl, text="", fg="#555555")
        self.group_label.pack(anchor=tk.W, pady=(2,0))
        tk.Label(ctrl, text="").pack()

        # Grid Size
        tk.Label(ctrl, text="Grid Size", font=("",10,"bold")).pack(anchor=tk.W)
        gs_container = tk.Frame(ctrl)
        gs_container.pack(anchor=tk.W)

        # Rectangular frame (1×/2×): W and H sliders
        self._rect_frame = tk.Frame(gs_container)
        for lbl, var, attr in [("W", self.grid_w_var, "_grid_w_refresh"),
                                ("H", self.grid_h_var, "_grid_h_refresh")]:
            row = tk.Frame(self._rect_frame)
            row.pack(anchor=tk.W, pady=1)
            tk.Label(row, text=f"{lbl}:", width=2).pack(side=tk.LEFT)
            frm, refresh = make_slider_entry(row, var, 2, 25, 1,
                                              slider_length=120, entry_width=3,
                                              command=self.generate)
            frm.pack(side=tk.LEFT)
            setattr(self, attr, refresh)

        # Square frame (4×): single N slider
        self._sq_frame = tk.Frame(gs_container)
        n_row = tk.Frame(self._sq_frame)
        n_row.pack(anchor=tk.W, pady=1)
        tk.Label(n_row, text="N:", width=2).pack(side=tk.LEFT)
        frm, self._grid_n_refresh = make_slider_entry(
            n_row, self.grid_n_var, 2, 25, 1,
            slider_length=120, entry_width=3,
            command=self.generate)
        frm.pack(side=tk.LEFT)

        # Show correct frame for initial rotation value
        self._update_grid_size_frame()
        tk.Label(ctrl, text="").pack()

        # Fill Density
        tk.Label(ctrl, text="Fill Density", font=("",10,"bold")).pack(anchor=tk.W)
        df, self._density_refresh = make_slider_entry(
            ctrl, self.density_var, 0.1, 0.9, 0.05,
            slider_length=160, entry_width=5)
        df.pack(anchor=tk.W)
        tk.Label(ctrl, text="").pack()

        # Cell Size
        tk.Label(ctrl, text="Cell Size (px)", font=("",10,"bold")).pack(anchor=tk.W)
        csf, self._cell_size_refresh = make_slider_entry(
            ctrl, self.cell_size_var, 12, 60, 4,
            slider_length=160, entry_width=4,
            command=self.draw)
        csf.pack(anchor=tk.W)
        tk.Label(ctrl, text="").pack()

        # Domain highlight + action buttons
        tk.Checkbutton(ctrl, text="Highlight fundamental domain",
                       variable=self.show_domain_var, command=self.draw).pack(anchor=tk.W)
        tk.Label(ctrl, text="").pack()
        tk.Button(ctrl, text="Generate", command=self.generate, width=18).pack(pady=3)
        tk.Button(ctrl, text="Clear",    command=self.clear,    width=18).pack(pady=3)

    def _update_grid_size_frame(self):
        if self.rotation_var.get() == 4:
            self._rect_frame.pack_forget()
            self._sq_frame.pack(anchor=tk.W)
        else:
            self._sq_frame.pack_forget()
            self._rect_frame.pack(anchor=tk.W)

    def _on_rotation_change(self):
        self._update_grid_size_frame()
        self.generate()

    # ------------------------------------------------------------------
    # Floating windows
    # ------------------------------------------------------------------
    def _build_color_window(self):
        win = tk.Toplevel(self.root)
        win.title("Colors")
        win.resizable(False, False)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        win.withdraw()
        self._color_win = win

        _panel = [None]
        def on_color_change():
            self.draw()
            if _panel[0]:
                _panel[0].refresh()

        frame = tk.Frame(win, padx=12, pady=12)
        frame.pack()
        fc = tk.Frame(frame); fc.pack(side=tk.LEFT, anchor=tk.N, padx=(0,16))
        self.fill_picker = ColorPicker(fc, "Fill",       "#000000", on_color_change)
        bc = tk.Frame(frame); bc.pack(side=tk.LEFT, anchor=tk.N)
        self.bg_picker   = ColorPicker(bc, "Background", "#ffffff", on_color_change)

        bottom = tk.Frame(win, padx=12)
        bottom.pack(fill=tk.X, pady=(0,12))
        _panel[0] = ColorComparePanel(
            bottom,
            get_fill  = self.fill_picker.get,
            get_bg    = self.bg_picker.get,
            on_bg_click = lambda h: (self.bg_picker.set_color(h), on_color_change()),
        )

    def _build_tiling_window(self):
        self._tiling_win = TilingWindow(self.root, self)

    def _build_preview_window(self):
        self._preview_win = PreviewWindow(self.root, self)

    def _show_colors(self):
        self._toggle_win(self._color_win)

    def _show_tiling(self):
        self._toggle_win(self._tiling_win)

    def _show_preview(self):
        win = self._preview_win
        if win.winfo_viewable():
            win.withdraw()
        else:
            win.deiconify()
            win.lift()
            win.refresh()

    def _toggle_win(self, win):
        if win.winfo_viewable():
            win.withdraw()
        else:
            win.deiconify()
            win.lift()

    # ------------------------------------------------------------------
    # Strip management
    # ------------------------------------------------------------------
    def _resize_strips(self):
        H, W, sw = self.H, self.W, self.strip_width_var.get()

        def _resize(old, rows, cols):
            new = [[False]*cols for _ in range(rows)]
            for r in range(min(rows, len(old))):
                for c in range(min(cols, len(old[r]) if r < len(old) else 0)):
                    new[r][c] = old[r][c]
            return new

        self.col_strip = _resize(self.col_strip, H,  sw)
        self.row_strip = _resize(self.row_strip, sw, W)
        self.corner    = _resize(self.corner,    sw, sw)

    def _on_tiling_change(self):
        self._resize_strips()
        self.draw()

    # ------------------------------------------------------------------
    # Pattern generation
    # ------------------------------------------------------------------
    _PREFERRED_CELL_SIZES = {8:56,9:56,12:44,13:44,16:40,17:40,24:36,25:36}

    def _auto_fit_cell_size(self):
        sh = self.root.winfo_screenheight()
        sw = self.root.winfo_screenwidth()
        avail_w = sw - 260 - 2*PADDING
        avail_h = sh - 60  - 2*PADDING
        max_cs  = min(avail_w // max(self.W, 1), avail_h // max(self.H, 1))
        max_cs  = max(12, (max_cs // 4) * 4)
        N = max(self.H, self.W)
        preferred = self._PREFERRED_CELL_SIZES.get(N, max_cs)
        self.cell_size_var.set(min(preferred, max_cs))
        if self._cell_size_refresh:
            self._cell_size_refresh()

    def _orbit_fn(self):
        return ORBIT_FNS[(self.rotation_var.get(), self.reflect_var.get())]

    def generate(self):
        rot = self.rotation_var.get()
        if rot == 4:
            N = self.grid_n_var.get()
            self.H = self.W = N
        else:
            self.W = self.grid_w_var.get()
            self.H = self.grid_h_var.get()
        self._auto_fit_cell_size()
        self._resize_strips()
        self.grid = [[False]*self.W for _ in range(self.H)]

        orbit_fn = self._orbit_fn()
        key = (self.rotation_var.get(), self.reflect_var.get())
        self.group_label.config(text=f"Group: {GROUP_NAMES[key]}")

        domain = compute_fundamental_domain(self.H, self.W, orbit_fn)
        self.domain_cells = set(domain)
        self.cell_to_canonical = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, self.H, self.W):
                self.cell_to_canonical[(dr, dc)] = (r, c)

        density = self.density_var.get()
        for (r, c) in domain:
            filled = random.random() < density
            for (dr, dc) in orbit_fn(r, c, self.H, self.W):
                self.grid[dr][dc] = filled
        self.draw()

    # ------------------------------------------------------------------
    # Strip reflection helpers
    # ------------------------------------------------------------------
    def _apply_col_strip(self, r, sc, val):
        """Set col_strip[r][sc] = val and mirror according to strip symmetry flags."""
        H  = self.H
        sw = self.strip_width_var.get()
        rs  = {r,  H-1-r}  if self.strip_h_reflect_var.get() else {r}
        scs = {sc, sw-1-sc} if self.strip_v_reflect_var.get() else {sc}
        for rr in rs:
            for cc in scs:
                if 0 <= rr < len(self.col_strip) and 0 <= cc < len(self.col_strip[rr]):
                    self.col_strip[rr][cc] = val

    def _apply_row_strip(self, sr, c, val):
        """Set row_strip[sr][c] = val and mirror according to strip symmetry flags."""
        W  = self.W
        sw = self.strip_width_var.get()
        srs = {sr, sw-1-sr} if self.strip_h_reflect_var.get() else {sr}
        cs  = {c,  W-1-c}   if self.strip_v_reflect_var.get() else {c}
        for rr in srs:
            for cc in cs:
                if 0 <= rr < len(self.row_strip) and 0 <= cc < len(self.row_strip[rr]):
                    self.row_strip[rr][cc] = val

    def _apply_corner(self, sr, sc, val):
        """Set corner[sr][sc] = val and mirror according to strip symmetry flags."""
        sw  = self.strip_width_var.get()
        srs = {sr, sw-1-sr} if self.strip_h_reflect_var.get() else {sr}
        scs = {sc, sw-1-sc} if self.strip_v_reflect_var.get() else {sc}
        for rr in srs:
            for cc in scs:
                if 0 <= rr < len(self.corner) and 0 <= cc < len(self.corner[rr]):
                    self.corner[rr][cc] = val

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def _on_click(self, event):
        cs   = self.cell_size_var.get()
        sw   = self.strip_width_var.get()
        H, W = self.H, self.W
        h_on = self.h_repeat_var.get() and sw > 0
        v_on = self.v_repeat_var.get() and sw > 0

        ci = (int(self.canvas.canvasx(event.x)) - PADDING) // cs
        ri = (int(self.canvas.canvasy(event.y)) - PADDING) // cs

        in_tc = 0 <= ci < W
        in_tr = 0 <= ri < H
        in_cs = h_on and W <= ci < W + sw
        in_rs = v_on and H <= ri < H + sw

        if in_tr and in_tc:
            canonical = self.cell_to_canonical.get((ri, ci))
            if canonical is None: return
            r0, c0 = canonical
            new_val = not self.grid[r0][c0]
            for (dr, dc) in self._orbit_fn()(r0, c0, self.H, self.W):
                self.grid[dr][dc] = new_val
        elif in_tr and in_cs:
            sc, r = ci - W, ri
            if r < len(self.col_strip) and sc < len(self.col_strip[r]):
                self._apply_col_strip(r, sc, not self.col_strip[r][sc])
        elif in_rs and in_tc:
            sr, c = ri - H, ci
            if sr < len(self.row_strip) and c < len(self.row_strip[sr]):
                self._apply_row_strip(sr, c, not self.row_strip[sr][c])
        elif in_cs and in_rs:
            sr, sc = ri - H, ci - W
            if sr < len(self.corner) and sc < len(self.corner[sr]):
                self._apply_corner(sr, sc, not self.corner[sr][sc])
        else:
            return
        self.draw()

    def clear(self):
        H, W = self.H, self.W
        sw   = self.strip_width_var.get()
        self.grid      = [[False]*W  for _ in range(H)]
        self.col_strip = [[False]*sw for _ in range(H)]
        self.row_strip = [[False]*W  for _ in range(sw)]
        self.corner    = [[False]*sw for _ in range(sw)]
        self.domain_cells = set()
        self.draw()

    # ------------------------------------------------------------------
    # Save / load  — projects
    # ------------------------------------------------------------------
    def _project_to_dict(self):
        """Serialise the complete app state to a plain dict (JSON-safe)."""
        key = (self.rotation_var.get(), self.reflect_var.get())
        return {
            "tile": {
                "grid_w":         self.W,
                "grid_h":         self.H,
                "symmetry_group": GROUP_NAMES[key],
                "fill_color":     self.fill_picker.get(),
                "bg_color":       self.bg_picker.get(),
                "fill_density":   self.density_var.get(),
                "cell_size":      self.cell_size_var.get(),
                "grid":           self.grid,
            },
            "strips": {
                "width":      self.strip_width_var.get(),
                "h_reflect":  self.strip_h_reflect_var.get(),
                "v_reflect":  self.strip_v_reflect_var.get(),
                "col_strip":  self.col_strip,
                "row_strip":  self.row_strip,
                "corner":     self.corner,
            },
            "tiling": {
                "h_repeat":   self.h_repeat_var.get(),
                "v_repeat":   self.v_repeat_var.get(),
                "h_type":     self.h_repeat_type_var.get(),
                "v_type":     self.v_repeat_type_var.get(),
                "row_offset": self.row_offset_var.get(),
                "col_offset": self.col_offset_var.get(),
            },
        }

    def _restore_project(self, data):
        """Restore full app state from a project dict."""
        tile = data["tile"]
        self.W = tile["grid_w"]
        self.H = tile["grid_h"]
        rotation, reflections = GROUP_TO_PARAMS[tile["symmetry_group"]]
        self.rotation_var.set(rotation)
        self.reflect_var.set(reflections)
        self.group_label.config(text=f"Group: {tile['symmetry_group']}")
        if rotation == 4:
            self.grid_n_var.set(self.W)
            if self._grid_n_refresh: self._grid_n_refresh()
        else:
            self.grid_w_var.set(self.W)
            self.grid_h_var.set(self.H)
            if self._grid_w_refresh: self._grid_w_refresh()
            if self._grid_h_refresh: self._grid_h_refresh()
        self._update_grid_size_frame()
        self.fill_picker.set_color(tile["fill_color"])
        self.bg_picker.set_color(tile["bg_color"])
        self.density_var.set(tile["fill_density"])
        if self._density_refresh: self._density_refresh()
        self.cell_size_var.set(tile.get("cell_size", 40))
        if self._cell_size_refresh: self._cell_size_refresh()
        self.grid = tile["grid"]

        strips = data["strips"]
        self.strip_width_var.set(strips["width"])
        self.strip_h_reflect_var.set(strips["h_reflect"])
        self.strip_v_reflect_var.set(strips["v_reflect"])
        self.col_strip = strips["col_strip"]
        self.row_strip = strips["row_strip"]
        self.corner    = strips["corner"]

        tiling = data["tiling"]
        self.h_repeat_var.set(tiling["h_repeat"])
        self.v_repeat_var.set(tiling["v_repeat"])
        self.h_repeat_type_var.set(tiling["h_type"])
        self.v_repeat_type_var.set(tiling["v_type"])
        self.row_offset_var.set(tiling.get("row_offset", 0))
        self.col_offset_var.set(tiling.get("col_offset", 0))

        orbit_fn = self._orbit_fn()
        domain = compute_fundamental_domain(self.H, self.W, orbit_fn)
        self.domain_cells = set(domain)
        self.cell_to_canonical = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, self.H, self.W):
                self.cell_to_canonical[(dr, dc)] = (r, c)
        self.draw()
        self._tiling_win.deiconify()
        self._tiling_win.lift()
        self._preview_win.deiconify()
        self._preview_win.lift()
        self._preview_win.refresh()

    def _save_project(self):
        name = simpledialog.askstring("Save Project", "Name this project:", parent=self.root)
        if not name: return
        pid = db.save_project(name, self._project_to_dict())
        messagebox.showinfo("Saved", f"Project '{name}' saved (id {pid}).", parent=self.root)

    def _load_project(self):
        LoadProjectDialog(self.root, self._restore_project)

    # ------------------------------------------------------------------
    # Save / load  — patterns (tile only)
    # ------------------------------------------------------------------
    def _save_pattern(self):
        name = simpledialog.askstring("Save Pattern", "Name this pattern:", parent=self.root)
        if not name: return
        key = (self.rotation_var.get(), self.reflect_var.get())
        pid = db.save_pattern(name=name, grid_w=self.W, grid_h=self.H,
                               symmetry_group=GROUP_NAMES[key],
                               fill_color=self.fill_picker.get(),
                               bg_color=self.bg_picker.get(),
                               fill_density=self.density_var.get(),
                               grid=self.grid)
        messagebox.showinfo("Saved", f"'{name}' saved (id {pid}).", parent=self.root)

    def _load_pattern(self):
        LoadDialog(self.root, self._restore_pattern)

    def _restore_pattern(self, data):
        self.W = data["grid_w"]
        self.H = data["grid_h"]
        rotation, reflections = GROUP_TO_PARAMS[data["symmetry_group"]]
        self.rotation_var.set(rotation)
        self.reflect_var.set(reflections)
        self.group_label.config(text=f"Group: {data['symmetry_group']}")
        if rotation == 4:
            self.grid_n_var.set(self.W)
            if self._grid_n_refresh: self._grid_n_refresh()
        else:
            self.grid_w_var.set(self.W)
            self.grid_h_var.set(self.H)
            if self._grid_w_refresh: self._grid_w_refresh()
            if self._grid_h_refresh: self._grid_h_refresh()
        self._update_grid_size_frame()
        self.fill_picker.set_color(data["fill_color"])
        self.bg_picker.set_color(data["bg_color"])
        self.density_var.set(data["fill_density"])
        if self._density_refresh: self._density_refresh()
        self.grid = data["grid"]
        self._auto_fit_cell_size()
        self._resize_strips()
        orbit_fn = self._orbit_fn()
        domain = compute_fundamental_domain(self.H, self.W, orbit_fn)
        self.domain_cells = set(domain)
        self.cell_to_canonical = {}
        for (r, c) in domain:
            for (dr, dc) in orbit_fn(r, c, self.H, self.W):
                self.cell_to_canonical[(dr, dc)] = (r, c)
        self.draw()

    # ------------------------------------------------------------------
    # PDF export
    # ------------------------------------------------------------------
    def _export_pdf(self):
        import subprocess, tempfile, os

        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("PostScript files", "*.ps")],
            title="Export PDF…",
            parent=self.root,
        )
        if not path:
            return

        # ---- capture each canvas as PostScript ----------------------------
        def canvas_postscript(canvas):
            """Return full-scrollregion PostScript for a canvas."""
            sr = canvas.cget("scrollregion")
            kw = {"colormode": "color"}
            if sr:
                try:
                    parts = [float(v) for v in sr.split()]
                    kw["width"]  = int(parts[2] - parts[0])
                    kw["height"] = int(parts[3] - parts[1])
                except Exception:
                    pass
            return canvas.postscript(**kw)

        pages = [canvas_postscript(self.canvas)]
        if self._preview_win.winfo_viewable():
            pages.append(canvas_postscript(self._preview_win.canvas))

        # ---- combine into a single PS document ----------------------------
        # Strip %%EOF from all but the last page so interpreters read all pages
        def strip_eof(ps):
            lines = ps.splitlines()
            return "\n".join(l for l in lines if l.strip() != "%%EOF")

        if len(pages) > 1:
            combined = "\n".join(strip_eof(p) for p in pages[:-1])
            combined += "\n" + pages[-1]
        else:
            combined = pages[0]

        # ---- write temp .ps and convert -----------------------------------
        if path.lower().endswith(".ps"):
            # user explicitly wants PostScript
            with open(path, "w") as f:
                f.write(combined)
            messagebox.showinfo("Saved", f"PostScript saved to:\n{path}", parent=self.root)
            return

        with tempfile.NamedTemporaryFile(suffix=".ps", delete=False, mode="w") as f:
            f.write(combined)
            ps_path = f.name

        success = False
        for cmd in (
            ["/usr/bin/pstopdf", ps_path, "-o", path],
            ["ps2pdf", ps_path, path],
            ["/opt/homebrew/bin/ps2pdf", ps_path, path],
        ):
            try:
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0 and os.path.exists(path):
                    success = True
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        try:
            os.unlink(ps_path)
        except Exception:
            pass

        if success:
            messagebox.showinfo("PDF Exported", f"Saved to:\n{path}", parent=self.root)
        else:
            # pstopdf unavailable — write PS and open in Preview for manual export
            ps_fallback = path[:-4] + ".ps" if path.lower().endswith(".pdf") else path + ".ps"
            with open(ps_fallback, "w") as f:
                f.write(combined)
            subprocess.Popen(["open", "-a", "Preview", ps_fallback])
            messagebox.showinfo(
                "Opened in Preview",
                f"Automatic PDF conversion unavailable.\n\n"
                f"The pattern has been opened in Preview as:\n{ps_fallback}\n\n"
                "In Preview: File \u2192 Export as PDF\u2026",
                parent=self.root,
            )

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def draw(self):
        cs   = self.cell_size_var.get()
        H, W = self.H, self.W
        sw   = self.strip_width_var.get()
        h_on = self.h_repeat_var.get() and sw > 0
        v_on = self.v_repeat_var.get() and sw > 0
        ex_c = sw if h_on else 0
        ex_r = sw if v_on else 0

        cw = (W + ex_c) * cs + 2 * PADDING + NUM_W
        ch = (H + ex_r) * cs + 2 * PADDING + NUM_H
        max_cw = self.root.winfo_screenwidth()  - 320  # reserve room for control panel
        max_ch = self.root.winfo_screenheight() - 80   # reserve room for menu/OS chrome
        self.canvas.config(width=min(cw, max_cw), height=min(ch, max_ch),
                           scrollregion=(0, 0, cw, ch))
        self.canvas.delete("all")

        fill_color  = self.fill_picker.get()
        bg_color    = self.bg_picker.get()
        show_domain = self.show_domain_var.get()

        # Tile
        for r in range(H):
            for c in range(W):
                x0, y0 = PADDING + c*cs, PADDING + r*cs
                fill = fill_color if self.grid[r][c] else bg_color
                if show_domain and (r, c) in self.domain_cells:
                    ol, ow = "#e63946", 2
                else:
                    ol, ow = "#cccccc", 1
                self.canvas.create_rectangle(x0, y0, x0+cs, y0+cs,
                                              fill=fill, outline=ol, width=ow)

        def _strip_cell(x0, y0, filled):
            fill = fill_color if filled else STRIP_BG
            self.canvas.create_rectangle(x0, y0, x0+cs, y0+cs,
                                          fill=fill, outline=STRIP_LINE, width=1)

        # Col strip (right of tile) — H rows × sw cols
        if h_on:
            for r in range(H):
                for sc in range(sw):
                    filled = (r < len(self.col_strip) and
                              sc < len(self.col_strip[r]) and
                              self.col_strip[r][sc])
                    _strip_cell(PADDING+(W+sc)*cs, PADDING+r*cs, filled)

        # Row strip (below tile) — sw rows × W cols
        if v_on:
            for sr in range(sw):
                for c in range(W):
                    filled = (sr < len(self.row_strip) and
                              c < len(self.row_strip[sr]) and
                              self.row_strip[sr][c])
                    _strip_cell(PADDING+c*cs, PADDING+(H+sr)*cs, filled)

        # Corner
        if h_on and v_on:
            for sr in range(sw):
                for sc in range(sw):
                    filled = (sr < len(self.corner) and
                              sc < len(self.corner[sr]) and
                              self.corner[sr][sc])
                    _strip_cell(PADDING+(W+sc)*cs, PADDING+(H+sr)*cs, filled)

        # Row and column numbers
        # All columns numbered right-to-left: col 1 = far right (strip or tile)
        # All rows numbered bottom-to-top:    row 1 = bottom (strip or tile)
        num_size = max(7, min(10, cs // 4))
        num_font = ("", num_size)
        num_color = "#777777"
        total_cols = W + ex_c
        total_rows = H + ex_r
        num_y = PADDING + total_rows * cs + NUM_H // 2 + 1
        for c in range(W):
            x = PADDING + c * cs + cs // 2
            self.canvas.create_text(x, num_y, text=str(total_cols - c),
                                    font=num_font, fill=num_color, anchor=tk.CENTER)
        for sc in range(ex_c):
            x = PADDING + (W + sc) * cs + cs // 2
            self.canvas.create_text(x, num_y, text=str(ex_c - sc),
                                    font=num_font, fill=num_color, anchor=tk.CENTER)
        num_x = PADDING + total_cols * cs + NUM_W // 2 + 1
        for r in range(H):
            y = PADDING + r * cs + cs // 2
            self.canvas.create_text(num_x, y, text=str(total_rows - r),
                                    font=num_font, fill=num_color, anchor=tk.CENTER)
        for sr in range(ex_r):
            y = PADDING + (H + sr) * cs + cs // 2
            self.canvas.create_text(num_x, y, text=str(ex_r - sr),
                                    font=num_font, fill=num_color, anchor=tk.CENTER)

        # Refresh preview if visible
        self._preview_win.refresh()


def main():
    db.init_db()
    root = tk.Tk()
    PatternApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
