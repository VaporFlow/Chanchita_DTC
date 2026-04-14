import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import json
import os
import re
import shutil
import configparser
import string
import urllib.request

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


def _load_navdata_config():
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("paths", "nav_data", fallback="")


def _save_navdata_config(path):
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    if not cfg.has_section("paths"):
        cfg.add_section("paths")
    cfg.set("paths", "nav_data", path)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


def _find_nav_data_db():
    """Search for nav_data.db in DCS World C-130J module across all drives."""
    candidates = []
    # Common DCS install paths
    patterns = [
        os.path.join(f"{letter}:\\", "**", "Mods", "aircraft", "C130J",
                      "Cockpit", "Resources", "nav_data.db")
        for letter in string.ascii_uppercase
    ]
    # Check Program Files and Eagle Dynamics paths first
    quick_paths = [
        os.path.join(f"{letter}:\\", base, "Mods", "aircraft", "C130J",
                      "Cockpit", "Resources", "nav_data.db")
        for letter in string.ascii_uppercase
        for base in [
            "Eagle Dynamics\\DCS World",
            "Eagle Dynamics\\DCS World OpenBeta",
            "Program Files\\Eagle Dynamics\\DCS World",
            "DCS World",
            "DCS World OpenBeta",
        ]
    ]
    for p in quick_paths:
        if os.path.isfile(p) and p not in candidates:
            candidates.append(p)
    return candidates


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
        self.nav_conn = None  # Connection to nav_data.db
        self.names_conn = None  # Connection to airport_names.db

        self._apply_cdu_theme()
        self._build_menu()
        self._build_tabs()
        self._load_nav_data()  # try to load nav_data.db at startup
        self._load_airport_names()  # load airport_names.db

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
        ttk.Button(tb, text="💾 Guardar", command=self.save_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="Eliminar", command=self.delete_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="Clonar", command=self.clone_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="🗺 Ver en Mapa", command=self.show_route_on_map).pack(side=tk.LEFT, padx=2)

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
        canvas = tk.Canvas(right, borderwidth=0, highlightthickness=0,
                           bg=self.CDU_BG)
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

        # Main points — waypoint list with toolbar
        mp_frame = ttk.LabelFrame(inner, text="Main Points (main_pts)")
        mp_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self._build_wpt_list(mp_frame, "main")

        # Alt points — waypoint list with toolbar
        ap_frame = ttk.LabelFrame(inner, text="Alt Points (alt_pts)")
        ap_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self._build_wpt_list(ap_frame, "alt")

        # Raw text (collapsed by default, for advanced editing)
        raw_frame = ttk.LabelFrame(inner, text="Edición manual (pipe-delimited)")
        raw_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._raw_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(raw_frame, text="Mostrar campos de texto raw",
                        variable=self._raw_visible,
                        command=self._toggle_raw_text).pack(anchor="w", padx=5, pady=2)
        self._raw_container = ttk.Frame(raw_frame)
        # Main pts raw
        ttk.Label(self._raw_container, text="main_pts:").pack(anchor="w", padx=5)
        self.main_pts_text = tk.Text(self._raw_container, height=3, wrap=tk.NONE, font=self.CDU_FONT_SM,
                                       bg=self.CDU_ENTRY_BG, fg=self.CDU_FG,
                                       insertbackground=self.CDU_FG, selectbackground=self.CDU_SEL_BG)
        self.main_pts_text.pack(fill=tk.X, padx=5, pady=(0, 3))
        # Alt pts raw
        ttk.Label(self._raw_container, text="alt_pts:").pack(anchor="w", padx=5)
        self.alt_pts_text = tk.Text(self._raw_container, height=2, wrap=tk.NONE, font=self.CDU_FONT_SM,
                                      bg=self.CDU_ENTRY_BG, fg=self.CDU_FG,
                                      insertbackground=self.CDU_FG, selectbackground=self.CDU_SEL_BG)
        self.alt_pts_text.pack(fill=tk.X, padx=5, pady=(0, 5))

    def _build_wpt_list(self, parent, tag):
        """Build a waypoint list with toolbar for main or alt points."""
        tb = ttk.Frame(parent)
        tb.pack(fill=tk.X, padx=5, pady=(5, 0))
        ttk.Button(tb, text="+ Agregar", command=lambda: self._wpt_list_add(tag)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="Quitar", command=lambda: self._wpt_list_remove(tag)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▲", width=3, command=lambda: self._wpt_list_move(tag, -1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▼", width=3, command=lambda: self._wpt_list_move(tag, 1)).pack(side=tk.LEFT, padx=2)

        cols = ("seq", "wpt_id", "nombre", "source")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6, selectmode="extended")
        tree.heading("seq", text="#")
        tree.column("seq", width=35, stretch=False)
        tree.heading("wpt_id", text="Waypoint")
        tree.column("wpt_id", width=100)
        tree.heading("nombre", text="Nombre")
        tree.column("nombre", width=200)
        tree.heading("source", text="Fuente")
        tree.column("source", width=80)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=(3, 5))

        if tag == "main":
            self._main_wpt_tree = tree
        else:
            self._alt_wpt_tree = tree

    def _toggle_raw_text(self):
        if self._raw_visible.get():
            self._raw_container.pack(fill=tk.X, padx=0, pady=(0, 5))
            self._sync_list_to_raw("main")
            self._sync_list_to_raw("alt")
        else:
            self._raw_container.pack_forget()

    def _get_wpt_tree(self, tag):
        return self._main_wpt_tree if tag == "main" else self._alt_wpt_tree

    # ── Native C-130J route format helpers ────────────────────────

    def _lookup_wpt_coords(self, wpt_id):
        """Look up (lat, lon, is_nav) for a waypoint ID."""
        if self.conn:
            cur = self.conn.cursor()
            cur.execute("SELECT lat, lon FROM custom_data WHERE name = ?", (wpt_id,))
            row = cur.fetchone()
            if row:
                return (row[0], row[1], False)
        if self.nav_conn:
            nav = self.nav_conn.cursor()
            nav.execute("SELECT lat, lon FROM airports WHERE icao = ?", (wpt_id,))
            row = nav.fetchone()
            if not row:
                ident = self._resolve_alias_to_ident(wpt_id)
                if ident:
                    nav.execute("SELECT lat, lon FROM airports WHERE icao = ?", (ident,))
                    row = nav.fetchone()
            if row:
                return (row[0], row[1], True)
            nav.execute("SELECT lat, lon FROM navaids WHERE name = ?", (wpt_id,))
            row = nav.fetchone()
            if row:
                return (row[0], row[1], True)
            nav.execute(
                "SELECT waypoint_latitude, waypoint_longitude FROM waypoints "
                "WHERE waypoint_identifier = ? LIMIT 1", (wpt_id,))
            row = nav.fetchone()
            if row:
                return (row[0], row[1], True)
        return (None, None, False)

    def _build_native_wpt_tuple(self, name, wpt_type, lat, lon,
                                speed=0, alt=-999, is_nav=True, flyover=None):
        """Build a single waypoint tuple in the native C-130J format (40 fields)."""
        if flyover is None:
            flyover = 1 if wpt_type == 0 else 0
        db_src = 1 if is_nav else 0
        fields = [
            name,               # 0  name
            str(wpt_type),      # 1  type: 2=origin, 0=enroute, 1=dest
            f" {lat:.5f}",      # 2  lat
            f" {lon:.5f}",      # 3  lon
            f"{speed:3d}",      # 4  speed (kts), 0=none
            "0",                # 5
            str(alt),           # 6  altitude (ft), -999=none
            "0",                # 7
            "",                 # 8
            "3",                # 9
            str(db_src),        # 10 1=nav_data, 0=custom
            "       ",          # 11
            "      ",           # 12
            "      ",           # 13
            "      ",           # 14
            "-99",              # 15
            "-99",              # 16
            "0",                # 17
            "0",                # 18
            "000000",           # 19
            "      ",           # 20
            "  0.0",            # 21
            "    0",            # 22
            "-99999",           # 23
            "0",                # 24
            "0",                # 25
            "0",                # 26
            "0",                # 27
            "    0",            # 28
            "    0",            # 29
            "    0",            # 30
            "    0",            # 31
            "    0",            # 32
            str(flyover),       # 33 1=flyover (enroute), 0=flyby
            "0",                # 34
            "    0",            # 35
            " -999",            # 36
            "    0",            # 37
            " -999",            # 38
            " -999",            # 39
        ]
        return "(" + "|".join(fields) + ")"

    def _build_native_wpt_for_id(self, wpt_id):
        """Look up coordinates for wpt_id and build a native tuple (enroute default)."""
        lat, lon, is_nav = self._lookup_wpt_coords(wpt_id)
        if lat is None or lon is None:
            lat, lon = 0.0, 0.0
        return self._build_native_wpt_tuple(wpt_id, 0, lat, lon, is_nav=is_nav)

    def _wpt_list_add(self, tag):
        """Open search dialog and add selected waypoint to the list."""
        result = self._wpt_search_dialog()
        if result:
            tree = self._get_wpt_tree(tag)
            seq = len(tree.get_children()) + 1
            wpt_id, source = result[0], result[1]
            nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
            native = self._build_native_wpt_for_id(wpt_id)
            tree.insert("", tk.END, values=(seq, wpt_id, nombre, source, native))
            self._sync_list_to_raw(tag)

    def _wpt_list_remove(self, tag):
        tree = self._get_wpt_tree(tag)
        sel = tree.selection()
        for item in sel:
            tree.delete(item)
        self._renumber_wpt_list(tag)
        self._sync_list_to_raw(tag)

    def _wpt_list_move(self, tag, direction):
        tree = self._get_wpt_tree(tag)
        sel = tree.selection()
        if not sel:
            return
        items = list(tree.get_children())
        indices = [items.index(s) for s in sel]
        if direction == -1 and min(indices) == 0:
            return
        if direction == 1 and max(indices) == len(items) - 1:
            return
        for idx in (indices if direction == -1 else reversed(indices)):
            tree.move(items[idx], "", idx + direction)
        self._renumber_wpt_list(tag)
        self._sync_list_to_raw(tag)

    def _renumber_wpt_list(self, tag):
        tree = self._get_wpt_tree(tag)
        for i, item in enumerate(tree.get_children(), 1):
            vals = list(tree.item(item, "values"))
            vals[0] = i
            tree.item(item, values=vals)

    def _sync_list_to_raw(self, tag):
        """Sync waypoint list → raw text field (native C-130J format)."""
        tree = self._get_wpt_tree(tag)
        items = tree.get_children()
        tuples = []
        for idx, item in enumerate(items):
            vals = tree.item(item, "values")
            native_tuple = vals[4] if len(vals) > 4 else None
            if native_tuple:
                fields = native_tuple.strip("()").split("|")
                if len(fields) >= 34:
                    if len(items) == 1:
                        fields[1] = "2"
                        fields[33] = "0"
                    elif idx == 0:
                        fields[1] = "2"
                        fields[33] = "0"
                    elif idx == len(items) - 1:
                        fields[1] = "1"
                        fields[33] = "0"
                    else:
                        fields[1] = "0"
                        fields[33] = "1"
                tuples.append("(" + "|".join(fields) + ")")
            else:
                tuples.append(str(vals[1]))
        raw = ",".join(tuples)
        text_widget = self.main_pts_text if tag == "main" else self.alt_pts_text
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", raw)

    def _load_wpt_list_from_raw(self, tag, raw_text):
        """Parse native C-130J format or legacy pipe-delimited text."""
        tree = self._get_wpt_tree(tag)
        tree.delete(*tree.get_children())
        if not raw_text or not raw_text.strip():
            return
        raw = raw_text.strip()
        if raw.startswith("("):
            # Native format: (WPT|...),(WPT|...)
            wpt_tuples = re.findall(r'\([^)]+\)', raw)
            for i, t in enumerate(wpt_tuples, 1):
                wpt_id = t[1:].split("|", 1)[0].strip()
                source = self._identify_wpt_source(wpt_id)
                nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
                tree.insert("", tk.END, values=(i, wpt_id, nombre, source, t))
        else:
            # Legacy format: NAME|NAME|NAME — convert to native
            wpts = [w.strip() for w in raw.split("|") if w.strip()]
            for i, wpt_id in enumerate(wpts, 1):
                source = self._identify_wpt_source(wpt_id)
                nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
                native = self._build_native_wpt_for_id(wpt_id)
                tree.insert("", tk.END, values=(i, wpt_id, nombre, source, native))

    def _identify_wpt_source(self, wpt_id):
        """Try to identify where a waypoint comes from."""
        if self.conn:
            cur = self.conn.cursor()
            cur.execute("SELECT COUNT(*) FROM custom_data WHERE name = ?", (wpt_id,))
            if cur.fetchone()[0] > 0:
                return "custom"
        if self.nav_conn:
            cur = self.nav_conn.cursor()
            cur.execute("SELECT type FROM navaids WHERE name = ? LIMIT 1", (wpt_id,))
            row = cur.fetchone()
            if row:
                return row[0].lower()
            cur.execute("SELECT type FROM airports WHERE icao = ? LIMIT 1", (wpt_id,))
            row = cur.fetchone()
            if row:
                return "airport"
            cur.execute("SELECT COUNT(*) FROM waypoints WHERE waypoint_identifier = ? LIMIT 1", (wpt_id,))
            if cur.fetchone()[0] > 0:
                return "fix"
        return ""

    # ── Waypoint Search Dialog ───────────────────────────────────────

    def _wpt_search_dialog(self):
        """Search dialog that queries custom_data + nav_data.db. Returns (wpt_id, source) or None."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Buscar Waypoint")
        dlg.geometry("680x420")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(True, True)
        dlg.configure(bg=self.CDU_BG)

        result = [None]

        # Search bar
        search_frame = ttk.Frame(dlg)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Label(search_frame, text="Buscar:").pack(side=tk.LEFT, padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=25, font=self.CDU_FONT)
        search_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_frame, text="Buscar",
                   command=lambda: do_search()).pack(side=tk.LEFT, padx=2)

        # Source filter
        src_var = tk.StringVar(value="Todos")
        ttk.Label(search_frame, text="Fuente:").pack(side=tk.LEFT, padx=(10, 5))
        src_combo = ttk.Combobox(search_frame, textvariable=src_var, width=12, state="readonly",
                                  values=["Todos", "custom_data", "airports", "navaids", "waypoints"])
        src_combo.pack(side=tk.LEFT)

        # Results tree
        cols = ("wpt_id", "name", "source", "lat", "lon")
        res_tree = ttk.Treeview(dlg, columns=cols, show="headings", height=14)
        res_tree.heading("wpt_id", text="ID")
        res_tree.column("wpt_id", width=80)
        res_tree.heading("name", text="Nombre")
        res_tree.column("name", width=250)
        res_tree.heading("source", text="Fuente")
        res_tree.column("source", width=70)
        res_tree.heading("lat", text="Lat")
        res_tree.column("lat", width=80)
        res_tree.heading("lon", text="Lon")
        res_tree.column("lon", width=80)
        res_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        vsb = ttk.Scrollbar(dlg, orient=tk.VERTICAL, command=res_tree.yview)
        res_tree.configure(yscrollcommand=vsb.set)

        # Status label
        status_var = tk.StringVar(value="Escribí un nombre o ICAO y presioná Buscar")
        ttk.Label(dlg, textvariable=status_var, foreground=self.CDU_FG_DIM).pack(padx=10, anchor="w")

        # Buttons
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        def do_select():
            sel = res_tree.selection()
            if sel:
                vals = res_tree.item(sel[0], "values")
                result[0] = (vals[0], vals[2])
                dlg.destroy()

        def do_search():
            query = search_var.get().strip().upper()
            if len(query) < 2:
                status_var.set("Ingresá al menos 2 caracteres")
                return
            source = src_var.get()
            results = self._search_waypoints(query, source)
            res_tree.delete(*res_tree.get_children())
            for r in results:
                res_tree.insert("", tk.END, values=r)
            status_var.set(f"{len(results)} resultados encontrados" +
                           (" (máx 100)" if len(results) >= 100 else ""))

        ttk.Button(btn_frame, text="Seleccionar", command=do_select).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        # Bind enter and double-click
        search_entry.bind("<Return>", lambda e: do_search())
        res_tree.bind("<Double-1>", lambda e: do_select())
        search_entry.focus_set()

        dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.root.wait_window(dlg)
        return result[0]

    def _search_waypoints(self, query, source="Todos", limit=100):
        """Search across custom_data and nav_data.db. Returns list of (id, name, source, lat, lon)."""
        results = []
        like = f"%{query}%"

        # custom_data
        if source in ("Todos", "custom_data") and self.conn:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT name, name, 'custom', lat, lon FROM custom_data WHERE UPPER(name) LIKE ? LIMIT ?",
                (like, limit))
            results.extend(cur.fetchall())

        if not self.nav_conn:
            return results[:limit]

        remaining = limit - len(results)
        if remaining <= 0:
            return results[:limit]

        nav = self.nav_conn.cursor()

        # airports (search by ICAO and also by name via airport_names.db)
        if source in ("Todos", "airports"):
            found_icaos = set()
            if self.names_conn:
                # Search airport_names by ident, icao, name, or municipality
                name_rows = self.names_conn.execute(
                    "SELECT ident, icao FROM airport_names "
                    "WHERE UPPER(ident) LIKE ? OR UPPER(icao) LIKE ? "
                    "OR UPPER(name) LIKE ? OR UPPER(municipality) LIKE ? "
                    "LIMIT ?",
                    (like, like, like, like, remaining * 3)).fetchall()
                # Collect all possible ICAO codes to query nav_data
                for ident, icao_col in name_rows:
                    found_icaos.add(ident)
                    if icao_col:
                        found_icaos.add(icao_col)
            # Also search directly by ICAO in nav_data
            nav.execute(
                "SELECT icao FROM airports WHERE UPPER(icao) LIKE ? LIMIT ?",
                (like, remaining))
            for row in nav.fetchall():
                found_icaos.add(row[0])
            # Now fetch actual airport records from nav_data
            if found_icaos:
                placeholders = ",".join("?" * len(found_icaos))
                nav.execute(
                    f"SELECT icao, icao, 'airport', lat, lon FROM airports "
                    f"WHERE icao IN ({placeholders}) LIMIT ?",
                    (*found_icaos, remaining))
                seen = set()
                for row in nav.fetchall():
                    # Prefer DCS alias code (e.g. URKL instead of RU-0090)
                    display_id = self._get_dcs_alias(row[0]) or row[0]
                    if display_id in seen:
                        continue
                    seen.add(display_id)
                    aname = self._get_airport_name(display_id) or self._get_airport_name(row[0])
                    results.append((display_id, aname or row[1], row[2], row[3], row[4]))
            remaining = limit - len(results)

        # navaids
        if remaining > 0 and source in ("Todos", "navaids"):
            nav.execute(
                "SELECT name, name, 'navaid', lat, lon FROM navaids "
                "WHERE UPPER(name) LIKE ? LIMIT ?",
                (like, remaining))
            results.extend(nav.fetchall())
            remaining = limit - len(results)

        # waypoints/fixes
        if remaining > 0 and source in ("Todos", "waypoints"):
            nav.execute(
                "SELECT waypoint_identifier, waypoint_name, 'fix', "
                "waypoint_latitude, waypoint_longitude FROM waypoints "
                "WHERE UPPER(waypoint_identifier) LIKE ? LIMIT ?",
                (like, remaining))
            results.extend(nav.fetchall())

        return results[:limit]

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
        self._tile_var = tk.StringVar(value="DCS Caucasus")
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
        self.map_widget.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 0))

        # Status bar below map
        self._map_status = ttk.Frame(self.map_frame)
        self._map_status.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._map_lat_lon_var = tk.StringVar(value="---")
        self._map_mgrs_var = tk.StringVar(value="---")
        self._map_elev_var = tk.StringVar(value="---")
        self._map_zoom_var = tk.StringVar(value="Z: 7")
        ttk.Label(self._map_status, textvariable=self._map_lat_lon_var,
                  font=("Consolas", 9), width=32, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_mgrs_var,
                  font=("Consolas", 9), width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_elev_var,
                  font=("Consolas", 9), width=16, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_zoom_var,
                  font=("Consolas", 9), width=6, anchor="w").pack(side=tk.LEFT)

        # Default: Caucasus region (DCS theater)
        self.map_widget.set_tile_server(
            "https://maps.bigbeautifulboards.com/alt-caucasus/{z}/{x}/{y}.png",
            max_zoom=15)
        self.map_widget.set_position(42.0, 43.5)
        self.map_widget.set_zoom(7)

        # Right-click context menu
        self.map_widget.add_right_click_menu_command(
            "Crear waypoint aquí", self._map_create_wpt, pass_coords=True)

        self._map_markers = []
        self._map_route_markers = []
        self._map_route_path = None
        self._wpt_marker_icons = {}  # cache: size -> PhotoImage

        # Bind events on the map's internal canvas
        self.map_widget.canvas.bind("<Motion>", self._on_map_mouse_motion)
        self.map_widget.canvas.bind("<MouseWheel>", self._on_map_zoom_event, add="+")
        self.map_widget.canvas.bind("<ButtonRelease-1>", lambda e: self.root.after(100, self._on_map_zoom), add="+")
        self._last_zoom = self.map_widget.zoom
        self._elev_cache = {}  # (lat_round, lon_round) -> elevation
        self._elev_pending = None  # scheduled after-id for elevation query

    def _make_circle_icon(self, size=10, fill="#33ff33", outline="#1a8c1a"):
        """Create a small circle marker icon as PhotoImage. Cached by size."""
        if size in self._wpt_marker_icons:
            return self._wpt_marker_icons[size]
        dim = size + 2  # padding for outline
        img = tk.PhotoImage(width=dim, height=dim)
        # Draw filled circle with 1px outline
        cx, cy = dim // 2, dim // 2
        r_out = size // 2
        r_in = r_out - 1
        for y in range(dim):
            for x in range(dim):
                dx, dy = x - cx, y - cy
                dist_sq = dx * dx + dy * dy
                if dist_sq <= r_in * r_in:
                    img.put(fill, (x, y))
                elif dist_sq <= r_out * r_out:
                    img.put(outline, (x, y))
        self._wpt_marker_icons[size] = img
        return img

    def _on_map_zoom_event(self, event=None):
        """Called after mouse wheel on map canvas."""
        self.root.after(200, self._on_map_zoom)

    def _on_map_zoom(self):
        """Update marker text visibility based on zoom level."""
        if not hasattr(self, "map_widget"):
            return
        zoom = self.map_widget.zoom
        self._map_zoom_var.set(f"Z: {zoom:.0f}")
        if zoom == self._last_zoom:
            return
        self._last_zoom = zoom
        # At zoom >= 9 show text labels, below that hide them
        for marker in self._map_markers:
            if hasattr(marker, '_orig_text'):
                if zoom >= 9:
                    marker.text = marker._orig_text
                else:
                    marker.text = ""
                marker.draw()

    def _on_map_mouse_motion(self, event):
        """Update status bar with coordinates under mouse cursor."""
        try:
            coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        except Exception:
            return
        lat, lon = coords
        self._map_lat_lon_var.set(f"{dd_to_ddm(lat, True)}  {dd_to_ddm(lon, False)}")
        # MGRS
        if _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
                self._map_mgrs_var.set(mgrs_str)
            except Exception:
                self._map_mgrs_var.set("---")
        # Throttled elevation lookup
        lat_r = round(lat, 3)
        lon_r = round(lon, 3)
        key = (lat_r, lon_r)
        if key in self._elev_cache:
            self._map_elev_var.set(f"Elev: {self._elev_cache[key] * METERS_TO_FEET:.0f} ft")
        else:
            if self._elev_pending:
                self.root.after_cancel(self._elev_pending)
            self._elev_pending = self.root.after(400, self._fetch_elevation, lat_r, lon_r)

    def _fetch_elevation(self, lat, lon):
        """Fetch elevation from Open-Meteo API in background thread."""
        self._elev_pending = None
        key = (lat, lon)
        if key in self._elev_cache:
            self._map_elev_var.set(f"Elev: {self._elev_cache[key] * METERS_TO_FEET:.0f} ft")
            return

        def _worker():
            try:
                url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
                req = urllib.request.Request(url, headers={"User-Agent": "ChanchitaDTC/0.2"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                elev = data["elevation"][0]
                self._elev_cache[key] = elev
                elev_ft = elev * METERS_TO_FEET
                self.root.after(0, lambda: self._map_elev_var.set(f"Elev: {elev_ft:.0f} ft"))
            except Exception:
                self.root.after(0, lambda: self._map_elev_var.set("Elev: ---"))

        threading.Thread(target=_worker, daemon=True).start()

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
        icon = self._make_circle_icon(10, fill="#ff3333", outline="#cc0000")
        zoom = self.map_widget.zoom
        cur = self.conn.cursor()
        cur.execute("SELECT name, lat, lon, alt FROM custom_data WHERE lat IS NOT NULL AND lon IS NOT NULL")
        for name, lat, lon, alt in cur.fetchall():
            if lat == 0 and lon == 0:
                continue
            show_text = name if zoom >= 9 else ""
            marker = self.map_widget.set_marker(
                lat, lon, text=show_text,
                icon=icon,
                text_color="#000000",
                font=("Consolas", 9, "bold"),
                command=lambda m, n=name: self._on_marker_click(n))
            marker._orig_text = name
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
        # MGRS
        mgrs_str = ""
        if _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
        # Elevation from cache or fetch synchronously
        elev_str = ""
        lat_r, lon_r = round(lat, 3), round(lon, 3)
        key = (lat_r, lon_r)
        if key in self._elev_cache:
            elev_str = f"{self._elev_cache[key] * METERS_TO_FEET:.0f}"
        else:
            try:
                url = f"https://api.open-meteo.com/v1/elevation?latitude={lat_r}&longitude={lon_r}"
                req = urllib.request.Request(url, headers={"User-Agent": "ChanchitaDTC/0.2"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read())
                elev_m = data["elevation"][0]
                self._elev_cache[key] = elev_m
                elev_str = f"{elev_m * METERS_TO_FEET:.0f}"
            except Exception:
                pass
        pre = ("", mgrs_str, dd_to_ddm(lat, True), dd_to_ddm(lon, False), elev_str)
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
        self._load_nav_data()
        self.refresh_waypoints()
        self.refresh_routes()

    def _load_airport_names(self):
        """Open airport_names.db (ICAO -> name lookup) bundled with the app."""
        names_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "airport_names.db")
        if os.path.isfile(names_path):
            self.names_conn = sqlite3.connect(names_path)

    def _get_airport_name(self, icao):
        """Look up the human-readable name for an ICAO code."""
        if not self.names_conn:
            return ""
        # Try by ident first (most common match)
        row = self.names_conn.execute(
            "SELECT name FROM airport_names WHERE ident = ? LIMIT 1", (icao,)
        ).fetchone()
        if row:
            return row[0]
        # Fallback: some airports use a different ident but have the icao column
        row = self.names_conn.execute(
            "SELECT name FROM airport_names WHERE icao = ? LIMIT 1", (icao,)
        ).fetchone()
        return row[0] if row else ""

    def _get_dcs_alias(self, airport_ident):
        """Get the DCS ICAO alias for an airport ident (e.g. RU-0090 -> URKL)."""
        if not self.names_conn:
            return None
        try:
            row = self.names_conn.execute(
                "SELECT alias FROM icao_alias WHERE airport_ident = ? LIMIT 1",
                (airport_ident,)
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def _resolve_alias_to_ident(self, alias):
        """Reverse alias lookup: DCS ICAO alias → nav_data airport ident (e.g. UGKS → GE-0010)."""
        if not self.names_conn:
            return None
        try:
            row = self.names_conn.execute(
                "SELECT airport_ident FROM icao_alias WHERE alias = ? LIMIT 1",
                (alias,)
            ).fetchone()
            return row[0] if row else None
        except Exception:
            return None



    def _load_nav_data(self):
        """Detect and open nav_data.db from the C-130J module."""
        if self.nav_conn:
            return  # already connected

        # 1. Check saved config
        saved = _load_navdata_config()
        if saved and os.path.isfile(saved):
            self.nav_conn = sqlite3.connect(saved)
            return

        # 2. Auto-detect
        found = _find_nav_data_db()
        if found:
            path = found[0]
            self.nav_conn = sqlite3.connect(path)
            _save_navdata_config(path)
            return

        # 3. Silently continue without nav_data (still functional)

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
            dlg.configure(bg=self.CDU_BG)

            ttk.Label(dlg, text="Se encontraron varias instalaciones de DCS.C130J.\nSeleccioná cuál usar:",
                      font=self.CDU_FONT).pack(padx=20, pady=(15, 10))

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
        dlg.geometry("540x290")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)

        labels = ["Name:", "MGRS (entry_pos):", "Lat (DDM):", "Lon (DDM):", "Elevación (ft):"]
        entries = []
        for i, lbl in enumerate(labels):
            ttk.Label(dlg, text=lbl, style="TLabel").grid(row=i, column=0, sticky="e", padx=(15, 5), pady=6)
            e = ttk.Entry(dlg, width=32, font=self.CDU_FONT)
            e.grid(row=i, column=1, padx=(0, 10), pady=6)
            if existing and i < len(existing):
                e.insert(0, existing[i])
            entries.append(e)

        # Hint labels (dimmed green, visible on dark bg)
        ttk.Label(dlg, text="N 41° 23.456'", foreground=self.CDU_FG_DIM).grid(row=2, column=2, sticky="w")
        ttk.Label(dlg, text="E 044° 12.345'", foreground=self.CDU_FG_DIM).grid(row=3, column=2, sticky="w")
        ttk.Label(dlg, text="en pies (MSL)", foreground=self.CDU_FG_DIM).grid(row=4, column=2, sticky="w")

        is_edit = existing and not is_duplicate and bool(existing[0])
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

        # Populate raw text fields
        main_raw = data.get("main_pts", "") or ""
        alt_raw = data.get("alt_pts", "") or ""
        self.main_pts_text.delete("1.0", tk.END)
        self.main_pts_text.insert("1.0", main_raw)
        self.alt_pts_text.delete("1.0", tk.END)
        self.alt_pts_text.insert("1.0", alt_raw)

        # Populate waypoint lists from raw text
        self._load_wpt_list_from_raw("main", main_raw)
        self._load_wpt_list_from_raw("alt", alt_raw)

    def add_route(self):
        if not self._ensure_db():
            return
        for var in self.route_vars.values():
            var.set("")
        self.main_pts_text.delete("1.0", tk.END)
        self.alt_pts_text.delete("1.0", tk.END)
        self._main_wpt_tree.delete(*self._main_wpt_tree.get_children())
        self._alt_wpt_tree.delete(*self._alt_wpt_tree.get_children())
        self.route_tree.selection_remove(*self.route_tree.selection())

    def save_route(self):
        if not self._ensure_db():
            return
        name = self.route_vars["name"].get().strip()
        if not name:
            messagebox.showwarning("Error", "El nombre de la ruta es obligatorio")
            return

        # Sync lists → raw text before saving
        self._sync_list_to_raw("main")
        self._sync_list_to_raw("alt")

        # ── Origin / Destination auto-sync ──────────────────────────
        tree = self._main_wpt_tree
        items = tree.get_children()
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()

        if origin:
            # Insert origin as first waypoint if not already there
            first_id = tree.item(items[0], "values")[1] if items else None
            if first_id != origin:
                native = self._build_native_wpt_for_id(origin)
                source = self._identify_wpt_source(origin)
                nombre = self._get_airport_name(origin) if source == "airport" else ""
                tree.insert("", 0, values=(0, origin, nombre, source, native))
                self._renumber_wpt_list("main")
                items = tree.get_children()
        else:
            # No origin specified → use first waypoint
            if items:
                origin = tree.item(items[0], "values")[1]
                self.route_vars["origin"].set(origin)

        if dest:
            # Insert dest as last waypoint if not already there
            last_id = tree.item(items[-1], "values")[1] if items else None
            if last_id != dest:
                native = self._build_native_wpt_for_id(dest)
                source = self._identify_wpt_source(dest)
                nombre = self._get_airport_name(dest) if source == "airport" else ""
                seq = len(tree.get_children()) + 1
                tree.insert("", tk.END, values=(seq, dest, nombre, source, native))
                items = tree.get_children()
        else:
            # No dest specified → use last waypoint
            if items:
                dest = tree.item(items[-1], "values")[1]
                self.route_vars["dest"].set(dest)

        # Re-sync after possible insertions (updates type flags)
        self._sync_list_to_raw("main")

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

    def clone_route(self):
        if not self._ensure_db():
            return
        sel = self.route_tree.selection()
        if not sel:
            messagebox.showwarning("Error", "Selecciona una ruta para clonar")
            return
        src_name = self.route_tree.item(sel[0], "values")[0]
        new_name = simpledialog.askstring(
            "Clonar Ruta", f"Nombre para la copia de '{src_name}':",
            parent=self.root)
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()[:10]
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM routes WHERE name = ?", (new_name,))
        if cur.fetchone()[0] > 0:
            messagebox.showwarning("Error", f"Ya existe una ruta '{new_name}'")
            return
        cur.execute("SELECT * FROM routes WHERE name = ?", (src_name,))
        row = cur.fetchone()
        if not row:
            return
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))
        data["name"] = new_name
        self.conn.execute(
            """INSERT INTO routes (name, wpt_trans, main_pts, alt_pts, origin, dest, alt,
               rwy_dep, rwy_arr, rwy_dep_return, rwy_alt, rwy_dep_sid, rwy_arr_star,
               rwy_alt_star, rwy_dep_return_star, rwy_dep_trans, rwy_arr_trans)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(data[c] for c in cols),
        )
        self.conn.commit()
        self.refresh_routes()

    def show_route_on_map(self):
        if not hasattr(self, "map_widget"):
            messagebox.showwarning("Error", "El mapa no está disponible")
            return
        tree = self._main_wpt_tree
        items = tree.get_children()
        if not items:
            messagebox.showwarning("Error", "No hay waypoints en la ruta")
            return
        # Clear previous route overlay
        self._clear_route_overlay()
        # Collect coordinates from native tuples
        coords = []
        icon = self._make_circle_icon(10, fill="#3399ff", outline="#0055cc")
        zoom = self.map_widget.zoom
        for item in items:
            vals = tree.item(item, "values")
            wpt_id = vals[1]
            native = vals[4] if len(vals) > 4 else None
            lat, lon = None, None
            if native and native.startswith("("):
                fields = native.strip("()").split("|")
                try:
                    lat = float(fields[2])
                    lon = float(fields[3])
                except (IndexError, ValueError):
                    pass
            if lat is None or lon is None:
                lat, lon, _ = self._lookup_wpt_coords(wpt_id)
            if lat is not None and lon is not None and not (lat == 0 and lon == 0):
                coords.append((lat, lon))
                show_text = wpt_id if zoom >= 7 else ""
                marker = self.map_widget.set_marker(
                    lat, lon, text=show_text,
                    icon=icon,
                    text_color="#000000",
                    font=("Consolas", 9, "bold"))
                marker._orig_text = wpt_id
                self._map_route_markers.append(marker)
        if len(coords) >= 2:
            self._map_route_path = self.map_widget.set_path(
                coords, color="#3399ff", width=3)
        # Switch to map tab and fit view
        self.notebook.select(self.map_frame)
        if coords:
            lats = [c[0] for c in coords]
            lons = [c[1] for c in coords]
            center_lat = (min(lats) + max(lats)) / 2
            center_lon = (min(lons) + max(lons)) / 2
            self.map_widget.set_position(center_lat, center_lon)
            if len(coords) >= 2:
                self.map_widget.set_zoom(8)

    def _clear_route_overlay(self):
        if hasattr(self, "_map_route_path") and self._map_route_path:
            self._map_route_path.delete()
            self._map_route_path = None
        if hasattr(self, "_map_route_markers"):
            for m in self._map_route_markers:
                m.delete()
            self._map_route_markers.clear()

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
        dlg.configure(bg=self.CDU_BG)

        result = tk.StringVar(value="skip")

        ttk.Label(dlg, text=f"⚠  {tipo} '{name}' ya existe",
                  font=self.CDU_FONT_HDR, foreground=self.CDU_AMBER).pack(padx=20, pady=(18, 5))
        ttk.Label(dlg, text="¿Qué querés hacer?",
                  font=self.CDU_FONT_SM).pack(padx=20, pady=(0, 12))

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
