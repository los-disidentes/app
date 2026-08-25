#!/usr/bin/env python3
"""Tests de leer_detalle() y validar_resultados() con el HTML real de la Liga.

Se escribió después del incidente del 24/08/2026: la ficha de San Eliseo vs
Disidentes B traía 'TB 0 - 0' en las tres canchas, el parser la contaba como un
set y la validación rechazaba el partido entero. La 5B quedó sin estadísticas.

Los fragmentos de HTML de abajo se copiaron del DOM real de
ligacountrysur.com.ar/liga/ver-resultado/{hash}, no son inventados.
"""
import sys, types, importlib.util
from pathlib import Path

# --- Stub de requests: los tests no salen a internet -------------------------
RESPUESTAS = {}


class _Resp:
    def __init__(self, texto):
        self.text = texto

    def raise_for_status(self):
        pass


def _get(url, **kw):
    for clave, html in RESPUESTAS.items():
        if clave in url:
            return _Resp(html)
    raise AssertionError(f'el test no esperaba esta URL: {url}')


falso = types.ModuleType('requests')
falso.get = _get
sys.modules['requests'] = falso

spec = importlib.util.spec_from_file_location('liga', Path(__file__).parent / 'actualizar-liga.py')
liga = importlib.util.module_from_spec(spec)
spec.loader.exec_module(liga)


# --- Fragmentos de HTML real -------------------------------------------------
def cancha(n, local, visitante, filas):
    sets = ''.join(f'<div class="dr-set won"><span>{r}</span>{a} - {b}</div>'
                   for r, a, b in filas)
    return f'''
    <div class="dr-tenis-match">
      <span class="dr-modalidad-tag">Dobles {n}</span>
      <div class="dr-tenis-side"><span class="dr-tenis-side-name">{local}</span></div>
      <div class="dr-tenis-side"><span class="dr-tenis-side-name">{visitante}</span></div>
      {sets}
    </div>'''


L1 = 'della Paolera, Tomás (1), Prots, Gustavo martin (3)'
V1 = 'correa, sebastian (1), ROLANDI, ALEJANDRO (2)'
L2 = 'Spyrakis, Leonardo (2), Almada, Alfredo Ruben (4)'
V2 = 'ESPELET, SEBASTIAN (3), Latorre, Leandro (4)'
L3 = 'Colombo, Carlos Alberto (5), Mortarini, Jorge Alberto (6)'
V3 = 'CERULLI, GUSTAVO (5), Connell, Facundo (6)'

# San Eliseo 3-0 Disidentes B — el caso que rompía: TB vacío en las 3 canchas
HTML_B = (cancha(1, L1, V1, [('1°', 6, 0), ('2°', 6, 0), ('TB', 0, 0)]) +
          cancha(2, L2, V2, [('1°', 6, 1), ('2°', 6, 2), ('TB', 0, 0)]) +
          cancha(3, L3, V3, [('1°', 6, 3), ('2°', 6, 4), ('TB', 0, 0)]))

# Santa Rita 3-0 Disidentes A — la ficha vieja, sin fila TB. No se debe alterar.
HTML_A = (cancha(1, L1, V1, [('1°', 6, 2), ('2°', 6, 2)]) +
          cancha(2, L2, V2, [('1°', 6, 2), ('2°', 6, 2)]) +
          cancha(3, L3, V3, [('1°', 6, 1), ('2°', 6, 1)]))

# Cancha definida por super tiebreak, ganada por el visitante
HTML_TB = cancha(1, L1, V1, [('1°', 6, 4), ('2°', 4, 6), ('TB', 8, 10)])

RESPUESTAS.update({'HASH-B': HTML_B, 'HASH-A': HTML_A, 'HASH-TB': HTML_TB})

fallos = []


def check(nombre, cond, detalle=''):
    print(('  ✓ ' if cond else '  ✗ ') + nombre + (f'  → {detalle}' if not cond and detalle else ''))
    if not cond:
        fallos.append(nombre)


print('\n1. El TB vacío ya no se cuenta como set (el bug de la 5B)')
b = liga.leer_detalle('HASH-B')
check('lee las 3 canchas', len(b) == 3, len(b))
check('D1 guarda 2 sets, no 3', b[0]['sets'] == [[6, 0], [6, 0]], b[0]['sets'])
check('D1 no guarda tb', 'tb' not in b[0], b[0].get('tb'))
check('ningún set empatado', all(s[0] != s[1] for c in b for s in c['sets']))
check('las 3 las ganó el local', all(c['ganoLocal'] for c in b))

print('\n2. Ese partido ahora pasa la validación')
res_b = [{'id': '5B-1', 'rueda': 1, 'fecha': '2026-08-23',
          'local': 'San Eliseo', 'visitor': 'Miralagos Los Disidentes B', 'canchas': b}]
err_b = liga.validar_resultados('5B', res_b)
check('sin errores de validación', err_b == [], err_b)

print('\n3. La 5A no cambia (ficha sin TB)')
a = liga.leer_detalle('HASH-A')
check('D1 sigue 6-2 6-2', a[0]['sets'] == [[6, 2], [6, 2]], a[0]['sets'])
check('sigue sin clave tb', all('tb' not in c for c in a))
res_a = [{'id': '5A-1', 'rueda': 1, 'fecha': '2026-08-23',
          'local': 'Santa Rita', 'visitor': 'Miralagos Los Disidentes A', 'canchas': a}]
check('sigue validando', liga.validar_resultados('5A', res_a) == [])

print('\n4. Super tiebreak con números: define la cancha, no suma games')
t = liga.leer_detalle('HASH-TB')[0]
check('guarda sólo los 2 sets reales', t['sets'] == [[6, 4], [4, 6]], t['sets'])
check('guarda el tb aparte', t.get('tb') == [8, 10], t.get('tb'))
check('ganó el visitante', t['ganoLocal'] is False, t['ganoLocal'])
games = sum(s[0] + s[1] for s in t['sets'])
check('games = 20, sin contar el tb', games == 20, games)
res_t = [{'id': '5B-9', 'rueda': 9, 'fecha': '2026-11-01',
          'local': 'Miralagos Los Disidentes B', 'visitor': 'X', 'canchas': [t]}]
check('el tb válido pasa validación', liga.validar_resultados('5B', res_t) == [])

print('\n5. Un tb empatado con números sí se rechaza (la guarda sigue viva)')
malo = dict(t, tb=[7, 7])
res_m = [{'id': '5B-9', 'rueda': 9, 'fecha': '2026-11-01',
          'local': 'Miralagos Los Disidentes B', 'visitor': 'X', 'canchas': [malo]}]
check('rechaza tiebreak empatado', liga.validar_resultados('5B', res_m) != [])

print('\n6. Los nombres y números de jugador siguen bien')
check('D1 local, 2 jugadores', len(b[0]['local']) == 2, b[0]['local'])
check('respeta el (n) del reglamento',
      [j['n'] for j in b[0]['local']] == [1, 3], b[0]['local'])
check('nombre limpio', b[0]['visitante'][0]['nombre'] == 'correa, sebastian',
      b[0]['visitante'][0]['nombre'])

print()
if fallos:
    print(f'✗ {len(fallos)} test(s) fallaron: ' + ' · '.join(fallos))
    sys.exit(1)
print('✅ TODO OK')
