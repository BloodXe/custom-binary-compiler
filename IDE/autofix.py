import re



# Encabezados de bloque: func, si, sino, mientras, para
_BLOCK_HEADER = re.compile(
    r"""^
    (
        func \s+ \w[\w.]* \s* \(.*        
      | si   \s* \(.*                       
      | sino \s*                           
      | mientras \s* \(.*                  
      | para \s* \(.*                       
    )
    (\s* \{ \s* )?                          
    $""",
    re.VERBOSE,
)


_STRUCTURAL = re.compile(r"^(\{|\}|@boveda|@code)\s*$")

# Línea vacía o sólo comentario
_BLANK_OR_COMMENT = re.compile(r"^\s*(#.*)?$")

# Línea de importación
_IMPORT_LINE = re.compile(r"^importar\s+")

# Ya tiene terminador
_HAS_TERMINATOR = re.compile(r"'\s*(#.*)?$")

# Función que determina si una línea necesita un terminador ( ' ) al final
def _needs_terminator(stripped: str) -> bool:
    """Devuelve True si la línea debería terminar en ' pero no lo hace."""
    if not stripped:
        return False
    if _BLANK_OR_COMMENT.match(stripped):
        return False
    if _HAS_TERMINATOR.search(stripped):
        return False
    if _STRUCTURAL.match(stripped):
        return False
    if _IMPORT_LINE.match(stripped):
        return False
    if _BLOCK_HEADER.match(stripped):
        return False
    # Línea que termina en { (encabezado de bloque en una sola línea)
    if stripped.endswith("{"):
        return False
    return True


#  Corrección de terminadores faltantes

def fix_terminators(source):
    """
    Añade ' al final de las sentencias que lo necesitan.

    Retorna:
        fixed_source  - texto corregido
        fixed_lines   - lista con los números de línea (1-indexed) modificados
    """

    # El proceso es línea por línea para evitar interferencias entre correcciones
    lines = source.splitlines()
    fixed_lines = []
    result = []

    # Recorremos cada línea y decidimos si necesita un terminador ( ' ) al final
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Si la línea necesita un terminador, lo añadimos antes de cualquier comentario inline
        if _needs_terminator(stripped):
            # Insertar ' antes del comentario inline si existe
            comment_match = re.search(r"\s+#.*$", line)

            # Si hay un comentario, insertamos el terminador antes de él, si no, al final de la línea
            if comment_match:
                insert_pos = comment_match.start()
                line = line[:insert_pos] + "'" + line[insert_pos:]
            else:
                line = line.rstrip() + "'"
            fixed_lines.append(i)
        result.append(line)

    return "\n".join(result), fixed_lines


#  Corrección de llaves sin cerrar

def fix_braces(source):

    # Contamos la profundidad de llaves en el código, ignorando las que estén dentro de strings.
    depth = 0
    in_string = False

    # Recorremos cada carácter para mantener un conteo preciso de las llaves, sin que los strings interfieran
    for ch in source:
        if ch == '"':
            in_string = not in_string
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

    # Si la profundidad es negativa, significa que hay más } que {, lo cual es un error de sintaxis que no podemos corregir automáticamente.
    if depth <= 0:
        return source, 0

    # Agregar las llaves faltantes al final
    closing = "\n" + "}\n" * depth
    return source + closing, depth


#  Corrección de paréntesis sin cerrar (dentro de cada línea)

def fix_parens(source):


    # El proceso es línea por línea para evitar interferencias entre correcciones
    lines = source.splitlines()
    fixed_lines = []
    result = []

    # Recorremos cada línea y contamos los paréntesis abiertos y cerrados para detectar si falta alguno
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Si la línea es vacía o sólo un comentario, la dejamos igual
        if _BLANK_OR_COMMENT.match(stripped):
            result.append(line)
            continue

        if "{" in stripped:
            idx_dc = line.find("::")
            if idx_dc != -1:
                before_dc = line[:idx_dc]
                idx_open  = before_dc.rfind("(")
                # solo corregimos si entre ( y :: no hay nada (paréntesis vacío mal cerrado)
                if idx_open != -1 and before_dc[idx_open + 1:].strip() == "":
                    line = line[:idx_dc] + ")" + line[idx_dc:]
                    fixed_lines.append(i)
            result.append(line)
            continue

        open_count = close_count = 0
        in_string = False
        for ch in line:
            if ch == '"':
                in_string = not in_string
            if in_string:
                continue
            if ch == '(':
                open_count += 1
            elif ch == ')':
                close_count += 1
        diff = open_count - close_count

        # Si hay más paréntesis abiertos que cerrados, añadimos los ) faltantes al final de la línea (antes de cualquier comentario inline)
        if diff > 0:
            # Insertar los ) faltantes antes del terminador o al final
            term_match = re.search(r"'\s*(#.*)?$", line)

            # Si hay un terminador, insertamos los paréntesis antes de él, si no, antes del comentario inline, o al final de la línea
            if term_match:
                insert_pos = term_match.start()
                line = line[:insert_pos] + ")" * diff + line[insert_pos:]
            else:
                comment_match = re.search(r"\s+#.*$", line)

                # Si hay un comentario, insertamos los paréntesis antes de él, si no, al final de la línea
                if comment_match:
                    insert_pos = comment_match.start()
                    line = line[:insert_pos] + ")" * diff + line[insert_pos:]
                else:
                    line = line.rstrip() + ")" * diff
            fixed_lines.append(i)

        result.append(line)

    return "\n".join(result), fixed_lines


# Función principal de autofix que aplica todas las correcciones en orden y genera un resumen legible de los cambios realizados.

def autofix(source):
    original = source

    # paréntesis
    source, paren_lines = fix_parens(source)

    # terminadores
    source, term_lines = fix_terminators(source)

    # llaves
    source, braces_added = fix_braces(source)

    changed = source != original

    # Generar un resumen legible de los cambios realizados
    parts = []

    # Listar las líneas donde se añadieron terminadores o paréntesis, o las llaves añadidas al final
    if term_lines:
        parts.append(
            f"• Terminador (') añadido en línea(s): {', '.join(map(str, term_lines))}"
        )
    # Si se añadieron paréntesis, listarlos también
    if paren_lines:
        parts.append(
            f"• Paréntesis cerrado en línea(s): {', '.join(map(str, paren_lines))}"
        )
    # Si se añadieron llaves, indicar cuántas y que fueron añadidas al final del archivo
    if braces_added:
        plural = "llave" if braces_added == 1 else "llaves"
        parts.append(f"• {braces_added} {plural} de cierre (}}) añadida(s) al final")

    summary = "\n".join(parts) if parts else "No se encontraron errores que corregir."

    # Devolver el resultado con toda la información relevante para el IDE
    return {
        "fixed_source": source,
        "changed": changed,
        "summary": summary,
        "term_lines": term_lines,
        "paren_lines": paren_lines,
        "braces_added": braces_added,
    }