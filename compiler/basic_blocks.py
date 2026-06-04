# Representa un bloque básico del código intermedio.
class BasicBlock:
    def __init__(self, name):
        self.name = name
        self.lineas = []   # Lista donde se almacenan las instrucciones del bloque

    def add(self, instr):
        self.lineas.append(instr)  # Agrega una instrucción al bloque

    def __str__(self):  # Imprime el bloque nice
        lines = [f"{self.name}:"]
        lines += [f"  {instr}" for instr in self.lineas]
        return "\n".join(lines)

# Si una instrucción es una etiqueta.
def is_label(instr):
    return instr.strip().endswith(":")

# Si una instrucción produce un salto
def is_jump(instr):
    s = instr.strip()
    return (
        s.startswith("goto ")
        or s.startswith("if ")
        or s.startswith("iffalse ")
        or s.startswith("return")
    )

# Construye los bloques básicos a partir del código intermedio.
def build_basic_blocks(ir_code):
    lines = [line.strip() for line in ir_code.splitlines() if line.strip()]

    blocks = []
    current = None
    block_count = 1

    # Crea un nuevo bloque y lo agrega a la lista
    def new_block():
        nonlocal block_count
        block = BasicBlock(f"B{block_count}")
        block_count += 1
        blocks.append(block)
        return block

    # Recorremos cada instrucción del IR
    for line in lines:
        if current is None:
            current = new_block()

        elif is_label(line):
            current = new_block()

        current.add(line)

        if is_jump(line):
            current = None

    return blocks

# Convierte todos los bloques en texto 
def format_blocks(blocks):
    return "\n\n".join(str(block) for block in blocks)