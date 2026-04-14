import sqlite3, configparser, os

cfg = configparser.ConfigParser()
ini = 'chanchita_dtc.ini'
if os.path.isfile(ini):
    cfg.read(ini, encoding='utf-8')
    print('INI contents:')
    for s in cfg.sections():
        for k,v in cfg.items(s):
            print(f'  [{s}] {k} = {v}')
else:
    print('No INI file found')

nav_paths = [
    r'F:\Eagle Dynamics\DCS World\Mods\aircraft\C130J\Cockpit\Resources\nav_data.db',
    r'F:\Eagle Dynamics\DCS World OpenBeta\Mods\aircraft\C130J\Cockpit\Resources\nav_data.db',
    r'C:\Program Files\Eagle Dynamics\DCS World\Mods\aircraft\C130J\Cockpit\Resources\nav_data.db'
]

found = False
for nav_path in nav_paths:
    if os.path.isfile(nav_path):
        print(f'\nnav_data found at: {nav_path}')
        found = True
        try:
            c = sqlite3.connect(nav_path)
            cur = c.cursor()
            cur.execute("SELECT icao, lat, lon FROM airports WHERE UPPER(icao) LIKE '%UG%' LIMIT 10")
            print('Airports matching UG:')
            for r in cur.fetchall():
                print(f'  {r}')
            cur.execute("SELECT name, lat, lon, type FROM navaids WHERE UPPER(name) LIKE '%UG%' LIMIT 10")
            print('Navaids matching UG:')
            for r in cur.fetchall():
                print(f'  {r}')
            c.close()
            break
        except Exception as e:
            print(f"Error: {e}")

if not found:
    print('\nnav_data.db not found in common locations.')
