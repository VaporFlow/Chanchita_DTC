================================================================================
                         CHANCHITA DTC - C-130J Hercules
                      Data Transfer Cartridge Editor for DCS
================================================================================

  [Español abajo / Spanish below]

================================================================================
  ENGLISH
================================================================================

DESCRIPTION
-----------
Chanchita DTC is a waypoint and route editor for the C-130J Hercules module
in DCS World. It lets you create, edit, import, and export navigation points
and routes directly in the module's user_data.db database, without needing
DCS to be running.

You can also share waypoints and routes between pilots via .dtc packages.

The interface is available in English and Spanish. The language is selected
on first launch and saved for future sessions.


INSTALLATION
------------
1. Copy Chanchita_DTC.exe to any folder (e.g., G:\Chanchita_DTC\).
2. Double-click to run. No Python or other software required.
3. On first launch, select your language (English / Español).
4. Done.


STEP-BY-STEP TUTORIAL
---------------------

1. LOAD YOUR DATABASE
   - File > Load DTC (Ctrl+L)
     Automatically searches for user_data.db in Saved Games\DCS.C130J
     across all drives. If found, it opens directly.
   - File > Open DB... (Ctrl+O)
     Open any .db file manually.
   - If multiple DCS.C130J installations are found, a dialog lets you
     choose which one to use.

2. MANAGE WAYPOINTS
   - Go to the "Waypoints (custom_data)" tab.
   - All custom waypoints are displayed with Name, MGRS, Lat/Lon (DDM),
     and Elevation (ft).
   - "+ Add" to create a new waypoint:
       * Enter a name (max 5 characters, used as the waypoint ID in DCS).
       * Enter MGRS coordinates (10 digits). Lat/Lon are calculated
         automatically from MGRS.
       * Optionally enter Lat/Lon in DDM format (e.g., N 41° 23.456').
       * Optionally enter elevation in feet (MSL).
   - "Edit" or double-click to modify an existing waypoint.
   - "Delete" to remove selected waypoints.
   - "Duplicate" to copy a waypoint with a new name.
   - "Delete All" to remove every custom waypoint (with confirmation).

3. CREATE AND EDIT ROUTES
   - Go to the "Routes" tab.
   - Route list on the left, detail editor on the right.
   - "+ New" to create a route. Enter a name (max 10 characters).
   - Fill in Origin and Destination (ICAO airport codes).
   - Add waypoints to Main Points using "+ Add" — a search dialog lets
     you find waypoints from custom_data, airports, navaids, or waypoints
     in the nav_data.db.
   - The route is stored in the native C-130J 40-field pipe-delimited
     format. Each waypoint becomes a native tuple automatically.
   - Origin is auto-inserted as the first waypoint; Destination as the
     last. If left empty, they are auto-filled from the first/last
     waypoint.
   - "Save" (💾) to save the route to the database.
   - "Clone" to duplicate a route with a new name.
   - "Back Route" to reverse waypoints and swap Origin/Destination; appends R to
     the route name (replaces last character if name is already 10 chars).
   - Two-waypoint routes (origin + destination only) automatically add the
     destination again in the middle (AAA → BBB becomes AAA, BBB, BBB).
     When origin and destination are the same point, the list keeps two
     entries — origin first, destination last (AAA, FIX1, AAA).
   - "🗺 Show on Map" to visualize the route on the map tab with blue
     markers and a polyline.
   - Flight Plan Calculator (below Main Points): enter speed (kts),
     altitude (ft) and fuel flow (lbs/hr), then Calculate to see per-leg
     distance, time and fuel, plus route totals.

4. USE THE MAP
   - Go to the "Map" tab.
   - Custom waypoints are red circle markers; airports from nav_data.db
     are yellow diamonds with ICAO labels (click for airport info).
     Click a custom waypoint for ID, coordinates, Copy ID, or Add to route.
   - Optional "Fixes" checkbox shows nav fixes/waypoints from nav_data.db
     as small cyan triangles in the current map view (click for ID, name,
     coordinates; Add to route or Copy ID).
   - Use the Tiles dropdown to switch between:
       * DCS theater tiles (Caucasus, Marianas, Nevada, Persian Gulf, Syria,
         Normandy, Germany CW, Marianas WWII)
       * South Atlantic / Falklands (ArcGIS satellite)
       * OpenStreetMap, Google Satellite, ArcGIS Satellite
       * Local MBTiles files (Load MBTiles...)
   - Right-click on the map to create a waypoint at that position.
     Coordinates are auto-filled from the click location (MGRS, DDM,
     and elevation fetched from Open-Meteo API). Use "Save and add to route"
     to save the waypoint and insert it into the active route plan.
   - The status bar at the bottom shows cursor coordinates in DDM, MGRS,
     elevation (ft), zoom level, and ruler bearing/distance when active.
   - Middle-click sets a ruler origin; move the mouse for magnetic heading
     and distance (NM) to the cursor. Esc clears the ruler.
   - "Search" opens the waypoint/airport search dialog and centers the map
     on the selected result.
   - A "Loading map…" message appears while tiles load after pan or zoom.
   - "Refresh" to update markers after external changes.
   - "Center on WPTs" to fit all waypoints in view.

5. SHARE WAYPOINTS AND ROUTES (.dtc PACKAGES)
   - Select waypoints and/or routes to share (Ctrl+Click or Shift+Click
     for multiple selection).
   - DTC Package > Export .dtc package... (Ctrl+E)
     Creates a .dtc file with the selected items.
   - Send the .dtc file to the other pilot.
   - The other pilot opens their user_data.db and uses:
     DTC Package > Import .dtc package... (Ctrl+I)
   - On name conflicts, the program offers:
       * Rename the imported item
       * Rename the existing item
       * Overwrite with the imported item
       * Skip (don't import)

6. IMPORT/EXPORT CSV
   - Import/Export > Import/Export Waypoints or Routes as CSV files.
   - Useful for bulk editing in spreadsheets.

7. SAVE YOUR WORK
   - File > Save (Ctrl+S) — commits changes to the open database.
   - File > Save As... (Ctrl+Shift+S) — save a copy.
   - Close DCS before loading the DTC, and restart DCS after saving
     to see changes in the sim.

8. CONFIGURE DCS PATH
   - File > Configure DCS path...
     Manually set the DCS.C130J folder location if auto-detection
     doesn't find it.
   - The path is saved in chanchita_dtc.ini for future sessions.


TECHNICAL NOTES
---------------
- Elevation (alt) is not used by the C-130J module in the DB.
  DCS always shows the terrain elevation at the MGRS coordinates.
  This is a known module bug.
- The entry_pos (MGRS) field determines the actual waypoint position.
- MGRS coordinates must have 10 digits (5 easting + 5 northing).
- Routes use the native C-130J 40-field pipe-delimited format.
  Each waypoint is a tuple: (NAME|type|lat|lon|speed|...|39 fields).
- The app writes the chanchita_dtc.ini file next to the executable
  to remember settings (DCS path, language, MBTiles path).


================================================================================
  ESPAÑOL
================================================================================

DESCRIPCIÓN
-----------
Chanchita DTC es un editor de waypoints y rutas para el módulo C-130J Hercules
de DCS World. Permite crear, editar, importar y exportar puntos de navegación
y rutas directamente en la base de datos user_data.db del módulo, sin necesidad
de tener DCS abierto.

Además permite compartir waypoints y rutas entre pilotos mediante paquetes .dtc.

La interfaz está disponible en inglés y español. El idioma se selecciona
en el primer inicio y se guarda para futuras sesiones.


INSTALACIÓN
-----------
1. Copiar Chanchita_DTC.exe en cualquier carpeta (ej: G:\Chanchita_DTC\).
2. Ejecutar con doble clic. No requiere Python ni ningún otro software.
3. En el primer inicio, seleccionar el idioma (English / Español).
4. Listo.


TUTORIAL PASO A PASO
--------------------

1. CARGAR LA BASE DE DATOS
   - Archivo > Cargar DTC (Ctrl+L)
     Busca automáticamente user_data.db en Saved Games\DCS.C130J
     de todos los discos. Si la encuentra, la abre directo.
   - Archivo > Abrir BD... (Ctrl+O)
     Abre cualquier archivo .db manualmente.
   - Si hay varias instalaciones de DCS.C130J, aparece un diálogo
     para elegir cuál usar.

2. ADMINISTRAR WAYPOINTS
   - Ir a la pestaña "Waypoints (custom_data)".
   - Se muestran todos los waypoints personalizados con Nombre, MGRS,
     Lat/Lon (DDM) y Elevación (ft).
   - "+ Agregar" para crear un nuevo waypoint:
       * Ingresar nombre (máx 5 caracteres, se usa como ID en DCS).
       * Ingresar coordenadas MGRS (10 dígitos). Lat/Lon se calculan
         automáticamente desde el MGRS.
       * Opcionalmente ingresar Lat/Lon en formato DDM (ej: N 41° 23.456').
       * Opcionalmente ingresar elevación en pies (MSL).
   - "Editar" o doble clic para modificar un waypoint existente.
   - "Eliminar" para borrar waypoints seleccionados.
   - "Duplicar" para copiar un waypoint con nuevo nombre.
   - "Eliminar todo" para borrar todos los waypoints personalizados
     (con confirmación).

3. CREAR Y EDITAR RUTAS
   - Ir a la pestaña "Routes".
   - Lista de rutas a la izquierda, editor de detalle a la derecha.
   - "+ Nueva" para crear una ruta. Ingresar nombre (máx 10 caracteres).
   - Completar Origen y Destino (códigos ICAO de aeropuertos).
   - Agregar waypoints a Main Points usando "+ Agregar" — un buscador
     permite encontrar waypoints en custom_data, airports, navaids o
     waypoints de nav_data.db.
   - La ruta se almacena en el formato nativo del C-130J (40 campos
     separados por pipe). Cada waypoint se convierte automáticamente
     en una tupla nativa.
   - El origen se inserta automáticamente como primer waypoint; el
     destino como último. Si se dejan vacíos, se auto-completan
     desde el primer/último waypoint.
   - "💾 Guardar" para guardar la ruta en la base de datos.
   - "Clonar" para duplicar una ruta con nuevo nombre.
   - "Ruta inversa" invierte waypoints e intercambia Origen/Destino; agrega R al
     nombre (reemplaza el último carácter si el nombre tiene 10 chars).
   - Rutas de solo origen y destino agregan automáticamente el destino en el
     medio (AAA → BBB pasa a ser AAA, BBB, BBB). Si origen y destino son el
     mismo punto, la lista queda con dos entradas — origen primero, destino
     al final (AAA, FIX1, AAA).
   - "🗺 Ver en Mapa" para visualizar la ruta en la pestaña del mapa
     con marcadores azules y una polilínea.
   - Calculadora de plan de vuelo (debajo de Main Points): ingresar
     velocidad (kts), altitud (ft) y flujo de combustible (lbs/hr);
     Calcular muestra distancia, tiempo y combustible por tramo y totales.

4. USAR EL MAPA
   - Ir a la pestaña "Mapa".
   - Los waypoints personalizados son círculos rojos; los aeropuertos de
     nav_data.db son rombos amarillos con etiqueta ICAO (clic para info).
     Clic en un waypoint personalizado: ID, coordenadas, Copiar ID o
     Agregar a ruta.
   - Casilla opcional "Fixes" muestra fixes/waypoints de nav_data.db como
     triángulos cian en el área visible del mapa (clic para ID, nombre,
     coordenadas; Agregar a ruta o Copiar ID).
   - Usar el desplegable Tiles para cambiar entre:
       * Tiles de teatros DCS (Caucasus, Marianas, Nevada, Persian Gulf,
         Syria, Normandy, Germany CW, Marianas WWII)
       * South Atlantic / Falklands (satélite ArcGIS)
       * OpenStreetMap, Google Satélite, ArcGIS Satélite
       * Archivos MBTiles locales (Cargar MBTiles...)
   - Click derecho en el mapa para crear un waypoint en esa posición.
     Las coordenadas se auto-completan desde la posición del clic
     (MGRS, DDM y elevación obtenida de la API Open-Meteo). "Guardar y
     agregar a ruta" guarda el waypoint y lo inserta en el plan de vuelo.
   - La barra de estado inferior muestra las coordenadas del cursor
     en DDM, MGRS, elevación (ft), zoom y regla (rumbo/distancia) si está activa.
   - Clic medio fija el origen de la regla; mover el mouse muestra rumbo
     magnético y distancia (NM). Esc borra la regla.
   - "Buscar" abre el diálogo de búsqueda y centra el mapa en el resultado.
   - Aparece "Cargando mapa…" mientras cargan los tiles al mover o hacer zoom.
   - "Actualizar" para refrescar los marcadores después de cambios.
   - "Centrar en WPTs" para ajustar la vista a todos los waypoints.

5. COMPARTIR WAYPOINTS Y RUTAS (Paquetes .dtc)
   - Seleccionar waypoints y/o rutas a compartir (Ctrl+Click o
     Shift+Click para selección múltiple).
   - Paquete DTC > Exportar paquete .dtc... (Ctrl+E)
     Genera un archivo .dtc con los elementos seleccionados.
   - Enviar el archivo .dtc al otro piloto.
   - El otro piloto abre su user_data.db y usa:
     Paquete DTC > Importar paquete .dtc... (Ctrl+I)
   - Si hay conflictos de nombres, el programa pregunta:
       * Renombrar el importado
       * Renombrar el existente
       * Sobrescribir con el importado
       * Omitir (no importar)

6. IMPORTAR/EXPORTAR CSV
   - Importar/Exportar > Importar/Exportar waypoints o rutas como CSV.
   - Útil para edición masiva en hojas de cálculo.

7. GUARDAR CAMBIOS
   - Archivo > Guardar (Ctrl+S) — guarda los cambios en la BD abierta.
   - Archivo > Guardar como... (Ctrl+Shift+S) — guarda una copia.
   - Cerrar DCS antes de cargar el DTC, y reiniciar DCS después de
     guardar para ver los cambios en el simulador.

8. CONFIGURAR RUTA DCS
   - Archivo > Configurar ruta DCS...
     Para cambiar manualmente la ubicación de Saved Games\DCS.C130J
     si la detección automática no la encuentra.
   - La ruta se guarda en chanchita_dtc.ini para futuras sesiones.


NOTAS TÉCNICAS
--------------
- La elevación (alt) no es utilizada por el módulo C-130J en la BD.
  DCS siempre muestra la elevación del terreno en las coordenadas MGRS.
  Esto es un bug conocido del módulo.
- El campo entry_pos (MGRS) determina la posición real del waypoint.
- Las coordenadas MGRS deben tener 10 dígitos (5 easting + 5 northing).
- Las rutas usan el formato nativo del C-130J (40 campos pipe-delimited).
  Cada waypoint es una tupla: (NOMBRE|tipo|lat|lon|velocidad|...|39 campos).
- La app escribe chanchita_dtc.ini junto al ejecutable para recordar
  configuración (ruta DCS, idioma, ruta MBTiles).


================================================================================

LOG DE VERSIÓN / VERSION LOG
-----------------------------
Alpha 0.2l (260627)
  - Routes: same Origin and Destination — origin stays first, destination
    last; enroute waypoints insert between them (AAA, FIX1, AAA).

Alpha 0.2k (260627)
  - Map: smoother panning — tile loading and fix refresh deferred until drag ends.
  - Map: click custom waypoint — popup with Copy ID and Add to route.
  - Map: mouse wheel zoom steps one level at a time (Z:9 → 10 → 11; fixes skip).
  - Map: Fixes layer viewport bounds corrected (tile-based query).

Alpha 0.2j (260627)
  - Map: optional Fixes layer — nav_data waypoints as cyan triangles in the
    current view; click for info, Copy ID, or Add to route.
  - Map: right-click Create waypoint — "Save and add to route" button.
  - Routes: when Origin and Destination are the same point, Add to route,
    save, and load keep two list entries (AAA, AAA).
  - Routes: Add to route no longer treats ICAO vs DCS alias as a duplicate
    skip when they refer to the same airport.

Alpha 0.2i (260627)
  - Waypoints / Routes: Delete now removes all selected items (multi-select with
    Ctrl+Click or Shift+Click), not only the first.

Alpha 0.2h (260627)
  - Routes: Back Route — reverse Main Points, swap Origin/Destination, suffix name with R
    (at 10 chars, last character becomes R).
  - Routes: origin+destination only routes auto-insert destination in the middle
    (AAA, BBB → AAA, BBB, BBB) for C-130J flight plan format.

Alpha 0.2g (260626)
  - Routes: Flight Plan Calculator — leg distances (NM), time per leg and total,
    fuel per leg and total (lbs); inputs for speed (kts), altitude (ft), fuel flow (lbs/hr).
  - Calculator auto-updates when Main Points change or a route is loaded.

Alpha 0.2f (260626)
  - Map: fix airport click opening two dialog windows.
  - Map: opening another airport closes the previous info dialog first.
  - Map: Search button — find waypoint/airport/navaid and center the map on it.

Alpha 0.2e (260626)
  - Routes: Set Origin / Destination / Add to route now update Main Points
    immediately (flight plan list), not only on Save.
  - Map: ruler tool — middle-click sets origin; cursor shows magnetic heading
    and distance (NM); Esc or second middle-click on origin clears.
  - Map: "Loading map…" overlay while tiles load after pan, zoom, or layer change.

Alpha 0.2d (260626)
  - Map: clickable airport markers from nav_data.db (ICAO labels + info panel).
  - Airport popup actions: Copy ICAO, Add to route, Set Origin, Set Destination.
  - Map: new tile layers — DCS Normandy, Germany CW, Marianas WWII (dcsolympus.com),
    South Atlantic / Falklands (ArcGIS satellite).
  - Waypoints tab: Delete All button (clears all custom_data with confirmation).
  - Map: reliable airport click detection on icon and ICAO text.

Alpha 0.2c (260424)
  - Map auto-centers on selected DCS theater.
  - Waypoint name conflict now asks to overwrite instead of erroring.

Alpha 0.2b (260414)
  - Full English/Spanish i18n (language picker on first launch).
  - Bilingual README with step-by-step tutorial.

Alpha 0.2 (260413)
  - CDU-style interface: dark background with green/amber text and Consolas font.
  - Menus, tables, tabs and text fields with unified theme.
  - DCS map tiles: Caucasus, Marianas, Nevada, Persian Gulf and Syria.
    (source: maps.bigbeautifulboards.com, max zoom level 15)
  - Native C-130J 40-field route format support.
  - Clone route, view route on map features.
  - Origin/Destination auto-sync with waypoint list.

Alpha 0.1 (260504)
  - Initial version.
  - Waypoint editor with table and edit dialog.
  - Route editor with editable fields.
  - Lat/Lon coordinates shown in DDM format.
  - Automatic MGRS → Lat/Lon conversion.
  - MGRS validation (10 digits required).
  - Import/Export waypoints and routes as CSV.
  - .dtc package system for sharing between pilots.
  - Conflict resolution on import (rename, overwrite, skip).
  - Auto-detection of user_data.db in Saved Games\DCS.C130J.
  - Quick "Load DTC" and "Save" buttons for module DB access.
  - Compiled to .exe (no Python required).

================================================================================
