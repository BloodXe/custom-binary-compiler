# resolver.py — Fase 5: Cálculo de Saltos y Resolución de Referencias
#
# Responsabilidad:
#   Toma el ensamblador textual generado por AsmGen (con etiquetas como nombres)
#   y produce ensamblador con los nombres de etiqueta reemplazados por offsets
#   relativos al PC de la instrucción que hace el salto.
#
# Offset relativo en TEA-ISA:
#   PC_destino = PC_instruccion + offset * 4
#   → offset = (addr_label - addr_instruccion) / 4
#
# El offset se mide en palabras (no bytes), ya que la ISA multiplica el campo
# de offset por el tamaño de instrucción internamente.
#
# Ejemplo:
#   0x00  jal r0, fin      → fin está en 0x10
#         offset = (0x10 - 0x00) / 4 = 4
#   0x10  fin:             ← aquí llega el salto

import re

INSTRUCTION_SIZE = 4   # bytes por instrucción (word-aligned)


class Resolver:
    """
    Dos pasadas sobre el código ensamblador textual:
      Pasada 1 — labels_direction : construye {nombre_label → dirección_byte}
      Pasada 2 — labels_rewrite   : reemplaza nombres por offsets relativos
    """

    def __init__(self, asm: str):
        # Separar en líneas y limpiar
        self.asm    = asm.splitlines()
        self.labels = {}   # {nombre: dirección_byte}

    # Pasada 1: construir tabla de etiquetas
    def labels_direction(self):
        """
        Recorre el ASM y registra la dirección de byte de cada etiqueta.

        Reglas de clasificación de líneas:
          - Vacía o solo comentario (#...)  → ignorar (no avanza PC)
          - Termina con ':'                 → etiqueta, registrar dirección
          - Cualquier otra cosa             → instrucción, avanzar PC en 4

        Las líneas de comentario puro (que empiezan con '#') NO son
        instrucciones, pero el AsmGen las emite sin ':' final.
        Las detectamos buscando si la línea (sin el '#') corresponde
        a una instrucción real: si la primer palabra no es una mnemónica
        conocida, la tratamos como comentario/label-comentario.
        """
        address = 0
        for line in self.asm:
            stripped = line.strip()

            if not stripped: # línea vacía
                continue

            if stripped.startswith('#'): # comentario puro
                continue

            if stripped.endswith(':'): # etiqueta
                # El nombre puede tener espacios antes del ':'
                # y puede haber un comentario inline: "foo:  # comentario"
                label_part = stripped.rstrip(':').split('#')[0].strip()
                if label_part: # etiqueta con nombre real
                    self.labels[label_part] = address
                continue

            # Instrucción real: avanzar PC
            address += INSTRUCTION_SIZE

    # Pasada 2: reemplazar etiquetas por offsets
    def labels_rewrite(self) -> list:
        """
        Para cada instrucción, busca si contiene algún nombre de etiqueta
        y lo reemplaza por el offset relativo (en palabras) al PC actual.

        Matching exacto: usamos \\b (word boundary) para que 'end' no
        matchee dentro de 'while_end'. Esto evita el bug del amigo donde
        un label corto pisaba al largo.
        """
        new_code = []
        actual_pc = 0

        for line in self.asm:
            stripped = line.strip()

            # Ignorar vacías, comentarios puros y etiquetas
            if not stripped:
                continue
            if stripped.startswith('#'):
                continue
            if stripped.endswith(':'):
                continue

            # Separar instrucción de comentario inline (si hay)
            instr_part, _, comment_part = stripped.partition('#')
            instr_part = instr_part.strip()

            # Buscar y reemplazar etiquetas en la parte de instrucción
            # Ordenar por longitud descendente para evitar que un label
            # corto reemplace parte de uno largo (e.g. 'end' vs 'while_end')
            for label in sorted(self.labels, key=len, reverse=True):
                # Matching de palabra completa con regex
                pattern = r'\b' + re.escape(label) + r'\b'
                if re.search(pattern, instr_part):
                    label_addr  = self.labels[label]
                    # Offset en palabras relativo al PC de ESTA instrucción
                    offset = (label_addr - actual_pc) // INSTRUCTION_SIZE
                    instr_part = re.sub(pattern, str(offset), instr_part)

            # Reconstruir línea con comentario si lo había
            if comment_part:
                resolved_line = f"{instr_part}  #{comment_part}"
            else:
                resolved_line = instr_part

            new_code.append(resolved_line)
            actual_pc += INSTRUCTION_SIZE

        return new_code

    # Punto de entrada

    def resolve(self) -> str:
        """Ejecuta las dos pasadas y retorna el ASM con referencias resueltas."""
        self.labels_direction()
        resolved_lines = self.labels_rewrite()
        return "\n".join(resolved_lines)

    def get_label_table(self) -> dict:
        """Retorna la tabla de etiquetas para debugging."""
        return dict(self.labels)
    