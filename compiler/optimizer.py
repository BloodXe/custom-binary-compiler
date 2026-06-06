import re
from typing import List, Optional, Tuple


class OptStats:
    def __init__(self):
        self.unrolled_loops = 0
        self.unrolled_iterations = 0
        self.renamed = 0
        self.instr_before = 0
        self.instr_after = 0

    def __str__(self):
        return "\n".join([
            "Estadisticas de Optimizacion",
            f"  Instrucciones antes    : {self.instr_before}",
            f"  Instrucciones despues  : {self.instr_after}",
            f"  Loops desenrollados    : {self.unrolled_loops}",
            f"  Iteraciones unroll     : {self.unrolled_iterations}",
            f"  Temporales renombrados : {self.renamed}",
        ])



# Funciones auxiliares


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
    """Verifica si el texto corresponde a un identificador válido"""
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


#LOOP UNROLLING


def loop_unrolling(lines: List[str],
                   factor: int = 4,
                   total: bool = False,
                   stats: OptStats = None) -> List[str]:

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

        label, var, limit, step = (
            m.group(1),
            m.group(2),
            m.group(3),
            m.group(4)
        )

        # Guardar todas las instrucciones que pertenecen al ciclo
        body = []
        j = i + 1

        while j < len(lines) and lines[j].strip() != f'LOOP_END:{label}':
            body.append(lines[j])
            j += 1

        # Si no aparece el final del ciclo, se deja sin modificar
        if j >= len(lines):
            result.append(lines[i])
            i += 1
            continue

        try:
            lim_val = int(limit)
            step_val = int(step)

            if step_val == 0:
                raise ValueError("paso cero")

            iters = lim_val // abs(step_val) if step_val > 0 else 0

            if iters <= 0:
                result.append(lines[i])
                i += 1
                continue

            if total:
                # Reemplazar completamente el ciclo por sus iteraciones
                result.append(f'# TOTAL_UNROLL x{iters}: {line}')

                if stats:
                    stats.unrolled_loops += 1
                    stats.unrolled_iterations += iters - 1

                for rep in range(iters):
                    for bl in body:
                        result.append(
                            _rename_temps(bl, f'__u{rep}_')
                        )

            else:
                # Replicar únicamente una parte del ciclo
                reps = min(factor, iters)

                if reps < 2:
                    result.append(lines[i])
                    i += 1
                    continue

                result.append(f'# PARTIAL_UNROLL x{reps}: {line}')

                if stats:
                    stats.unrolled_loops += 1
                    stats.unrolled_iterations += reps - 1

                for rep in range(reps):
                    for bl in body:
                        result.append(
                            _rename_temps(bl, f'__u{rep}_')
                        )

            # Saltar el LOOP_END ya procesado
            i = j + 1

        except (ValueError, TypeError):
            # Si el límite no es constante, usar el factor indicado
            result.append(f'# VAR_UNROLL x{factor}: {line}')

            if stats:
                stats.unrolled_loops += 1
                stats.unrolled_iterations += factor - 1

            for rep in range(factor):
                for bl in body:
                    result.append(
                        _rename_temps(bl, f'__u{rep}_')
                    )

            i = j + 1

    return result


def _rename_temps(line: str, prefix: str) -> str:
  
    #Agrega un prefijo a los temporales para que cada copia del ciclo utilice nombres distintos
    

    return re.sub(
        r'\bt(\d+)\b',
        lambda m: f't{prefix}{m.group(1)}',
        line
    )



#REGISTER RENAMING


def register_renaming(lines: List[str],
                      stats: OptStats = None) -> List[str]:

    #Crea nuevas versiones de los temporales cada vez que son redefinidos.

    current = {}
    version = {}
    result = []

    for line in lines:
        s = line.strip()

        # Estas líneas no necesitan modificarse
        if not s or s.endswith(':') or s.startswith('LOOP_') or s.startswith('#'):
            result.append(line)
            continue

        # Actualizar referencias usando la versión más reciente
        new_line = line

        for old, new in sorted(
            current.items(),
            key=lambda x: len(x[0]),
            reverse=True
        ):
            new_line = re.sub(
                r'\b' + re.escape(old) + r'\b',
                new,
                new_line
            )

        # Si un temporal se redefine, crear una nueva versión
        d = get_def(s)

        if d and re.match(r'^t\d+$', d):
            version[d] = version.get(d, 0) + 1

            new_name = f'{d}_v{version[d]}'
            current[d] = new_name

            if '=' in new_line:
                eq = new_line.index('=')

                new_line = (
                    re.sub(
                        r'\b' + re.escape(d) + r'\b',
                        new_name,
                        new_line[:eq]
                    )
                    + new_line[eq:]
                )

            if stats:
                stats.renamed += 1

        result.append(new_line)

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

    stats.instr_before = sum(
        1 for l in lines
        if l.strip() and not l.strip().endswith(':')
    )

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

    stats.instr_after = sum(
        1 for l in lines
        if l.strip() and not l.strip().endswith(':')
    )

    return "\n".join(lines), stats