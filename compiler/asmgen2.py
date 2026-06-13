# Assembly Generator v2 — TEA-ISA 23-bit
# Trabaja sobre el IR optimizado (texto) en lugar del AST.
# Esto permite que todas las optimizaciones (DCE, unrolling, rename)
# se reflejen directamente en el código ensamblador generado.

import re

# Convención de registros
ARG_REGS  = ["r4", "r5", "r6", "r7"]   # argumentos / retorno
TEMP_REGS = ["r8", "r9", "r10", "r11"] # temporales
WORD      = 4

# Instrucciones de bóveda (se emiten directamente como mnemónicas)
VAULT_OPS = {
    'login', 'logout', 'setpwd', 'authchk',
    'authorize', 'vkload', 'vkinv', 'tea_add1', 'tea_add2',
}

# Patrones de líneas IR — orden importa (más específicos primero)
_RE_BEGIN_FUNC  = re.compile(r'^begin_func\s+(\w+)$')
_RE_END_FUNC    = re.compile(r'^end_func\s+(\w+)$')
_RE_FPARAM      = re.compile(r'^fparam\s+(\w+)$')
_RE_PARAM       = re.compile(r'^param\s+(.+)$')
_RE_CALL        = re.compile(r'^(\w[\w.]*)\s*=\s*call\s+(\w[\w.]*),\s*(\d+)$')
_RE_RETURN_VAL  = re.compile(r'^return\s+(.+)$')
_RE_RETURN_VOID = re.compile(r'^return$')
_RE_LABEL       = re.compile(r'^(\w+):$')
_RE_GOTO        = re.compile(r'^goto\s+(\w+)$')
_RE_IF          = re.compile(r'^if\s+(.+)\s+goto\s+(\w+)$')
_RE_IFFALSE     = re.compile(r'^iffalse\s+(.+)\s+goto\s+(\w+)$')
_RE_ALLOC       = re.compile(r'^(\w[\w.]*)\s*=\s*alloc\s+(\d+)$')
_RE_ARRAY_GET   = re.compile(r'^(\w[\w.]*)\s*=\s*(\w[\w.]*)\[(.+)\]$')   # t = arr[idx]
_RE_ARRAY_SET   = re.compile(r'^(\w[\w.]*)\[(.+)\]\s*=\s*(.+)$')          # arr[idx] = val
_RE_MEM_SET     = re.compile(r'^mem\[(.+)\]\s*=\s*(.+)$')
# BINOP: los operadores de dos chars (<=, >=, ==, !=, <<, >>, **) deben ir ANTES
# que los de un char para que el regex no parta <= en < y = 1
_RE_BINOP = re.compile(
    r'^(\w[\w.]*)\s*=\s*(.+?)\s*(==|!=|<=|>=|<<|>>|\*\*|[+\-*/%<>|&^])\s*(.+)$'
)
_RE_ASSIGN      = re.compile(r'^(\w[\w.]*)\s*=\s*(.+)$')
_RE_SAVE        = re.compile(r'^save\s+(\w+)$')
_RE_COMMENT     = re.compile(r'^#')
_RE_LOOP_ANN    = re.compile(r'^LOOP_')


class AsmGen2:
    """Genera ensamblador TEA-ISA a partir del IR optimizado (string)."""

    def __init__(self):
        self.code       = []   # líneas de ASM generadas
        self.pc         = 0    # contador de instrucciones (palabras)

        # Pool de registros temporales
        self._pool      = list(TEMP_REGS)
        self._used      = []

        # Contexto de función activa
        self._func      = None   # nombre de la función actual
        self._params    = []     # lista de nombres de parámetros (en orden)
        self._locals    = {}     # nombre → offset desde SP (positivo)
        self._frame_sz  = 0      # bytes reservados en el frame actual

        # Cola de params pendientes para la próxima call
        self._param_buf = []

        # Contador para etiquetas sintéticas (mul, div, etc.)
        self._lbl_count = 0

        # Globals declarados fuera de funciones
        # nombre → dirección (en palabras, se multiplica x4 para bytes)
        self._globals   = {}
        self._global_ptr = 0x0100  # DATA_BASE igual que el semántico original

    # ─────────────────────────────────────────────────────────────────────
    #  Punto de entrada
    # ─────────────────────────────────────────────────────────────────────

    def generate(self, ir: str) -> str:
        """Recibe el IR optimizado como string y retorna el ASM."""
        lines = [l.rstrip() for l in ir.splitlines()]

        # Pasada 1: descubrir globals (variables asignadas fuera de funciones)
        self._discover_globals(lines)

        # Pasada 2: generar código
        self._emit("lli r2, 0, 0")
        self._emit("lli r2, 0xE0, 1")

        # ¿Hay una función main?
        has_main = any(re.match(r'^begin_func\s+main$', l) for l in lines)

        # Inicializar globals
        self._emit_comment("--- globals ---")
        self._emit_globals(lines)

        if has_main:
            self._emit("jal r1, main")
            self._emit("halt")
        
        # Emitir funciones
        self._emit_comment("--- funciones ---")
        self._emit_functions(lines)

        if not has_main:
            self._emit("halt")

        return "\n".join(self.code)

    # ─────────────────────────────────────────────────────────────────────
    #  Pasada 1: descubrir globals
    # ─────────────────────────────────────────────────────────────────────

    def _discover_globals(self, lines):
        """Registra variables asignadas fuera de funciones con dirección."""
        in_func = False
        for line in lines:
            s = line.strip()
            if _RE_BEGIN_FUNC.match(s):
                in_func = True
            elif _RE_END_FUNC.match(s):
                in_func = False
            elif not in_func and not _RE_COMMENT.match(s) and not _RE_LOOP_ANN.match(s):
                # var = algo  (global)
                m = _RE_ASSIGN.match(s)
                if m:
                    name = m.group(1)
                    if name not in self._globals and name != 'mem':
                        self._globals[name] = self._global_ptr
                        self._global_ptr += 1

    # ─────────────────────────────────────────────────────────────────────
    #  Pasada 2a: inicializar globals
    # ─────────────────────────────────────────────────────────────────────

    def _emit_globals(self, lines):
        in_func = False
        for line in lines:
            s = line.strip()
            if _RE_BEGIN_FUNC.match(s):
                in_func = True
            elif _RE_END_FUNC.match(s):
                in_func = False
            elif not in_func:
                self._translate_line(s)

    # ─────────────────────────────────────────────────────────────────────
    #  Pasada 2b: emitir funciones
    # ─────────────────────────────────────────────────────────────────────

    def _emit_functions(self, lines):
        in_func = False
        for line in lines:
            s = line.strip()
            if _RE_BEGIN_FUNC.match(s):
                in_func = True
                self._translate_line(s)
            elif _RE_END_FUNC.match(s):
                self._translate_line(s)
                in_func = False
            elif in_func:
                self._translate_line(s)

    # ─────────────────────────────────────────────────────────────────────
    #  Dispatch principal
    # ─────────────────────────────────────────────────────────────────────

    def _translate_line(self, s: str):
        if not s or _RE_COMMENT.match(s) or _RE_LOOP_ANN.match(s):
            return  # ignorar comentarios y anotaciones del optimizador

        if _RE_SAVE.match(s):
            return  # save es solo una marca para DCE, no genera ASM

        m = _RE_BEGIN_FUNC.match(s)
        if m: return self._on_begin_func(m.group(1))

        m = _RE_END_FUNC.match(s)
        if m: return self._on_end_func(m.group(1))

        m = _RE_FPARAM.match(s)
        if m: return self._on_fparam(m.group(1))

        m = _RE_PARAM.match(s)
        if m: return self._on_param(m.group(1))

        m = _RE_CALL.match(s)
        if m: return self._on_call(m.group(1), m.group(2), int(m.group(3)))

        m = _RE_RETURN_VAL.match(s)
        if m: return self._on_return(m.group(1))

        if _RE_RETURN_VOID.match(s): return self._on_return(None)

        m = _RE_LABEL.match(s)
        if m: return self._emit_label(m.group(1))

        m = _RE_GOTO.match(s)
        if m: return self._emit(f"jal r0, {m.group(1)}")

        m = _RE_IF.match(s)
        if m: return self._on_if(m.group(1), m.group(2), invert=False)

        m = _RE_IFFALSE.match(s)
        if m: return self._on_if(m.group(1), m.group(2), invert=True)

        m = _RE_MEM_SET.match(s)
        if m: return self._on_mem_set(m.group(1), m.group(2))

        m = _RE_ARRAY_GET.match(s)
        if m: return self._on_array_get(m.group(1), m.group(2), m.group(3))

        m = _RE_ARRAY_SET.match(s)
        if m: return self._on_array_set(m.group(1), m.group(2), m.group(3))

        m = _RE_ALLOC.match(s)
        if m: return self._on_alloc(m.group(1), int(m.group(2)))

        # Binop: intentar antes que assign simple
        m = _RE_BINOP.match(s)
        if m: return self._on_binop(m.group(1), m.group(2).strip(),
                                     m.group(3), m.group(4).strip())

        m = _RE_ASSIGN.match(s)
        if m: return self._on_assign(m.group(1), m.group(2).strip())

    # ─────────────────────────────────────────────────────────────────────
    #  Gestión de funciones
    # ─────────────────────────────────────────────────────────────────────

    def _on_begin_func(self, name):
        self._func     = name
        self._params   = []
        self._locals   = {}
        self._frame_sz = 0
        self._param_buf = []
        self._emit_label(name)

    def _on_end_func(self, name):
        # Epílogo implícito si no se emitió jr r1
        last = next((l for l in reversed(self.code) if l.strip()), "")
        if last not in ("jr r1",):
            if self._frame_sz > 0:
                self._emit(f"addi r2, r2, {self._frame_sz}")
            self._emit("jr r1")
        self._func     = None
        self._params   = []
        self._locals   = {}
        self._frame_sz = 0

    def _on_fparam(self, name):
        """Registra un parámetro formal de la función.
        Los primeros 4 van en r4-r7. Los extras se spill al stack.
        """
        idx = len(self._params)
        self._params.append(name)
        # Si hay más de 4 params, el llamador los puso en el stack
        # los registramos como locales para que _load_value los encuentre
        if idx >= len(ARG_REGS):
            # El llamador empuja extras en el stack antes del jal
            # offset relativo al frame actual (se actualiza con _adjust_locals)
            spill_offset = (idx - len(ARG_REGS)) * WORD
            self._locals[name] = spill_offset

    # ─────────────────────────────────────────────────────────────────────
    #  Llamadas a función
    # ─────────────────────────────────────────────────────────────────────

    def _on_param(self, val):
        """Acumula un argumento en el buffer para la próxima call."""
        self._param_buf.append(val)

    def _on_call(self, dest, func_name, nargs):
        """Emite la llamada a función con sus argumentos."""
        # Guardar r1 (dirección de retorno)
        self._adjust_locals(+WORD)
        self._emit("addi r2, r2, -4")
        self._emit("store r1, 0(r2)")

        # Cargar argumentos en registros a0..a3
        args = self._param_buf[-nargs:] if nargs else []
        self._param_buf = self._param_buf[:-nargs] if nargs else self._param_buf
        for i, arg in enumerate(args):
            r = self._load_value(arg)
            self._emit(f"add {ARG_REGS[i]}, {r}, r0")
            self._free_if_temp(r)

        self._emit(f"jal r1, {func_name}")

        # Restaurar r1
        self._emit("load r1, 0(r2)")
        self._emit("addi r2, r2, 4")
        self._adjust_locals(-WORD)

        # Capturar valor de retorno
        r_ret = self._alloc()
        self._emit(f"add {r_ret}, r4, r0")
        self._store_var(dest, r_ret)
        self._free_if_temp(r_ret)

    # ─────────────────────────────────────────────────────────────────────
    #  Return
    # ─────────────────────────────────────────────────────────────────────

    def _on_return(self, val):
        if val is not None:
            val = val.strip()
            # Si el valor es una expresión binaria (ej: n * r, a + b)
            m = re.match(
                r'^(.+?)\s*(==|!=|<=|>=|<<|>>|\*\*|[+\-*/%<>|&^])\s*(.+)$',
                val
            )
            if m:
                left  = m.group(1).strip()
                op    = m.group(2)
                right = m.group(3).strip()
                # Usar temporal interno para calcular la expresión
                tmp = "__ret_tmp__"
                self._on_binop(tmp, left, op, right)
                r = self._load_value(tmp)
                self._emit(f"add r4, {r}, r0")
                self._free_if_temp(r)
                # Limpiar el temporal del frame
                if tmp in self._locals:
                    del self._locals[tmp]
                    self._frame_sz -= WORD
            else:
                r = self._load_value(val)
                self._emit(f"add r4, {r}, r0")
                self._free_if_temp(r)
        if self._frame_sz > 0:
            self._emit(f"addi r2, r2, {self._frame_sz}")
        self._emit("jr r1")

    # ─────────────────────────────────────────────────────────────────────
    #  Asignaciones
    # ─────────────────────────────────────────────────────────────────────

    def _on_assign(self, dest, src):
        r = self._load_value(src)
        self._store_var(dest, r)
        self._free_if_temp(r)

    def _on_binop(self, dest, left, op, right):
        # Multiplicación, división y módulo tienen su propio manejo
        if op == '*':
            return self._emit_mul(dest, left, right)
        if op == '/':
            return self._emit_div(dest, left, right)
        if op == '%':
            return self._emit_mod(dest, left, right)

        r1 = self._load_value(left)
        r2 = self._load_value(right)
        rd = self._alloc()

        ISA = {
            '+':  f"add  {rd}, {r1}, {r2}",
            '-':  f"sub  {rd}, {r1}, {r2}",
            '&':  f"and  {rd}, {r1}, {r2}",
            '|':  f"or   {rd}, {r1}, {r2}",
            '^':  f"xor  {rd}, {r1}, {r2}",
            '<<': f"sll  {rd}, {r1}, {r2}",
            '>>': f"srl  {rd}, {r1}, {r2}",
        }

        if op in ISA:
            self._emit(ISA[op])
        elif op in ('==', '!=', '<', '>', '<=', '>='):
            self._emit_cmp(rd, r1, r2, op)
        else:
            self._emit(f"add {rd}, {r1}, r0  # op '{op}' no soportado")

        self._free_if_temp(r1)
        self._free_if_temp(r2)
        self._store_var(dest, rd)
        self._free_if_temp(rd)

    def _emit_cmp(self, rd, r1, r2, op):
        """Genera r_dest = (r1 op r2) ? 1 : 0"""
        n    = self._lbl_count; self._lbl_count += 1
        lend = f"cmp_end_{n}"
        self._emit(f"addi {rd}, r0, 1")   # asumir true
        if   op == '==': self._emit(f"beq {r1}, {r2}, {lend}")
        elif op == '!=': self._emit(f"bne {r1}, {r2}, {lend}")
        elif op == '<':  self._emit(f"bgt {r2}, {r1}, {lend}")
        elif op == '>':  self._emit(f"bgt {r1}, {r2}, {lend}")
        elif op == '<=': self._emit(f"bge {r2}, {r1}, {lend}")
        elif op == '>=': self._emit(f"bge {r1}, {r2}, {lend}")
        self._emit(f"addi {rd}, r0, 0")
        self._emit_label(lend)

    def _emit_mul(self, dest, left, right):
        # Usa r3 como contador y r0 como acumulador fijo para no agotar el pool
        r_a   = self._load_value(left)
        r_b   = self._load_value(right)
        r_res = self._alloc()
        n     = self._lbl_count; self._lbl_count += 1
        lloop = f"mul_loop_{n}"
        lend  = f"mul_end_{n}"
        # r3 = contador (no es temporal, no necesita alloc)
        # r_res = acumulador resultado
        self._emit(f"addi {r_res}, r0, 0")
        self._emit(f"add  r3, {r_b}, r0")       # r3 = b (contador)
        self._emit(f"addi r3, r3, 0")            # nop para alineación
        self._free_if_temp(r_b)                  # liberar b ya copiado en r3
        self._emit_label(lloop)
        self._emit(f"beq  r3, r0, {lend}")
        self._emit(f"add  {r_res}, {r_res}, {r_a}")
        self._emit(f"addi r3, r3, -1")
        self._emit(f"jal  r0, {lloop}")
        self._emit_label(lend)
        self._free_if_temp(r_a)
        self._store_var(dest, r_res)
        self._free_if_temp(r_res)

    def _emit_div(self, dest, left, right):
        r_a   = self._load_value(left)
        r_b   = self._load_value(right)
        r_res = self._alloc()
        n     = self._lbl_count; self._lbl_count += 1
        lloop = f"div_loop_{n}"
        lbody = f"div_body_{n}"
        lend  = f"div_end_{n}"
        self._emit(f"addi {r_res}, r0, 0")
        self._emit_label(lloop)
        self._emit(f"bge {r_a}, {r_b}, {lbody}")
        self._emit(f"jal r0, {lend}")
        self._emit_label(lbody)
        self._emit(f"sub {r_a}, {r_a}, {r_b}")
        self._emit(f"addi {r_res}, {r_res}, 1")
        self._emit(f"jal r0, {lloop}")
        self._emit_label(lend)
        self._free_if_temp(r_a)
        self._free_if_temp(r_b)
        self._store_var(dest, r_res)
        self._free_if_temp(r_res)

    def _emit_mod(self, dest, left, right):
        r_a  = self._load_value(left)
        r_b  = self._load_value(right)
        n    = self._lbl_count; self._lbl_count += 1
        lloop = f"mod_loop_{n}"
        lbody = f"mod_body_{n}"
        lend  = f"mod_end_{n}"
        self._emit_label(lloop)
        self._emit(f"bge {r_a}, {r_b}, {lbody}")
        self._emit(f"jal r0, {lend}")
        self._emit_label(lbody)
        self._emit(f"sub {r_a}, {r_a}, {r_b}")
        self._emit(f"jal r0, {lloop}")
        self._emit_label(lend)
        self._free_if_temp(r_b)
        self._store_var(dest, r_a)
        self._free_if_temp(r_a)

    # ─────────────────────────────────────────────────────────────────────
    #  Control de flujo
    # ─────────────────────────────────────────────────────────────────────

    def _on_if(self, cond_var, label, invert: bool):
        """
        if  t goto L  →  si t != 0 salta a L  (invert=False)
        iffalse t goto L  →  si t == 0 salta a L  (invert=True)
        """
        r = self._load_value(cond_var)
        if invert:
            self._emit(f"beq {r}, r0, {label}")
        else:
            self._emit(f"bne {r}, r0, {label}")
        self._free_if_temp(r)

    # ─────────────────────────────────────────────────────────────────────
    #  Arrays y memoria
    # ─────────────────────────────────────────────────────────────────────

    def _on_alloc(self, dest, size):
        """t = alloc N  →  reservar N palabras en el stack."""
        bytes_ = size * WORD
        self._emit(f"addi r2, r2, -{bytes_}")
        self._adjust_locals(+bytes_, exclude=dest)
        self._locals[dest] = 0
        self._frame_sz    += bytes_

    def _on_array_get(self, dest, arr, idx_expr):
        """t = arr[idx]  →  load desde base + idx*4."""
        r_base = self._addr_of(arr)
        try:
            idx = int(idx_expr)
            r   = self._alloc()
            self._emit(f"load {r}, {idx * WORD}({r_base})")
            self._free_if_temp(r_base)
        except ValueError:
            # Índice variable: usar r3 como contador, r como acumulador de offset
            r_idx = self._load_value(idx_expr)
            r     = self._alloc()
            n = self._lbl_count; self._lbl_count += 1
            lloop = f"idx_loop_{n}"; lend = f"idx_end_{n}"
            self._emit(f"add  r3, {r_idx}, r0")   # r3 = idx (contador)
            self._free_if_temp(r_idx)
            self._emit(f"addi {r}, r0, 0")         # r = 0 (acum offset)
            self._emit_label(lloop)
            self._emit(f"beq  r3, r0, {lend}")
            self._emit(f"addi {r}, {r}, {WORD}")
            self._emit(f"addi r3, r3, -1")
            self._emit(f"jal  r0, {lloop}")
            self._emit_label(lend)
            self._emit(f"add  {r_base}, {r_base}, {r}")
            self._emit(f"load {r}, 0({r_base})")
            self._free_if_temp(r_base)
        self._store_var(dest, r)
        self._free_if_temp(r)

    def _on_array_set(self, arr, idx_expr, val):
        """arr[idx] = val  →  store en base + idx*4."""
        r_val  = self._load_value(val)
        r_base = self._addr_of(arr)
        try:
            idx = int(idx_expr)
            if idx == 0:
                self._emit(f"store {r_val}, 0({r_base})")
            else:
                r_off = self._load_immediate(idx * WORD)
                r_dst = self._alloc()
                self._emit(f"add {r_dst}, {r_base}, {r_off}")
                self._emit(f"store {r_val}, 0({r_dst})")
                self._free_if_temp(r_off)
                self._free_if_temp(r_dst)
        except ValueError:
            # Índice variable
            r_idx  = self._load_value(idx_expr)
            r_off  = self._alloc()
            r_addr = self._alloc()
            self._emit(f"addi {r_off}, r0, {WORD}")
            self._emit(f"add  r3, {r_idx}, r0")
            n = self._lbl_count; self._lbl_count += 1
            lloop = f"sidx_loop_{n}"; lend = f"sidx_end_{n}"
            self._emit(f"add  {r_addr}, r0, r0")
            self._emit_label(lloop)
            self._emit(f"beq  r3, r0, {lend}")
            self._emit(f"add  {r_addr}, {r_addr}, {r_off}")
            self._emit(f"addi r3, r3, -1")
            self._emit(f"jal  r0, {lloop}")
            self._emit_label(lend)
            self._emit(f"add  {r_addr}, {r_base}, {r_addr}")
            self._emit(f"store {r_val}, 0({r_addr})")
            self._free_if_temp(r_idx)
            self._free_if_temp(r_off)
            self._free_if_temp(r_addr)
        self._free_if_temp(r_val)
        self._free_if_temp(r_base)

    def _on_mem_set(self, addr_expr, val_expr):
        """mem[addr] = val  →  store directo en dirección."""
        r_addr = self._load_value(addr_expr)
        r_val  = self._load_value(val_expr)
        # addr lógica → addr en bytes (x4)
        r_shift = self._alloc()
        r_addr4 = self._alloc()
        self._emit(f"addi {r_shift}, r0, 2")
        self._emit(f"sll  {r_addr4}, {r_addr}, {r_shift}")
        self._free_if_temp(r_shift)
        self._free_if_temp(r_addr)
        self._emit(f"store {r_val}, 0({r_addr4})")
        self._free_if_temp(r_val)
        self._free_if_temp(r_addr4)

    # ─────────────────────────────────────────────────────────────────────
    #  Carga y almacenamiento de valores
    # ─────────────────────────────────────────────────────────────────────

    def _load_value(self, token: str) -> str:
        """Carga 'token' en un registro y lo retorna.
        token puede ser: nombre de variable, literal entero, hex, o bool.
        """
        t = token.strip()

        # Literal booleano
        if t == 'true':  return self._load_immediate(1)
        if t == 'false': return self._load_immediate(0)

        # Literal hexadecimal
        if re.match(r'^0[xX][0-9a-fA-F]+$', t):
            return self._load_immediate(int(t, 16))

        # Literal entero (con posible signo)
        if re.match(r'^-?\d+$', t):
            return self._load_immediate(int(t))

        # Parámetro formal de la función actual
        if t in self._params:
            idx = self._params.index(t)
            if idx < len(ARG_REGS):
                r   = self._alloc()
                self._emit(f"add {r}, {ARG_REGS[idx]}, r0")
                return r

        # Variable local
        if t in self._locals:
            offset = self._locals[t]
            r      = self._alloc()
            self._emit(f"load {r}, {offset}(r2)")
            return r

        # Variable global
        if t in self._globals:
            addr   = self._globals[t]
            r_addr = self._load_immediate(addr * WORD)
            r      = self._alloc()
            self._emit(f"load {r}, 0({r_addr})")
            self._free_if_temp(r_addr)
            return r

        # Si es un nombre no registrado todavía, declararlo como local
        r = self._alloc()
        self._emit(f"addi {r}, r0, 0  # variable '{t}' no encontrada")
        return r

    def _store_var(self, name: str, reg: str):
        """Almacena el registro en la variable local o global."""
        if name in self._params:
            idx = self._params.index(name)
            self._emit(f"add {ARG_REGS[idx]}, {reg}, r0")
            return

        if name in self._locals:
            offset = self._locals[name]
            self._emit(f"store {reg}, {offset}(r2)")
            return

        # Si es local nueva, reservar en el stack
        if self._func is not None and name not in self._globals:
            self._emit("addi r2, r2, -4")
            self._adjust_locals(+WORD, exclude=name)
            self._locals[name] = 0
            self._frame_sz    += WORD
            self._emit(f"store {reg}, 0(r2)")
            return

        # Global
        if name not in self._globals:
            self._globals[name] = self._global_ptr
            self._global_ptr   += 1
        addr   = self._globals[name]
        r_addr = self._load_immediate(addr * WORD)
        self._emit(f"store {reg}, 0({r_addr})")
        self._free_if_temp(r_addr)

    def _addr_of(self, name: str) -> str:
        """Retorna un registro con la DIRECCIÓN de la variable (no su valor)."""
        if name in self._locals:
            offset = self._locals[name]
            r      = self._alloc()
            if offset == 0:
                self._emit(f"add {r}, r2, r0")
            elif offset > 0:
                self._emit(f"addi {r}, r2, {offset}")
            else:
                r_off = self._load_immediate(offset)
                self._emit(f"add {r}, r2, {r_off}")
                self._free_if_temp(r_off)
            return r

        if name in self._globals:
            addr = self._globals[name]
            return self._load_immediate(addr * WORD)

        r = self._alloc()
        self._emit(f"addi {r}, r0, 0  # addr de '{name}' desconocida")
        return r

    # ─────────────────────────────────────────────────────────────────────
    #  Inmediatos
    # ─────────────────────────────────────────────────────────────────────

    def _load_immediate(self, value: int) -> str:
        r      = self._alloc()
        value32 = value & 0xFFFFFFFF
        if 0 <= value < 1023:
            self._emit(f"addi {r}, r0, {value}")
            return r
        if -1024 <= value < 0:
            self._emit(f"addi {r}, r0, {value}")
            return r
        # Cargar byte a byte
        b = [(value32 >> (i*8)) & 0xFF for i in range(4)]
        first = True
        for i, byte in enumerate(b):
            if byte != 0 or (i == 0 and all(x == 0 for x in b)):
                self._emit(f"lli {r}, {hex(byte)}, {i}")
                first = False
            elif i == 0:
                self._emit(f"lli {r}, 0, 0")
                first = False
        if first:
            self._emit(f"addi {r}, r0, 0")
        return r

    # ─────────────────────────────────────────────────────────────────────
    #  Gestión de registros
    # ─────────────────────────────────────────────────────────────────────

    def _alloc(self) -> str:
        if not self._pool:
            raise RuntimeError("Pool de registros temporales agotado")
        r = self._pool.pop(0)
        self._used.append(r)
        return r

    def _free_if_temp(self, reg: str):
        if reg in TEMP_REGS and reg in self._used:
            self._used.remove(reg)
            self._pool.insert(0, reg)

    # ─────────────────────────────────────────────────────────────────────
    #  Helpers de frame
    # ─────────────────────────────────────────────────────────────────────

    def _adjust_locals(self, delta: int, exclude: str = None):
        """Ajusta todos los offsets locales cuando cambia SP."""
        for k in self._locals:
            if k != exclude:
                self._locals[k] += delta

    # ─────────────────────────────────────────────────────────────────────
    #  Emisión de instrucciones
    # ─────────────────────────────────────────────────────────────────────

    def _emit(self, instr: str):
        self.code.append(instr)
        self.pc += 1

    def _emit_label(self, label: str):
        self.code.append(f"{label}:")

    def _emit_comment(self, msg: str):
        self.code.append(f"# {msg}")
