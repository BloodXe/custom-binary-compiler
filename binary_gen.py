# binary_gen.py — Fase 6: Generación de Código Binario
#
# Entrada : ASM resuelto (sin etiquetas, solo offsets numéricos)
# Salida  : archivo .bin (little-endian, word-aligned)
#           opcional .hex (una instrucción por línea en hex)
#
# Formato de instrucción TEA-ISA (23 bits, almacenados en 32 bits little-endian):
#
#   R-Type:  [op(4)|rd(4)|rs1(4)|rs2(4)|funct(3)|res(4)]   bits 22..0
#   I-Type:  [op(4)|rd(4)|rs1(4)|imm(11)]
#   S-Type:  [op(4)|rs2(4)|rs1(4)|offset(11)]
#   B-Type:  [op(4)|rs1(4)|rs2(4)|offset(11)]
#              offset[10]   = selector de condición (BEQ/BGE=0, BNE/BGT=1)
#              offset[9:0]  = desplazamiento con signo (10 bits)
#   J-Type:  [op(4)|rd(4)|offset(15)]
#   JR-Type: [op(4)|rs1(4)|res(15)=0]
#   V-Type:  [op(4)|rd(4)|rs1(4)|ki(2)|funct(9)]

import struct


# Opcodes (bits [22:19])
OPCODES = {
    "nop":      0b0000,
    "addi":     0b0001,
    "lli":      0b0010,
    "load":     0b0011,
    "store":    0b0100,
    "beq":      0b0101,
    "bne":      0b0101,
    "bge":      0b0110,
    "bgt":      0b0110,
    "jal":      0b0111,
    "jr":       0b1000,
    "halt":     0b1001,
    "tea_add1": 0b1010,
    "tea_add2": 0b1011,
    # R-type ALU (add/sub/and/or/xor/sll/srl/sra comparten opcode 1100)
    "add":      0b1100,
    "sub":      0b1100,
    "and":      0b1100,
    "or":       0b1100,
    "xor":      0b1100,
    "sll":      0b1100,
    "srl":      0b1100,
    "sra":      0b1100,
    # Vault (login/logout/setpwd/authorize/vkload/vkinv comparten opcode 1101)
    "login":     0b1101,
    "logout":    0b1101,
    "setpwd":    0b1101,
    "authorize": 0b1101,
    "vkload":    0b1101,
    "vkinv":     0b1101,
    # Auth check
    "authchk":  0b1110,
}

# funct[2:0] para instrucciones R-type ALU (bits [6:4])
ALU_FUNCT = {
    "add": 0b000,
    "sub": 0b001,
    "and": 0b010,
    "or":  0b011,
    "xor": 0b100,
    "sll": 0b101,
    "srl": 0b110,
    "sra": 0b111,
}

# funct[8:0] para instrucciones de bóveda V-type (bits [8:0])
VAULT_FUNCT = {
    "setpwd":    0b000000000,
    "login":     0b000000001,
    "logout":    0b000000010,
    "authorize": 0b000000011,
    "vkload":    0b000000100,
    "vkinv":     0b000000101,
}

AUTHCHK_FUNCT = 0b000000011


# Helpers

def reg(r: str) -> int:
    """Convierte 'r0'..'r15' a número 0..15."""
    r = r.strip().lower()
    if not r.startswith('r'):
        raise ValueError(f"Registro inválido: '{r}'")
    return int(r[1:])


def parse_int(s: str) -> int:
    """Parsea entero decimal o hexadecimal (0x...)."""
    s = s.strip()
    if s.startswith('0x') or s.startswith('0X'):
        return int(s, 16)
    return int(s)


def sign_extend_to_field(value: int, bits: int) -> int:
    """
    Convierte un entero con signo a su representación de `bits` bits
    en complemento a dos. Valida el rango.
    """
    max_pos =  (1 << (bits - 1)) - 1
    min_neg = -(1 << (bits - 1))
    if not (min_neg <= value <= max_pos):
        raise ValueError(
            f"Valor {value} fuera de rango [{min_neg}, {max_pos}] "
            f"para campo de {bits} bits"
        )
    if value < 0:
        value = value + (1 << bits)
    return value & ((1 << bits) - 1)


def parse_offset_reg(token: str):
    """
    Parsea 'offset(reg)' → (offset_int, reg_str).
    Soporta offsets negativos: '-4(r2)' → (-4, 'r2').
    """
    import re
    m = re.match(r'^(-?\d+)\((\w+)\)$', token.strip())
    if not m:
        raise ValueError(f"Formato inválido offset(reg): '{token}'")
    return int(m.group(1)), m.group(2)


def to_bin23(x: int) -> str:
    """Representación binaria de 23 bits."""
    return format(x & 0x7FFFFF, '023b')



# Codificadores por tipo de instrucción

def encode_r(op, rd, rs1, rs2, funct):
    """R-Type: [op(4)|rd(4)|rs1(4)|rs2(4)|funct(3)|res(4)=0]"""
    return ((op & 0xF) << 19 | (rd  & 0xF) << 15 |
            (rs1 & 0xF) << 11 | (rs2 & 0xF) << 7 |
            (funct & 0x7) << 4)


def encode_i(op, rd, rs1, imm):
    """I-Type: [op(4)|rd(4)|rs1(4)|imm(11)]"""
    imm11 = sign_extend_to_field(imm, 11)
    return ((op & 0xF) << 19 | (rd  & 0xF) << 15 |
            (rs1 & 0xF) << 11 | (imm11 & 0x7FF))


def encode_s(op, rs2, rs1, offset):
    """S-Type: [op(4)|rs2(4)|rs1(4)|offset(11)]"""
    off11 = sign_extend_to_field(offset, 11)
    return ((op & 0xF) << 19 | (rs2 & 0xF) << 15 |
            (rs1 & 0xF) << 11 | (off11 & 0x7FF))


def encode_b(op, rs1, rs2, offset, cond_bit):
    """
    B-Type: [op(4)|rs1(4)|rs2(4)|offset(11)]
    offset[10]  = cond_bit  (0=BEQ/BGE, 1=BNE/BGT)
    offset[9:0] = desplazamiento con signo (10 bits)
    """
    off10 = sign_extend_to_field(offset, 10)  # 10 bits de desplazamiento
    field = ((cond_bit & 1) << 10) | (off10 & 0x3FF)  # bit10 + 10 bits
    return ((op & 0xF) << 19 | (rs1 & 0xF) << 15 |
            (rs2 & 0xF) << 11 | (field & 0x7FF))


def encode_j(op, rd, offset):
    """J-Type: [op(4)|rd(4)|offset(15)]"""
    off15 = sign_extend_to_field(offset, 15)
    return ((op & 0xF) << 19 | (rd & 0xF) << 15 | (off15 & 0x7FFF))


def encode_jr(op, rs1):
    """JR-Type: [op(4)|rs1(4)|res(15)=0]"""
    return ((op & 0xF) << 19 | (rs1 & 0xF) << 15)


def encode_v(op, rd, rs1, ki, funct):
    """V-Type: [op(4)|rd(4)|rs1(4)|ki(2)|funct(9)]"""
    return ((op & 0xF) << 19 | (rd  & 0xF) << 15 |
            (rs1 & 0xF) << 11 | (ki  & 0x3) << 9 |
            (funct & 0x1FF))


# Codificador de instrucción individual

def encode_instruction(line: str) -> int:
    """
    Toma una línea de ASM resuelto y retorna el entero de 23 bits.
    La línea no debe tener etiquetas ni comentarios (ya resueltos).
    """
    # Quitar comentarios inline
    line = line.split('#')[0].strip()
    if not line:
        return None

    tokens = line.split()
    op     = tokens[0].lower()

    # NOP 
    if op == 'nop':
        return 0

    # HALT
    if op == 'halt':
        return encode_jr(OPCODES['halt'], 0)

    # R-Type ALU: add sub and or xor sll srl sra
    if op in ALU_FUNCT:
        rd  = reg(tokens[1].rstrip(','))
        rs1 = reg(tokens[2].rstrip(','))
        rs2 = reg(tokens[3].rstrip(','))
        return encode_r(OPCODES[op], rd, rs1, rs2, ALU_FUNCT[op])

    # ADDI (I-Type)
    if op == 'addi':
        rd  = reg(tokens[1].rstrip(','))
        rs1 = reg(tokens[2].rstrip(','))
        imm = parse_int(tokens[3])
        return encode_i(OPCODES['addi'], rd, rs1, imm)

    # LLI (I-Type especial)
    # lli rd, imm8, pos
    # imm[10:9] = pos (selector de byte 0-3)
    # imm[8:0]  = imm8 (valor del byte)
    if op == 'lli':
        rd   = reg(tokens[1].rstrip(','))
        imm8 = parse_int(tokens[2].rstrip(',')) & 0xFF
        pos  = parse_int(tokens[3].rstrip(',')) & 0x3

        imm11 = (pos << 9) | imm8

        return encode_lli(OPCODES['lli'], rd, imm11)

    # LOAD (I-Type): load rd, offset(rs1)
    if op == 'load':
        rd            = reg(tokens[1].rstrip(','))
        offset, rs1_n = parse_offset_reg(tokens[2])
        return encode_i(OPCODES['load'], rd, reg(rs1_n), offset)

    # STORE (S-Type): store rs2, offset(rs1)
    if op == 'store':
        rs2           = reg(tokens[1].rstrip(','))
        offset, rs1_n = parse_offset_reg(tokens[2])
        return encode_s(OPCODES['store'], rs2, reg(rs1_n), offset)

    # BEQ / BNE (B-Type, opcode 0101)
    if op in ('beq', 'bne'):
        rs1    = reg(tokens[1].rstrip(','))
        rs2    = reg(tokens[2].rstrip(','))
        offset = parse_int(tokens[3])
        cond   = 1 if op == 'bne' else 0
        return encode_b(OPCODES['beq'], rs1, rs2, offset, cond)

    # BGE / BGT (B-Type, opcode 0110)
    if op in ('bge', 'bgt'):
        rs1    = reg(tokens[1].rstrip(','))
        rs2    = reg(tokens[2].rstrip(','))
        offset = parse_int(tokens[3])
        cond   = 1 if op == 'bgt' else 0
        return encode_b(OPCODES['bge'], rs1, rs2, offset, cond)

    # JAL (J-Type): jal rd, offset
    if op == 'jal':
        rd     = reg(tokens[1].rstrip(','))
        offset = parse_int(tokens[2])
        return encode_j(OPCODES['jal'], rd, offset)

    # JR (JR-Type): jr rs1
    if op == 'jr':
        return encode_jr(OPCODES['jr'], reg(tokens[1]))

    # TEA_ADD1 / TEA_ADD2 (V-Type)
    # tea_add1 rd, rs1, ki
    if op in ('tea_add1', 'tea_add2'):
        rd  = reg(tokens[1].rstrip(','))
        rs1 = reg(tokens[2].rstrip(','))
        ki  = parse_int(tokens[3]) & 0x3
        return encode_v(OPCODES[op], rd, rs1, ki, 0)

    # Instrucciones de bóveda (V-Type, opcode 1101)

    # login rs2_uid, rs1_pwd
    if op == 'login':
        rs2 = reg(tokens[1].rstrip(','))
        rs1 = reg(tokens[2].rstrip(','))
        return encode_v(OPCODES['login'], rs2, rs1, 0, VAULT_FUNCT['login'])

    # logout  (sin operandos)
    if op == 'logout':
        return encode_v(OPCODES['logout'], 0, 0, 0, VAULT_FUNCT['logout'])

    # setpwd rs2_uid, rs1_pwd
    if op == 'setpwd':
        rs2 = reg(tokens[1].rstrip(','))
        rs1 = reg(tokens[2].rstrip(','))
        return encode_v(OPCODES['setpwd'], rs2, rs1, 0, VAULT_FUNCT['setpwd'])

    # authorize rs1_token
    if op == 'authorize':
        rs1 = reg(tokens[1].rstrip(','))
        return encode_v(OPCODES['authorize'], 0, rs1, 0, VAULT_FUNCT['authorize'])

    # vkload rs1_data, ki
    if op == 'vkload':
        rs1 = reg(tokens[1].rstrip(','))
        ki  = parse_int(tokens[2]) & 0x3
        return encode_v(OPCODES['vkload'], 0, rs1, ki, VAULT_FUNCT['vkload'])

    # vkinv ki
    if op == 'vkinv':
        ki = parse_int(tokens[1]) & 0x3
        return encode_v(OPCODES['vkinv'], 0, 0, ki, VAULT_FUNCT['vkinv'])

    # authchk  (sin operandos)
    if op == 'authchk':
        return encode_v(OPCODES['authchk'], 0, 0, 0, AUTHCHK_FUNCT)

    raise ValueError(f"Instrucción no reconocida: '{line}'")


def encode_lli(op, rd, imm11):
    # NO signed check, solo 11 bits
    if not (0 <= imm11 <= 0x7FF):
        raise ValueError(f"LLI fuera de rango 11 bits: {imm11}")
    
    return ((op & 0xF) << 19 |
            (rd & 0xF) << 15 |
            (0 << 11) |
            (imm11 & 0x7FF))

# Clase principal

class BinaryGen:
    """
    Fase 6: convierte ASM resuelto en binario TEA-ISA.

    Formato del .bin (little-endian):
      Cada instrucción de 23 bits se almacena en 4 bytes (word-aligned).
      Los bits [31:23] son 0.
    """

    def __init__(self, asm_code: str):
        # Filtrar líneas vacías, comentarios puros y etiquetas
        self.lines = []
        for line in asm_code.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                continue
            if s.endswith(':'):
                continue
            self.lines.append(s)

        self.words  = []   # instrucciones codificadas (ints de 23 bits)
        self.errors = []

    def encode(self) -> bool:
        """Codifica todas las instrucciones. Retorna True si no hubo errores."""
        self.words  = []
        self.errors = []

        for lineno, line in enumerate(self.lines, start=1):
            try:
                result = encode_instruction(line)
                if result is None:
                    continue   # línea vacía o comentario
                # Validar que cabe en 23 bits
                if not (0 <= result <= 0x7FFFFF):
                    raise ValueError(
                        f"Resultado {result:#010x} excede 23 bits"
                    )
                self.words.append(result)
            except Exception as e:
                self.errors.append(f"Línea {lineno}: {e}  →  '{line}'")

        return len(self.errors) == 0

    def generate(self, bin_path: str, hex_path: str = None) -> bool:
        """
        Ensambla y escribe los archivos de salida.
        Retorna True si todo salió bien.
        """
        ok = self.encode()

        if not ok:
            print(f"\nErrores de codificación ({len(self.errors)}):")
            for e in self.errors:
                print(f"  {e}")
            return False

        # Archivo binario
        # Cada instrucción en 4 bytes little-endian (bits [31:23] = 0)
        with open(bin_path, 'wb') as f:
            for word in self.words:
                f.write(struct.pack('<I', word))

        print(f"Binario generado : {bin_path}  "
              f"({len(self.words)} instrucciones, "
              f"{len(self.words) * 4} bytes)")

        # Hex dump opcional
        if hex_path:
            with open(hex_path, 'w') as f:
                f.write(self._hex_dump())
            print(f"Hex dump generado: {hex_path}")

        return True

    def _hex_dump(self) -> str:
        """
        Hex dump legible para debugging.
        Formato por línea:
          0x0000  00000000  00000000000000000000000  addi r2, r0, 65532
        """
        lines = ["ADDR      HEX        BINARIO (23 bits)         ",
                 "-" * 55]
        for i, w in enumerate(self.words):
            addr    = i * 4
            bin_str = to_bin23(w)
            # Agrupar bits por campos para legibilidad
            grouped = (f"{bin_str[0:4]} {bin_str[4:8]} "
                       f"{bin_str[8:12]} {bin_str[12:16]} "
                       f"{bin_str[16:19]} {bin_str[19:23]}")
            lines.append(f"0x{addr:04X}  {w:06X}  {grouped}")
        return "\n".join(lines)

    def preview(self) -> list:
        """Retorna lista de strings binarios de 23 bits (para debug)."""
        self.encode()
        return [to_bin23(w) for w in self.words]