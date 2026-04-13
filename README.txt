================================================================================
                         CHANCHITA DTC - C-130J Hercules
                     Data Transfer Cartridge Editor para DCS
================================================================================

DESCRIPCIÓN
-----------
Chanchita DTC es un editor de waypoints y rutas para el módulo C-130J Hercules
de DCS World. Permite crear, editar, importar y exportar puntos de navegación
y rutas directamente en la base de datos user_data.db del módulo, sin necesidad
de tener DCS abierto.

Además permite compartir waypoints y rutas entre pilotos mediante paquetes .dtc.


INSTALACIÓN
-----------
1. Copiar Chanchita_DTC.exe en cualquier carpeta (ej: G:\Chanchita_DTC\).
2. Ejecutar con doble clic. No requiere Python ni ningún otro software.
3. Listo.


USO
---
CARGAR BASE DE DATOS:
  - Archivo > Cargar DTC (Ctrl+L)
    Busca automáticamente user_data.db en la carpeta Saved Games\DCS.C130J
    de todos los discos. Si la encuentra, la abre directo.
  - Archivo > Abrir BD... (Ctrl+O)
    Abre cualquier archivo .db manualmente.

GUARDAR CAMBIOS:
  - Archivo > Guardar (Ctrl+S)
    Guarda los cambios en el archivo abierto.
  - Archivo > Guardar como... (Ctrl+Shift+S)
    Guarda una copia en otra ubicación.

WAYPOINTS:
  - Pestaña "Waypoints" muestra todos los puntos personalizados.
  - Coordenadas se muestran en formato DDM (N 41° 23.456') en pantalla.
  - En la BD se guardan en grados decimales.
  - "Agregar" para crear un nuevo waypoint. Ingresar nombre (máx 5 caracteres)
    y coordenadas MGRS (10 dígitos). Lat/Lon se calculan automáticamente.
  - "Editar" o doble clic para modificar un waypoint existente.
  - "Eliminar" para borrar waypoints seleccionados.
  - "Duplicar" para copiar un waypoint con nuevo nombre.

RUTAS:
  - Pestaña "Routes" muestra todas las rutas guardadas.
  - Lista de rutas a la izquierda, editor de detalle a la derecha.
  - Campos main_pts y alt_pts contienen los waypoints de la ruta en formato
    interno del C-130J (pipe-delimited).

COMPARTIR WAYPOINTS Y RUTAS (Paquetes .dtc):
  - Seleccionar waypoints y/o rutas a compartir.
  - Paquete DTC > Exportar paquete .dtc (Ctrl+E)
    Genera un archivo .dtc con los elementos seleccionados.
  - Enviar el archivo .dtc al otro piloto.
  - El otro piloto abre su user_data.db y usa:
    Paquete DTC > Importar paquete .dtc (Ctrl+I)
  - Si hay conflictos de nombres, el programa pregunta:
      * Renombrar el importado
      * Renombrar el existente
      * Sobrescribir
      * Omitir

IMPORTAR/EXPORTAR CSV:
  - Importar/Exportar > Importar/Exportar waypoints o rutas en formato CSV.

CONFIGURAR RUTA DCS:
  - Archivo > Configurar ruta DCS...
    Para cambiar manualmente la ubicación de Saved Games\DCS.C130J si la
    detección automática no la encuentra.
  - La ruta se guarda en chanchita_dtc.ini para futuras sesiones.


NOTAS TÉCNICAS
--------------
- La elevación (alt) no es utilizada por el módulo C-130J en la BD.
  DCS siempre muestra la elevación del terreno del mapa en las coordenadas
  MGRS del waypoint. Esto es un bug conocido del módulo.
- El campo entry_pos (MGRS) es el que determina la posición real del waypoint.
- Las coordenadas MGRS deben tener 10 dígitos (5 easting + 5 northing).


LOG DE VERSIÓN
--------------
Alpha 0.2 (260413)
  - Interfaz estilo CDU: fondo oscuro con texto verde/ámbar y fuente Consolas.
  - Menús, tablas, pestañas y campos de texto con tema unificado.
  - Tiles de mapas DCS: Caucasus, Marianas, Nevada, Persian Gulf y Syria.
    (fuente: maps.bigbeautifulboards.com, zoom máximo nivel 15)

Alpha 0.1 (260504)
  - Versión inicial.
  - Editor de waypoints con tabla y diálogo de edición.
  - Editor de rutas con campos editables.
  - Coordenadas Lat/Lon mostradas en formato DDM (grados y minutos decimales).
  - Conversión automática MGRS → Lat/Lon al guardar waypoints.
  - Validación de MGRS (10 dígitos requeridos).
  - Importar/Exportar waypoints y rutas en CSV.
  - Sistema de paquetes .dtc para compartir waypoints y rutas entre pilotos.
  - Resolución de conflictos al importar (renombrar, sobrescribir, omitir).
  - Detección automática de user_data.db en Saved Games\DCS.C130J.
  - Botón "Cargar DTC" y "Guardar" para acceso rápido a la BD del módulo.
  - Compilado a .exe (no requiere Python).

================================================================================
