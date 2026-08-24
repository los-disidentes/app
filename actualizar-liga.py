#!/usr/bin/env python3
"""
Actualiza fixture-5A/5B.json y standings-5A/5B.json desde la web de la Liga.

Corre solo, una vez por día, desde GitHub Actions. También se puede correr a mano:

    pip install requests beautifulsoup4
    python actualizar-liga.py            # escribe si hay cambios
    python actualizar-liga.py --dry-run  # sólo muestra qué cambiaría

POR QUÉ ESTE ARCHIVO EXISTE
La app lee JSON estáticos del repo. Hasta ahora había que actualizarlos a mano
después de cada fecha, y eso significaba que el equipo veía datos viejos hasta
que alguien se acordara.

CÓMO LEE LA PÁGINA
La página de la Liga es server-rendered: el HTML ya trae las 11 fechas y la tabla
completas, aunque el carrusel muestre sólo 3 fechas por vez. No hace falta un
navegador. Los selectores (.alt-round, .alt-match, table.alt-table) se verificaron
contra el DOM real antes de escribir esto.

REGLA DE ORO
Este script NUNCA escribe un archivo que no pase las validaciones. Ante la duda,
deja los datos como están: que la app muestre algo viejo es molesto, que muestre
algo incorrecto es peor. Un equipo que ve una formación mal armada puede perder
puntos por el Art. 16.1.
"""

import argparse, json, re, sys, unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TORNEO = 329
EQUIPOS = {
    '5A': {'campeonato': 4302, 'nombre': 'Miralagos Los Disidentes A', 'zona': 'Quinta A Zona 2'},
    '5B': {'campeonato': 4304, 'nombre': 'Miralagos Los Disidentes B', 'zona': 'Quinta B Zona 2'},
}
# OJO: la página /tenis?torneo=..&campeonato=.. IGNORA esos parámetros del lado del
# servidor. Un fetch plano devuelve siempre una categoría por defecto (aparecían
# Ducilo, Abril, Grand Bell y ningún Disidentes). El navegador ve lo correcto
# porque después pide este endpoint, que sí lleva campeonato y torneo en la ruta
# y devuelve el fragmento HTML con la tabla y las 11 fechas de esa zona.
BASE = 'https://ligacountrysur.com.ar/liga/tabla-resultados-alt'
# Sin User-Agent de navegador el sitio (detrás de Cloudflare) puede no responder.
CABECERAS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'es-AR,es;q=0.9',
}
MESES = {'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,'julio':7,
         'agosto':8,'septiembre':9,'setiembre':9,'octubre':10,'noviembre':11,'diciembre':12}

avisos = []


def limpiar(s):
    """Normaliza espacios y saca la basura que la Liga a veces deja al final
    del nombre de un equipo (apareció 'La Martona La Sorprendeta_')."""
    return re.sub(r'\s+', ' ', (s or '')).strip().rstrip('_').strip()


def sin_acentos(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '')
                   if unicodedata.category(c) != 'Mn').lower()


def normalizar_hora(h):
    """'10:00hs' → '10:00' · '9hs' → '09:00' · '' → ''
    La app parsea con /^(\\d{1,2}):(\\d{2})/, así que el formato importa."""
    m = re.search(r'(\d{1,2})(?::(\d{2}))?', h or '')
    return f"{int(m.group(1)):02d}:{m.group(2) or '00'}" if m else ''


def parsear_fecha(texto, anio):
    """'domingo 23 de agosto' + 2026 → '2026-08-23'.
    La Liga no publica el año, así que se toma del dato que ya teníamos."""
    t = sin_acentos(texto)
    m = re.search(r'(\d{1,2})\s+de\s+([a-z]+)', t)
    if not m:
        return None
    mes = MESES.get(m.group(2))
    return f'{anio}-{mes:02d}-{int(m.group(1)):02d}' if mes else None


def bajar(campeonato):
    url = f'{BASE}/{campeonato}/{TORNEO}'
    r = requests.get(url, headers=CABECERAS, timeout=45)
    r.raise_for_status()
    if 'alt-table' not in r.text:
        raise RuntimeError(f'la respuesta no tiene la tabla esperada ({len(r.text)} bytes)')
    return BeautifulSoup(r.text, 'html.parser')


def leer_fixture(sopa):
    """Todos los partidos de la zona, agrupados por fecha."""
    partidos = []
    for ronda in sopa.select('.alt-round'):
        badge = ronda.select_one('.alt-round-badge')
        if not badge:
            continue
        digitos = re.sub(r'\D', '', badge.get_text())
        if not digitos:
            continue
        rueda = int(digitos)
        cab = ronda.select_one('.alt-round-date')
        dia = limpiar(cab.get_text()) if cab else ''
        for m in ronda.select('.alt-match'):
            d = m.select_one('.alt-match-desktop') or m
            def txt(sel):
                e = d.select_one(sel)
                return limpiar(e.get_text()) if e else ''
            marcador = re.search(r'(\d+)\s*[–-]\s*(\d+)', txt('.score-pill'))
            partidos.append({
                'rueda': rueda, 'dia': dia,
                'hora': normalizar_hora(txt('.amd-time')),
                'local': txt('.amd-local'), 'visitor': txt('.amd-visitor'),
                'gL': int(marcador.group(1)) if marcador else 0,
                'gV': int(marcador.group(2)) if marcador else 0,
                'played': 'alt-match--played' in (m.get('class') or []),
                'estado': txt('.amd-status'),
            })
    return partidos


def leer_tabla(sopa):
    """La tabla de posiciones. `span.team-nm` ya trae el nombre sin la sigla
    que la web antepone ('SR Santa Rita')."""
    filas = []
    for tr in sopa.select('table.alt-table tbody tr'):
        pos, nom = tr.select_one('.rank-pill'), tr.select_one('.team-nm')
        if not pos or not nom:
            continue
        n = [td.get_text().strip() for td in tr.select('td')][2:]
        if len(n) < 9:
            continue
        filas.append({'Posicion': limpiar(pos.get_text()), 'Equipo': limpiar(nom.get_text()),
                      'Jugados': n[0], 'Ganados': n[1], 'Perdidos': n[2],
                      'PuntosFavor': n[3], 'PuntosContra': n[4], 'diferencia': n[5],
                      'Puntos': n[8]})
    return filas


def armar_fixture(partidos, eq, actual):
    """Deja el fixture con nuestros partidos, conservando id y año.
    Se empareja por número de fecha, que es lo único estable."""
    nombre = EQUIPOS[eq]['nombre']
    mios = [p for p in partidos if nombre in (p['local'], p['visitor'])]
    por_rueda = {p['rueda']: p for p in mios}
    previos = {m['rueda']: m for m in actual}
    salida = []
    for rueda in sorted(por_rueda):
        p, viejo = por_rueda[rueda], previos.get(rueda, {})
        anio = (viejo.get('fecha') or '2026')[:4]
        fecha = parsear_fecha(p['dia'], anio) or viejo.get('fecha')
        if viejo.get('fecha') and fecha != viejo['fecha']:
            avisos.append(f'{eq} F{rueda}: la Liga movió la fecha, {viejo["fecha"]} → {fecha}')
        salida.append({'id': f'{eq}-{rueda}', 'rueda': rueda, 'fecha': fecha,
                       'hora': p['hora'], 'local': p['local'], 'visitor': p['visitor'],
                       'gL': p['gL'], 'gV': p['gV'], 'played': p['played']})
    return salida


def validar(eq, fixture, tabla):
    """Las mismas invariantes que qa-check.js. Si algo no da, no se escribe nada."""
    nombre = EQUIPOS[eq]['nombre']
    err = []
    if not fixture:
        err.append('fixture vacío')
    if not tabla:
        err.append('tabla vacía')
    if err:
        return err

    for m in fixture:
        if nombre not in (m['local'], m['visitor']):
            err.append(f'F{m["rueda"]}: no jugamos ese partido')
        if m['local'] == m['visitor']:
            err.append(f'F{m["rueda"]}: un equipo contra sí mismo')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', m['fecha'] or ''):
            err.append(f'F{m["rueda"]}: fecha inválida ({m["fecha"]})')
        if m['hora'] and not re.fullmatch(r'\d{2}:\d{2}', m['hora']):
            err.append(f'F{m["rueda"]}: hora inválida ({m["hora"]})')
        for k in ('gL', 'gV'):
            if not isinstance(m[k], int) or not 0 <= m[k] <= 3:
                err.append(f'F{m["rueda"]}: marcador fuera de rango ({m[k]})')
        if not m['played'] and (m['gL'] or m['gV']):
            err.append(f'F{m["rueda"]}: tiene resultado pero figura sin jugar')

    if len({m['rueda'] for m in fixture}) != len(fixture):
        err.append('hay fechas repetidas')
    if not any(t['Equipo'] == nombre for t in tabla):
        err.append(f'{nombre} no aparece en la tabla')
    if len({t['Equipo'] for t in tabla}) != len(tabla):
        err.append('equipos repetidos en la tabla')
    if [int(t['Posicion']) for t in tabla] != list(range(1, len(tabla) + 1)):
        err.append('las posiciones no van 1..N')

    equipos = {t['Equipo'] for t in tabla}
    faltan = {m['local'] for m in fixture} | {m['visitor'] for m in fixture} - equipos
    faltan = {r for r in faltan if r not in equipos}
    if faltan:
        err.append(f'rivales del fixture que no están en la tabla: {sorted(faltan)}')

    # Coherencia fixture ↔ tabla: caza el resultado cargado en un solo lado
    yo = next((t for t in tabla if t['Equipo'] == nombre), None)
    if yo:
        jugados = [m for m in fixture if m['played']]
        if int(yo['Jugados']) != len(jugados):
            err.append(f'jugados no coinciden: fixture {len(jugados)}, tabla {yo["Jugados"]}')
        pf = sum(m['gL'] if m['local'] == nombre else m['gV'] for m in jugados)
        pc = sum(m['gV'] if m['local'] == nombre else m['gL'] for m in jugados)
        if (int(yo['PuntosFavor']), int(yo['PuntosContra'])) != (pf, pc):
            err.append(f'parciales no coinciden: fixture {pf}-{pc}, tabla '
                       f'{yo["PuntosFavor"]}-{yo["PuntosContra"]}')
    return err


def escribir(ruta, datos, dry):
    nuevo = json.dumps(datos, ensure_ascii=False, separators=(',', ':'))
    anterior = ruta.read_text(encoding='utf-8') if ruta.exists() else None
    if nuevo == anterior:
        return False
    if not dry:
        ruta.write_text(nuevo, encoding='utf-8')
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--dir', default='.')
    args = ap.parse_args()
    raiz = Path(args.dir)
    cambios, fallas = [], []

    for eq, cfg in EQUIPOS.items():
        print(f'\n=== {eq} · {cfg["zona"]} (campeonato {cfg["campeonato"]}) ===')
        try:
            sopa = bajar(cfg['campeonato'])
            partidos, tabla = leer_fixture(sopa), leer_tabla(sopa)
        except Exception as e:
            fallas.append(f'{eq}: no se pudo leer la Liga — {e}')
            print(f'  ✗ {e}')
            continue

        rf, rt = raiz / f'fixture-{eq}.json', raiz / f'standings-{eq}.json'
        actual = json.loads(rf.read_text(encoding='utf-8')) if rf.exists() else []
        fixture = armar_fixture(partidos, eq, actual)
        print(f'  leídos {len(partidos)} partidos de la zona · {len(fixture)} nuestros · '
              f'{sum(1 for m in fixture if m["played"])} jugados · tabla {len(tabla)} equipos')

        # Nunca achicar: si la Liga devuelve menos fechas que las que ya teníamos,
        # es mucho más probable que sea un error de lectura que un cambio real.
        if actual and len(fixture) < len(actual):
            fallas.append(f'{eq}: la Liga devolvió {len(fixture)} fechas y teníamos '
                          f'{len(actual)}. No se toca nada.')
            print(f'  ✗ menos fechas que antes, se aborta')
            continue

        errores = validar(eq, fixture, tabla)
        if errores:
            fallas.append(f'{eq}: ' + ' · '.join(errores))
            print('  ✗ no pasa validación:')
            for e in errores:
                print(f'      {e}')
            continue

        for ruta, datos, que in ((rf, fixture, 'fixture'), (rt, tabla, 'tabla')):
            if escribir(ruta, datos, args.dry_run):
                cambios.append(f'{eq} {que}')
                print(f'  ✓ {que} actualizado')
            else:
                print(f'  = {que} sin cambios')

    print('\n' + '─' * 58)
    for a in avisos:
        print(f'⚠  {a}')
    if fallas:
        for f in fallas:
            print(f'✗  {f}')
        print('\nHubo problemas: no se escribió nada de lo que falló.')
        return 1
    print(('Cambios: ' + ', '.join(cambios)) if cambios else 'Sin cambios.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
