import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import json
import os
import shutil
import configparser
import string

try:
    import mgrs as _mgrs_mod
    _mgrs = _mgrs_mod.MGRS()
except ImportError:
    _mgrs = None

try:
    from tkintermapview import TkinterMapView
    _HAS_MAPVIEW = True
except ImportError:
    _HAS_MAPVIEW = False

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


# ── Conversion helpers ────────────────────────────────────────────

METERS_TO_FEET = 3.28084
FEET_TO_METERS = 1 / METERS_TO_FEET


def dd_to_ddm(dd, is_lat=True):
    """Decimal degrees → N/S/E/W DD° MM.MMM' string."""
    if dd is None:
        return ""
    dd = float(dd)
    if is_lat:
        hemi = "N" if dd >= 0 else "S"
    else:
        hemi = "E" if dd >= 0 else "W"
    dd = abs(dd)
    deg = int(dd)
    minutes = (dd - deg) * 60
    return f"{hemi} {deg:02d}° {minutes:06.3f}'"


def ddm_to_dd(text):
    """Parse 'N/S/E/W DD° MM.MMM' back to decimal degrees. Also accepts plain float."""
    text = text.strip()
    if not text:
        return 0.0
    # Try plain float first
    try:
        return float(text)
    except ValueError:
        pass
    text = text.upper().replace("°", " ").replace("'", " ").replace("\u00b4", " ")
    parts = text.split()
    if len(parts) < 3:
        raise ValueError(f"Formato inválido: '{text}'  — usar  N 41° 23.456'")
    hemi = parts[0]
    deg = float(parts[1])
    mins = float(parts[2])
    dd = deg + mins / 60.0
    if hemi in ("S", "W"):
        dd = -dd
    return dd


def m_to_ft(m):
    if m is None:
        return ""
    return round(float(m) * METERS_TO_FEET)


def ft_to_m(ft):
    return float(ft) * FEET_TO_METERS


def mgrs_to_latlon(mgrs_str):
    """Convert MGRS string to (lat, lon). Returns None on failure."""
    if not _mgrs:
        return None
    mgrs_str = mgrs_str.strip().replace(" ", "")
    if not mgrs_str:
        return None
    try:
        lat, lon = _mgrs.toLatLon(mgrs_str.encode())
        return lat, lon
    except Exception:
        return None


def is_valid_mgrs(mgrs_str):
    """Check if string looks like a valid MGRS coordinate."""
    s = mgrs_str.strip().replace(" ", "")
    if len(s) < 5:
        return False
    # Zone number (1-2 digits) + band letter + 2 square letters + even digits
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if i == 0 or i > 2:
        return False
    if i >= len(s) or not s[i].isalpha():
        return False
    i += 1  # band letter
    if i + 1 >= len(s) or not s[i].isalpha() or not s[i + 1].isalpha():
        return False
    i += 2  # square letters
    digits = s[i:]
    if not digits.isdigit():
        return False
    if len(digits) % 2 != 0:
        return False
    return True


# ── DCS.C130J path detection ─────────────────────────────────────

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chanchita_dtc.ini")


def _find_dcs_c130j_paths():
    """Search for DCS.C130J user_data.db in Saved Games across all drives."""
    candidates = []
    # Check user profile first
    user_saved = os.path.join(os.path.expanduser("~"), "Saved Games", "DCS.C130J", "user_data.db")
    if os.path.isfile(user_saved):
        candidates.append(user_saved)
    # Check all drive letters
    for letter in string.ascii_uppercase:
        drive_saved = os.path.join(f"{letter}:\\Saved Games", "DCS.C130J", "user_data.db")
        if os.path.isfile(drive_saved) and drive_saved not in candidates:
            candidates.append(drive_saved)
    return candidates


def _load_config():
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("paths", "dcs_c130j", fallback="")


def _save_config(path):
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    if not cfg.has_section("paths"):
        cfg.add_section("paths")
    cfg.set("paths", "dcs_c130j", path)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


def _load_mbtiles_config():
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("paths", "mbtiles", fallback="")


def _save_mbtiles_config(path):
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    if not cfg.has_section("paths"):
        cfg.add_section("paths")
    cfg.set("paths", "mbtiles", path)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


# ── Embedded MBTiles tile server (from dynCamp) ─────────────────

_MBTILES_PORT = 8082


class _MBTilesHandler(BaseHTTPRequestHandler):
    db_path = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path
        if path.startswith("/tiles/"):
            parts = path.split("/")
            if len(parts) >= 5:
                try:
                    z, x = int(parts[2]), int(parts[3])
                    y = int(parts[4].split(".")[0])
                except ValueError:
                    self.send_response(400)
                    self.end_headers()
                    return
                try:
                    con = sqlite3.connect(self.db_path)
                    cur = con.cursor()
                    tms_y = (2 ** z - 1) - y
                    cur.execute(
                        "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, tms_y),
                    )
                    r = cur.fetchone()
                    if not r:
                        cur.execute(
                            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                            (z, x, y),
                        )
                        r = cur.fetchone()
                    con.close()
                    if r:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(r[0])
                        return
                except Exception:
                    pass
        self.send_response(404)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()


def _start_mbtiles_server(mbtiles_path):
    _MBTilesHandler.db_path = mbtiles_path
    try:
        srv = HTTPServer(("127.0.0.1", _MBTILES_PORT), _MBTilesHandler)
    except OSError:
        return None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class DBEditor:
    # ── CDU Color Palette ─────────────────────────────────────────
    CDU_BG       = "#0a0a0a"      # near-black background
    CDU_FG       = "#33ff33"      # green text (primary)
    CDU_FG_DIM   = "#1a8c1a"      # dimmed green (labels, hints)
    CDU_AMBER    = "#ffbf00"      # amber (headings, accents)
    CDU_ENTRY_BG = "#111111"      # entry/text field background
    CDU_SEL_BG   = "#1a5c1a"      # selection/highlight background
    CDU_SEL_FG   = "#ffffff"      # selection foreground
    CDU_FONT     = ("Consolas", 10)
    CDU_FONT_SM  = ("Consolas", 9)
    CDU_FONT_HDR = ("Consolas", 11, "bold")

    def __init__(self, root):
        self.root = root
        self.version = "Alpha 0.2 (260413)"
        self.root.title(f"Chanchita DTC — {self.version}")
        self.root.geometry("1100x700")
        self.root.configure(bg=self.CDU_BG)
        self.db_path = None
        self.conn = None
        self.dcs_path = None  # Path to DCS.C130J user_data.db

        self._apply_cdu_theme()
        self._build_menu()
        self._build_tabs()

    def _apply_cdu_theme(self):
        style = ttk.Style()
        style.theme_use("clam")

        # General
        style.configure(".", background=self.CDU_BG, foreground=self.CDU_FG,
                         font=self.CDU_FONT, fieldbackground=self.CDU_ENTRY_BG,
                         borderwidth=1, focuscolor=self.CDU_FG_DIM)

        # Frames
        style.configure("TFrame", background=self.CDU_BG)
        style.configure("TLabelframe", background=self.CDU_BG, foreground=self.CDU_AMBER,
                         font=self.CDU_FONT_HDR)
        style.configure("TLabelframe.Label", background=self.CDU_BG, foreground=self.CDU_AMBER,
                         font=self.CDU_FONT_HDR)

        # Notebook (tabs)
        style.configure("TNotebook", background=self.CDU_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a1a", foreground=self.CDU_FG,
                         font=self.CDU_FONT, padding=[12, 4])
        style.map("TNotebook.Tab",
                  background=[("selected", "#222222"), ("active", "#2a2a2a")],
                  foreground=[("selected", self.CDU_AMBER)])

        # Buttons
        style.configure("TButton", background="#1a1a1a", foreground=self.CDU_FG,
                         font=self.CDU_FONT, padding=[8, 3])
        style.map("TButton",
                  background=[("active", "#2a2a2a"), ("pressed", "#333333")],
                  foreground=[("active", self.CDU_AMBER)])

        # Labels
        style.configure("TLabel", background=self.CDU_BG, foreground=self.CDU_FG,
                         font=self.CDU_FONT)
        style.configure("Dim.TLabel", foreground=self.CDU_FG_DIM)

        # Entry
        style.configure("TEntry", fieldbackground=self.CDU_ENTRY_BG, foreground=self.CDU_FG,
                         insertcolor=self.CDU_FG, font=self.CDU_FONT)

        # Combobox
        style.configure("TCombobox", fieldbackground=self.CDU_ENTRY_BG, foreground=self.CDU_FG,
                         selectbackground=self.CDU_SEL_BG, selectforeground=self.CDU_SEL_FG,
                         font=self.CDU_FONT)
        style.map("TCombobox",
                  fieldbackground=[("readonly", self.CDU_ENTRY_BG)],
                  foreground=[("readonly", self.CDU_FG)])

        # Treeview
        style.configure("Treeview", background=self.CDU_ENTRY_BG, foreground=self.CDU_FG,
                         fieldbackground=self.CDU_ENTRY_BG, font=self.CDU_FONT_SM,
                         rowheight=24)
        style.configure("Treeview.Heading", background="#1a1a1a", foreground=self.CDU_AMBER,
                         font=self.CDU_FONT)
        style.map("Treeview",
                  background=[("selected", self.CDU_SEL_BG)],
                  foreground=[("selected", self.CDU_SEL_FG)])

        # Scrollbar
        style.configure("TScrollbar", background="#1a1a1a", troughcolor=self.CDU_BG,
                         arrowcolor=self.CDU_FG_DIM)

        # Separator
        style.configure("TSeparator", background=self.CDU_FG_DIM)

        # PanedWindow
        style.configure("TPanedwindow", background=self.CDU_BG)

        # Radiobutton
        style.configure("TRadiobutton", background=self.CDU_BG, foreground=self.CDU_FG,
                         font=self.CDU_FONT)

    def _build_menu(self):
        menu_kw = dict(bg=self.CDU_BG, fg=self.CDU_FG, activebackground=self.CDU_SEL_BG,
                       activeforeground=self.CDU_AMBER, font=self.CDU_FONT)
        menubar = tk.Menu(self.root, **menu_kw)

        file_menu = tk.Menu(menubar, tearoff=0, **menu_kw)
        file_menu.add_command(label="Cargar DTC", command=self.load_dcs_dtc, accelerator="Ctrl+L")
        file_menu.add_command(label="Guardar", command=self.save_dcs_dtc, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Abrir BD...", command=self.open_db, accelerator="Ctrl+O")
        file_menu.add_command(label="Guardar como...", command=self.save_db_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Configurar ruta DCS...", command=self.configure_dcs_path)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.root.quit)
        menubar.add_cascade(label="Archivo", menu=file_menu)

        imp_menu = tk.Menu(menubar, tearoff=0, **menu_kw)
        imp_menu.add_command(label="Importar Waypoints CSV...", command=self.import_waypoints_csv)
        imp_menu.add_command(label="Importar Routes CSV...", command=self.import_routes_csv)
        imp_menu.add_separator()
        imp_menu.add_command(label="Exportar Waypoints CSV...", command=self.export_waypoints_csv)
        imp_menu.add_command(label="Exportar Routes CSV...", command=self.export_routes_csv)
        menubar.add_cascade(label="Importar/Exportar", menu=imp_menu)

        dtc_menu = tk.Menu(menubar, tearoff=0, **menu_kw)
        dtc_menu.add_command(label="Exportar paquete .dtc...", command=self.export_dtc, accelerator="Ctrl+E")
        dtc_menu.add_command(label="Importar paquete .dtc...", command=self.import_dtc, accelerator="Ctrl+I")
        menubar.add_cascade(label="Paquete DTC", menu=dtc_menu)

        self.root.config(menu=menubar)
        self.root.bind("<Control-l>", lambda e: self.load_dcs_dtc())
        self.root.bind("<Control-s>", lambda e: self.save_dcs_dtc())
        self.root.bind("<Control-o>", lambda e: self.open_db())
        self.root.bind("<Control-Shift-S>", lambda e: self.save_db_as())
        self.root.bind("<Control-e>", lambda e: self.export_dtc())
        self.root.bind("<Control-i>", lambda e: self.import_dtc())

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.wpt_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.wpt_frame, text=" Waypoints (custom_data) ")
        self._build_waypoints_tab()

        self.route_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.route_frame, text=" Routes ")
        self._build_routes_tab()

        if _HAS_MAPVIEW:
            self.map_frame = ttk.Frame(self.notebook)
            self.notebook.add(self.map_frame, text=" Mapa ")
            self._build_map_tab()

    # ── Waypoints tab ────────────────────────────────────────────────

    def _build_waypoints_tab(self):
        toolbar = ttk.Frame(self.wpt_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(toolbar, text="+ Agregar", command=self.add_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Editar", command=self.edit_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Eliminar", command=self.delete_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Duplicar", command=self.duplicate_waypoint).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(self.wpt_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        cols = ("name", "entry_pos", "lat", "lon", "alt")
        self.wpt_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        for col, heading, w in [
            ("name", "Name", 100), ("entry_pos", "MGRS", 170),
            ("lat", "Lat (DDM)", 160), ("lon", "Lon (DDM)", 160),
            ("alt", "Elev (ft)", 80),
        ]:
            self.wpt_tree.heading(col, text=heading, command=lambda c=col: self._sort_wpt(c))
            self.wpt_tree.column(col, width=w)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.wpt_tree.yview)
        self.wpt_tree.configure(yscrollcommand=vsb.set)
        self.wpt_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.wpt_tree.bind("<Double-1>", lambda e: self.edit_waypoint())

        # Status
        self.wpt_status = ttk.Label(self.wpt_frame, text="Sin BD cargada")
        self.wpt_status.pack(fill=tk.X, padx=5, pady=(0, 5))

    def _sort_wpt(self, col):
        items = [(self.wpt_tree.set(k, col), k) for k in self.wpt_tree.get_children()]
        try:
            items.sort(key=lambda t: float(t[0]))
        except ValueError:
            items.sort(key=lambda t: t[0].lower())
        for i, (_, k) in enumerate(items):
            self.wpt_tree.move(k, "", i)

    # ── Routes tab ───────────────────────────────────────────────────

    def _build_routes_tab(self):
        paned = ttk.PanedWindow(self.route_frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel — route list
        left = ttk.Frame(paned)
        paned.add(left, weight=1)

        tb = ttk.Frame(left)
        tb.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(tb, text="+ Nueva", command=self.add_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="Eliminar", command=self.delete_route).pack(side=tk.LEFT, padx=2)

        cols = ("name", "origin", "dest")
        self.route_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="extended")
        for col, heading, w in [("name", "Name", 110), ("origin", "Origin", 70), ("dest", "Dest", 70)]:
            self.route_tree.heading(col, text=heading)
            self.route_tree.column(col, width=w)
        self.route_tree.pack(fill=tk.BOTH, expand=True)
        self.route_tree.bind("<<TreeviewSelect>>", self._on_route_select)

        # Right panel — route detail editor
        right = ttk.Frame(paned)
        paned.add(right, weight=3)

        # Scrollable detail area
        canvas = tk.Canvas(right, borderwidth=0, highlightthickness=0)
        detail_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=canvas.yview)
        self.detail_inner = ttk.Frame(canvas)
        self.detail_inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.detail_inner, anchor="nw")
        canvas.configure(yscrollcommand=detail_scroll.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        inner = self.detail_inner

        # Fields grid
        fields_frame = ttk.LabelFrame(inner, text="Datos de la Ruta")
        fields_frame.pack(fill=tk.X, padx=5, pady=5)

        self.route_vars = {}
        route_fields = [
            ("name", "Nombre"), ("origin", "Origen"), ("dest", "Destino"),
            ("alt", "Alternativa"), ("wpt_trans", "WPT Trans"), ("rwy_dep", "RWY Dep"),
            ("rwy_arr", "RWY Arr"), ("rwy_dep_return", "RWY Dep Ret"), ("rwy_alt", "RWY Alt"),
            ("rwy_dep_sid", "SID"), ("rwy_arr_star", "STAR Arr"), ("rwy_alt_star", "STAR Alt"),
            ("rwy_dep_return_star", "STAR Dep Ret"), ("rwy_dep_trans", "Trans Dep"), ("rwy_arr_trans", "Trans Arr"),
        ]
        for i, (key, label) in enumerate(route_fields):
            row, col = divmod(i, 3)
            ttk.Label(fields_frame, text=label + ":").grid(row=row, column=col * 2, sticky="e", padx=(8, 2), pady=3)
            var = tk.StringVar()
            ttk.Entry(fields_frame, textvariable=var, width=18).grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 12), pady=3)
            self.route_vars[key] = var

        # Main points
        mp_frame = ttk.LabelFrame(inner, text="Main Points (main_pts)")
        mp_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.main_pts_text = tk.Text(mp_frame, height=8, wrap=tk.NONE, font=self.CDU_FONT_SM,
                                       bg=self.CDU_ENTRY_BG, fg=self.CDU_FG,
                                       insertbackground=self.CDU_FG, selectbackground=self.CDU_SEL_BG)
        mp_hsb = ttk.Scrollbar(mp_frame, orient=tk.HORIZONTAL, command=self.main_pts_text.xview)
        self.main_pts_text.configure(xscrollcommand=mp_hsb.set)
        self.main_pts_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        mp_hsb.pack(fill=tk.X, padx=5, pady=(0, 5))

        # Alt points
        ap_frame = ttk.LabelFrame(inner, text="Alt Points (alt_pts)")
        ap_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.alt_pts_text = tk.Text(ap_frame, height=5, wrap=tk.NONE, font=self.CDU_FONT_SM,
                                      bg=self.CDU_ENTRY_BG, fg=self.CDU_FG,
                                      insertbackground=self.CDU_FG, selectbackground=self.CDU_SEL_BG)
        ap_hsb = ttk.Scrollbar(ap_frame, orient=tk.HORIZONTAL, command=self.alt_pts_text.xview)
        self.alt_pts_text.configure(xscrollcommand=ap_hsb.set)
        self.alt_pts_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        ap_hsb.pack(fill=tk.X, padx=5, pady=(0, 5))

        # Save button
        ttk.Button(inner, text="💾 Guardar Ruta", command=self.save_route).pack(pady=8)

    # ── Map tab ──────────────────────────────────────────────────────

    def _build_map_tab(self):
        toolbar = ttk.Frame(self.map_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="Actualizar",
                   command=self._refresh_map_markers).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Centrar en WPTs",
                   command=self._center_map_on_wpts).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Label(toolbar, text="Tiles:").pack(side=tk.LEFT, padx=(0, 4))
        self._tile_var = tk.StringVar(value="OpenStreetMap")
        tile_values = ["OpenStreetMap", "Google Satélite", "ArcGIS Satélite",
                       "DCS Caucasus", "DCS Marianas", "DCS Nevada",
                       "DCS Persian Gulf", "DCS Syria"]
        self._mbtiles_server = None

        mbtiles_path = _load_mbtiles_config()
        if mbtiles_path and os.path.isfile(mbtiles_path):
            self._mbtiles_server = _start_mbtiles_server(mbtiles_path)
            if self._mbtiles_server:
                tile_values.append("MBTiles (local)")

        self._tile_combo = ttk.Combobox(toolbar, textvariable=self._tile_var,
                                         values=tile_values, state="readonly", width=22)
        self._tile_combo.pack(side=tk.LEFT, padx=2)
        self._tile_combo.bind("<<ComboboxSelected>>", self._on_tile_change)

        ttk.Button(toolbar, text="Cargar MBTiles...",
                   command=self._load_mbtiles_file).pack(side=tk.LEFT, padx=(8, 2))

        # Map widget
        self.map_widget = TkinterMapView(self.map_frame, corner_radius=0)
        self.map_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # Default: Caucasus region (DCS theater)
        self.map_widget.set_position(42.0, 43.5)
        self.map_widget.set_zoom(7)

        # Right-click context menu
        self.map_widget.add_right_click_menu_command(
            "Crear waypoint aquí", self._map_create_wpt, pass_coords=True)

        self._map_markers = []

    def _on_tile_change(self, event=None):
        choice = self._tile_var.get()
        if choice == "OpenStreetMap":
            self.map_widget.set_tile_server(
                "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png")
        elif choice == "Google Satélite":
            self.map_widget.set_tile_server(
                "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga")
        elif choice == "ArcGIS Satélite":
            self.map_widget.set_tile_server(
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
        elif choice == "DCS Caucasus":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-caucasus/{z}/{x}/{y}.png",
                max_zoom=15)
        elif choice == "DCS Marianas":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-marianasislands/{z}/{x}/{y}.png",
                max_zoom=15)
        elif choice == "DCS Nevada":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-nevada/{z}/{x}/{y}.png",
                max_zoom=15)
        elif choice == "DCS Persian Gulf":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-persiangulf/{z}/{x}/{y}.png",
                max_zoom=15)
        elif choice == "DCS Syria":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-syria/{z}/{x}/{y}.png",
                max_zoom=15)
        elif choice == "MBTiles (local)":
            self.map_widget.set_tile_server(
                "http://127.0.0.1:" + str(_MBTILES_PORT) + "/tiles/{z}/{x}/{y}.png",
                max_zoom=12)

    def _load_mbtiles_file(self):
        path = filedialog.askopenfilename(
            title="Seleccionar archivo MBTiles",
            filetypes=[("MBTiles", "*.mbtiles"), ("Todos", "*.*")])
        if not path or not os.path.isfile(path):
            return
        if self._mbtiles_server:
            self._mbtiles_server.shutdown()
        self._mbtiles_server = _start_mbtiles_server(path)
        if self._mbtiles_server:
            _save_mbtiles_config(path)
            vals = list(self._tile_combo["values"])
            if "MBTiles (local)" not in vals:
                vals.append("MBTiles (local)")
                self._tile_combo["values"] = vals
            self._tile_var.set("MBTiles (local)")
            self._on_tile_change()
            messagebox.showinfo("MBTiles", f"Tiles cargados:\n{os.path.basename(path)}")
        else:
            messagebox.showwarning("Error",
                "No se pudo iniciar el servidor de tiles.\nEl puerto puede estar en uso.")

    def _refresh_map_markers(self):
        if not hasattr(self, "map_widget"):
            return
        self.map_widget.delete_all_marker()
        self._map_markers.clear()
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT name, lat, lon, alt FROM custom_data WHERE lat IS NOT NULL AND lon IS NOT NULL")
        for name, lat, lon, alt in cur.fetchall():
            if lat == 0 and lon == 0:
                continue
            marker = self.map_widget.set_marker(
                lat, lon, text=name,
                command=lambda m, n=name: self._on_marker_click(n))
            self._map_markers.append(marker)

    def _center_map_on_wpts(self):
        if not hasattr(self, "map_widget") or not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT lat, lon FROM custom_data WHERE lat IS NOT NULL AND lon IS NOT NULL")
        rows = [(r[0], r[1]) for r in cur.fetchall() if r[0] != 0 or r[1] != 0]
        if not rows:
            return
        if len(rows) == 1:
            self.map_widget.set_position(rows[0][0], rows[0][1])
            self.map_widget.set_zoom(10)
        else:
            avg_lat = sum(r[0] for r in rows) / len(rows)
            avg_lon = sum(r[1] for r in rows) / len(rows)
            self.map_widget.set_position(avg_lat, avg_lon)
            self.map_widget.set_zoom(8)

    def _on_marker_click(self, wpt_name):
        for iid in self.wpt_tree.get_children():
            if self.wpt_tree.item(iid, "values")[0] == wpt_name:
                self.wpt_tree.selection_set(iid)
                self.wpt_tree.see(iid)
                self.notebook.select(self.wpt_frame)
                break

    def _map_create_wpt(self, coords):
        if not self._ensure_db():
            return
        lat, lon = coords
        pre = ("", "", dd_to_ddm(lat, True), dd_to_ddm(lon, False), "")
        self._waypoint_dialog(pre)

    # ── DB helpers ───────────────────────────────────────────────────

    def _ensure_db(self):
        if not self.conn:
            messagebox.showwarning("Aviso", "Primero cargá la BD\n(Archivo → Cargar DTC)")
            return False
        return True

    def _load_db(self, path):
        """Open a .db file and refresh everything."""
        self.db_path = path
        if self.conn:
            self.conn.close()
        self.conn = sqlite3.connect(self.db_path)
        self.root.title(f"Chanchita DTC — {self.version} — {self.db_path}")
        self.refresh_waypoints()
        self.refresh_routes()

    def _resolve_dcs_path(self, silent=False):
        """Find the DCS.C130J user_data.db path. Returns path or None."""
        # 1. Check saved config
        saved = _load_config()
        if saved and os.path.isfile(saved):
            self.dcs_path = saved
            return saved

        # 2. Auto-detect
        found = _find_dcs_c130j_paths()
        if len(found) == 1:
            self.dcs_path = found[0]
            _save_config(found[0])
            return found[0]
        elif len(found) > 1:
            # Let user pick
            dlg = tk.Toplevel(self.root)
            dlg.title("Seleccionar ruta DCS.C130J")
            dlg.transient(self.root)
            dlg.grab_set()
            dlg.resizable(False, False)

            ttk.Label(dlg, text="Se encontraron varias instalaciones de DCS.C130J.\nSeleccioná cuál usar:",
                      font=("Segoe UI", 10)).pack(padx=20, pady=(15, 10))

            selected = tk.StringVar(value=found[0])
            for p in found:
                ttk.Radiobutton(dlg, text=p, variable=selected, value=p).pack(anchor="w", padx=25, pady=2)

            result = [None]

            def on_ok():
                result[0] = selected.get()
                dlg.destroy()

            ttk.Button(dlg, text="Aceptar", command=on_ok).pack(pady=(10, 15))
            dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
            dlg.update_idletasks()
            w, h = 550, 80 + len(found) * 30 + 80
            px = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
            py = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
            dlg.geometry(f"{w}x{h}+{px}+{py}")
            self.root.wait_window(dlg)

            if result[0]:
                self.dcs_path = result[0]
                _save_config(result[0])
                return result[0]
            return None

        # 3. Not found — ask user
        if not silent:
            messagebox.showinfo(
                "DCS.C130J no encontrado",
                "No se encontró la carpeta DCS.C130J automáticamente.\n"
                "Seleccioná manualmente el archivo user_data.db")
            path = filedialog.askopenfilename(
                title="Seleccionar user_data.db de DCS.C130J",
                filetypes=[("SQLite DB", "user_data.db"), ("Todos", "*.*")])
            if path and os.path.isfile(path):
                self.dcs_path = path
                _save_config(path)
                return path
        return None

    def load_dcs_dtc(self):
        """Cargar DTC — opens user_data.db from DCS.C130J folder."""
        path = self._resolve_dcs_path()
        if not path:
            return
        self._load_db(path)

    def save_dcs_dtc(self):
        """Guardar — saves to the current DB (commits changes)."""
        if not self._ensure_db():
            return
        self.conn.commit()
        messagebox.showinfo("Guardado", f"Cambios guardados en:\n{self.db_path}")

    def configure_dcs_path(self):
        """Let the user manually set the DCS.C130J path."""
        current = _load_config()
        path = filedialog.askopenfilename(
            title="Seleccionar user_data.db de DCS.C130J",
            initialdir=os.path.dirname(current) if current else None,
            filetypes=[("SQLite DB", "user_data.db"), ("SQLite DB", "*.db"), ("Todos", "*.*")])
        if path and os.path.isfile(path):
            self.dcs_path = path
            _save_config(path)
            messagebox.showinfo("OK", f"Ruta configurada:\n{path}")

    def open_db(self):
        path = filedialog.askopenfilename(filetypes=[("SQLite DB", "*.db"), ("Todos", "*.*")])
        if not path:
            return
        self._load_db(path)

    def save_db_as(self):
        if not self._ensure_db():
            return
        path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite DB", "*.db")])
        if not path:
            return
        self.conn.commit()
        self.conn.close()
        shutil.copy2(self.db_path, path)
        self._load_db(path)
        messagebox.showinfo("OK", f"Guardado en:\n{path}")

    # ── Waypoint CRUD ────────────────────────────────────────────────

    def refresh_waypoints(self):
        for item in self.wpt_tree.get_children():
            self.wpt_tree.delete(item)
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT name, entry_pos, lat, lon, alt FROM custom_data ORDER BY name")
        rows = cur.fetchall()
        for row in rows:
            display = (
                row[0],
                row[1],
                dd_to_ddm(row[2], is_lat=True),
                dd_to_ddm(row[3], is_lat=False),
                m_to_ft(row[4]) if row[4] is not None else "",
            )
            self.wpt_tree.insert("", tk.END, values=display)
        self.wpt_status.config(text=f"{len(rows)} waypoints cargados — {os.path.basename(self.db_path)}")
        if _HAS_MAPVIEW and hasattr(self, "map_widget"):
            self._refresh_map_markers()

    def add_waypoint(self):
        if not self._ensure_db():
            return
        self._waypoint_dialog()

    def edit_waypoint(self):
        if not self._ensure_db():
            return
        sel = self.wpt_tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Seleccioná un waypoint primero")
            return
        self._waypoint_dialog(self.wpt_tree.item(sel[0], "values"))

    def duplicate_waypoint(self):
        if not self._ensure_db():
            return
        sel = self.wpt_tree.selection()
        if not sel:
            return
        vals = list(self.wpt_tree.item(sel[0], "values"))
        vals[0] = vals[0] + "_CP"
        self._waypoint_dialog(tuple(vals), is_duplicate=True)

    def delete_waypoint(self):
        if not self._ensure_db():
            return
        sel = self.wpt_tree.selection()
        if not sel:
            return
        name = self.wpt_tree.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirmar", f"¿Eliminar waypoint '{name}'?"):
            self.conn.execute("DELETE FROM custom_data WHERE name = ?", (name,))
            self.conn.commit()
            self.refresh_waypoints()

    def _waypoint_dialog(self, existing=None, is_duplicate=False):
        dlg = tk.Toplevel(self.root)
        dlg.title("Nuevo Waypoint" if (not existing or is_duplicate) else "Editar Waypoint")
        dlg.geometry("520x270")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)

        labels = ["Name:", "MGRS (entry_pos):", "Lat (DDM):", "Lon (DDM):", "Elevación (ft):"]
        entries = []
        for i, lbl in enumerate(labels):
            ttk.Label(dlg, text=lbl).grid(row=i, column=0, sticky="e", padx=(15, 5), pady=6)
            e = ttk.Entry(dlg, width=32)
            e.grid(row=i, column=1, padx=(0, 15), pady=6)
            if existing and i < len(existing):
                e.insert(0, existing[i])
            entries.append(e)

        # Hint labels
        ttk.Label(dlg, text="N 41° 23.456'", foreground="gray").grid(row=2, column=2, sticky="w")
        ttk.Label(dlg, text="E 044° 12.345'", foreground="gray").grid(row=3, column=2, sticky="w")
        ttk.Label(dlg, text="en pies (MSL)", foreground="gray").grid(row=4, column=2, sticky="w")

        is_edit = existing and not is_duplicate
        old_name = existing[0] if is_edit else None
        if is_edit:
            entries[0].config(state="disabled")

        def save():
            vals = [e.get().strip() for e in entries]
            if not vals[0]:
                messagebox.showwarning("Error", "El nombre es obligatorio", parent=dlg)
                return

            mgrs_str = vals[1]

            # Validate MGRS if it looks like one
            if mgrs_str and not mgrs_str[0].isalpha():
                if not is_valid_mgrs(mgrs_str):
                    messagebox.showwarning(
                        "MGRS inválido",
                        f"El MGRS '{mgrs_str}' tiene un número impar de dígitos u otro error de formato.\n"
                        "Verificá que la coordenada sea correcta.",
                        parent=dlg,
                    )
                    return

            try:
                lat = ddm_to_dd(vals[2]) if vals[2] else None
                lon = ddm_to_dd(vals[3]) if vals[3] else None
            except ValueError as exc:
                messagebox.showwarning("Error", f"Valor inválido:\n{exc}", parent=dlg)
                return

            # Auto-fill lat/lon from MGRS if not provided
            if (lat is None or lon is None) and mgrs_str:
                result = mgrs_to_latlon(mgrs_str)
                if result:
                    lat, lon = result
                else:
                    # Library failed — let user enter manually
                    if lat is None or lon is None:
                        messagebox.showwarning(
                            "Conversión MGRS",
                            "La librería no pudo convertir este MGRS a lat/lon.\n"
                            "Ingresá lat/lon manualmente (copiá del CDU de DCS).",
                            parent=dlg,
                        )
                        return
            lat = lat or 0.0
            lon = lon or 0.0

            # Parse elevation (ft → m for storage)
            alt_ft_str = vals[4] if len(vals) > 4 else ""
            try:
                alt_m = ft_to_m(float(alt_ft_str)) if alt_ft_str else None
            except ValueError:
                messagebox.showwarning("Error", f"Elevación inválida: '{alt_ft_str}'", parent=dlg)
                return

            if is_edit:
                self.conn.execute(
                    "UPDATE custom_data SET entry_pos=?, lat=?, lon=?, alt=? WHERE name=?",
                    (vals[1], lat, lon, alt_m, old_name),
                )
            else:
                try:
                    self.conn.execute(
                        "INSERT INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)",
                        (vals[0], vals[1], lat, lon, alt_m),
                    )
                except sqlite3.IntegrityError:
                    messagebox.showwarning("Error", f"Ya existe un waypoint con nombre '{vals[0]}'", parent=dlg)
                    return
            self.conn.commit()
            self.refresh_waypoints()
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=12)
        ttk.Button(btn_frame, text="Guardar", command=save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        dlg.bind("<Return>", lambda e: save())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        entries[0 if not is_edit else 1].focus_set()

    # ── Route CRUD ───────────────────────────────────────────────────

    def refresh_routes(self):
        for item in self.route_tree.get_children():
            self.route_tree.delete(item)
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT name, origin, dest FROM routes ORDER BY name")
        for row in cur.fetchall():
            self.route_tree.insert("", tk.END, values=row)

    def _on_route_select(self, event=None):
        sel = self.route_tree.selection()
        if not sel or not self.conn:
            return
        name = self.route_tree.item(sel[0], "values")[0]
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM routes WHERE name = ?", (name,))
        row = cur.fetchone()
        if not row:
            return
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))

        for key, var in self.route_vars.items():
            var.set(str(data.get(key, "") or ""))

        self.main_pts_text.delete("1.0", tk.END)
        self.main_pts_text.insert("1.0", data.get("main_pts", "") or "")
        self.alt_pts_text.delete("1.0", tk.END)
        self.alt_pts_text.insert("1.0", data.get("alt_pts", "") or "")

    def add_route(self):
        if not self._ensure_db():
            return
        for var in self.route_vars.values():
            var.set("")
        self.main_pts_text.delete("1.0", tk.END)
        self.alt_pts_text.delete("1.0", tk.END)
        self.route_tree.selection_remove(*self.route_tree.selection())

    def save_route(self):
        if not self._ensure_db():
            return
        name = self.route_vars["name"].get().strip()
        if not name:
            messagebox.showwarning("Error", "El nombre de la ruta es obligatorio")
            return

        data = {k: v.get().strip() for k, v in self.route_vars.items()}
        data["main_pts"] = self.main_pts_text.get("1.0", tk.END).strip()
        data["alt_pts"] = self.alt_pts_text.get("1.0", tk.END).strip()

        try:
            data["wpt_trans"] = int(data["wpt_trans"]) if data["wpt_trans"] else 0
        except ValueError:
            data["wpt_trans"] = 0

        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM routes WHERE name = ?", (name,))
        exists = cur.fetchone()[0] > 0

        if exists:
            self.conn.execute(
                """UPDATE routes SET wpt_trans=?, main_pts=?, alt_pts=?, origin=?, dest=?, alt=?,
                   rwy_dep=?, rwy_arr=?, rwy_dep_return=?, rwy_alt=?, rwy_dep_sid=?, rwy_arr_star=?,
                   rwy_alt_star=?, rwy_dep_return_star=?, rwy_dep_trans=?, rwy_arr_trans=?
                   WHERE name=?""",
                (
                    data["wpt_trans"], data["main_pts"], data["alt_pts"],
                    data["origin"], data["dest"], data["alt"],
                    data["rwy_dep"], data["rwy_arr"], data["rwy_dep_return"], data["rwy_alt"],
                    data["rwy_dep_sid"], data["rwy_arr_star"], data["rwy_alt_star"],
                    data["rwy_dep_return_star"], data["rwy_dep_trans"], data["rwy_arr_trans"],
                    name,
                ),
            )
        else:
            self.conn.execute(
                """INSERT INTO routes (name, wpt_trans, main_pts, alt_pts, origin, dest, alt,
                   rwy_dep, rwy_arr, rwy_dep_return, rwy_alt, rwy_dep_sid, rwy_arr_star,
                   rwy_alt_star, rwy_dep_return_star, rwy_dep_trans, rwy_arr_trans)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    name, data["wpt_trans"], data["main_pts"], data["alt_pts"],
                    data["origin"], data["dest"], data["alt"],
                    data["rwy_dep"], data["rwy_arr"], data["rwy_dep_return"], data["rwy_alt"],
                    data["rwy_dep_sid"], data["rwy_arr_star"], data["rwy_alt_star"],
                    data["rwy_dep_return_star"], data["rwy_dep_trans"], data["rwy_arr_trans"],
                ),
            )

        self.conn.commit()
        self.refresh_routes()
        messagebox.showinfo("OK", f"Ruta '{name}' guardada")

    def delete_route(self):
        if not self._ensure_db():
            return
        sel = self.route_tree.selection()
        if not sel:
            return
        name = self.route_tree.item(sel[0], "values")[0]
        if messagebox.askyesno("Confirmar", f"¿Eliminar ruta '{name}'?"):
            self.conn.execute("DELETE FROM routes WHERE name = ?", (name,))
            self.conn.commit()
            self.refresh_routes()

    # ── DTC Package Export / Import ─────────────────────────────────

    def export_dtc(self):
        """Export selected waypoints + routes to a .dtc package file."""
        if not self._ensure_db():
            return

        wpt_sel = self.wpt_tree.selection()
        route_sel = self.route_tree.selection()

        if not wpt_sel and not route_sel:
            messagebox.showwarning("Aviso",
                "Seleccioná al menos un waypoint o una ruta para exportar.\n"
                "(Usá Ctrl+Click o Shift+Click para selección múltiple)")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".dtc",
            filetypes=[("Paquete DTC", "*.dtc"), ("Todos", "*.*")],
            title="Exportar paquete DTC",
        )
        if not path:
            return

        # Gather selected waypoint names
        wpt_names = [self.wpt_tree.item(iid, "values")[0] for iid in wpt_sel]
        route_names = [self.route_tree.item(iid, "values")[0] for iid in route_sel]

        # Create the .dtc SQLite file
        if os.path.exists(path):
            os.remove(path)
        dtc_conn = sqlite3.connect(path)
        dtc_conn.execute("""CREATE TABLE custom_data (
            name TEXT PRIMARY KEY, entry_pos TEXT, lat REAL, lon REAL, alt REAL)""")
        dtc_conn.execute("""CREATE TABLE routes (
            name TEXT PRIMARY KEY, wpt_trans INTEGER, main_pts TEXT, alt_pts TEXT,
            origin TEXT, dest TEXT, alt TEXT,
            rwy_dep TEXT, rwy_arr TEXT, rwy_dep_return TEXT, rwy_alt TEXT,
            rwy_dep_sid TEXT, rwy_arr_star TEXT, rwy_alt_star TEXT,
            rwy_dep_return_star TEXT, rwy_dep_trans TEXT, rwy_arr_trans TEXT)""")

        src = self.conn.cursor()
        for name in wpt_names:
            src.execute("SELECT name, entry_pos, lat, lon, alt FROM custom_data WHERE name = ?", (name,))
            row = src.fetchone()
            if row:
                dtc_conn.execute("INSERT INTO custom_data VALUES (?,?,?,?,?)", row)

        route_cols = [
            "name", "wpt_trans", "main_pts", "alt_pts", "origin", "dest", "alt",
            "rwy_dep", "rwy_arr", "rwy_dep_return", "rwy_alt", "rwy_dep_sid",
            "rwy_arr_star", "rwy_alt_star", "rwy_dep_return_star", "rwy_dep_trans", "rwy_arr_trans",
        ]
        for name in route_names:
            src.execute("SELECT * FROM routes WHERE name = ?", (name,))
            row = src.fetchone()
            if row:
                cols = [d[0] for d in src.description]
                data = dict(zip(cols, row))
                vals = [data.get(c, "") for c in route_cols]
                placeholders = ",".join(["?"] * len(route_cols))
                dtc_conn.execute(f"INSERT INTO routes ({','.join(route_cols)}) VALUES ({placeholders})", vals)

        dtc_conn.commit()
        dtc_conn.close()

        messagebox.showinfo("Exportado",
            f"Paquete DTC guardado:\n{os.path.basename(path)}\n\n"
            f"• {len(wpt_names)} waypoint(s)\n• {len(route_names)} ruta(s)")

    def import_dtc(self):
        """Import a .dtc package, merging into the current DB with conflict resolution."""
        if not self._ensure_db():
            return

        path = filedialog.askopenfilename(
            filetypes=[("Paquete DTC", "*.dtc"), ("SQLite DB", "*.db"), ("Todos", "*.*")],
            title="Importar paquete DTC",
        )
        if not path:
            return

        try:
            dtc_conn = sqlite3.connect(path)
            dtc_conn.execute("SELECT 1 FROM custom_data LIMIT 1")
        except Exception:
            messagebox.showerror("Error", "El archivo no es un paquete DTC válido.")
            return

        # ── Import waypoints ──
        dtc_cur = dtc_conn.cursor()
        dtc_cur.execute("SELECT name, entry_pos, lat, lon, alt FROM custom_data")
        wpt_rows = dtc_cur.fetchall()

        wpt_imported = 0
        wpt_skipped = 0
        for row in wpt_rows:
            name = row[0]
            existing = self.conn.execute(
                "SELECT name FROM custom_data WHERE name = ?", (name,)
            ).fetchone()

            if existing:
                action = self._conflict_dialog("Waypoint", name)
                if action == "skip":
                    wpt_skipped += 1
                    continue
                elif action == "overwrite":
                    self.conn.execute("DELETE FROM custom_data WHERE name = ?", (name,))
                    self.conn.execute(
                        "INSERT INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)", row)
                elif action.startswith("rename_new:"):
                    new_name = action.split(":", 1)[1]
                    self.conn.execute(
                        "INSERT INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)",
                        (new_name, row[1], row[2], row[3], row[4]))
                elif action.startswith("rename_old:"):
                    new_name = action.split(":", 1)[1]
                    self.conn.execute("UPDATE custom_data SET name = ? WHERE name = ?", (new_name, name))
                    self.conn.execute(
                        "INSERT INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)", row)
            else:
                self.conn.execute(
                    "INSERT INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)", row)
            wpt_imported += 1

        # ── Import routes ──
        route_cols = [
            "name", "wpt_trans", "main_pts", "alt_pts", "origin", "dest", "alt",
            "rwy_dep", "rwy_arr", "rwy_dep_return", "rwy_alt", "rwy_dep_sid",
            "rwy_arr_star", "rwy_alt_star", "rwy_dep_return_star", "rwy_dep_trans", "rwy_arr_trans",
        ]
        try:
            dtc_cur.execute("SELECT * FROM routes")
            route_rows = dtc_cur.fetchall()
            route_col_names = [d[0] for d in dtc_cur.description]
        except Exception:
            route_rows = []
            route_col_names = []

        route_imported = 0
        route_skipped = 0
        for row in route_rows:
            data = dict(zip(route_col_names, row))
            name = data.get("name", "")
            if not name:
                continue

            existing = self.conn.execute(
                "SELECT name FROM routes WHERE name = ?", (name,)
            ).fetchone()

            vals = [data.get(c, "") for c in route_cols]

            if existing:
                action = self._conflict_dialog("Ruta", name)
                if action == "skip":
                    route_skipped += 1
                    continue
                elif action == "overwrite":
                    self.conn.execute("DELETE FROM routes WHERE name = ?", (name,))
                    placeholders = ",".join(["?"] * len(route_cols))
                    self.conn.execute(
                        f"INSERT INTO routes ({','.join(route_cols)}) VALUES ({placeholders})", vals)
                elif action.startswith("rename_new:"):
                    new_name = action.split(":", 1)[1]
                    vals[0] = new_name
                    placeholders = ",".join(["?"] * len(route_cols))
                    self.conn.execute(
                        f"INSERT INTO routes ({','.join(route_cols)}) VALUES ({placeholders})", vals)
                elif action.startswith("rename_old:"):
                    new_name = action.split(":", 1)[1]
                    self.conn.execute("UPDATE routes SET name = ? WHERE name = ?", (new_name, name))
                    placeholders = ",".join(["?"] * len(route_cols))
                    self.conn.execute(
                        f"INSERT INTO routes ({','.join(route_cols)}) VALUES ({placeholders})", vals)
            else:
                placeholders = ",".join(["?"] * len(route_cols))
                self.conn.execute(
                    f"INSERT INTO routes ({','.join(route_cols)}) VALUES ({placeholders})", vals)
            route_imported += 1

        self.conn.commit()
        dtc_conn.close()

        self.refresh_waypoints()
        self.refresh_routes()

        messagebox.showinfo("Importación completa",
            f"Waypoints: {wpt_imported} importados, {wpt_skipped} omitidos\n"
            f"Rutas: {route_imported} importadas, {route_skipped} omitidas")

    def _conflict_dialog(self, tipo, name):
        """Show conflict resolution dialog. Returns action string."""
        dlg = tk.Toplevel(self.root)
        dlg.title(f"Conflicto — {tipo}")
        dlg.resizable(False, False)
        dlg.transient(self.root)

        result = tk.StringVar(value="skip")

        ttk.Label(dlg, text=f"⚠  {tipo} '{name}' ya existe",
                  font=("Segoe UI", 11, "bold")).pack(padx=20, pady=(18, 5))
        ttk.Label(dlg, text="¿Qué querés hacer?",
                  font=("Segoe UI", 9)).pack(padx=20, pady=(0, 12))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=20, pady=5)

        def do_overwrite():
            result.set("overwrite")
            dlg.destroy()

        def do_rename_new():
            dlg.grab_release()
            new = simpledialog.askstring("Renombrar importado",
                f"Nuevo nombre para el {tipo.lower()} que estás importando:",
                initialvalue=name + "_imp", parent=self.root)
            if new and new.strip():
                result.set(f"rename_new:{new.strip()}")
                dlg.destroy()
            else:
                dlg.grab_set()

        def do_rename_old():
            dlg.grab_release()
            new = simpledialog.askstring("Renombrar existente",
                f"Nuevo nombre para el {tipo.lower()} que ya tenés guardado:",
                initialvalue=name + "_old", parent=self.root)
            if new and new.strip():
                result.set(f"rename_old:{new.strip()}")
                dlg.destroy()
            else:
                dlg.grab_set()

        def do_skip():
            result.set("skip")
            dlg.destroy()

        ttk.Button(btn_frame, text="📝 Renombrar el importado",
                   command=do_rename_new).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="📝 Renombrar el existente",
                   command=do_rename_old).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="⚡ Sobrescribir con el importado",
                   command=do_overwrite).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="⏭  Omitir (no importar)",
                   command=do_skip).pack(fill=tk.X, pady=3)

        dlg.protocol("WM_DELETE_WINDOW", do_skip)
        dlg.bind("<Escape>", lambda e: do_skip())

        # Ensure the window is mapped before grabbing focus
        dlg.update_idletasks()
        # Center on parent
        w, h = 480, 260
        px = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        py = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{px}+{py}")
        dlg.lift()
        dlg.focus_force()
        dlg.grab_set()

        self.root.wait_window(dlg)
        return result.get()

    # ── Import / Export ──────────────────────────────────────────────

    def import_waypoints_csv(self):
        if not self._ensure_db():
            return
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if not path:
            return
        count = 0
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.conn.execute(
                    "INSERT OR REPLACE INTO custom_data (name, entry_pos, lat, lon, alt) VALUES (?,?,?,?,?)",
                    (
                        row["name"],
                        row.get("entry_pos", ""),
                        float(row.get("lat", 0)),
                        float(row.get("lon", 0)),
                        float(row.get("alt", 0)),
                    ),
                )
                count += 1
        self.conn.commit()
        self.refresh_waypoints()
        messagebox.showinfo("OK", f"{count} waypoints importados")

    def import_routes_csv(self):
        if not self._ensure_db():
            return
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("Todos", "*.*")])
        if not path:
            return
        route_cols = [
            "name", "wpt_trans", "main_pts", "alt_pts", "origin", "dest", "alt",
            "rwy_dep", "rwy_arr", "rwy_dep_return", "rwy_alt", "rwy_dep_sid",
            "rwy_arr_star", "rwy_alt_star", "rwy_dep_return_star", "rwy_dep_trans", "rwy_arr_trans",
        ]
        count = 0
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vals = [row.get(c, "") for c in route_cols]
                vals[1] = int(vals[1]) if vals[1] else 0
                placeholders = ",".join(["?"] * len(route_cols))
                col_names = ",".join(route_cols)
                self.conn.execute(
                    f"INSERT OR REPLACE INTO routes ({col_names}) VALUES ({placeholders})", vals
                )
                count += 1
        self.conn.commit()
        self.refresh_routes()
        messagebox.showinfo("OK", f"{count} rutas importadas")

    def export_waypoints_csv(self):
        if not self._ensure_db():
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT name, entry_pos, lat, lon, alt FROM custom_data ORDER BY name")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "entry_pos", "lat", "lon", "alt"])
            writer.writerows(cur.fetchall())
        messagebox.showinfo("OK", f"Waypoints exportados a:\n{path}")

    def export_routes_csv(self):
        if not self._ensure_db():
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM routes ORDER BY name")
        cols = [d[0] for d in cur.description]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(cols)
            writer.writerows(cur.fetchall())
        messagebox.showinfo("OK", f"Rutas exportadas a:\n{path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = DBEditor(root)
    root.mainloop()
