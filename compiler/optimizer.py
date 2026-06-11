import re
import math
from typing import List, Optional, Tuple


class OptStats:
    def __init__(self):
        self.unrolled_loops = 0
        self.unrolled_iterations = 0
        self.renamed = 0
        self.reordered = 0
        self.instr_before = 0
        self.instr_after = 0

    def _count_instrs(self, lines):
        """Cuenta solo instrucciones ejecutables reales, excluyendo etiquetas y anotaciones del compilador."""
        count = 0
        for l in lines:
            s = l.strip()
            if not s:
                continue
            if s.endswith(':'):
                continue
            if s.startswith('LOOP_'):
                continue
            if s.startswith('#'):
                continue
            count += 1
        return count

    def __str__(self):
        return "\n".join([
            "Estadisticas de Optimizacion",
            f"  Instrucciones antes    : {self.instr_before}",
            f"  Instrucciones despues  : {self.instr_after}",
            f"  Loops desenrollados    : {self.unrolled_loops}",
            f"  Iteraciones extra      : {self.unrolled_iterations}",
            f"  Temporales renombrados : {self.renamed}",
            f"  Instrucciones reordenadas: {self.reordered}",
        ])


#Funciones auxiliares
def get_def(instr: str) -> Optional[str]:
    #Obtiene la variable que se está definiendo en una instrucción
    s = instr.strip()

    if (not s or s.endswith(':') or s.startswith('LOOP_') or s.startswith('#')
            or s.startswith('goto') or s.startswith('if')
            or s.startswith('iffalse')
            or s.startswith('param') or s.startswith('return')
            or s.startswith('call ')):
        return None

    if '=' in s and '[' in s.split('=')[0]:
        return None

    m = re.match(r'^(\w+)\s*=', s)
    return m.group(1) if m else None


def _is_var(s: str) -> bool:
    #Verifica si el texto corresponde a un identificador válido
    if re.match(r'^\d+$', s):
        return False

    if re.match(r'^0x[0-9a-fA-F]+$', s):
        return False

    if s in (
        'goto', 'if', 'iffalse',
        'return', 'param', 'call',
        'true', 'false'
    ):
        return False

    return bool(re.match(r'^[a-zA-Z_]\w*$', s))


def _rename_temps(line: str, prefix: str) -> str:
    #Agrega un prefijo a los temporales para evitar colisiones
    return re.sub(
        r'\bt(\d+)\b',
        lambda m: f't{prefix}{m.group(1)}',
        line
    )


def _substitute_var(lines: List[str], var: str, value: int) -> List[str]:
    #Sustituye la variable del loop por un valor entero constante
    return [re.sub(r'\b' + re.escape(var) + r'\b', str(value), l) for l in lines]


def _parse_loop_body(body: List[str], var: str, step_val: int) -> Optional[dict]:
    #Parsea el cuerpo de un loop e identifica sus partes:
    #init, label, cond_lines, work_lines, update_lines, goto_line, after_goto
    parts = {
        'init': [],
        'label': None,
        'cond_lines': [],
        'work_lines': [],
        'update_lines': [],
        'goto_line': None,
        'after_goto': []
    }

    label_line = None
    label_idx = -1

    for i, line in enumerate(body):
        s = line.strip()
        if s.endswith(':') and not s.startswith('LOOP_'):
            label_line = s[:-1]
            label_idx = i
            parts['label'] = s
            break

    if label_line is None:
        return None

    parts['init'] = body[:label_idx]

    goto_idx = -1
    for i in range(label_idx + 1, len(body)):
        s = body[i].strip()
        if s == f'goto {label_line}':
            goto_idx = i
            parts['goto_line'] = body[i]
            break

    if goto_idx == -1:
        return None

    between = body[label_idx + 1:goto_idx]

    #Separar condicion del resto
    cond_done = False
    after_cond = []

    for line in between:
        s = line.strip()
        if not cond_done:
            parts['cond_lines'].append(line)
            if s.startswith('iffalse'):
                cond_done = True
        else:
            after_cond.append(line)

    #Separar update del cuerpo real
    work = list(after_cond)
    update = []
    i = len(work) - 1

    while i >= 0:
        s = work[i].strip()
        if re.match(rf'^{re.escape(var)}\s*=\s*t\d+', s):
            update.insert(0, work.pop(i))
            i -= 1
            if i >= 0:
                s2 = work[i].strip()
                if (re.search(rf'\b{re.escape(var)}\b', s2) and
                        str(abs(step_val)) in s2):
                    update.insert(0, work.pop(i))
            break
        i -= 1

    parts['work_lines'] = work
    parts['update_lines'] = update
    parts['after_goto'] = body[goto_idx + 1:]

    return parts



# Renombra todas las etiquetas internas de un bloque de líneas añadiendo un sufijo único,
# y actualiza los goto/if/iffalse que las referencian.
def _rename_labels(lines: List[str], suffix: str) -> List[str]:
    # Detectar qué etiquetas existen en el bloque
    labels = set()
    for line in lines:
        s = line.strip()
        if s.endswith(':') and not s.startswith('LOOP_'):
            labels.add(s[:-1])

    result = []
    for line in lines:
        s = line.strip()
        new = line
        # Renombrar definición de etiqueta
        if s.endswith(':') and not s.startswith('LOOP_') and s[:-1] in labels:
            new = f'{s[:-1]}{suffix}:'
        else:
            # Renombrar referencias en saltos
            for lbl in sorted(labels, key=len, reverse=True):
                new = re.sub(r'\b' + re.escape(lbl) + r'\b', lbl + suffix, new)
        result.append(new)
    return result


def _copy_lines(lines: List[str], temp_prefix: str, label_suffix: str = "") -> List[str]:
    """Copia un bloque renombrando temporales y, opcionalmente, etiquetas internas."""
    copied = [_rename_temps(l, temp_prefix) for l in lines]
    if label_suffix:
        copied = _rename_labels(copied, label_suffix)
    return copied


#LOOP UNROLLING
def loop_unrolling(lines: List[str],
                   factor: int = 4,
                   total: bool = False,
                   stats: OptStats = None) -> List[str]:

    # Desenrolla loops anotados con LOOP_START / LOOP_END
    # total=True  → unrolling TOTAL (elimina el loop, sustituye i=0,1,2,...)
    # total=False → unrolling PARCIAL (cada vuelta del loop ejecuta 'factor'
    #               unidades de trabajo; se añade ciclo residual si hace falta)

    result = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Buscar el inicio de un ciclo marcado para optimización
        m = re.match(
            r'^LOOP_START:([^:]+):([^:]+):([^:]+):([^:]+)$',
            line
        )

        if not m:
            result.append(lines[i])
            i += 1
            continue

        label_ann = m.group(1)
        var       = m.group(2)
        limit_str = m.group(3)
        step_str  = m.group(4)

        # Recoger todas las instrucciones que pertenecen al ciclo
        body = []
        j = i + 1
        while j < len(lines) and lines[j].strip() != f'LOOP_END:{label_ann}':
            body.append(lines[j])
            j += 1

        # Si no aparece el final del ciclo, dejarlo sin modificar
        if j >= len(lines):
            result.append(lines[i])
            i += 1
            continue

        try:
            lim_val  = int(limit_str)
            step_val = int(step_str)

            if step_val == 0:
                raise ValueError("paso cero")

            # Número de iteraciones del loop original
            iters = math.ceil(lim_val / abs(step_val)) if step_val > 0 else 0

            if iters <= 0:
                # Loop que nunca ejecuta, dejarlo intacto
                result.append(lines[i])
                result.extend(body)
                result.append(f'LOOP_END:{label_ann}')
                i = j + 1
                continue

            parts = _parse_loop_body(body, var, step_val)

            # ── UNROLLING TOTAL ──────────────────────────────────────────────
            if total and parts is not None and iters <= 64:
                result.append(f'#TOTAL_UNROLL x{iters}: {line}')
                result.extend(parts['init'])

                for rep in range(iters):
                    i_val = rep * step_val
                    result.append(f'#iteracion {rep} (i={i_val})')
                    work = _substitute_var(parts['work_lines'], var, i_val)
                    for w in work:
                        result.append(_rename_temps(w, f'__t{rep}_'))

                if stats:
                    stats.unrolled_loops      += 1
                    stats.unrolled_iterations += iters - 1

            # ── UNROLLING PARCIAL ────────────────────────────────────────────
            else:
                reps = min(factor, iters)

                if reps < 2 or parts is None:
                    # No se puede desenrollar, dejarlo intacto
                    result.append(lines[i])
                    result.extend(body)
                    result.append(f'LOOP_END:{label_ann}')
                    i = j + 1
                    continue

                result.append(f'#PARTIAL_UNROLL x{reps}: {line}')
                result.extend(parts['init'])

                # ── Cuerpo del loop principal (grupos de 'reps' iteraciones) ─
                if parts['label']:
                    result.append(parts['label'])

                # En cada copia se vuelve a chequear la condición. Así el
                # desenrollado parcial sigue siendo correcto aunque el número de
                # iteraciones no sea múltiplo del factor. Por eso NO hace falta
                # un bloque residual aparte.
                for rep in range(reps):
                    result.append(f'#copia {rep}')

                    result.extend(_copy_lines(parts['cond_lines'], f'__c{rep}_'))

                    body_copy = parts['work_lines'] + parts['update_lines']
                    result.extend(_copy_lines(body_copy, f'__p{rep}_', f'_u{rep}'))

                if parts['goto_line']:
                    result.append(parts['goto_line'])

                result.extend(parts.get('after_goto', []))

                if stats:
                    stats.unrolled_loops      += 1
                    stats.unrolled_iterations += reps - 1

        # ── LÍMITE VARIABLE (VAR_UNROLL) ─────────────────────────────────────
        # El límite no es un literal entero: no sabemos cuántas iteraciones hay.
        # Solo podemos replicar el cuerpo 'factor' veces DENTRO del loop,
        # re-chequeando la condición antes de cada copia.
        # NO se pueden hacer incrementos intermedios de la variable de control
        # porque el trabajo del cuerpo ya la modifica (e.g. n = n - divisor).
        except (ValueError, TypeError):
            parts = _parse_loop_body(body, var, 1)

            if parts is None or factor < 2:
                result.append(lines[i])
                result.extend(body)
                result.append(f'LOOP_END:{label_ann}')
            else:
                result.append(f'#VAR_UNROLL x{factor}: {line}')
                result.extend(parts['init'])

                if parts['label']:
                    result.append(parts['label'])

                # Cada copia: chequear condición → ejecutar cuerpo completo.
                # En loops con límite variable, el update puede estar dentro del
                # cuerpo real (ej.: n = n - divisor), por eso se copia también
                # update_lines.
                for rep in range(factor):
                    result.append(f'#copia {rep}')
                    result.extend(_copy_lines(parts['cond_lines'], f'__vc{rep}_'))

                    body_copy = parts['work_lines'] + parts['update_lines']
                    result.extend(_copy_lines(body_copy, f'__v{rep}_', f'_v{rep}'))

                if parts['goto_line']:
                    result.append(parts['goto_line'])

                result.extend(parts.get('after_goto', []))

                if stats:
                    stats.unrolled_loops      += 1
                    stats.unrolled_iterations += factor - 1

        i = j + 1

    return result


#REGISTER RENAMING
def register_renaming(lines: List[str],
                      stats: OptStats = None) -> List[str]:
    """Renombra temporales tN con versiones tN_vK.

    Corrección importante: primero se separa el lado izquierdo del derecho.
    Así, cuando se redefine un temporal, no se reemplaza accidentalmente el
    temporal del lado izquierdo por su versión anterior.
    """
    current = {}
    version = {}
    result = []

    for line in lines:
        s = line.strip()

        if not s or s.endswith(':') or s.startswith('LOOP_') or s.startswith('#'):
            result.append(line)
            continue

        d = get_def(s)

        # Caso 1: la línea define un temporal tN.
        if d and re.match(r'^t\d+$', d) and '=' in line:
            lhs, rhs = line.split('=', 1)

            # El RHS usa las versiones vigentes.
            new_rhs = rhs
            for old, new in sorted(current.items(), key=lambda x: len(x[0]), reverse=True):
                new_rhs = re.sub(r'\b' + re.escape(old) + r'\b', new, new_rhs)

            # El LHS recibe una versión nueva.
            version[d] = version.get(d, 0) + 1
            new_name = f'{d}_v{version[d]}'
            current[d] = new_name

            new_lhs = re.sub(r'\b' + re.escape(d) + r'\b', new_name, lhs)
            result.append(new_lhs + '=' + new_rhs)

            if stats:
                stats.renamed += 1
            continue

        # Caso 2: cualquier otra línea solo actualiza usos.
        new_line = line
        for old, new in sorted(current.items(), key=lambda x: len(x[0]), reverse=True):
            new_line = re.sub(r'\b' + re.escape(old) + r'\b', new, new_line)

        result.append(new_line)

    return result

def dead_code_elimination(lines: List[str],
                           stats: OptStats = None) -> List[str]:
    """Eliminación de código muerto usando análisis de liveness hacia atrás.

    Raíces de liveness (variables siempre vivas):
      - Instrucciones save(x)    → x es observable
      - return <val>             → val es observable
      - param <val>              → val es observable (argumento de llamada)
      - Asignaciones a arreglos  → base e índice son observables
      - Llamadas a función       → sus argumentos son observables

    Algoritmo (backward):
      1. Recolectar conjunto inicial de variables vivas (roots).
      2. Recorrer las instrucciones de abajo hacia arriba.
      3. Si una instrucción define una variable que NO está en el conjunto
         de vivas → es código muerto → se elimina.
      4. Si la instrucción SÍ define una variable viva → marcarla como viva
         y agregar todos los operandos del lado derecho al conjunto de vivas.
    """

    def _uses(instr: str) -> List[str]:
        """Extrae los identificadores usados en el lado derecho de una instrucción."""
        s = instr.strip()

        # save x  →  x es usada
        m = re.match(r'^save\s+(\w+)', s)
        if m:
            return [m.group(1)]

        # return val
        m = re.match(r'^return\s+(.+)$', s)
        if m:
            return [t for t in re.findall(r'[a-zA-Z_]\w*', m.group(1))
                    if _is_var(t)]

        # param val
        m = re.match(r'^param\s+(.+)$', s)
        if m:
            return [t for t in re.findall(r'[a-zA-Z_]\w*', m.group(1))
                    if _is_var(t)]

        # goto / if / iffalse  → no producen definiciones, sus operandos son vivos
        if s.startswith('goto ') or s.startswith('if ') or s.startswith('iffalse '):
            return [t for t in re.findall(r'[a-zA-Z_]\w*', s)
                    if _is_var(t)]

        # base[idx] = val  →  base, idx y val son usados (escritura a arreglo)
        m = re.match(r'^(\w+)\[(.+?)\]\s*=\s*(.+)$', s)
        if m:
            used = []
            for part in [m.group(1), m.group(2), m.group(3)]:
                used += [t for t in re.findall(r'[a-zA-Z_]\w*', part)
                         if _is_var(t)]
            return used

        # t = call func, N  → los params anteriores ya se capturan con 'param'
        m = re.match(r'^\w+\s*=\s*call\s+(\w+)', s)
        if m:
            return [m.group(1)] if _is_var(m.group(1)) else []

        # var = expr  → lado derecho
        if '=' in s:
            rhs = s.split('=', 1)[1]
            return [t for t in re.findall(r'[a-zA-Z_]\w*', rhs)
                    if _is_var(t)]

        return []

    def _is_eliminable(instr: str) -> bool:
        """True si la instrucción puede eliminarse (solo asignaciones simples)."""
        s = instr.strip()
        if not s or s.endswith(':') or s.startswith('#') or s.startswith('LOOP_'):
            return False
        # No eliminar estructuras de control ni llamadas con efectos
        if (s.startswith('goto') or s.startswith('if') or s.startswith('iffalse')
                or s.startswith('return') or s.startswith('param')
                or s.startswith('save') or s.startswith('begin_func')
                or s.startswith('end_func') or s.startswith('fparam')):
            return False
        # No eliminar escrituras a arreglo (efecto en memoria)
        if re.match(r'^\w+\[', s):
            return False
        # No eliminar llamadas a función sin asignación (efectos secundarios)
        if re.match(r'^call\s+', s):
            return False
        # Solo eliminamos: var = expr
        return bool(re.match(r'^\w+\s*=', s))

    # ── Paso 1: recolectar raíces de liveness ─────────────────────────────
    live: set = set()
    for line in lines:
        s = line.strip()
        # save x → x es raíz
        m = re.match(r'^save\s+(\w+)', s)
        if m:
            live.add(m.group(1))
        # return val → val es raíz
        m = re.match(r'^return\s+([a-zA-Z_]\w*)', s)
        if m and _is_var(m.group(1)):
            live.add(m.group(1))
        # Escrituras a arreglo → base siempre viva
        m = re.match(r'^(\w+)\[', s)
        if m:
            live.add(m.group(1))

    # ── Paso 2: análisis backward ──────────────────────────────────────────
    kept = [True] * len(lines)

    for idx in range(len(lines) - 1, -1, -1):
        line = lines[idx]
        s = line.strip()

        if not _is_eliminable(s):
            # Instrucción no eliminable: sus usos siempre están vivos
            for v in _uses(s):
                live.add(v)
            continue

        defined = get_def(s)

        if defined and defined not in live:
            # La variable definida nunca se usa → código muerto
            kept[idx] = False
            if stats:
                stats.instr_before  # ya contado
        else:
            # La definición es necesaria: agregar sus usos al conjunto vivo
            if defined:
                live.discard(defined)
            for v in _uses(s):
                live.add(v)

    # ── Paso 3: reconstruir código sin las instrucciones muertas ──────────
    eliminated = kept.count(False)
    result = [lines[i] for i in range(len(lines)) if kept[i]]

    if stats:
        stats.instr_after = stats._count_instrs(result)

    return result



def instruction_reordering(lines: List[str],
                            stats: OptStats = None) -> List[str]:
    """Reordenamiento de instrucciones dentro de bloques básicos.

    Respeta dependencias de datos:
      - RAW (Read After Write): si B lee una variable que A escribe, B debe ir después de A.
      - WAR (Write After Read): si B escribe una variable que A lee, B debe ir después de A.
      - WAW (Write After Write): si B escribe lo mismo que A, B debe ir después de A.

    También respeta dependencias de control:
      - Ninguna instrucción puede moverse fuera de su bloque básico.
      - Las instrucciones de salto, return, param y call mantienen su posición relativa.

    Algoritmo: list scheduling (greedy topológico).
      1. Dividir en bloques básicos.
      2. Dentro de cada bloque, construir un grafo de dependencias.
      3. Emitir instrucciones en orden topológico, priorizando
         las que tienen más dependientes (heurística de ruta crítica).
    """

    def _get_uses(s: str) -> set:
        """Variables leídas por la instrucción."""
        if not s or s.endswith(':') or s.startswith('#') or s.startswith('LOOP_'):
            return set()
        # param, return, save, if, iffalse, goto — leer sus operandos
        for prefix in ('param ', 'return ', 'save ', 'if ', 'iffalse ', 'goto '):
            if s.startswith(prefix):
                return {t for t in re.findall(r'[a-zA-Z_]\w*', s[len(prefix):])
                        if _is_var(t)}
        # t = call func, N  →  solo el nombre de la función como uso simbólico
        m = re.match(r'^\w[\w.]*\s*=\s*call\s+(\w[\w.]*)', s)
        if m:
            return {m.group(1)} if _is_var(m.group(1)) else set()
        # arr[idx] = val
        m = re.match(r'^(\w+)\[(.+?)\]\s*=\s*(.+)$', s)
        if m:
            uses = set()
            for part in [m.group(1), m.group(2), m.group(3)]:
                uses |= {t for t in re.findall(r'[a-zA-Z_]\w*', part) if _is_var(t)}
            return uses
        # var = expr  →  leer RHS
        if '=' in s:
            rhs = s.split('=', 1)[1]
            return {t for t in re.findall(r'[a-zA-Z_]\w*', rhs) if _is_var(t)}
        return set()

    def _get_def(s: str):
        """Variable escrita por la instrucción (None si no define nada)."""
        return get_def(s)

    def _is_fixed(s: str) -> bool:
        """True si la instrucción NO puede moverse (ancla del bloque)."""
        if not s or s.endswith(':') or s.startswith('#') or s.startswith('LOOP_'):
            return True
        for prefix in ('goto', 'if ', 'iffalse', 'return', 'param',
                       'call ', 'begin_func', 'end_func', 'fparam', 'save'):
            if s.startswith(prefix):
                return True
        # Escritura a memoria: mem[x] = y o arr[i] = v
        if re.match(r'^\w+\[', s):
            return True
        return False

    def _reorder_block(block: List[str]) -> List[str]:
        """Reordena un bloque básico con list scheduling."""
        if len(block) <= 1:
            return block

        n = len(block)
        stripped = [l.strip() for l in block]

        # Construir grafo de dependencias: deps[i] = set de índices que i debe esperar
        deps = [set() for _ in range(n)]

        for i in range(n):
            def_i   = _get_def(stripped[i])
            uses_i  = _get_uses(stripped[i])
            fixed_i = _is_fixed(stripped[i])

            for j in range(i + 1, n):
                def_j   = _get_def(stripped[j])
                uses_j  = _get_uses(stripped[j])
                fixed_j = _is_fixed(stripped[j])

                # Si cualquiera es fija, mantener orden relativo
                if fixed_i or fixed_j:
                    deps[j].add(i)
                    continue

                # RAW: j lee lo que i escribe
                if def_i and def_i in uses_j:
                    deps[j].add(i)

                # WAR: j escribe lo que i lee
                if def_j and def_j in uses_i:
                    deps[j].add(i)

                # WAW: ambos escriben la misma variable
                if def_i and def_j and def_i == def_j:
                    deps[j].add(i)

        # Calcular número de dependientes de cada nodo (para priorizar)
        dependents = [0] * n
        for j in range(n):
            for i in deps[j]:
                dependents[i] += 1

        # List scheduling: emitir instrucciones listas (sin deps pendientes)
        # priorizando las de mayor número de dependientes
        emitted  = [False] * n
        result   = []
        pending  = set(range(n))

        while pending:
            # Instrucciones listas: todas sus dependencias ya emitidas
            ready = [i for i in pending
                     if all(emitted[d] for d in deps[i])]

            if not ready:
                # Ciclo en el grafo (no debería pasar con IR bien formado)
                # Emitir el primero pendiente para no bloquearse
                ready = [min(pending)]

            # Priorizar: mayor número de dependientes primero
            chosen = max(ready, key=lambda i: dependents[i])

            result.append(block[chosen])
            emitted[chosen] = True
            pending.discard(chosen)

        return result

    # ── Dividir en bloques básicos y reordenar cada uno ───────────────────
    result       = []
    current_block = []

    def _flush():
        if current_block:
            result.extend(_reorder_block(current_block))
            current_block.clear()

    for line in lines:
        s = line.strip()

        # Inicio de bloque básico: etiqueta
        if s.endswith(':') and not s.startswith('#') and not s.startswith('LOOP_'):
            _flush()
            result.append(line)
            continue

        # Fin de bloque básico: salto o return
        if (s.startswith('goto') or s.startswith('if ') or s.startswith('iffalse')
                or s.startswith('return') or s.startswith('end_func')):
            current_block.append(line)
            _flush()
            continue

        current_block.append(line)

    _flush()

    if stats:
        reordered = sum(
            1 for orig, new in zip(lines, result) if orig != new
        )

    return result


def optimize(ir_code: str,
             unroll_factor: int = 4,
             total_unroll: bool = False,
             enable_unroll: bool = True,
             enable_dce: bool = False,   
             enable_reorder: bool = False,  
             enable_rename: bool = True) -> Tuple[str, OptStats]:

    stats = OptStats()

    lines = ir_code.splitlines()

    stats.instr_before = stats._count_instrs(lines)

    if enable_unroll:
        lines = loop_unrolling(
            lines,
            factor=unroll_factor,
            total=total_unroll,
            stats=stats
        )

    if enable_rename:
        lines = register_renaming(
            lines,
            stats=stats
        )

    if enable_dce:
        lines = dead_code_elimination(
            lines,
            stats=stats
        )

    if enable_reorder:
        before_reorder = list(lines)
        lines = instruction_reordering(lines, stats=stats)
        stats.reordered = sum(1 for a, b in zip(before_reorder, lines) if a != b)

    stats.instr_after = stats._count_instrs(lines)

    return "\n".join(lines), stats