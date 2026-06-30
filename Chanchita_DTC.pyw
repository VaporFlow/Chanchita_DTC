import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import json
import math
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


def true_bearing_deg(lat1, lon1, lat2, lon2):
    """Initial true bearing from point 1 to point 2, degrees 0–360."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def haversine_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance in nautical miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 3440.065 * 2 * math.asin(math.sqrt(a))


def format_duration_hours(hours):
    """Format fractional hours as HH:MM."""
    if hours is None or hours < 0:
        return "—"
    if hours < 1 / 120:
        return "00:00"
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h += 1
        m = 0
    return f"{h:02d}:{m:02d}"


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
DCS_OLYMPUS_MAPS = "https://maps.dcsolympus.com/maps"

# ── Internationalisation ─────────────────────────────────────────

_LANG = "es"  # default language

STRINGS = {
    # ── Menus ──
    "menu_load_dtc":        {"es": "Cargar DTC",              "en": "Load DTC"},
    "menu_save":            {"es": "Guardar",                 "en": "Save"},
    "menu_open_db":         {"es": "Abrir BD...",             "en": "Open DB..."},
    "menu_save_as":         {"es": "Guardar como...",         "en": "Save As..."},
    "menu_config_dcs":      {"es": "Configurar ruta DCS...",  "en": "Configure DCS path..."},
    "menu_exit":            {"es": "Salir",                   "en": "Exit"},
    "menu_file":            {"es": "Archivo",                 "en": "File"},
    "menu_import_wpt_csv":  {"es": "Importar Waypoints CSV...", "en": "Import Waypoints CSV..."},
    "menu_import_rte_csv":  {"es": "Importar Routes CSV...",    "en": "Import Routes CSV..."},
    "menu_export_wpt_csv":  {"es": "Exportar Waypoints CSV...", "en": "Export Waypoints CSV..."},
    "menu_export_rte_csv":  {"es": "Exportar Routes CSV...",    "en": "Export Routes CSV..."},
    "menu_import_export":   {"es": "Importar/Exportar",        "en": "Import/Export"},
    "menu_export_dtc":      {"es": "Exportar paquete .dtc...",  "en": "Export .dtc package..."},
    "menu_import_dtc":      {"es": "Importar paquete .dtc...",  "en": "Import .dtc package..."},
    "menu_dtc_pkg":         {"es": "Paquete DTC",              "en": "DTC Package"},
    # ── Tabs ──
    "tab_waypoints":        {"es": " Waypoints (custom_data) ", "en": " Waypoints (custom_data) "},
    "tab_routes":           {"es": " Routes ",                   "en": " Routes "},
    "tab_map":              {"es": " Mapa ",                     "en": " Map "},
    # ── Waypoint toolbar ──
    "btn_add":              {"es": "+ Agregar",   "en": "+ Add"},
    "btn_edit":             {"es": "Editar",      "en": "Edit"},
    "btn_delete":           {"es": "Eliminar",    "en": "Delete"},
    "btn_duplicate":        {"es": "Duplicar",    "en": "Duplicate"},
    "btn_delete_all":       {"es": "Eliminar todo", "en": "Delete All"},
    # ── Route toolbar ──
    "btn_new_route":        {"es": "+ Nueva",        "en": "+ New"},
    "btn_save_route":       {"es": "💾 Guardar",    "en": "💾 Save"},
    "btn_delete_route":     {"es": "Eliminar",       "en": "Delete"},
    "btn_clone":            {"es": "Clonar",         "en": "Clone"},
    "btn_back_route":       {"es": "Ruta inversa",   "en": "Back Route"},
    "btn_show_map":         {"es": "🗺 Ver en Mapa", "en": "🗺 Show on Map"},
    "msg_route_no_wpts":    {"es": "No hay waypoints en Main Points para invertir.",
                            "en": "No waypoints in Main Points to reverse."},
    "btn_fp_calc":          {"es": "Calcular", "en": "Calculate"},
    "lbl_fp_speed":         {"es": "Velocidad:", "en": "Speed:"},
    "lbl_fp_kts":           {"es": "kts", "en": "kts"},
    "lbl_fp_alt":           {"es": "Altitud:", "en": "Altitude:"},
    "lbl_fp_ft":            {"es": "ft", "en": "ft"},
    "lbl_fp_ff":            {"es": "Flujo combustible:", "en": "Fuel flow:"},
    "lbl_fp_lbs_hr":        {"es": "lbs/hr", "en": "lbs/hr"},
    "lbl_fp_total_dist":    {"es": "Distancia total:", "en": "Total distance:"},
    "lbl_fp_total_time":    {"es": "Tiempo total:", "en": "Total time:"},
    "lbl_fp_total_fuel":    {"es": "Combustible total:", "en": "Total fuel:"},
    "lbl_fp_legs":          {"es": "Tramos", "en": "Legs"},
    "hd_fp_from":           {"es": "Desde", "en": "From"},
    "hd_fp_to":             {"es": "Hasta", "en": "To"},
    "hd_fp_dist":           {"es": "NM", "en": "NM"},
    "hd_fp_time":           {"es": "Tiempo", "en": "Time"},
    "hd_fp_fuel":           {"es": "Comb. (lbs)", "en": "Fuel (lbs)"},
    "msg_fp_need_wpts":     {"es": "Agregá al menos 2 waypoints en Main Points.",
                            "en": "Add at least 2 waypoints in Main Points."},
    "msg_fp_bad_speed":     {"es": "Ingresá una velocidad válida en kts (> 0).",
                            "en": "Enter a valid speed in kts (> 0)."},
    "msg_fp_bad_ff":        {"es": "Ingresá un flujo de combustible válido (lbs/hr ≥ 0).",
                            "en": "Enter a valid fuel flow (lbs/hr ≥ 0)."},
    # ── Wpt list (main/alt pts) ──
    "btn_list_add":         {"es": "+ Agregar",  "en": "+ Add"},
    "btn_list_remove":      {"es": "Quitar",     "en": "Remove"},
    # ── Search dialog ──
    "btn_search":           {"es": "Buscar",      "en": "Search"},
    "btn_goto_map":         {"es": "Ir al punto", "en": "Go to"},
    "msg_no_coords_map":    {"es": "Sin coordenadas para '{id}'", "en": "No coordinates for '{id}'"},
    "btn_select":           {"es": "Seleccionar", "en": "Select"},
    "btn_cancel":           {"es": "Cancelar",    "en": "Cancel"},
    "lbl_search":           {"es": "Buscar:",     "en": "Search:"},
    "lbl_source":           {"es": "Fuente:",     "en": "Source:"},
    "dlg_search_wpt":       {"es": "Buscar Waypoint", "en": "Search Waypoint"},
    # ── Map toolbar ──
    "btn_refresh":          {"es": "Actualizar",       "en": "Refresh"},
    "btn_center_wpts":      {"es": "Centrar en WPTs",  "en": "Center on WPTs"},
    "btn_load_mbtiles":     {"es": "Cargar MBTiles...", "en": "Load MBTiles..."},
    "lbl_tiles":            {"es": "Tiles:",            "en": "Tiles:"},
    "map_create_wpt":       {"es": "Crear waypoint aquí", "en": "Create waypoint here"},
    "map_loading":          {"es": "Cargando mapa…", "en": "Loading map…"},
    "map_ruler_hint":       {"es": "Regla: clic medio = origen", "en": "Ruler: middle-click = origin"},
    "map_ruler_clear":      {"es": "Regla: —", "en": "Ruler: —"},
    "map_ruler_fmt":        {"es": "Regla: M{brg:03.0f}°  {dist:.1f} NM",
                            "en": "Ruler: M{brg:03.0f}°  {dist:.1f} NM"},
    "map_ruler_fmt_true":   {"es": "Regla: T{brg:03.0f}°  {dist:.1f} NM",
                            "en": "Ruler: T{brg:03.0f}°  {dist:.1f} NM"},
    "map_show_fixes":       {"es": "Fixes", "en": "Fixes"},
    "dlg_fix":              {"es": "Fix — {id}", "en": "Fix — {id}"},
    "lbl_fix_name":         {"es": "Nombre:", "en": "Name:"},
    "btn_copy_fix":         {"es": "Copiar ID", "en": "Copy ID"},
    "msg_fix_copied":       {"es": "ID copiado: {id}", "en": "ID copied: {id}"},
    "msg_fix_added_route":  {"es": "'{id}' agregado a la ruta", "en": "'{id}' added to route"},
    "dlg_custom_wpt":       {"es": "Waypoint — {id}", "en": "Waypoint — {id}"},
    "lbl_wpt_elev_ft":      {"es": "Elevación (ft):", "en": "Elevation (ft):"},
    # ── Waypoint edit dialog ──
    "btn_save":             {"es": "Guardar",     "en": "Save"},
    "btn_save_add_route":   {"es": "Guardar y agregar a ruta", "en": "Save and add to route"},
    "dlg_new_wpt":          {"es": "Nuevo Waypoint",  "en": "New Waypoint"},
    "dlg_edit_wpt":         {"es": "Editar Waypoint", "en": "Edit Waypoint"},
    "lbl_wpt_name":         {"es": "Name:",                "en": "Name:"},
    "lbl_wpt_mgrs":         {"es": "MGRS (entry_pos):",    "en": "MGRS (entry_pos):"},
    "lbl_wpt_lat":          {"es": "Lat (DDM):",           "en": "Lat (DDM):"},
    "lbl_wpt_lon":          {"es": "Lon (DDM):",           "en": "Lon (DDM):"},
    "lbl_wpt_elev":         {"es": "Elevación (ft):",      "en": "Elevation (ft):"},
    "hint_lat":             {"es": "N 41° 23.456'",   "en": "N 41° 23.456'"},
    "hint_lon":             {"es": "E 044° 12.345'",  "en": "E 044° 12.345'"},
    "hint_elev":            {"es": "en pies (MSL)",    "en": "in feet (MSL)"},
    # ── Conflict dialog ──
    "btn_rename_imported":  {"es": "📝 Renombrar el importado",          "en": "📝 Rename imported"},
    "btn_rename_existing":  {"es": "📝 Renombrar el existente",          "en": "📝 Rename existing"},
    "btn_overwrite":        {"es": "⚡ Sobrescribir con el importado",   "en": "⚡ Overwrite with imported"},
    "btn_skip":             {"es": "⏭  Omitir (no importar)",            "en": "⏭  Skip (don't import)"},
    "lbl_conflict":         {"es": "¿Qué querés hacer?",    "en": "What do you want to do?"},
    "dlg_conflict":         {"es": "Conflicto — {tipo}",    "en": "Conflict — {tipo}"},
    # ── Route field labels ──
    "fld_nombre":           {"es": "Nombre",       "en": "Name"},
    "fld_origen":           {"es": "Origen",       "en": "Origin"},
    "fld_destino":          {"es": "Destino",      "en": "Destination"},
    "fld_alternativa":      {"es": "Alternativa",  "en": "Alternate"},
    "fld_wpt_trans":        {"es": "WPT Trans",    "en": "WPT Trans"},
    "fld_rwy_dep":          {"es": "RWY Dep",      "en": "RWY Dep"},
    "fld_rwy_arr":          {"es": "RWY Arr",      "en": "RWY Arr"},
    "fld_rwy_dep_ret":      {"es": "RWY Dep Ret",  "en": "RWY Dep Ret"},
    "fld_rwy_alt":          {"es": "RWY Alt",      "en": "RWY Alt"},
    "fld_sid":              {"es": "SID",           "en": "SID"},
    "fld_star_arr":         {"es": "STAR Arr",      "en": "STAR Arr"},
    "fld_star_alt":         {"es": "STAR Alt",      "en": "STAR Alt"},
    "fld_star_dep_ret":     {"es": "STAR Dep Ret",  "en": "STAR Dep Ret"},
    "fld_trans_dep":        {"es": "Trans Dep",     "en": "Trans Dep"},
    "fld_trans_arr":        {"es": "Trans Arr",     "en": "Trans Arr"},
    # ── LabelFrames ──
    "lf_route_data":        {"es": "Datos de la Ruta",   "en": "Route Data"},
    "lf_main_pts":          {"es": "Main Points (main_pts)", "en": "Main Points (main_pts)"},
    "lf_flight_plan":       {"es": "Calculadora de plan de vuelo", "en": "Flight Plan Calculator"},
    "lf_alt_pts":           {"es": "Alt Points (alt_pts)",   "en": "Alt Points (alt_pts)"},
    "lf_raw_edit":          {"es": "Edición manual (pipe-delimited)", "en": "Manual editing (pipe-delimited)"},
    "chk_show_raw":         {"es": "Mostrar campos de texto raw", "en": "Show raw text fields"},
    # ── Table headings ──
    "hd_name":              {"es": "Name",      "en": "Name"},
    "hd_mgrs":              {"es": "MGRS",      "en": "MGRS"},
    "hd_lat_ddm":           {"es": "Lat (DDM)", "en": "Lat (DDM)"},
    "hd_lon_ddm":           {"es": "Lon (DDM)", "en": "Lon (DDM)"},
    "hd_elev":              {"es": "Elev (ft)", "en": "Elev (ft)"},
    "hd_origin":            {"es": "Origin",    "en": "Origin"},
    "hd_dest":              {"es": "Dest",      "en": "Dest"},
    "hd_waypoint":          {"es": "Waypoint",  "en": "Waypoint"},
    "hd_nombre":            {"es": "Nombre",    "en": "Name"},
    "hd_fuente":            {"es": "Fuente",    "en": "Source"},
    "hd_id":                {"es": "ID",        "en": "ID"},
    "hd_lat":               {"es": "Lat",       "en": "Lat"},
    "hd_lon":               {"es": "Lon",       "en": "Lon"},
    # ── Status bar / misc labels ──
    "lbl_no_db":            {"es": "Sin BD cargada",  "en": "No DB loaded"},
    "lbl_wpts_loaded":      {"es": "{n} waypoints cargados — {f}", "en": "{n} waypoints loaded — {f}"},
    # ── Messageboxes ──
    "ttl_error":            {"es": "Error",      "en": "Error"},
    "ttl_confirm":          {"es": "Confirmar",  "en": "Confirm"},
    "ttl_warning":          {"es": "Aviso",      "en": "Warning"},
    "ttl_saved":            {"es": "Guardado",   "en": "Saved"},
    "ttl_exported":         {"es": "Exportado",  "en": "Exported"},
    "ttl_import_done":      {"es": "Importación completa", "en": "Import complete"},
    "ttl_dcs_not_found":    {"es": "DCS.C130J no encontrado", "en": "DCS.C130J not found"},
    "ttl_mgrs_invalid":     {"es": "MGRS inválido", "en": "Invalid MGRS"},
    "ttl_mgrs_conv":        {"es": "Conversión MGRS", "en": "MGRS Conversion"},
    "msg_route_name_required": {"es": "El nombre de la ruta es obligatorio", "en": "Route name is required"},
    "msg_name_required":    {"es": "El nombre es obligatorio", "en": "Name is required"},
    "msg_load_db_first":    {"es": "Primero cargá la BD\n(Archivo → Cargar DTC)", "en": "Load the DB first\n(File → Load DTC)"},
    "msg_select_wpt":       {"es": "Seleccioná un waypoint primero", "en": "Select a waypoint first"},
    "msg_saved_to":         {"es": "Guardado en:\n{path}", "en": "Saved to:\n{path}"},
    "msg_path_set":         {"es": "Ruta configurada:\n{path}", "en": "Path configured:\n{path}"},
    "msg_route_saved":      {"es": "Ruta '{name}' guardada", "en": "Route '{name}' saved"},
    "msg_confirm_del_wpt":  {"es": "¿Eliminar waypoint '{name}'?", "en": "Delete waypoint '{name}'?"},
    "msg_confirm_del_wpts": {"es": "¿Eliminar {n} waypoints?\n{names}",
                            "en": "Delete {n} waypoints?\n{names}"},
    "msg_confirm_del_all_wpt": {"es": "¿Eliminar los {n} waypoints?\nNo se puede deshacer.",
                                "en": "Delete all {n} waypoints?\nThis cannot be undone."},
    "msg_del_all_routes_warn": {"es": "\n\nLas rutas no se eliminan pero pueden referenciar waypoints inexistentes.",
                                "en": "\n\nRoutes are not deleted but may reference missing waypoints."},
    "msg_no_wpts":          {"es": "No hay waypoints para eliminar", "en": "No waypoints to delete"},
    "msg_confirm_del_rte":  {"es": "¿Eliminar ruta '{name}'?", "en": "Delete route '{name}'?"},
    "msg_confirm_del_rtes": {"es": "¿Eliminar {n} rutas?\n{names}",
                            "en": "Delete {n} routes?\n{names}"},
    "msg_clone_prompt":     {"es": "Nombre para la copia de '{name}':", "en": "Name for copy of '{name}':"},
    "dlg_clone_route":      {"es": "Clonar Ruta", "en": "Clone Route"},
    "msg_route_exists":     {"es": "Ya existe una ruta '{name}'", "en": "Route '{name}' already exists"},
    "msg_select_route_clone": {"es": "Seleccioná una ruta para clonar", "en": "Select a route to clone"},
    "msg_map_unavailable":  {"es": "El mapa no está disponible", "en": "Map is not available"},
    "msg_no_wpts_route":    {"es": "No hay waypoints en la ruta", "en": "No waypoints in route"},
    "msg_wpt_exists":       {"es": "Ya existe un waypoint con nombre '{name}'", "en": "A waypoint named '{name}' already exists"},
    "msg_wpt_overwrite":    {"es": "Ya existe un waypoint con nombre '{name}'.\n¿Querés sobreescribirlo?", "en": "A waypoint named '{name}' already exists.\nDo you want to overwrite it?"},
    "msg_invalid_elev":     {"es": "Elevación inválida: '{val}'", "en": "Invalid elevation: '{val}'"},
    "msg_invalid_value":    {"es": "Valor inválido:\n{err}", "en": "Invalid value:\n{err}"},
    "msg_mgrs_invalid":     {"es": "El MGRS '{mgrs}' tiene un número impar de dígitos u otro error de formato.\nVerificá que la coordenada sea correcta.",
                             "en": "The MGRS '{mgrs}' has an odd digit count or format error.\nPlease check the coordinate."},
    "msg_mgrs_conv_fail":   {"es": "La librería no pudo convertir este MGRS a lat/lon.\nIngresá lat/lon manualmente (copiá del CDU de DCS).",
                             "en": "The library could not convert this MGRS to lat/lon.\nEnter lat/lon manually (copy from DCS CDU)."},
    "msg_tiles_loaded":     {"es": "Tiles cargados:\n{name}", "en": "Tiles loaded:\n{name}"},
    "msg_tiles_error":      {"es": "No se pudo iniciar el servidor de tiles.\nEl puerto puede estar en uso.",
                             "en": "Could not start tile server.\nThe port may be in use."},
    "msg_dcs_not_found":    {"es": "No se encontró la carpeta DCS.C130J automáticamente.\nSeleccioná manualmente el archivo user_data.db",
                             "en": "DCS.C130J folder not found automatically.\nSelect user_data.db manually"},
    "msg_select_export":    {"es": "Seleccioná al menos un waypoint o una ruta para exportar.\n(Usá Ctrl+Click o Shift+Click para selección múltiple)",
                             "en": "Select at least one waypoint or route to export.\n(Use Ctrl+Click or Shift+Click for multiple selection)"},
    "msg_dtc_exported":     {"es": "Paquete DTC guardado:\n{name}\n\n• {wpts} waypoint(s)\n• {routes} ruta(s)",
                             "en": "DTC package saved:\n{name}\n\n• {wpts} waypoint(s)\n• {routes} route(s)"},
    "msg_import_summary":   {"es": "Waypoints: {wi} importados, {ws} omitidos\nRutas: {ri} importadas, {rs} omitidas",
                             "en": "Waypoints: {wi} imported, {ws} skipped\nRoutes: {ri} imported, {rs} skipped"},
    "msg_invalid_dtc":      {"es": "El archivo no es un paquete DTC válido.", "en": "The file is not a valid DTC package."},
    "msg_wpts_imported":    {"es": "{n} waypoints importados", "en": "{n} waypoints imported"},
    "msg_routes_imported":  {"es": "{n} rutas importadas", "en": "{n} routes imported"},
    "msg_wpts_exported":    {"es": "Waypoints exportados a:\n{path}", "en": "Waypoints exported to:\n{path}"},
    "msg_routes_exported":  {"es": "Rutas exportadas a:\n{path}", "en": "Routes exported to:\n{path}"},
    "msg_conflict_exists":  {"es": "⚠  {tipo} '{name}' ya existe", "en": "⚠  {tipo} '{name}' already exists"},
    "msg_conflict_action":  {"es": "¿Qué querés hacer?", "en": "What do you want to do?"},
    "msg_min_chars":        {"es": "Ingresá al menos 2 caracteres", "en": "Enter at least 2 characters"},
    "msg_search_hint":      {"es": "Escribí un nombre o ICAO y presioná Buscar", "en": "Type a name or ICAO and press Search"},
    "msg_results":          {"es": "{n} resultados encontrados", "en": "{n} results found"},
    "msg_max_100":          {"es": " (máx 100)", "en": " (max 100)"},
    # ── File dialogs ──
    "dlg_select_db":        {"es": "Seleccionar user_data.db de DCS.C130J", "en": "Select DCS.C130J user_data.db"},
    "dlg_export_dtc":       {"es": "Exportar paquete DTC", "en": "Export DTC package"},
    "dlg_import_dtc":       {"es": "Importar paquete DTC", "en": "Import DTC package"},
    "dlg_conflict":         {"es": "Conflicto — {tipo}", "en": "Conflict — {tipo}"},
    "ft_sqlite":            {"es": "SQLite DB",     "en": "SQLite DB"},
    "ft_all":               {"es": "Todos",         "en": "All files"},
    "ft_dtc":               {"es": "Paquete DTC",   "en": "DTC Package"},
    "src_all":              {"es": "Todos",          "en": "All"},
    # ── DCS multi-path dialog ──
    "lbl_dcs_multi":        {"es": "Se encontraron varias instalaciones de DCS.C130J.\nSeleccioná cuál usar:",
                             "en": "Multiple DCS.C130J installations found.\nSelect which to use:"},
    "btn_accept":           {"es": "Aceptar", "en": "OK"},
    # ── Rename dialogs ──
    "dlg_rename_imported":  {"es": "Renombrar importado", "en": "Rename imported"},
    "dlg_rename_existing":  {"es": "Renombrar existente", "en": "Rename existing"},
    "msg_rename_imported":  {"es": "Nuevo nombre para el {tipo} que estás importando:",
                             "en": "New name for the {tipo} you are importing:"},
    "msg_rename_existing":  {"es": "Nuevo nombre para el {tipo} que ya tenés guardado:",
                             "en": "New name for the {tipo} you already have:"},
    # ── Map tile names ──
    "tile_mbtiles":         {"es": "MBTiles (local)", "en": "MBTiles (local)"},
    "tile_google_sat":      {"es": "Google Satélite", "en": "Google Satellite"},
    "tile_arcgis_sat":      {"es": "ArcGIS Satélite", "en": "ArcGIS Satellite"},
    # ── MBTiles dialog ──
    "dlg_select_mbtiles":   {"es": "Seleccionar archivo MBTiles", "en": "Select MBTiles file"},
    # ── Airport map popup ──
    "dlg_airport":          {"es": "Aeropuerto — {icao}", "en": "Airport — {icao}"},
    "lbl_apt_icao":         {"es": "ICAO:",         "en": "ICAO:"},
    "lbl_apt_alias":        {"es": "Alias DCS:",    "en": "DCS alias:"},
    "lbl_apt_name":         {"es": "Nombre:",       "en": "Name:"},
    "lbl_apt_municipality": {"es": "Municipio:",    "en": "Municipality:"},
    "lbl_apt_type":         {"es": "Tipo:",         "en": "Type:"},
    "lbl_apt_coords":       {"es": "Coordenadas:",  "en": "Coordinates:"},
    "lbl_apt_mgrs":         {"es": "MGRS:",         "en": "MGRS:"},
    "lbl_apt_elev":         {"es": "Elevación:",    "en": "Elevation:"},
    "btn_copy_icao":        {"es": "Copiar ICAO",   "en": "Copy ICAO"},
    "btn_add_to_route":     {"es": "Agregar a ruta", "en": "Add to route"},
    "btn_set_origin":       {"es": "Establecer como Origen", "en": "Set as Origin"},
    "btn_set_dest":         {"es": "Establecer como Destino", "en": "Set as Destination"},
    "btn_coord_search":     {"es": "Buscar coordenadas", "en": "Coordinates search"},
    "dlg_coord_search":     {"es": "Buscar por coordenadas", "en": "Search by coordinates"},
    "lbl_coord_lat":        {"es": "Lat (DDM o decimal):", "en": "Lat (DDM or decimal):"},
    "lbl_coord_lon":        {"es": "Lon (DDM o decimal):", "en": "Lon (DDM or decimal):"},
    "lbl_coord_mgrs":       {"es": "MGRS (opcional):", "en": "MGRS (optional):"},
    "btn_coord_go":         {"es": "Ir", "en": "Go"},
    "dlg_coord_confirm":    {"es": "Confirmar ubicación", "en": "Confirm location"},
    "msg_coord_confirm":    {"es": "¿Es esta la ubicación correcta?", "en": "Is this the correct location?"},
    "btn_confirm":          {"es": "Confirmar", "en": "Confirm"},
    "dlg_coord_action":     {"es": "¿Qué querés hacer?", "en": "What do you want to do?"},
    "btn_add_as_wpt":       {"es": "Agregar como waypoint", "en": "Add as waypoint"},
    "btn_add_as_route_wpt": {"es": "Agregar como waypoint de ruta", "en": "Add as route waypoint"},
    "msg_coord_invalid":    {"es": "Ingresá coordenadas válidas (lat/lon o MGRS).",
                            "en": "Enter valid coordinates (lat/lon or MGRS)."},
    "msg_icao_copied":      {"es": "ICAO copiado: {icao}", "en": "ICAO copied: {icao}"},
    "msg_apt_added_route":  {"es": "'{icao}' agregado a la ruta", "en": "'{icao}' added to route"},
    "msg_apt_set_origin":   {"es": "Origen: {icao}", "en": "Origin set: {icao}"},
    "msg_apt_set_dest":     {"es": "Destino: {icao}", "en": "Destination set: {icao}"},
    # ── Language picker ──
}


def _t(key, **kwargs):
    """Translate a string key to the current language."""
    s = STRINGS.get(key, {}).get(_LANG) or STRINGS.get(key, {}).get("es", key)
    if kwargs:
        s = s.format(**kwargs)
    return s


def _load_lang_config():
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("ui", "language", fallback="")


def _save_lang_config(lang):
    cfg = configparser.ConfigParser()
    if os.path.isfile(CONFIG_FILE):
        cfg.read(CONFIG_FILE, encoding="utf-8")
    if not cfg.has_section("ui"):
        cfg.add_section("ui")
    cfg.set("ui", "language", lang)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)


def _ask_language(root):
    """Show a first-run language picker dialog. Returns 'es' or 'en'."""
    result = ["es"]
    dlg = tk.Toplevel(root)
    dlg.title("Idioma / Language")
    dlg.geometry("320x150")
    dlg.transient(root)
    dlg.grab_set()
    dlg.resizable(False, False)
    dlg.configure(bg="#0a0a0a")
    ttk.Label(dlg, text="Seleccioná tu idioma\nSelect your language",
              font=("Consolas", 11), anchor="center", justify="center").pack(pady=(20, 15))
    bf = ttk.Frame(dlg)
    bf.pack()
    def pick(lang):
        result[0] = lang
        dlg.destroy()
    ttk.Button(bf, text="Español", width=12, command=lambda: pick("es")).pack(side=tk.LEFT, padx=10)
    ttk.Button(bf, text="English", width=12, command=lambda: pick("en")).pack(side=tk.LEFT, padx=10)
    dlg.protocol("WM_DELETE_WINDOW", lambda: pick("es"))
    root.wait_window(dlg)
    return result[0]


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
        self.version = "Alpha 0.2l (260627)"

        # ── Language selection ──
        global _LANG
        saved_lang = _load_lang_config()
        if saved_lang in ("es", "en"):
            _LANG = saved_lang
        else:
            _LANG = _ask_language(root)
            _save_lang_config(_LANG)

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
        file_menu.add_command(label=_t("menu_load_dtc"), command=self.load_dcs_dtc, accelerator="Ctrl+L")
        file_menu.add_command(label=_t("menu_save"), command=self.save_dcs_dtc, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label=_t("menu_open_db"), command=self.open_db, accelerator="Ctrl+O")
        file_menu.add_command(label=_t("menu_save_as"), command=self.save_db_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label=_t("menu_config_dcs"), command=self.configure_dcs_path)
        file_menu.add_separator()
        file_menu.add_command(label=_t("menu_exit"), command=self.root.quit)
        menubar.add_cascade(label=_t("menu_file"), menu=file_menu)

        imp_menu = tk.Menu(menubar, tearoff=0, **menu_kw)
        imp_menu.add_command(label=_t("menu_import_wpt_csv"), command=self.import_waypoints_csv)
        imp_menu.add_command(label=_t("menu_import_rte_csv"), command=self.import_routes_csv)
        imp_menu.add_separator()
        imp_menu.add_command(label=_t("menu_export_wpt_csv"), command=self.export_waypoints_csv)
        imp_menu.add_command(label=_t("menu_export_rte_csv"), command=self.export_routes_csv)
        menubar.add_cascade(label=_t("menu_import_export"), menu=imp_menu)

        dtc_menu = tk.Menu(menubar, tearoff=0, **menu_kw)
        dtc_menu.add_command(label=_t("menu_export_dtc"), command=self.export_dtc, accelerator="Ctrl+E")
        dtc_menu.add_command(label=_t("menu_import_dtc"), command=self.import_dtc, accelerator="Ctrl+I")
        menubar.add_cascade(label=_t("menu_dtc_pkg"), menu=dtc_menu)

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
        self.notebook.add(self.wpt_frame, text=_t("tab_waypoints"))
        self._build_waypoints_tab()

        self.route_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.route_frame, text=_t("tab_routes"))
        self._build_routes_tab()

        if _HAS_MAPVIEW:
            self.map_frame = ttk.Frame(self.notebook)
            self.notebook.add(self.map_frame, text=_t("tab_map"))
            self._build_map_tab()

    # ── Waypoints tab ────────────────────────────────────────────────

    def _build_waypoints_tab(self):
        toolbar = ttk.Frame(self.wpt_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(toolbar, text=_t("btn_add"), command=self.add_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_edit"), command=self.edit_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_delete"), command=self.delete_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_duplicate"), command=self.duplicate_waypoint).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=2)
        ttk.Button(toolbar, text=_t("btn_delete_all"), command=self.delete_all_waypoints).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(self.wpt_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        cols = ("name", "entry_pos", "lat", "lon", "alt")
        self.wpt_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        for col, heading, w in [
            ("name", _t("hd_name"), 100), ("entry_pos", _t("hd_mgrs"), 170),
            ("lat", _t("hd_lat_ddm"), 160), ("lon", _t("hd_lon_ddm"), 160),
            ("alt", _t("hd_elev"), 80),
        ]:
            self.wpt_tree.heading(col, text=heading, command=lambda c=col: self._sort_wpt(c))
            self.wpt_tree.column(col, width=w)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.wpt_tree.yview)
        self.wpt_tree.configure(yscrollcommand=vsb.set)
        self.wpt_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.wpt_tree.bind("<Double-1>", lambda e: self.edit_waypoint())

        # Status
        self.wpt_status = ttk.Label(self.wpt_frame, text=_t("lbl_no_db"))
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
        ttk.Button(tb, text=_t("btn_new_route"), command=self.add_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_save_route"), command=self.save_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_delete_route"), command=self.delete_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_clone"), command=self.clone_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_back_route"), command=self.reverse_route).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_show_map"), command=self.show_route_on_map).pack(side=tk.LEFT, padx=2)

        cols = ("name", "origin", "dest")
        self.route_tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="extended")
        for col, heading, w in [("name", _t("hd_name"), 110), ("origin", _t("hd_origin"), 70), ("dest", _t("hd_dest"), 70)]:
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
        fields_frame = ttk.LabelFrame(inner, text=_t("lf_route_data"))
        fields_frame.pack(fill=tk.X, padx=5, pady=5)

        self.route_vars = {}
        route_fields = [
            ("name", _t("fld_nombre")), ("origin", _t("fld_origen")), ("dest", _t("fld_destino")),
            ("alt", _t("fld_alternativa")), ("wpt_trans", _t("fld_wpt_trans")), ("rwy_dep", _t("fld_rwy_dep")),
            ("rwy_arr", _t("fld_rwy_arr")), ("rwy_dep_return", _t("fld_rwy_dep_ret")), ("rwy_alt", _t("fld_rwy_alt")),
            ("rwy_dep_sid", _t("fld_sid")), ("rwy_arr_star", _t("fld_star_arr")), ("rwy_alt_star", _t("fld_star_alt")),
            ("rwy_dep_return_star", _t("fld_star_dep_ret")), ("rwy_dep_trans", _t("fld_trans_dep")), ("rwy_arr_trans", _t("fld_trans_arr")),
        ]
        for i, (key, label) in enumerate(route_fields):
            row, col = divmod(i, 3)
            ttk.Label(fields_frame, text=label + ":").grid(row=row, column=col * 2, sticky="e", padx=(8, 2), pady=3)
            var = tk.StringVar()
            ttk.Entry(fields_frame, textvariable=var, width=18).grid(row=row, column=col * 2 + 1, sticky="w", padx=(0, 12), pady=3)
            self.route_vars[key] = var

        # Main points — waypoint list with toolbar
        mp_frame = ttk.LabelFrame(inner, text=_t("lf_main_pts"))
        mp_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self._build_wpt_list(mp_frame, "main")

        self._build_flight_plan_panel(inner)

        # Alt points — waypoint list with toolbar
        ap_frame = ttk.LabelFrame(inner, text=_t("lf_alt_pts"))
        ap_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self._build_wpt_list(ap_frame, "alt")

        # Raw text (collapsed by default, for advanced editing)
        raw_frame = ttk.LabelFrame(inner, text=_t("lf_raw_edit"))
        raw_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._raw_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(raw_frame, text=_t("chk_show_raw"),
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
        ttk.Button(tb, text=_t("btn_list_add"), command=lambda: self._wpt_list_add(tag)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text=_t("btn_list_remove"), command=lambda: self._wpt_list_remove(tag)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▲", width=3, command=lambda: self._wpt_list_move(tag, -1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(tb, text="▼", width=3, command=lambda: self._wpt_list_move(tag, 1)).pack(side=tk.LEFT, padx=2)

        cols = ("seq", "wpt_id", "nombre", "source")
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=6, selectmode="extended")
        tree.heading("seq", text="#")
        tree.column("seq", width=35, stretch=False)
        tree.heading("wpt_id", text=_t("hd_waypoint"))
        tree.column("wpt_id", width=100)
        tree.heading("nombre", text=_t("hd_nombre"))
        tree.column("nombre", width=200)
        tree.heading("source", text=_t("hd_fuente"))
        tree.column("source", width=80)
        tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=(3, 5))

        if tag == "main":
            self._main_wpt_tree = tree
        else:
            self._alt_wpt_tree = tree

    def _build_flight_plan_panel(self, parent):
        """Flight plan calculator: leg distances, time and fuel from cruise inputs."""
        fp_frame = ttk.LabelFrame(parent, text=_t("lf_flight_plan"))
        fp_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        params = ttk.Frame(fp_frame)
        params.pack(fill=tk.X, padx=5, pady=(5, 2))

        self._fp_speed_var = tk.StringVar(value="250")
        self._fp_alt_var = tk.StringVar(value="25000")
        self._fp_ff_var = tk.StringVar(value="5000")

        ttk.Label(params, text=_t("lbl_fp_speed")).grid(row=0, column=0, sticky="e", padx=(0, 4))
        ttk.Entry(params, textvariable=self._fp_speed_var, width=7).grid(row=0, column=1, sticky="w")
        ttk.Label(params, text=_t("lbl_fp_kts")).grid(row=0, column=2, sticky="w", padx=(2, 14))

        ttk.Label(params, text=_t("lbl_fp_alt")).grid(row=0, column=3, sticky="e", padx=(0, 4))
        ttk.Entry(params, textvariable=self._fp_alt_var, width=8).grid(row=0, column=4, sticky="w")
        ttk.Label(params, text=_t("lbl_fp_ft")).grid(row=0, column=5, sticky="w", padx=(2, 14))

        ttk.Label(params, text=_t("lbl_fp_ff")).grid(row=0, column=6, sticky="e", padx=(0, 4))
        ttk.Entry(params, textvariable=self._fp_ff_var, width=7).grid(row=0, column=7, sticky="w")
        ttk.Label(params, text=_t("lbl_fp_lbs_hr")).grid(row=0, column=8, sticky="w", padx=(2, 14))

        ttk.Button(params, text=_t("btn_fp_calc"),
                   command=self._calculate_flight_plan).grid(row=0, column=9, padx=(4, 0))

        legs_cols = ("leg", "from_wpt", "to_wpt", "dist", "time", "fuel")
        self._fp_legs_tree = ttk.Treeview(
            fp_frame, columns=legs_cols, show="headings", height=5)
        self._fp_legs_tree.heading("leg", text="#")
        self._fp_legs_tree.column("leg", width=30, stretch=False)
        self._fp_legs_tree.heading("from_wpt", text=_t("hd_fp_from"))
        self._fp_legs_tree.column("from_wpt", width=80)
        self._fp_legs_tree.heading("to_wpt", text=_t("hd_fp_to"))
        self._fp_legs_tree.column("to_wpt", width=80)
        self._fp_legs_tree.heading("dist", text=_t("hd_fp_dist"))
        self._fp_legs_tree.column("dist", width=55, anchor="e")
        self._fp_legs_tree.heading("time", text=_t("hd_fp_time"))
        self._fp_legs_tree.column("time", width=55, anchor="e")
        self._fp_legs_tree.heading("fuel", text=_t("hd_fp_fuel"))
        self._fp_legs_tree.column("fuel", width=75, anchor="e")
        self._fp_legs_tree.pack(fill=tk.X, padx=5, pady=(2, 5))

        totals = ttk.Frame(fp_frame)
        totals.pack(fill=tk.X, padx=5, pady=(0, 8))
        self._fp_total_dist_var = tk.StringVar(value="—")
        self._fp_total_time_var = tk.StringVar(value="—")
        self._fp_total_fuel_var = tk.StringVar(value="—")
        ttk.Label(totals, text=_t("lbl_fp_total_dist"), font=self.CDU_FONT_SM).pack(side=tk.LEFT)
        ttk.Label(totals, textvariable=self._fp_total_dist_var,
                  font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=(2, 16))
        ttk.Label(totals, text=_t("lbl_fp_total_time"), font=self.CDU_FONT_SM).pack(side=tk.LEFT)
        ttk.Label(totals, textvariable=self._fp_total_time_var,
                  font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=(2, 16))
        ttk.Label(totals, text=_t("lbl_fp_total_fuel"), font=self.CDU_FONT_SM).pack(side=tk.LEFT)
        ttk.Label(totals, textvariable=self._fp_total_fuel_var,
                  font=("Consolas", 9, "bold")).pack(side=tk.LEFT, padx=(2, 0))

    def _coords_for_route_wpt(self, vals):
        """Resolve (lat, lon) for a main-route waypoint tree row."""
        wpt_id = vals[1]
        native = vals[4] if len(vals) > 4 else None
        lat, lon = None, None
        if native and str(native).startswith("("):
            fields = str(native).strip("()").split("|")
            try:
                lat = float(fields[2])
                lon = float(fields[3])
            except (IndexError, ValueError):
                pass
        if lat is None or lon is None or (lat == 0 and lon == 0):
            lat, lon, _ = self._lookup_wpt_coords(wpt_id)
        return lat, lon

    def _get_main_route_points(self):
        """Ordered list of (wpt_id, lat, lon) for Main Points with valid coordinates."""
        if not hasattr(self, "_main_wpt_tree"):
            return []
        points = []
        for item in self._main_wpt_tree.get_children():
            vals = self._main_wpt_tree.item(item, "values")
            wpt_id = vals[1]
            lat, lon = self._coords_for_route_wpt(vals)
            if lat is not None and lon is not None and not (lat == 0 and lon == 0):
                points.append((wpt_id, lat, lon))
        return points

    def _clear_flight_plan(self):
        if not hasattr(self, "_fp_legs_tree"):
            return
        self._fp_legs_tree.delete(*self._fp_legs_tree.get_children())
        self._fp_total_dist_var.set("—")
        self._fp_total_time_var.set("—")
        self._fp_total_fuel_var.set("—")

    def _refresh_flight_plan(self):
        if hasattr(self, "_fp_legs_tree"):
            self._calculate_flight_plan(silent=True)

    def _calculate_flight_plan(self, silent=False):
        if not hasattr(self, "_fp_legs_tree"):
            return
        self._fp_legs_tree.delete(*self._fp_legs_tree.get_children())

        points = self._get_main_route_points()
        if len(points) < 2:
            self._fp_total_dist_var.set("—")
            self._fp_total_time_var.set("—")
            self._fp_total_fuel_var.set("—")
            return

        try:
            speed = float(self._fp_speed_var.get().strip())
        except ValueError:
            if not silent:
                messagebox.showwarning(_t("ttl_warning"), _t("msg_fp_bad_speed"))
            return
        if speed <= 0:
            if not silent:
                messagebox.showwarning(_t("ttl_warning"), _t("msg_fp_bad_speed"))
            return

        try:
            fuel_flow = float(self._fp_ff_var.get().strip())
        except ValueError:
            if not silent:
                messagebox.showwarning(_t("ttl_warning"), _t("msg_fp_bad_ff"))
            return
        if fuel_flow < 0:
            if not silent:
                messagebox.showwarning(_t("ttl_warning"), _t("msg_fp_bad_ff"))
            return

        total_dist = 0.0
        total_time = 0.0
        total_fuel = 0.0

        for i in range(len(points) - 1):
            id1, lat1, lon1 = points[i]
            id2, lat2, lon2 = points[i + 1]
            dist = haversine_nm(lat1, lon1, lat2, lon2)
            time_h = dist / speed
            fuel = time_h * fuel_flow
            total_dist += dist
            total_time += time_h
            total_fuel += fuel
            self._fp_legs_tree.insert("", tk.END, values=(
                i + 1, id1, id2, f"{dist:.1f}", format_duration_hours(time_h), f"{fuel:.0f}",
            ))

        self._fp_total_dist_var.set(f"{total_dist:.1f} NM")
        self._fp_total_time_var.set(format_duration_hours(total_time))
        self._fp_total_fuel_var.set(f"{total_fuel:.0f} lbs")

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
        result = self._wpt_search_dialog(for_route=True)
        if result:
            wpt_id, source = result[0], result[1]
            if tag == "main":
                self._add_to_route_plan(wpt_id)
                return
            tree = self._get_wpt_tree(tag)
            seq = len(tree.get_children()) + 1
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
        if tag == "main":
            self._refresh_flight_plan()
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
        if tag == "main":
            self._refresh_flight_plan()

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

    def _wpt_search_dialog(self, for_map=False, for_route=False):
        """Search dialog that queries custom_data + nav_data.db.
        Returns (wpt_id, source) or (wpt_id, source, lat, lon) when for_map=True."""
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_search_wpt"))
        dlg.geometry("680x420")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(True, True)
        dlg.configure(bg=self.CDU_BG)

        result = [None]

        # Search bar
        search_frame = ttk.Frame(dlg)
        search_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        ttk.Label(search_frame, text=_t("lbl_search")).pack(side=tk.LEFT, padx=(0, 5))
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=25, font=self.CDU_FONT)
        search_entry.pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(search_frame, text=_t("btn_search"),
                   command=lambda: do_search()).pack(side=tk.LEFT, padx=2)

        # Source filter
        src_var = tk.StringVar(value=_t("src_all"))
        ttk.Label(search_frame, text=_t("lbl_source")).pack(side=tk.LEFT, padx=(10, 5))
        src_combo = ttk.Combobox(search_frame, textvariable=src_var, width=12, state="readonly",
                                  values=[_t("src_all"), "custom_data", "airports", "navaids", "waypoints"])
        src_combo.pack(side=tk.LEFT)

        # Results tree
        cols = ("wpt_id", "name", "source", "lat", "lon")
        res_tree = ttk.Treeview(dlg, columns=cols, show="headings", height=14)
        res_tree.heading("wpt_id", text=_t("hd_id"))
        res_tree.column("wpt_id", width=80)
        res_tree.heading("name", text=_t("hd_nombre"))
        res_tree.column("name", width=250)
        res_tree.heading("source", text=_t("hd_fuente"))
        res_tree.column("source", width=70)
        res_tree.heading("lat", text=_t("hd_lat"))
        res_tree.column("lat", width=80)
        res_tree.heading("lon", text=_t("hd_lon"))
        res_tree.column("lon", width=80)
        res_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        vsb = ttk.Scrollbar(dlg, orient=tk.VERTICAL, command=res_tree.yview)
        res_tree.configure(yscrollcommand=vsb.set)

        # Status label
        status_var = tk.StringVar(value=_t("msg_search_hint"))
        ttk.Label(dlg, textvariable=status_var, foreground=self.CDU_FG_DIM).pack(padx=10, anchor="w")

        # Buttons
        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=(5, 10))

        def do_select():
            sel = res_tree.selection()
            if sel:
                vals = res_tree.item(sel[0], "values")
                if for_map:
                    lat, lon = None, None
                    if len(vals) >= 5 and vals[3] and vals[4]:
                        try:
                            lat, lon = float(vals[3]), float(vals[4])
                        except ValueError:
                            pass
                    result[0] = (vals[0], vals[2], lat, lon)
                else:
                    result[0] = (vals[0], vals[2])
                dlg.destroy()

        def do_search():
            query = search_var.get().strip().upper()
            if len(query) < 2:
                status_var.set(_t("msg_min_chars"))
                return
            source = src_var.get()
            results = self._search_waypoints(query, source)
            res_tree.delete(*res_tree.get_children())
            for r in results:
                res_tree.insert("", tk.END, values=r)
            status_var.set(_t("msg_results", n=len(results)) +
                           (_t("msg_max_100") if len(results) >= 100 else ""))

        def do_set_origin():
            sel = res_tree.selection()
            if not sel:
                return
            vals = res_tree.item(sel[0], "values")
            if not self._ensure_db():
                return
            self._set_route_origin(vals[0])
            dlg.destroy()

        def do_set_dest():
            sel = res_tree.selection()
            if not sel:
                return
            vals = res_tree.item(sel[0], "values")
            if not self._ensure_db():
                return
            self._set_route_dest(vals[0])
            dlg.destroy()

        select_label = _t("btn_goto_map") if for_map else _t("btn_select")
        ttk.Button(btn_frame, text=select_label, command=do_select).pack(side=tk.LEFT, padx=5)
        if for_route:
            ttk.Button(btn_frame, text=_t("btn_set_origin"), command=do_set_origin).pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text=_t("btn_set_dest"), command=do_set_dest).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=_t("btn_cancel"), command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        # Bind enter and double-click
        search_entry.bind("<Return>", lambda e: do_search())
        res_tree.bind("<Double-1>", lambda e: do_select())
        search_entry.focus_set()

        dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.root.wait_window(dlg)
        return result[0]

    def _search_waypoints(self, query, source="all", limit=100):
        """Search across custom_data and nav_data.db. Returns list of (id, name, source, lat, lon)."""
        results = []
        like = f"%{query}%"
        is_all = source not in ("custom_data", "airports", "navaids", "waypoints")

        # custom_data
        if (is_all or source == "custom_data") and self.conn:
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
        if is_all or source == "airports":
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
        if remaining > 0 and (is_all or source == "navaids"):
            nav.execute(
                "SELECT name, name, 'navaid', lat, lon FROM navaids "
                "WHERE UPPER(name) LIKE ? LIMIT ?",
                (like, remaining))
            results.extend(nav.fetchall())
            remaining = limit - len(results)

        # waypoints/fixes
        if remaining > 0 and (is_all or source == "waypoints"):
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

        ttk.Button(toolbar, text=_t("btn_refresh"),
                   command=self._refresh_map_overlays).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_center_wpts"),
                   command=self._center_map_on_wpts).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_search"),
                   command=self._map_search_goto).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text=_t("btn_coord_search"),
                   command=self._map_coord_search).pack(side=tk.LEFT, padx=2)
        self._show_fix_markers = tk.BooleanVar(value=True)
        ttk.Checkbutton(toolbar, text=_t("map_show_fixes"), variable=self._show_fix_markers,
                        command=self._on_fix_layer_toggle).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Label(toolbar, text=_t("map_ruler_hint"),
                  font=("Segoe UI", 8), foreground="#666666").pack(side=tk.LEFT, padx=(12, 0))

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Label(toolbar, text=_t("lbl_tiles")).pack(side=tk.LEFT, padx=(0, 4))
        self._tile_var = tk.StringVar(value="DCS Caucasus")
        tile_values = ["OpenStreetMap", _t("tile_google_sat"), _t("tile_arcgis_sat"),
                       "DCS Caucasus", "DCS Marianas", "DCS Nevada",
                       "DCS Persian Gulf", "DCS Syria",
                       "DCS Normandy", "DCS Germany CW", "DCS Marianas WWII",
                       "DCS South Atlantic"]
        self._mbtiles_server = None

        mbtiles_path = _load_mbtiles_config()
        if mbtiles_path and os.path.isfile(mbtiles_path):
            self._mbtiles_server = _start_mbtiles_server(mbtiles_path)
            if self._mbtiles_server:
                tile_values.append(_t("tile_mbtiles"))

        self._tile_combo = ttk.Combobox(toolbar, textvariable=self._tile_var,
                                         values=tile_values, state="readonly", width=24)
        self._tile_combo.pack(side=tk.LEFT, padx=2)
        self._tile_combo.bind("<<ComboboxSelected>>", self._on_tile_change)

        ttk.Button(toolbar, text=_t("btn_load_mbtiles"),
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
        self._map_ruler_var = tk.StringVar(value=_t("map_ruler_clear"))
        self._map_loading_var = tk.StringVar(value="")
        ttk.Label(self._map_status, textvariable=self._map_lat_lon_var,
                  font=("Consolas", 9), width=32, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_mgrs_var,
                  font=("Consolas", 9), width=20, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_elev_var,
                  font=("Consolas", 9), width=16, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_zoom_var,
                  font=("Consolas", 9), width=6, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(self._map_status, textvariable=self._map_ruler_var,
                  font=("Consolas", 9), width=28, anchor="w").pack(side=tk.LEFT, padx=(0, 8))
        self._map_loading_label = ttk.Label(
            self.map_widget, textvariable=self._map_loading_var,
            font=("Segoe UI", 10, "bold"), foreground="#333333")
        self._map_loading_label.place(relx=0.5, rely=0.5, anchor="center")
        self._map_loading_label.place_forget()

        # Default: Caucasus region (DCS theater)
        self.map_widget.set_tile_server(
            "https://maps.bigbeautifulboards.com/alt-caucasus/{z}/{x}/{y}.png",
            max_zoom=15)
        self.map_widget.set_position(42.0, 43.5)
        self.map_widget.set_zoom(7)

        # Right-click context menu
        self.map_widget.add_right_click_menu_command(
            _t("map_create_wpt"), self._map_create_wpt, pass_coords=True)

        self._map_markers = []
        self._map_airport_markers = []
        self._map_fix_markers = []
        self._map_route_markers = []
        self._map_route_path = None
        self._coord_search_marker = None
        self._route_overlay_active = False
        self._airport_dlg = None
        self._fix_dlg = None
        self._wpt_dlg = None
        self._map_dragging = False
        self._wpt_marker_icons = {}  # cache: size -> PhotoImage
        self._airport_marker_icons = {}
        self._fix_marker_icons = {}
        self._fix_refresh_after = None

        # Ruler (middle-click origin → magnetic bearing + distance to cursor)
        self._ruler_origin = None
        self._ruler_cursor = None
        self._ruler_path = None
        self._ruler_marker = None
        self._decl_cache = {}
        self._decl_pending = None

        # Tile loading indicator
        self._map_loading_after = None
        self._map_loading_poll = None

        # Bind events on the map's internal canvas
        self._map_click_pos = None
        self.map_widget.canvas.bind("<Motion>", self._on_map_mouse_motion)
        self.map_widget.canvas.bind("<ButtonPress-1>", self._on_map_canvas_press, add="+")
        self.map_widget.canvas.bind("<ButtonRelease-1>", self._on_map_canvas_release, add="+")
        self.map_widget.canvas.bind("<ButtonPress-2>", self._on_map_ruler_press, add="+")
        self.map_widget.canvas.bind("<B1-Motion>", self._on_map_pan_motion, add="+")
        self.map_widget.canvas.unbind("<MouseWheel>")
        self.map_widget.canvas.unbind("<Button-4>")
        self.map_widget.canvas.unbind("<Button-5>")
        self.map_widget.canvas.bind("<MouseWheel>", self._on_map_wheel)
        self.map_widget.canvas.bind("<Button-4>", self._on_map_wheel_linux_in)
        self.map_widget.canvas.bind("<Button-5>", self._on_map_wheel_linux_out)
        self.map_widget.canvas.bind(
            "<ButtonRelease-1>", lambda e: self.root.after(100, self._on_map_zoom), add="+")
        self.map_frame.bind("<Escape>", lambda e: self._clear_ruler())
        self._last_zoom = self.map_widget.zoom
        self._elev_cache = {}  # (lat_round, lon_round) -> elevation
        self._elev_pending = None  # scheduled after-id for elevation query
        self._refresh_airport_markers()
        if self._show_fix_markers.get():
            self.root.after(300, self._refresh_fix_markers)
        self._schedule_map_loading_check()

    def _on_map_canvas_press(self, event):
        self._map_click_pos = (event.x, event.y)
        self._map_dragging = False

    def _on_map_canvas_release(self, event):
        """Pick airport/waypoint markers on click (icon tag_bind is unreliable on small tiles)."""
        was_drag = (
            self._map_click_pos is not None
            and self._map_click_pos != (event.x, event.y))
        if was_drag:
            self._map_dragging = False
            self._map_click_pos = None
            self._on_map_drag_finished()
            return
        self._map_click_pos = None
        icao = self._pick_airport_at_canvas(event.x, event.y)
        if icao:
            self._on_airport_click(icao)
            return
        fix_id = self._pick_fix_at_canvas(event.x, event.y)
        if fix_id:
            self._on_fix_click(fix_id)
            return
        wpt = self._pick_wpt_at_canvas(event.x, event.y)
        if wpt:
            self._on_custom_wpt_click(wpt)

    def _on_map_drag_finished(self):
        """Deferred map overlay work after pan — avoids jank during drag/inertia."""
        self._schedule_map_loading_check()
        if self._show_fix_markers.get():
            if self._fix_refresh_after:
                self.root.after_cancel(self._fix_refresh_after)
            self._fix_refresh_after = self.root.after(700, self._fix_refresh_markers_debounced)

    def _marker_hit_points(self, marker):
        """Canvas x,y points to test for a map marker click."""
        cx, cy = marker.get_canvas_pos(marker.position)
        points = [(cx, cy)]
        text = getattr(marker, "text", None) or getattr(marker, "_orig_text", "")
        if text:
            ty = cy + getattr(marker, "text_y_offset", -12)
            points.append((cx, ty))
        return points, text

    def _pick_airport_at_canvas(self, x, y, icon_radius=18):
        best = None
        best_score = icon_radius
        for marker in reversed(self._map_airport_markers):
            if getattr(marker, "deleted", False):
                continue
            points, label = self._marker_hit_points(marker)
            for px, py in points:
                dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if dist <= icon_radius and dist < best_score:
                    best_score = dist
                    best = marker
            if label:
                _, cy = points[0]
                ty = cy + getattr(marker, "text_y_offset", -12)
                half_w = max(22, len(label) * 5)
                if abs(y - ty) <= 14 and abs(x - points[0][0]) <= half_w:
                    return (marker.data or {}).get("icao")
        if best:
            return (best.data or {}).get("icao")
        return None

    def _pick_fix_at_canvas(self, x, y, icon_radius=14):
        best = None
        best_score = icon_radius
        for marker in reversed(self._map_fix_markers):
            if getattr(marker, "deleted", False):
                continue
            points, label = self._marker_hit_points(marker)
            for px, py in points:
                dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
                if dist <= icon_radius and dist < best_score:
                    best_score = dist
                    best = marker
            if label:
                _, cy = points[0]
                ty = cy + getattr(marker, "text_y_offset", -12)
                half_w = max(20, len(label) * 5)
                if abs(y - ty) <= 12 and abs(x - points[0][0]) <= half_w:
                    return (marker.data or {}).get("fix_id")
        if best:
            return (best.data or {}).get("fix_id")
        return None

    def _pick_wpt_at_canvas(self, x, y, icon_radius=16):
        for marker in reversed(self._map_markers):
            if getattr(marker, "deleted", False):
                continue
            points, label = self._marker_hit_points(marker)
            for px, py in points:
                if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 <= icon_radius:
                    return getattr(marker, "_orig_text", None) or label
        return None

    def _raise_map_markers(self):
        """Keep marker labels above map tiles after redraw."""
        if not hasattr(self, "map_widget"):
            return
        self.map_widget.canvas.tag_raise("marker")
        self.map_widget.canvas.tag_raise("marker_text")

    def _make_airport_icon(self, size=14, fill="#ffcc33", outline="#996600"):
        """Small diamond marker for airports. Cached by size."""
        if size in self._airport_marker_icons:
            return self._airport_marker_icons[size]
        dim = size + 4
        img = tk.PhotoImage(width=dim, height=dim)
        cx, cy = dim // 2, dim // 2
        r = size // 2
        for y in range(dim):
            for x in range(dim):
                if abs(x - cx) + abs(y - cy) <= r:
                    img.put(fill, (x, y))
                elif abs(x - cx) + abs(y - cy) == r + 1:
                    img.put(outline, (x, y))
        self._airport_marker_icons[size] = img
        return img

    def _make_fix_icon(self, size=12, fill="#00ccff", outline="#006688"):
        """Small upward triangle for nav fixes/waypoints."""
        if size in self._fix_marker_icons:
            return self._fix_marker_icons[size]
        dim = size + 8
        img = tk.PhotoImage(width=dim, height=dim)
        cx = dim // 2
        top = 1
        base = dim - 2
        half_base = size // 2 + 1
        for y in range(dim):
            for x in range(dim):
                if y < top or y > base:
                    continue
                span = int((y - top) / max(base - top, 1) * half_base)
                if abs(x - cx) <= span:
                    on_edge = abs(x - cx) >= span - 1 and span > 0
                    img.put(outline if on_edge else fill, (x, y))
        self._fix_marker_icons[size] = img
        return img

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

    def _on_map_wheel(self, event):
        """Integer zoom steps (library default uses fractional wheel delta and can skip levels)."""
        current = round(self.map_widget.zoom)
        if event.delta > 0:
            new_zoom = min(current + 1, self.map_widget.max_zoom)
        elif event.delta < 0:
            new_zoom = max(current - 1, self.map_widget.min_zoom)
        else:
            return "break"
        cw = max(self.map_widget.canvas.winfo_width(), 1)
        ch = max(self.map_widget.canvas.winfo_height(), 1)
        self.map_widget.set_zoom(
            new_zoom,
            relative_pointer_x=event.x / cw,
            relative_pointer_y=event.y / ch)
        self._schedule_map_loading_check()
        if self._show_fix_markers.get():
            self._schedule_fix_refresh()
        self.root.after(200, self._on_map_zoom)
        return "break"

    def _on_map_wheel_linux_in(self, event):
        event.delta = 120
        return self._on_map_wheel(event)

    def _on_map_wheel_linux_out(self, event):
        event.delta = -120
        return self._on_map_wheel(event)

    def _on_map_pan_motion(self, event=None):
        if (self._map_click_pos is not None and event is not None
                and self._map_click_pos != (event.x, event.y)):
            self._map_dragging = True
        if self._ruler_origin:
            try:
                coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
                self._update_ruler_display(coords[0], coords[1])
            except Exception:
                pass

    def _on_map_zoom(self):
        """Update marker text visibility based on zoom level."""
        if not hasattr(self, "map_widget"):
            return
        zoom = self.map_widget.zoom
        self._map_zoom_var.set(f"Z: {zoom:.0f}")
        if zoom == self._last_zoom:
            if self._ruler_origin and getattr(self, "_ruler_cursor", None):
                self._update_ruler_display(*self._ruler_cursor)
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
        for marker in self._map_airport_markers:
            if hasattr(marker, '_orig_text'):
                if zoom >= 8:
                    marker.text = marker._orig_text
                else:
                    marker.text = ""
                marker.draw()
        for marker in self._map_fix_markers:
            if hasattr(marker, '_orig_text'):
                if zoom >= 10:
                    marker.text = marker._orig_text
                else:
                    marker.text = ""
                marker.draw()
        self._raise_map_markers()
        if self._ruler_origin and getattr(self, "_ruler_cursor", None):
            self._update_ruler_display(*self._ruler_cursor)
        self._schedule_map_loading_check()

    def _on_map_ruler_press(self, event):
        """Middle-click sets ruler origin; click again at origin to clear."""
        try:
            coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        except Exception:
            return
        lat, lon = coords
        if self._ruler_origin:
            o_lat, o_lon = self._ruler_origin
            if abs(o_lat - lat) < 1e-5 and abs(o_lon - lon) < 1e-5:
                self._clear_ruler()
                return
        self._clear_ruler()
        self._ruler_origin = (lat, lon)
        icon = self._make_circle_icon(8, fill="#ff9900", outline="#cc6600")
        self._ruler_marker = self.map_widget.set_marker(lat, lon, icon=icon)
        self._update_ruler_display(lat, lon)
        self._fetch_declination(lat, lon)

    def _clear_ruler(self):
        self._ruler_origin = None
        self._ruler_cursor = None
        if self._ruler_path:
            self._ruler_path.delete()
            self._ruler_path = None
        if self._ruler_marker:
            self._ruler_marker.delete()
            self._ruler_marker = None
        self._map_ruler_var.set(_t("map_ruler_clear"))

    def _update_ruler_display(self, lat2, lon2):
        if not self._ruler_origin:
            return
        self._ruler_cursor = (lat2, lon2)
        lat1, lon1 = self._ruler_origin
        if self._ruler_path:
            self._ruler_path.delete()
        if abs(lat1 - lat2) > 1e-9 or abs(lon1 - lon2) > 1e-9:
            self._ruler_path = self.map_widget.set_path(
                [(lat1, lon1), (lat2, lon2)], color="#ff6600", width=2)
        dist = haversine_nm(lat1, lon1, lat2, lon2)
        brg_t = true_bearing_deg(lat1, lon1, lat2, lon2)
        decl = self._decl_cache.get((round(lat1, 1), round(lon1, 1)))
        if decl is not None:
            brg_m = (brg_t + decl) % 360
            self._map_ruler_var.set(_t("map_ruler_fmt", brg=brg_m, dist=dist))
        else:
            self._map_ruler_var.set(_t("map_ruler_fmt_true", brg=brg_t, dist=dist))

    def _fetch_declination(self, lat, lon):
        key = (round(lat, 1), round(lon, 1))
        if key in self._decl_cache:
            return

        def _worker():
            decl = 0.0
            try:
                url = (
                    "https://www.ngdc.noaa.gov/geomag-web/calculators/calculateDeclination"
                    f"?lat1={lat}&lon1={lon}&model=WMM&startYear=2025&resultFormat=json"
                )
                req = urllib.request.Request(url, headers={"User-Agent": "ChanchitaDTC/0.2"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = json.loads(resp.read())
                decl = float(data["result"][0][0]["declination"])
            except Exception:
                pass
            self._decl_cache[key] = decl
            self.root.after(0, self._on_declination_ready)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_declination_ready(self):
        if self._ruler_origin and self._ruler_cursor:
            self._update_ruler_display(*self._ruler_cursor)

    def _map_tiles_pending(self):
        if not hasattr(self, "map_widget"):
            return False
        mw = self.map_widget
        if len(mw.image_load_queue_tasks) > 0:
            return True
        try:
            for col in mw.canvas_tile_array:
                for tile in col:
                    if tile.image == mw.not_loaded_tile_image:
                        return True
        except Exception:
            pass
        return False

    def _schedule_map_loading_check(self):
        if not hasattr(self, "map_widget"):
            return
        if self._map_loading_after:
            self.root.after_cancel(self._map_loading_after)
        self._map_loading_after = self.root.after(120, self._start_map_loading_poll)

    def _start_map_loading_poll(self):
        self._map_loading_after = None
        self._update_map_loading_state()

    def _update_map_loading_state(self):
        if self._map_loading_poll:
            self.root.after_cancel(self._map_loading_poll)
            self._map_loading_poll = None
        if getattr(self, "_map_dragging", False):
            self._map_loading_poll = self.root.after(150, self._update_map_loading_state)
            return
        if self._map_tiles_pending():
            self._map_loading_var.set(_t("map_loading"))
            self._map_loading_label.place(relx=0.5, rely=0.5, anchor="center")
            self._map_loading_label.lift()
            self._map_loading_poll = self.root.after(100, self._update_map_loading_state)
        else:
            self._map_loading_var.set("")
            self._map_loading_label.place_forget()

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
        elif not getattr(self, "_map_dragging", False):
            if self._elev_pending:
                self.root.after_cancel(self._elev_pending)
            self._elev_pending = self.root.after(400, self._fetch_elevation, lat_r, lon_r)
        if self._ruler_origin:
            self._update_ruler_display(lat, lon)

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
        elif choice == _t("tile_google_sat"):
            self.map_widget.set_tile_server(
                "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga")
        elif choice == _t("tile_arcgis_sat"):
            self.map_widget.set_tile_server(
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
        elif choice == "DCS Caucasus":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-caucasus/{z}/{x}/{y}.png",
                max_zoom=15)
            self.map_widget.set_position(42.35, 43.32)
            self.map_widget.set_zoom(7)
        elif choice == "DCS Marianas":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-marianasislands/{z}/{x}/{y}.png",
                max_zoom=15)
            self.map_widget.set_position(15.2, 145.7)
            self.map_widget.set_zoom(8)
        elif choice == "DCS Nevada":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-nevada/{z}/{x}/{y}.png",
                max_zoom=15)
            self.map_widget.set_position(36.2, -115.0)
            self.map_widget.set_zoom(8)
        elif choice == "DCS Persian Gulf":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-persiangulf/{z}/{x}/{y}.png",
                max_zoom=15)
            self.map_widget.set_position(26.0, 56.0)
            self.map_widget.set_zoom(7)
        elif choice == "DCS Syria":
            self.map_widget.set_tile_server(
                "https://maps.bigbeautifulboards.com/alt-syria/{z}/{x}/{y}.png",
                max_zoom=15)
            self.map_widget.set_position(35.0, 38.5)
            self.map_widget.set_zoom(7)
        elif choice == "DCS Normandy":
            self.map_widget.set_tile_server(
                f"{DCS_OLYMPUS_MAPS}/alt-Normandy/{{z}}/{{x}}/{{y}}.png",
                max_zoom=17)
            self.map_widget.set_position(49.0, -0.5)
            self.map_widget.set_zoom(7)
        elif choice == "DCS Germany CW":
            self.map_widget.set_tile_server(
                f"{DCS_OLYMPUS_MAPS}/alt-GermanyCW/{{z}}/{{x}}/{{y}}.png",
                max_zoom=15)
            self.map_widget.set_position(51.0, 12.0)
            self.map_widget.set_zoom(6)
        elif choice == "DCS Marianas WWII":
            self.map_widget.set_tile_server(
                f"{DCS_OLYMPUS_MAPS}/alt-MarianaIslandsWWII/{{z}}/{{x}}/{{y}}.png",
                max_zoom=18)
            self.map_widget.set_position(15.2, 145.7)
            self.map_widget.set_zoom(8)
        elif choice == "DCS South Atlantic":
            self.map_widget.set_tile_server(
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")
            self.map_widget.set_position(-51.7, -59.0)
            self.map_widget.set_zoom(7)
        elif choice == _t("tile_mbtiles"):
            self.map_widget.set_tile_server(
                "http://127.0.0.1:" + str(_MBTILES_PORT) + "/tiles/{z}/{x}/{y}.png",
                max_zoom=12)
        self._schedule_map_loading_check()

    def _load_mbtiles_file(self):
        path = filedialog.askopenfilename(
            title=_t("dlg_select_mbtiles"),
            filetypes=[("MBTiles", "*.mbtiles"), (_t("ft_all"), "*.*")])
        if not path or not os.path.isfile(path):
            return
        if self._mbtiles_server:
            self._mbtiles_server.shutdown()
        self._mbtiles_server = _start_mbtiles_server(path)
        if self._mbtiles_server:
            _save_mbtiles_config(path)
            vals = list(self._tile_combo["values"])
            mbt_label = _t("tile_mbtiles")
            if mbt_label not in vals:
                vals.append(mbt_label)
                self._tile_combo["values"] = vals
            self._tile_var.set(mbt_label)
            self._on_tile_change()
            messagebox.showinfo("MBTiles", _t("msg_tiles_loaded", name=os.path.basename(path)))
        else:
            messagebox.showwarning(_t("ttl_error"),
                _t("msg_tiles_error"))

    def _refresh_map_overlays(self):
        """Refresh waypoint and airport markers on the map."""
        self._refresh_map_markers()
        self._refresh_airport_markers()
        if self._show_fix_markers.get():
            self._refresh_fix_markers()

    def _clear_wpt_markers(self):
        for marker in self._map_markers:
            marker.delete()
        self._map_markers.clear()

    def _clear_airport_markers(self):
        for marker in self._map_airport_markers:
            marker.delete()
        self._map_airport_markers.clear()

    def _clear_fix_markers(self):
        for marker in self._map_fix_markers:
            marker.delete()
        self._map_fix_markers.clear()

    def _get_map_view_bounds(self):
        """Return (min_lat, max_lat, min_lon, max_lon) for the visible map area."""
        try:
            from tkintermapview.utility_functions import osm_to_decimal
            mw = self.map_widget
            zoom = round(mw.zoom)
            lat0, lon0 = osm_to_decimal(
                mw.upper_left_tile_pos[0], mw.upper_left_tile_pos[1], zoom)
            lat1, lon1 = osm_to_decimal(
                mw.lower_right_tile_pos[0], mw.lower_right_tile_pos[1], zoom)
            margin = 0.02
            return (min(lat0, lat1) - margin, max(lat0, lat1) + margin,
                    min(lon0, lon1) - margin, max(lon0, lon1) + margin)
        except Exception:
            return None

    def _on_fix_layer_toggle(self):
        if self._show_fix_markers.get():
            self.root.update_idletasks()
            self._refresh_fix_markers()
            self._schedule_fix_refresh()
        else:
            self._clear_fix_markers()

    def _schedule_fix_refresh(self):
        if self._fix_refresh_after:
            self.root.after_cancel(self._fix_refresh_after)
        self._fix_refresh_after = self.root.after(350, self._fix_refresh_markers_debounced)

    def _fix_refresh_markers_debounced(self):
        self._fix_refresh_after = None
        if self._show_fix_markers.get():
            self._refresh_fix_markers()

    def _refresh_fix_markers(self):
        if not hasattr(self, "map_widget"):
            return
        self._clear_fix_markers()
        if not self._show_fix_markers.get() or not self.nav_conn:
            return
        bounds = self._get_map_view_bounds()
        if not bounds:
            self.root.after(200, self._refresh_fix_markers)
            return
        min_lat, max_lat, min_lon, max_lon = bounds
        icon = self._make_fix_icon(12)
        zoom = self.map_widget.zoom
        nav = self.nav_conn.cursor()
        nav.execute(
            "SELECT waypoint_identifier, waypoint_name, waypoint_latitude, waypoint_longitude "
            "FROM waypoints "
            "WHERE waypoint_latitude BETWEEN ? AND ? AND waypoint_longitude BETWEEN ? AND ? "
            "AND waypoint_latitude != 0 AND waypoint_longitude != 0 "
            "LIMIT 800",
            (min_lat, max_lat, min_lon, max_lon))
        for fix_id, name, lat, lon in nav.fetchall():
            if lat is None or lon is None:
                continue
            label = fix_id or ""
            show_text = label if zoom >= 10 else ""
            marker = self.map_widget.set_marker(
                lat, lon, text=show_text,
                icon=icon,
                text_color="#004466",
                font=("Consolas", 7, "bold"),
                data={"fix_id": fix_id, "kind": "fix"})
            marker._orig_text = label
            self._map_fix_markers.append(marker)
        self._raise_map_markers()

    def _close_fix_dialog(self):
        dlg = getattr(self, "_fix_dlg", None)
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.destroy()
            except tk.TclError:
                pass
        self._fix_dlg = None

    def _destroy_fix_dialog(self, dlg):
        if getattr(self, "_fix_dlg", None) is dlg:
            self._fix_dlg = None
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def _get_fix_details(self, fix_id):
        info = {"id": fix_id, "name": "", "lat": None, "lon": None}
        if not self.nav_conn:
            return info
        row = self.nav_conn.execute(
            "SELECT waypoint_identifier, waypoint_name, waypoint_latitude, waypoint_longitude "
            "FROM waypoints WHERE waypoint_identifier = ? LIMIT 1",
            (fix_id,)).fetchone()
        if row:
            info["id"] = row[0]
            info["name"] = row[1] or ""
            info["lat"], info["lon"] = row[2], row[3]
        return info

    def _on_fix_click(self, fix_id):
        self._close_fix_dialog()
        self._close_airport_dialog()
        self._close_wpt_dialog()
        info = self._get_fix_details(fix_id)
        fix_id = info["id"]
        lat, lon = info["lat"], info["lon"]

        dlg = tk.Toplevel(self.root)
        self._fix_dlg = dlg
        dlg.title(_t("dlg_fix", id=fix_id))
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)
        dlg.lift()
        dlg.focus_force()
        dlg.protocol("WM_DELETE_WINDOW", lambda: self._destroy_fix_dialog(dlg))

        mgrs_str = ""
        if lat is not None and lon is not None and _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
        coords_str = ""
        if lat is not None and lon is not None:
            coords_str = f"{dd_to_ddm(lat, True)}  {dd_to_ddm(lon, False)}"

        rows = [
            (_t("hd_id"), fix_id),
            (_t("lbl_fix_name"), info["name"] or "—"),
            (_t("lbl_apt_coords"), coords_str or "—"),
            (_t("lbl_apt_mgrs"), mgrs_str or "—"),
        ]
        for i, (lbl, val) in enumerate(rows):
            ttk.Label(dlg, text=lbl, style="TLabel").grid(
                row=i, column=0, sticky="e", padx=(12, 6), pady=3)
            ttk.Label(dlg, text=val, style="TLabel", font=self.CDU_FONT).grid(
                row=i, column=1, sticky="w", padx=(0, 12), pady=3)

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=len(rows), column=0, columnspan=2, pady=(10, 12))

        def copy_id():
            self.root.clipboard_clear()
            self.root.clipboard_append(fix_id)
            messagebox.showinfo("OK", _t("msg_fix_copied", id=fix_id), parent=dlg)

        def add_to_route():
            if not self._ensure_db():
                return
            self._add_to_route_plan(fix_id)
            messagebox.showinfo("OK", _t("msg_fix_added_route", id=fix_id), parent=dlg)
            self._destroy_fix_dialog(dlg)

        ttk.Button(btn_frame, text=_t("btn_copy_fix"), command=copy_id).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_add_to_route"), command=add_to_route).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_cancel"),
                   command=lambda: self._destroy_fix_dialog(dlg)).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Escape>", lambda e: self._destroy_fix_dialog(dlg))

    def _refresh_map_markers(self):
        if not hasattr(self, "map_widget"):
            return
        self._clear_wpt_markers()
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
                data={"wpt_id": name, "kind": "custom"})
            marker._orig_text = name
            self._map_markers.append(marker)
        self._raise_map_markers()

    def _close_wpt_dialog(self):
        dlg = getattr(self, "_wpt_dlg", None)
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.destroy()
            except tk.TclError:
                pass
        self._wpt_dlg = None

    def _destroy_wpt_dialog(self, dlg):
        if getattr(self, "_wpt_dlg", None) is dlg:
            self._wpt_dlg = None
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def _get_custom_wpt_details(self, wpt_id):
        info = {"id": wpt_id, "lat": None, "lon": None, "alt": None}
        if not self.conn:
            return info
        row = self.conn.execute(
            "SELECT name, lat, lon, alt FROM custom_data WHERE name = ? LIMIT 1",
            (wpt_id,)).fetchone()
        if row:
            info["id"], info["lat"], info["lon"], info["alt"] = row[0], row[1], row[2], row[3]
        return info

    def _on_custom_wpt_click(self, wpt_id):
        self._close_wpt_dialog()
        self._close_airport_dialog()
        self._close_fix_dialog()
        info = self._get_custom_wpt_details(wpt_id)
        wpt_id = info["id"]
        lat, lon, alt = info["lat"], info["lon"], info["alt"]

        dlg = tk.Toplevel(self.root)
        self._wpt_dlg = dlg
        dlg.title(_t("dlg_custom_wpt", id=wpt_id))
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)
        dlg.lift()
        dlg.focus_force()
        dlg.protocol("WM_DELETE_WINDOW", lambda: self._destroy_wpt_dialog(dlg))

        mgrs_str = ""
        if lat is not None and lon is not None and _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
        coords_str = ""
        if lat is not None and lon is not None:
            coords_str = f"{dd_to_ddm(lat, True)}  {dd_to_ddm(lon, False)}"
        elev_str = f"{alt:.0f}" if alt is not None else "—"

        rows = [
            (_t("hd_id"), wpt_id),
            (_t("lbl_apt_coords"), coords_str or "—"),
            (_t("lbl_apt_mgrs"), mgrs_str or "—"),
            (_t("lbl_wpt_elev_ft"), elev_str),
        ]
        for i, (lbl, val) in enumerate(rows):
            ttk.Label(dlg, text=lbl, style="TLabel").grid(
                row=i, column=0, sticky="e", padx=(12, 6), pady=3)
            ttk.Label(dlg, text=val, style="TLabel", font=self.CDU_FONT).grid(
                row=i, column=1, sticky="w", padx=(0, 12), pady=3)

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=len(rows), column=0, columnspan=2, pady=(10, 12))

        def copy_id():
            self.root.clipboard_clear()
            self.root.clipboard_append(wpt_id)
            messagebox.showinfo("OK", _t("msg_fix_copied", id=wpt_id), parent=dlg)

        def add_to_route():
            if not self._ensure_db():
                return
            self._add_to_route_plan(wpt_id)
            messagebox.showinfo("OK", _t("msg_fix_added_route", id=wpt_id), parent=dlg)
            self._destroy_wpt_dialog(dlg)

        ttk.Button(btn_frame, text=_t("btn_copy_fix"), command=copy_id).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_add_to_route"), command=add_to_route).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_cancel"),
                   command=lambda: self._destroy_wpt_dialog(dlg)).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Escape>", lambda e: self._destroy_wpt_dialog(dlg))

    def _refresh_airport_markers(self):
        if not hasattr(self, "map_widget"):
            return
        self._clear_airport_markers()
        if not self.nav_conn:
            return
        icon = self._make_airport_icon(14)
        zoom = self.map_widget.zoom
        nav = self.nav_conn.cursor()
        nav.execute(
            "SELECT icao, lat, lon FROM airports WHERE lat IS NOT NULL AND lon IS NOT NULL")
        for icao, lat, lon in nav.fetchall():
            if lat == 0 and lon == 0:
                continue
            alias = self._get_dcs_alias(icao)
            label = alias if alias else icao
            show_text = label if zoom >= 8 else ""
            marker = self.map_widget.set_marker(
                lat, lon, text=show_text,
                icon=icon,
                text_color="#000000",
                font=("Consolas", 8, "bold"),
                data={"icao": icao, "kind": "airport"})
            marker._orig_text = label
            self._map_airport_markers.append(marker)
        self._raise_map_markers()

    def _close_airport_dialog(self):
        dlg = getattr(self, "_airport_dlg", None)
        if dlg is not None:
            try:
                if dlg.winfo_exists():
                    dlg.destroy()
            except tk.TclError:
                pass
        self._airport_dlg = None

    def _destroy_airport_dialog(self, dlg):
        if getattr(self, "_airport_dlg", None) is dlg:
            self._airport_dlg = None
        try:
            dlg.destroy()
        except tk.TclError:
            pass

    def _map_search_goto(self):
        """Search for a waypoint/airport and center the map on it."""
        if not hasattr(self, "map_widget"):
            return
        result = self._wpt_search_dialog(for_map=True)
        if not result:
            return
        wpt_id, _source, lat, lon = result[0], result[1], result[2], result[3]
        if lat is None or lon is None or (lat == 0 and lon == 0):
            lat, lon, _ = self._lookup_wpt_coords(wpt_id)
        if lat is None or lon is None or (lat == 0 and lon == 0):
            messagebox.showwarning(_t("ttl_error"), _t("msg_no_coords_map", id=wpt_id))
            return
        self.map_widget.set_position(lat, lon)
        self.map_widget.set_zoom(10)
        self._schedule_map_loading_check()

    def _clear_coord_search_marker(self):
        if getattr(self, "_coord_search_marker", None):
            try:
                self._coord_search_marker.delete()
            except Exception:
                pass
            self._coord_search_marker = None

    def _map_coord_search(self):
        """Search map by known coordinates (DDM, decimal, or MGRS)."""
        if not hasattr(self, "map_widget"):
            return
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_coord_search"))
        dlg.geometry("480x200")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)

        lat_var = tk.StringVar()
        lon_var = tk.StringVar()
        mgrs_var = tk.StringVar()

        ttk.Label(dlg, text=_t("lbl_coord_lat")).grid(row=0, column=0, sticky="e", padx=(12, 6), pady=8)
        lat_entry = ttk.Entry(dlg, textvariable=lat_var, width=28, font=self.CDU_FONT)
        lat_entry.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=8)
        ttk.Label(dlg, text=_t("hint_lat"), foreground=self.CDU_FG_DIM).grid(row=0, column=2, sticky="w")

        ttk.Label(dlg, text=_t("lbl_coord_lon")).grid(row=1, column=0, sticky="e", padx=(12, 6), pady=8)
        lon_entry = ttk.Entry(dlg, textvariable=lon_var, width=28, font=self.CDU_FONT)
        lon_entry.grid(row=1, column=1, sticky="w", padx=(0, 12), pady=8)
        ttk.Label(dlg, text=_t("hint_lon"), foreground=self.CDU_FG_DIM).grid(row=1, column=2, sticky="w")

        ttk.Label(dlg, text=_t("lbl_coord_mgrs")).grid(row=2, column=0, sticky="e", padx=(12, 6), pady=8)
        mgrs_entry = ttk.Entry(dlg, textvariable=mgrs_var, width=28, font=self.CDU_FONT)
        mgrs_entry.grid(row=2, column=1, sticky="w", padx=(0, 12), pady=8)

        def go():
            lat, lon = None, None
            mgrs_str = mgrs_var.get().strip()
            if mgrs_str:
                if not is_valid_mgrs(mgrs_str):
                    messagebox.showwarning(
                        _t("ttl_mgrs_invalid"), _t("msg_mgrs_invalid", mgrs=mgrs_str), parent=dlg)
                    return
                result = mgrs_to_latlon(mgrs_str)
                if not result:
                    messagebox.showwarning(_t("ttl_mgrs_conv"), _t("msg_mgrs_conv_fail"), parent=dlg)
                    return
                lat, lon = result
            else:
                try:
                    if lat_var.get().strip():
                        lat = ddm_to_dd(lat_var.get())
                    if lon_var.get().strip():
                        lon = ddm_to_dd(lon_var.get())
                except ValueError as exc:
                    messagebox.showwarning(_t("ttl_error"), _t("msg_invalid_value", err=exc), parent=dlg)
                    return
            if lat is None or lon is None:
                messagebox.showwarning(_t("ttl_error"), _t("msg_coord_invalid"), parent=dlg)
                return
            dlg.destroy()
            self._map_show_coord_location(lat, lon)

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=(8, 12))
        ttk.Button(btn_frame, text=_t("btn_coord_go"), command=go).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=_t("btn_cancel"), command=dlg.destroy).pack(side=tk.LEFT, padx=5)
        dlg.bind("<Return>", lambda e: go())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        lat_entry.focus_set()

    def _map_show_coord_location(self, lat, lon):
        """Center map on coordinates, show marker, and ask user to confirm."""
        self._clear_coord_search_marker()
        self.notebook.select(self.map_frame)
        self.map_widget.set_position(lat, lon)
        self.map_widget.set_zoom(12)
        icon = self._make_circle_icon(12, fill="#00ccff", outline="#0088cc")
        self._coord_search_marker = self.map_widget.set_marker(
            lat, lon, icon=icon, text="?", text_color="#000000",
            font=("Consolas", 9, "bold"))
        self._schedule_map_loading_check()
        self._map_coord_confirm_dialog(lat, lon)

    def _map_coord_confirm_dialog(self, lat, lon):
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_coord_confirm"))
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)

        mgrs_str = ""
        if _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
        coords_str = f"{dd_to_ddm(lat, True)}  {dd_to_ddm(lon, False)}"

        ttk.Label(dlg, text=_t("msg_coord_confirm"), font=self.CDU_FONT).pack(
            padx=12, pady=(12, 8))
        ttk.Label(dlg, text=coords_str, font=self.CDU_FONT).pack(padx=12, pady=2)
        if mgrs_str:
            ttk.Label(dlg, text=f"MGRS: {mgrs_str}", font=self.CDU_FONT).pack(padx=12, pady=2)

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(12, 12))

        def confirm():
            dlg.destroy()
            self._map_coord_action_dialog(lat, lon)

        def cancel():
            self._clear_coord_search_marker()
            dlg.destroy()

        ttk.Button(btn_frame, text=_t("btn_confirm"), command=confirm).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=_t("btn_cancel"), command=cancel).pack(side=tk.LEFT, padx=5)
        dlg.bind("<Escape>", lambda e: cancel())

    def _find_wpt_id_at_coords(self, lat, lon, tol=0.0005):
        """Find a custom/nav waypoint id near lat, lon (~50 m)."""
        def near(la, lo):
            return la is not None and lo is not None and abs(la - lat) <= tol and abs(lo - lon) <= tol

        if self.conn:
            for name, la, lo in self.conn.execute(
                    "SELECT name, lat, lon FROM custom_data WHERE lat IS NOT NULL AND lon IS NOT NULL"):
                if near(la, lo):
                    return name
        if self.nav_conn:
            for icao, la, lo in self.nav_conn.execute(
                    "SELECT icao, lat, lon FROM airports WHERE lat IS NOT NULL AND lon IS NOT NULL"):
                if near(la, lo):
                    return self._get_dcs_alias(icao) or icao
            for name, la, lo in self.nav_conn.execute(
                    "SELECT name, lat, lon FROM navaids WHERE lat IS NOT NULL AND lon IS NOT NULL"):
                if near(la, lo):
                    return name
            for wid, la, lo in self.nav_conn.execute(
                    "SELECT waypoint_identifier, waypoint_latitude, waypoint_longitude FROM waypoints "
                    "WHERE waypoint_latitude IS NOT NULL AND waypoint_longitude IS NOT NULL"):
                if near(la, lo):
                    return wid
        return None

    def _map_coord_action_dialog(self, lat, lon):
        """After confirming a coordinate search, ask what to do with the location."""
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_coord_action"))
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)

        ttk.Label(dlg, text=_t("dlg_coord_action"), font=self.CDU_FONT).pack(
            padx=12, pady=(12, 8))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(padx=12, pady=(4, 12))

        def close():
            self._clear_coord_search_marker()
            dlg.destroy()

        def with_wpt_id(action):
            wpt_id = self._find_wpt_id_at_coords(lat, lon)
            if wpt_id:
                if action == "route":
                    if self._ensure_db():
                        self._add_to_route_plan(wpt_id)
                elif action == "origin":
                    if self._ensure_db():
                        self._set_route_origin(wpt_id)
                elif action == "dest":
                    if self._ensure_db():
                        self._set_route_dest(wpt_id)
                close()
                return
            pre = self._coord_pre_fill(lat, lon)
            if action == "wpt":
                close()
                self._waypoint_dialog(pre, from_map=True)
            elif action == "route":
                close()
                self._waypoint_dialog(pre, from_map=True, post_save="route")
            elif action == "origin":
                close()
                self._waypoint_dialog(pre, from_map=True, post_save="origin")
            elif action == "dest":
                close()
                self._waypoint_dialog(pre, from_map=True, post_save="dest")

        ttk.Button(btn_frame, text=_t("btn_add_as_wpt"),
                   command=lambda: with_wpt_id("wpt")).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text=_t("btn_add_as_route_wpt"),
                   command=lambda: with_wpt_id("route")).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text=_t("btn_set_origin"),
                   command=lambda: with_wpt_id("origin")).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text=_t("btn_set_dest"),
                   command=lambda: with_wpt_id("dest")).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text=_t("btn_cancel"), command=close).pack(fill=tk.X, pady=(8, 2))
        dlg.bind("<Escape>", lambda e: close())

    def _coord_pre_fill(self, lat, lon):
        mgrs_str = ""
        if _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
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
        return ("", mgrs_str, dd_to_ddm(lat, True), dd_to_ddm(lon, False), elev_str)

    def _get_airport_details(self, icao):
        """Collect airport info from nav_data and airport_names."""
        info = {
            "icao": icao,
            "name": "",
            "municipality": "",
            "lat": None,
            "lon": None,
            "type": "",
            "alias": "",
            "route_id": icao,
        }
        if self.names_conn:
            row = self.names_conn.execute(
                "SELECT name, municipality, ident, icao FROM airport_names "
                "WHERE ident = ? OR icao = ? LIMIT 1",
                (icao, icao),
            ).fetchone()
            if row:
                info["name"] = row[0] or ""
                info["municipality"] = row[1] or ""
        alias = self._get_dcs_alias(icao)
        if alias:
            info["alias"] = alias
            info["route_id"] = alias
        else:
            resolved = self._resolve_alias_to_ident(icao)
            if resolved:
                info["route_id"] = icao
                icao = resolved
                info["icao"] = resolved
        if self.nav_conn:
            row = self.nav_conn.execute(
                "SELECT icao, lat, lon, type FROM airports WHERE icao = ? LIMIT 1",
                (icao,),
            ).fetchone()
            if row:
                info["icao"] = row[0]
                info["lat"], info["lon"] = row[1], row[2]
                info["type"] = row[3] or ""
                if not info["alias"]:
                    info["alias"] = self._get_dcs_alias(row[0]) or ""
                    if info["alias"]:
                        info["route_id"] = info["alias"]
        if not info["name"]:
            info["name"] = self._get_airport_name(info["icao"])
        return info

    def _on_airport_click(self, icao):
        self._close_airport_dialog()
        self._close_fix_dialog()
        self._close_wpt_dialog()
        info = self._get_airport_details(icao)
        route_id = info["route_id"]
        display_icao = info["alias"] or info["icao"]

        dlg = tk.Toplevel(self.root)
        self._airport_dlg = dlg
        dlg.title(_t("dlg_airport", icao=display_icao))
        dlg.transient(self.root)
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)
        dlg.lift()
        dlg.focus_force()
        dlg.protocol("WM_DELETE_WINDOW", lambda: self._destroy_airport_dialog(dlg))

        lat, lon = info["lat"], info["lon"]
        mgrs_str = ""
        if lat is not None and lon is not None and _mgrs:
            try:
                mgrs_str = _mgrs.toMGRS(lat, lon, MGRSPrecision=4)
            except Exception:
                pass
        elev_str = ""
        if lat is not None and lon is not None:
            key = (round(lat, 3), round(lon, 3))
            if key in self._elev_cache:
                elev_str = f"{self._elev_cache[key] * METERS_TO_FEET:.0f} ft"
        coords_str = ""
        if lat is not None and lon is not None:
            coords_str = f"{dd_to_ddm(lat, True)}  {dd_to_ddm(lon, False)}"

        rows = [
            (_t("lbl_apt_icao"), display_icao),
            (_t("lbl_apt_alias"), info["alias"] or "—"),
            (_t("lbl_apt_name"), info["name"] or "—"),
            (_t("lbl_apt_municipality"), info["municipality"] or "—"),
            (_t("lbl_apt_type"), info["type"] or "—"),
            (_t("lbl_apt_coords"), coords_str or "—"),
            (_t("lbl_apt_mgrs"), mgrs_str or "—"),
            (_t("lbl_apt_elev"), elev_str or "—"),
        ]
        for i, (lbl, val) in enumerate(rows):
            ttk.Label(dlg, text=lbl, style="TLabel").grid(
                row=i, column=0, sticky="e", padx=(12, 6), pady=3)
            ttk.Label(dlg, text=val, style="TLabel", font=self.CDU_FONT).grid(
                row=i, column=1, sticky="w", padx=(0, 12), pady=3)

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=len(rows), column=0, columnspan=2, pady=(10, 12))

        def copy_icao():
            self.root.clipboard_clear()
            self.root.clipboard_append(display_icao)
            messagebox.showinfo("OK", _t("msg_icao_copied", icao=display_icao), parent=dlg)

        def add_to_route():
            if not self._ensure_db():
                return
            self._add_airport_to_route(route_id)
            messagebox.showinfo("OK", _t("msg_apt_added_route", icao=display_icao), parent=dlg)
            self._destroy_airport_dialog(dlg)

        def set_origin():
            if not self._ensure_db():
                return
            self._set_route_origin(route_id)
            messagebox.showinfo("OK", _t("msg_apt_set_origin", icao=display_icao), parent=dlg)
            self._destroy_airport_dialog(dlg)

        def set_dest():
            if not self._ensure_db():
                return
            self._set_route_dest(route_id)
            messagebox.showinfo("OK", _t("msg_apt_set_dest", icao=display_icao), parent=dlg)
            self._destroy_airport_dialog(dlg)

        ttk.Button(btn_frame, text=_t("btn_copy_icao"), command=copy_icao).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_add_to_route"), command=add_to_route).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_set_origin"), command=set_origin).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_set_dest"), command=set_dest).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text=_t("btn_cancel"),
                   command=lambda: self._destroy_airport_dialog(dlg)).pack(side=tk.LEFT, padx=4)

        dlg.bind("<Escape>", lambda e: self._destroy_airport_dialog(dlg))

    def _is_same_origin_dest_route(self):
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()
        return bool(origin and dest and self._same_route_wpt_id(origin, dest))

    def _sync_same_origin_dest_route(self):
        """Origin and destination are the same: first row = origin, last row = dest."""
        if not self._is_same_origin_dest_route():
            return False
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()
        tree = self._main_wpt_tree
        items = list(tree.get_children())

        middle_rows = []
        for item in items:
            vals = list(tree.item(item, "values"))
            if not self._same_route_wpt_id(vals[1], origin):
                middle_rows.append(vals)

        if items:
            first_id = tree.item(items[0], "values")[1]
            last_id = tree.item(items[-1], "values")[1]
            endpoint_count = sum(
                1 for item in items
                if self._same_route_wpt_id(tree.item(item, "values")[1], origin))
            if (endpoint_count == 2
                    and self._same_route_wpt_id(first_id, origin)
                    and self._same_route_wpt_id(last_id, dest)
                    and len(middle_rows) == len(items) - 2):
                return False

        start_native = self._build_native_wpt_for_id(origin)
        end_native = self._build_native_wpt_for_id(dest)
        start_source = self._identify_wpt_source(origin)
        end_source = self._identify_wpt_source(dest)
        start_nombre = self._get_airport_name(origin) if start_source == "airport" else ""
        end_nombre = self._get_airport_name(dest) if end_source == "airport" else ""

        tree.delete(*items)
        tree.insert("", tk.END, values=(1, origin, start_nombre, start_source, start_native))
        for vals in middle_rows:
            tree.insert("", tk.END, values=vals)
        tree.insert("", tk.END, values=(0, dest, end_nombre, end_source, end_native))
        self._renumber_wpt_list("main")
        self._sync_list_to_raw("main")
        self._refresh_route_map_if_shown()
        self._refresh_flight_plan()
        return True

    def _ensure_wpt_in_route_plan(self, wpt_id, where="append"):
        """Insert or reposition a waypoint in the main route flight plan list."""
        wpt_id = (wpt_id or "").strip()
        if not wpt_id:
            return
        tree = self._main_wpt_tree
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()
        same_od = self._is_same_origin_dest_route()

        if same_od and self._same_route_wpt_id(wpt_id, origin):
            self._sync_same_origin_dest_route()
            return

        if same_od and where == "append":
            items = tree.get_children()
            for item in items:
                if self._same_route_wpt_id(tree.item(item, "values")[1], wpt_id):
                    return
            self._sync_same_origin_dest_route()
            items = tree.get_children()
            insert_at = len(items) - 1 if items else 0
            native = self._build_native_wpt_for_id(wpt_id)
            source = self._identify_wpt_source(wpt_id)
            nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
            tree.insert("", insert_at, values=(0, wpt_id, nombre, source, native))
            self._renumber_wpt_list("main")
            self._sync_list_to_raw("main")
            self._refresh_route_map_if_shown()
            self._refresh_flight_plan()
            return

        items = tree.get_children()
        existing = None
        for item in items:
            if self._same_route_wpt_id(tree.item(item, "values")[1], wpt_id):
                existing = item
                break
        if existing:
            items = tree.get_children()
            if where == "start" and items and existing != items[0]:
                tree.move(existing, "", 0)
                self._renumber_wpt_list("main")
            elif where == "end" and items and existing != items[-1]:
                tree.move(existing, "", tk.END)
                self._renumber_wpt_list("main")
        else:
            native = self._build_native_wpt_for_id(wpt_id)
            source = self._identify_wpt_source(wpt_id)
            nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
            if where == "start":
                tree.insert("", 0, values=(0, wpt_id, nombre, source, native))
                self._renumber_wpt_list("main")
            else:
                seq = len(tree.get_children()) + 1
                tree.insert("", tk.END, values=(seq, wpt_id, nombre, source, native))
        self._sync_list_to_raw("main")
        self._refresh_route_map_if_shown()
        self._refresh_flight_plan()

    def _ensure_dest_middle_duplicate(self):
        """Origin+destination only: insert destination again between origin and final dest."""
        tree = self._main_wpt_tree
        items = tree.get_children()
        if len(items) != 2:
            return False
        vals0 = tree.item(items[0], "values")
        vals1 = tree.item(items[1], "values")
        if vals0[1] == vals1[1]:
            return False
        nombre = vals1[2] if len(vals1) > 2 else ""
        source = vals1[3] if len(vals1) > 3 else self._identify_wpt_source(vals1[1])
        native = vals1[4] if len(vals1) > 4 else self._build_native_wpt_for_id(vals1[1])
        tree.insert("", 1, values=(2, vals1[1], nombre, source, native))
        self._renumber_wpt_list("main")
        return True

    def _set_route_origin(self, wpt_id):
        self.route_vars["origin"].set(wpt_id)
        if self._is_same_origin_dest_route():
            self._sync_same_origin_dest_route()
        else:
            self._ensure_wpt_in_route_plan(wpt_id, "start")
        self.notebook.select(self.route_frame)

    def _set_route_dest(self, wpt_id):
        self.route_vars["dest"].set(wpt_id)
        if self._is_same_origin_dest_route():
            self._sync_same_origin_dest_route()
        else:
            self._ensure_wpt_in_route_plan(wpt_id, "end")
        self.notebook.select(self.route_frame)

    def _refresh_route_map_if_shown(self):
        if getattr(self, "_route_overlay_active", False) and hasattr(self, "map_widget"):
            self.show_route_on_map(switch_tab=False)

    def _add_to_route_plan(self, wpt_id):
        """Add a waypoint (airport, nav, or custom) to the main route plan."""
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()
        if self._is_same_origin_dest_route():
            if not self._same_route_wpt_id(wpt_id, origin):
                self._ensure_wpt_in_route_plan(wpt_id, "append")
            else:
                self._sync_same_origin_dest_route()
            self.notebook.select(self.route_frame)
            return
        if origin and not self._same_route_wpt_id(origin, wpt_id):
            self._ensure_wpt_in_route_plan(origin, "start")
        if self._same_route_wpt_id(wpt_id, origin):
            where = "start"
        elif self._same_route_wpt_id(wpt_id, dest):
            where = "end"
        else:
            where = "append"
        self._ensure_wpt_in_route_plan(wpt_id, where)
        self.notebook.select(self.route_frame)

    def _add_airport_to_route(self, wpt_id, tag="main"):
        """Add an airport/nav waypoint to the route list."""
        if tag == "main":
            self._add_to_route_plan(wpt_id)
            return
        tree = self._get_wpt_tree(tag)
        seq = len(tree.get_children()) + 1
        source = self._identify_wpt_source(wpt_id)
        nombre = self._get_airport_name(wpt_id) if source == "airport" else ""
        native = self._build_native_wpt_for_id(wpt_id)
        tree.insert("", tk.END, values=(seq, wpt_id, nombre, source, native))
        self._sync_list_to_raw(tag)
        self.notebook.select(self.route_frame)

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

    def _map_create_wpt(self, coords):
        if not self._ensure_db():
            return
        lat, lon = coords
        self._waypoint_dialog(self._coord_pre_fill(lat, lon), from_map=True)

    # ── DB helpers ───────────────────────────────────────────────────

    def _ensure_db(self):
        if not self.conn:
            messagebox.showwarning(_t("ttl_warning"), _t("msg_load_db_first"))
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

    def _same_route_wpt_id(self, a, b):
        """True if two route waypoint ids refer to the same airport/nav point."""
        if not a or not b:
            return False
        a, b = a.strip(), b.strip()
        if a == b:
            return True
        if self._get_dcs_alias(a) == b or self._get_dcs_alias(b) == a:
            return True
        ra, rb = self._resolve_alias_to_ident(a), self._resolve_alias_to_ident(b)
        if ra and ra == b:
            return True
        if rb and rb == a:
            return True
        if ra and rb and ra == rb:
            return True
        return False

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
            if _HAS_MAPVIEW and hasattr(self, "map_widget"):
                self._refresh_airport_markers()
                if getattr(self, "_show_fix_markers", None) and self._show_fix_markers.get():
                    self._refresh_fix_markers()
            return

        # 2. Auto-detect
        found = _find_nav_data_db()
        if found:
            path = found[0]
            self.nav_conn = sqlite3.connect(path)
            _save_navdata_config(path)
            if _HAS_MAPVIEW and hasattr(self, "map_widget"):
                self._refresh_airport_markers()
                if getattr(self, "_show_fix_markers", None) and self._show_fix_markers.get():
                    self._refresh_fix_markers()
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
            dlg.title(_t("dlg_select_db"))
            dlg.transient(self.root)
            dlg.grab_set()
            dlg.resizable(False, False)
            dlg.configure(bg=self.CDU_BG)

            ttk.Label(dlg, text=_t("lbl_dcs_multi"),
                      font=self.CDU_FONT).pack(padx=20, pady=(15, 10))

            selected = tk.StringVar(value=found[0])
            for p in found:
                ttk.Radiobutton(dlg, text=p, variable=selected, value=p).pack(anchor="w", padx=25, pady=2)

            result = [None]

            def on_ok():
                result[0] = selected.get()
                dlg.destroy()

            ttk.Button(dlg, text=_t("btn_accept"), command=on_ok).pack(pady=(10, 15))
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
                _t("ttl_dcs_not_found"),
                _t("msg_dcs_not_found"))
            path = filedialog.askopenfilename(
                title=_t("dlg_select_db"),
                filetypes=[(_t("ft_sqlite"), "user_data.db"), (_t("ft_all"), "*.*")])
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
        messagebox.showinfo(_t("ttl_saved"), _t("msg_saved_to", path=self.db_path))

    def configure_dcs_path(self):
        """Let the user manually set the DCS.C130J path."""
        current = _load_config()
        path = filedialog.askopenfilename(
            title=_t("dlg_select_db"),
            initialdir=os.path.dirname(current) if current else None,
            filetypes=[(_t("ft_sqlite"), "user_data.db"), (_t("ft_sqlite"), "*.db"), (_t("ft_all"), "*.*")])
        if path and os.path.isfile(path):
            self.dcs_path = path
            _save_config(path)
            messagebox.showinfo("OK", _t("msg_path_set", path=path))

    def open_db(self):
        path = filedialog.askopenfilename(filetypes=[(_t("ft_sqlite"), "*.db"), (_t("ft_all"), "*.*")])
        if not path:
            return
        self._load_db(path)

    def save_db_as(self):
        if not self._ensure_db():
            return
        path = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[(_t("ft_sqlite"), "*.db")])
        if not path:
            return
        self.conn.commit()
        self.conn.close()
        shutil.copy2(self.db_path, path)
        self._load_db(path)
        messagebox.showinfo("OK", _t("msg_saved_to", path=path))

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
        self.wpt_status.config(text=_t("lbl_wpts_loaded", n=len(rows), f=os.path.basename(self.db_path)))
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
            messagebox.showinfo("Info", _t("msg_select_wpt"))
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
        names = [self.wpt_tree.item(iid, "values")[0] for iid in sel]
        if len(names) == 1:
            msg = _t("msg_confirm_del_wpt", name=names[0])
        else:
            listed = ", ".join(names[:8])
            if len(names) > 8:
                listed += f" (+{len(names) - 8})"
            msg = _t("msg_confirm_del_wpts", n=len(names), names=listed)
        if messagebox.askyesno(_t("ttl_confirm"), msg):
            for name in names:
                self.conn.execute("DELETE FROM custom_data WHERE name = ?", (name,))
            self.conn.commit()
            self.refresh_waypoints()

    def delete_all_waypoints(self):
        if not self._ensure_db():
            return
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM custom_data")
        count = cur.fetchone()[0]
        if count == 0:
            messagebox.showinfo("Info", _t("msg_no_wpts"))
            return
        msg = _t("msg_confirm_del_all_wpt", n=count)
        cur.execute("SELECT COUNT(*) FROM routes")
        if cur.fetchone()[0] > 0:
            msg += _t("msg_del_all_routes_warn")
        if messagebox.askyesno(_t("ttl_confirm"), msg):
            self.conn.execute("DELETE FROM custom_data")
            self.conn.commit()
            self.refresh_waypoints()

    def _waypoint_dialog(self, existing=None, is_duplicate=False, from_map=False, post_save=None):
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_new_wpt") if (not existing or is_duplicate) else _t("dlg_edit_wpt"))
        dlg.geometry("540x290")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=self.CDU_BG)

        labels = [_t("lbl_wpt_name"), _t("lbl_wpt_mgrs"), _t("lbl_wpt_lat"), _t("lbl_wpt_lon"), _t("lbl_wpt_elev")]
        entries = []
        for i, lbl in enumerate(labels):
            ttk.Label(dlg, text=lbl, style="TLabel").grid(row=i, column=0, sticky="e", padx=(15, 5), pady=6)
            e = ttk.Entry(dlg, width=32, font=self.CDU_FONT)
            e.grid(row=i, column=1, padx=(0, 10), pady=6)
            if existing and i < len(existing):
                e.insert(0, existing[i])
            entries.append(e)

        # Hint labels (dimmed green, visible on dark bg)
        ttk.Label(dlg, text=_t("hint_lat"), foreground=self.CDU_FG_DIM).grid(row=2, column=2, sticky="w")
        ttk.Label(dlg, text=_t("hint_lon"), foreground=self.CDU_FG_DIM).grid(row=3, column=2, sticky="w")
        ttk.Label(dlg, text=_t("hint_elev"), foreground=self.CDU_FG_DIM).grid(row=4, column=2, sticky="w")

        is_edit = existing and not is_duplicate and bool(existing[0])
        old_name = existing[0] if is_edit else None
        if is_edit:
            entries[0].config(state="disabled")

        def save(add_to_route=False):
            vals = [e.get().strip() for e in entries]
            if not vals[0]:
                messagebox.showwarning(_t("ttl_error"), _t("msg_name_required"), parent=dlg)
                return

            mgrs_str = vals[1]

            # Validate MGRS if it looks like one
            if mgrs_str and not mgrs_str[0].isalpha():
                if not is_valid_mgrs(mgrs_str):
                    messagebox.showwarning(
                        _t("ttl_mgrs_invalid"),
                        _t("msg_mgrs_invalid", mgrs=mgrs_str),
                        parent=dlg,
                    )
                    return

            try:
                lat = ddm_to_dd(vals[2]) if vals[2] else None
                lon = ddm_to_dd(vals[3]) if vals[3] else None
            except ValueError as exc:
                messagebox.showwarning(_t("ttl_error"), _t("msg_invalid_value", err=exc), parent=dlg)
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
                            _t("ttl_mgrs_conv"),
                            _t("msg_mgrs_conv_fail"),
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
                messagebox.showwarning(_t("ttl_error"), _t("msg_invalid_elev", val=alt_ft_str), parent=dlg)
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
                    if not messagebox.askyesno(_t("ttl_warning"), _t("msg_wpt_overwrite", name=vals[0]), parent=dlg):
                        return
                    self.conn.execute(
                        "UPDATE custom_data SET entry_pos=?, lat=?, lon=?, alt=? WHERE name=?",
                        (vals[1], lat, lon, alt_m, vals[0]),
                    )
            self.conn.commit()
            self.refresh_waypoints()
            if not is_edit:
                if post_save == "origin":
                    self._set_route_origin(vals[0])
                elif post_save == "dest":
                    self._set_route_dest(vals[0])
                elif add_to_route or post_save == "route":
                    self._add_to_route_plan(vals[0])
            dlg.destroy()

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=len(labels), column=0, columnspan=2, pady=12)
        ttk.Button(btn_frame, text=_t("btn_save"), command=lambda: save(False)).pack(side=tk.LEFT, padx=5)
        if from_map and not is_edit and not post_save:
            ttk.Button(btn_frame, text=_t("btn_save_add_route"),
                       command=lambda: save(True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=_t("btn_cancel"), command=dlg.destroy).pack(side=tk.LEFT, padx=5)

        dlg.bind("<Return>", lambda e: save(False))
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
        self._ensure_dest_middle_duplicate()
        self._sync_same_origin_dest_route()
        self._sync_list_to_raw("main")
        self._refresh_flight_plan()

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
        self._clear_flight_plan()

    def _back_route_name(self, name):
        """Append R to route name (max 10 chars); at length 10, replace last char with R."""
        name = (name or "").strip()
        if len(name) >= 10:
            return name[:9] + "R"
        return (name + "R")[:10]

    def reverse_route(self):
        """Reverse Main Points order and swap Origin/Destination; suffix route name with R."""
        tree = self._main_wpt_tree
        items = tree.get_children()
        if not items:
            messagebox.showwarning(_t("ttl_warning"), _t("msg_route_no_wpts"))
            return

        rows = [list(tree.item(item, "values")) for item in items]
        rows.reverse()
        tree.delete(*items)
        for i, vals in enumerate(rows, 1):
            vals[0] = i
            tree.insert("", tk.END, values=vals)

        self._sync_list_to_raw("main")

        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()
        self.route_vars["origin"].set(dest)
        self.route_vars["dest"].set(origin)

        self.route_vars["name"].set(self._back_route_name(self.route_vars["name"].get()))

        self._sync_list_to_raw("main")
        self._refresh_flight_plan()
        self._refresh_route_map_if_shown()

    def save_route(self):
        if not self._ensure_db():
            return
        name = self.route_vars["name"].get().strip()
        if not name:
            messagebox.showwarning(_t("ttl_error"), _t("msg_route_name_required"))
            return

        # Sync lists → raw text before saving
        self._sync_list_to_raw("main")
        self._sync_list_to_raw("alt")

        # ── Origin / Destination auto-sync ──────────────────────────
        tree = self._main_wpt_tree
        items = tree.get_children()
        origin = self.route_vars["origin"].get().strip()
        dest = self.route_vars["dest"].get().strip()

        if self._is_same_origin_dest_route():
            self._sync_same_origin_dest_route()
        else:
            if origin:
                self._ensure_wpt_in_route_plan(origin, "start")
                items = tree.get_children()
            elif items:
                origin = tree.item(items[0], "values")[1]
                self.route_vars["origin"].set(origin)

            if dest:
                self._ensure_wpt_in_route_plan(dest, "end")
                items = tree.get_children()
            elif items:
                dest = tree.item(items[-1], "values")[1]
                self.route_vars["dest"].set(dest)

            self._ensure_dest_middle_duplicate()

        # Re-sync after possible insertions (updates type flags)
        self._sync_list_to_raw("main")
        self._refresh_flight_plan()

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
        messagebox.showinfo("OK", _t("msg_route_saved", name=name))

    def delete_route(self):
        if not self._ensure_db():
            return
        sel = self.route_tree.selection()
        if not sel:
            return
        names = [self.route_tree.item(iid, "values")[0] for iid in sel]
        if len(names) == 1:
            msg = _t("msg_confirm_del_rte", name=names[0])
        else:
            listed = ", ".join(names[:8])
            if len(names) > 8:
                listed += f" (+{len(names) - 8})"
            msg = _t("msg_confirm_del_rtes", n=len(names), names=listed)
        if messagebox.askyesno(_t("ttl_confirm"), msg):
            for name in names:
                self.conn.execute("DELETE FROM routes WHERE name = ?", (name,))
            self.conn.commit()
            self.refresh_routes()

    def clone_route(self):
        if not self._ensure_db():
            return
        sel = self.route_tree.selection()
        if not sel:
            messagebox.showwarning(_t("ttl_error"), _t("msg_select_route_clone"))
            return
        src_name = self.route_tree.item(sel[0], "values")[0]
        new_name = simpledialog.askstring(
            _t("dlg_clone_route"), _t("msg_clone_prompt", name=src_name),
            parent=self.root)
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()[:10]
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM routes WHERE name = ?", (new_name,))
        if cur.fetchone()[0] > 0:
            messagebox.showwarning(_t("ttl_error"), _t("msg_route_exists", name=new_name))
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

    def show_route_on_map(self, switch_tab=True):
        if not hasattr(self, "map_widget"):
            messagebox.showwarning(_t("ttl_error"), _t("msg_map_unavailable"))
            return
        tree = self._main_wpt_tree
        items = tree.get_children()
        if not items:
            messagebox.showwarning(_t("ttl_error"), _t("msg_no_wpts_route"))
            return
        self._route_overlay_active = True
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
        if switch_tab:
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
            messagebox.showwarning(_t("ttl_warning"),
                _t("msg_select_export"))
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".dtc",
            filetypes=[(_t("ft_dtc"), "*.dtc"), (_t("ft_all"), "*.*")],
            title=_t("dlg_export_dtc"),
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

        messagebox.showinfo(_t("ttl_exported"),
            _t("msg_dtc_exported", name=os.path.basename(path), wpts=len(wpt_names), routes=len(route_names)))

    def import_dtc(self):
        """Import a .dtc package, merging into the current DB with conflict resolution."""
        if not self._ensure_db():
            return

        path = filedialog.askopenfilename(
            filetypes=[(_t("ft_dtc"), "*.dtc"), (_t("ft_sqlite"), "*.db"), (_t("ft_all"), "*.*")],
            title=_t("dlg_import_dtc"),
        )
        if not path:
            return

        try:
            dtc_conn = sqlite3.connect(path)
            dtc_conn.execute("SELECT 1 FROM custom_data LIMIT 1")
        except Exception:
            messagebox.showerror(_t("ttl_error"), _t("msg_invalid_dtc"))
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

        messagebox.showinfo(_t("ttl_import_done"),
            _t("msg_import_summary", wi=wpt_imported, ws=wpt_skipped, ri=route_imported, rs=route_skipped))

    def _conflict_dialog(self, tipo, name):
        """Show conflict resolution dialog. Returns action string."""
        dlg = tk.Toplevel(self.root)
        dlg.title(_t("dlg_conflict", tipo=tipo))
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.configure(bg=self.CDU_BG)

        result = tk.StringVar(value="skip")

        ttk.Label(dlg, text=_t("msg_conflict_exists", tipo=tipo, name=name),
                  font=self.CDU_FONT_HDR, foreground=self.CDU_AMBER).pack(padx=20, pady=(18, 5))
        ttk.Label(dlg, text=_t("msg_conflict_action"),
                  font=self.CDU_FONT_SM).pack(padx=20, pady=(0, 12))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=20, pady=5)

        def do_overwrite():
            result.set("overwrite")
            dlg.destroy()

        def do_rename_new():
            dlg.grab_release()
            new = simpledialog.askstring(_t("dlg_rename_imported"),
                _t("msg_rename_imported", tipo=tipo.lower()),
                initialvalue=name + "_imp", parent=self.root)
            if new and new.strip():
                result.set(f"rename_new:{new.strip()}")
                dlg.destroy()
            else:
                dlg.grab_set()

        def do_rename_old():
            dlg.grab_release()
            new = simpledialog.askstring(_t("dlg_rename_existing"),
                _t("msg_rename_existing", tipo=tipo.lower()),
                initialvalue=name + "_old", parent=self.root)
            if new and new.strip():
                result.set(f"rename_old:{new.strip()}")
                dlg.destroy()
            else:
                dlg.grab_set()

        def do_skip():
            result.set("skip")
            dlg.destroy()

        ttk.Button(btn_frame, text=_t("btn_rename_imported"),
                   command=do_rename_new).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text=_t("btn_rename_existing"),
                   command=do_rename_old).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text=_t("btn_overwrite"),
                   command=do_overwrite).pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text=_t("btn_skip"),
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
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), (_t("ft_all"), "*.*")])
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
        messagebox.showinfo("OK", _t("msg_wpts_imported", n=count))

    def import_routes_csv(self):
        if not self._ensure_db():
            return
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), (_t("ft_all"), "*.*")])
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
        messagebox.showinfo("OK", _t("msg_routes_imported", n=count))

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
        messagebox.showinfo("OK", _t("msg_wpts_exported", path=path))

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
        messagebox.showinfo("OK", _t("msg_routes_exported", path=path))


if __name__ == "__main__":
    root = tk.Tk()
    app = DBEditor(root)
    root.mainloop()
