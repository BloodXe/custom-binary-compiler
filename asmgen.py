# Assembly Generator — TEA-ISA 23-bit
# Ejecucion: python3 main.py CodigosTest/<input_file> -S

from platform import node
import sys
from ast_nodes import (
    Program, SectionBlock, FunctionDeclaration, VarDeclaration, ConstDeclaration,
    Assignment, ExpressionStatement, IfStatement, WhileStatement, ForStatement,
    ReturnStatement, ImportStatement,
    BinaryOp, UnaryOp, FunctionCall,
    Identifier, IndexAccess,
    IntLiteral, HexLiteral, RealLiteral, BoolLiteral, StringLiteral, ListLiteral,
)

# Instrucciones de bóveda: Se emiten directamente como mnemónica ISA
# en vez de tratarse como llamadas a función normales.
# tea_add1/tea_add2 también son de bóveda (requieren AUTH=1).
VAULT_OPS = {
    'login', 'logout', 'setpwd', 'authchk', 'authorize', 'vkload', 'vkinv',
    'tea_add1', 'tea_add2',
}

# Registros de argumentos / retorno según la convención del ISA
ARG_REGS    = ["r4", "r5", "r6", "r7"]   # a0-a3
TEMP_REGS   = ["r8", "r9", "r10", "r11"] # t0-t3

# Tamaño de palabra en bytes
WORD = 4


class AsmGen:
    """Genera código ensamblador TEA-ISA a partir del AST anotado por el semántico."""

    def __init__(self, semantic):
        self.semantic        = semantic # SemanticAnalyzer ya ejecutado
        self.code            = [] # líneas de ensamblador generadas
        self.pc              = 0 # contador de instrucciones (en bytes)

        # Pila de registros temporales disponibles
        # Permite anidar expresiones sin pisarse
        self._reg_pool       = list(TEMP_REGS)
        self._reg_stack      = [] # registros "en uso" actualmente

        # Contexto de función actual
        self.current_func_name = None # nombre de la función siendo compilada
        self.current_params  = [] # lista de nombres de parámetros
        self.current_locals  = {} # nombre → offset relativo a SP
        self.local_offset    = 0 # bytes usados en el frame local

        # Contador para etiquetas de multiplicación (evita colisiones)
        self._mul_count      = 0

    # Funcion principal de generación de código: recibe el AST completo y retorna el código ensamblador como string
    def generate(self, ast) -> str:
        """
        Orden de emisión:
          1. init SP
          2. inicializar globals  ← aquí, antes de saltar a main
          3. jal main / halt
          4. código de funciones
        """
        # Pasada 1: asignar direcciones reales a funciones
        self._assign_function_addresses(ast)
 
        # 1. Init SP
        self._emit("lli r2, 0, 0")    # r2[7:0]  = 0x00
        self._emit("lli r2, 0xE0, 1") # r2[15:8] = 0xE0  → r2 = 0xE000
 
        # 2. Globals: recorrer solo declaraciones de nivel superior
        self._emit_blank()
        self._emit_label("# --- inicialización de variables globales ---")
        for section in self._sections(ast):
            for node in section:
                if isinstance(node, (VarDeclaration, ConstDeclaration)):
                    self.visit(node)
 
        # 3. Saltar a main (si existe) o simplemente halt
        self._emit_blank()
        main_sym = self.semantic.symbol_table.lookup("main")
        if main_sym is not None:
            self._emit("jal r1, main")
            self._emit("halt")
 
        # 4. Funciones (y cualquier otra sentencia que no sea global)
        self._emit_blank()
        self._emit_label("# --- funciones ---")
        for section in self._sections(ast):
            for node in section:
                if not isinstance(node, (VarDeclaration, ConstDeclaration,
                                         ImportStatement)):
                    self.visit(node)

        if main_sym is None:
            self._emit("halt")

        return "\n".join(self.code)

    # Helper para iterar sobre las secciones del programa: maneja tanto programas con secciones 
    # @code/@boveda como programas sin secciones (donde el cuerpo es directamente el programa)
    def _sections(self, ast):
        """Itera sobre las listas de sentencias de cada sección del programa."""
        for stmt in (ast.statements if hasattr(ast, 'statements') else [ast]):
            if hasattr(stmt, 'body'):
                yield stmt.body
            else:
                yield [stmt]


    # Pasada 1: asignación de direcciones de funciones                   #
    def _assign_function_addresses(self, ast):
        """
        Recorre el AST en orden y simula cuántas instrucciones emitirá cada
        función para asignar su dirección real de entrada (en bytes) en la
        tabla de símbolos antes de la pasada 2.

        Por simplicidad usamos una estimación conservadora:
          - Cada instrucción ocupa 4 bytes (TEA-ISA usa 23 bits pero
            las instrucciones se almacenan word-aligned → 4 bytes/instr).
        
        Esto es suficiente para el enlazado de etiquetas de salto.
        """
        # PC inicial: 2 instrucciones de prólogo (addi sp + jal main/halt)
        estimated_pc = 2 * WORD

        # Para cada función, asignamos su dirección actual en la tabla de símbolos
        for section in (ast.statements if hasattr(ast, 'statements') else [ast]):

            # Las funciones pueden estar dentro de secciones @code o @boveda, o directamente en el programa
            body = section.body if hasattr(section, 'body') else [section]

            # Para cada nodo en el cuerpo, si es una función, asignamos su dirección y estimamos su tamaño
            for node in body:

                # Solo asignamos direcciones a las funciones declaradas
                if isinstance(node, FunctionDeclaration):
                    # Actualizar la dirección en la tabla de símbolos
                    sym = self.semantic.symbol_table.lookup(node.name)
                    if sym is not None:
                        sym.address = estimated_pc
                    # Estimar tamaño de la función (instrucciones aproximadas)
                    estimated_pc += self._estimate_func_size(node) * WORD
    
    # Estimación del tamaño de funciones e instrucciones para la asignación de direcciones
    def _estimate_func_size(self, node: FunctionDeclaration) -> int:
        """Estimación del número de instrucciones de una función."""
        # Contar sentencias recursivamente de forma sencilla
        count = 2  # etiqueta + jr r1 de retorno
        for stmt in node.body:
            count += self._estimate_stmt_size(stmt)
        return count

    # Estimación del tamaño de sentencias e instrucciones para la asignación de direcciones
    def _estimate_stmt_size(self, node) -> int:
        """Estimación recursiva por tipo de nodo."""
        if node is None:
            return 0
        t = type(node).__name__
        if t in ('VarDeclaration', 'ConstDeclaration'):
            return 6   # load_immediate (hasta 5) + store
        if t == 'Assignment':
            return 8
        if t == 'IfStatement':
            return (4
                    + sum(self._estimate_stmt_size(s) for s in node.then_block)
                    + sum(self._estimate_stmt_size(s) for s in node.else_block))
        if t == 'WhileStatement':
            return (4
                    + sum(self._estimate_stmt_size(s) for s in node.body))
        if t == 'ForStatement':
            return (6
                    + sum(self._estimate_stmt_size(s) for s in node.body))
        if t == 'ReturnStatement':
            return 3
        if t == 'ExpressionStatement':
            return 8   # llamada a función con prólogo/epílogo
        return 4

    # Helpers de generación de código: emisión de instrucciones y gestión de registros temporales
    def _emit(self, instr: str):
        """Agrega una instrucción a la lista y avanza el PC."""
        self.code.append(instr)
        self.pc += WORD

    def _emit_label(self, label: str):
        """Agrega una etiqueta (no cuenta como instrucción para el PC)."""
        self.code.append(f"{label}:")

    def _emit_blank(self):
        self.code.append("")

    # Gestión de registros temporales: asignación y liberación para evitar colisiones en expresiones anidadas
    def _alloc_reg(self) -> str:
        """
        Obtiene un registro temporal libre de la pool.
        Lanza excepción si se agotaron (expresión demasiado profunda).
        """
        # Si no quedan registros temporales, no podemos continuar sin pisar valores en uso.
        if not self._reg_pool:
            raise RuntimeError(
                "Se agotaron los registros temporales (expresión demasiado compleja). "
                "Considera simplificar la expresión o usar variables intermedias."
            )
        
        # Asignar el primer registro disponible y marcarlo como en uso
        reg = self._reg_pool.pop(0)
        self._reg_stack.append(reg)
        return reg
    
    # Liberar registros temporales: se pueden liberar explícitamente o automáticamente al salir de una expresión
    def _free_reg(self, reg: str):
        """Devuelve un registro temporal a la pool."""
        # Solo liberamos si es un registro temporal y no está ya libre
        if reg in TEMP_REGS and reg not in self._reg_pool:
            self._reg_stack.remove(reg)
            self._reg_pool.insert(0, reg)

    # Liberar un registro solo si es temporal (no argumento ni especial)
    def _free_if_temp(self, reg: str):
        """Libera el registro solo si es un temporal (no arg ni especial)."""
        if reg in TEMP_REGS:
            self._free_reg(reg)

    # ------------------------------------------------------------------ #
    #  Carga de inmediatos                                                 #
    # ------------------------------------------------------------------ #

    def load_immediate(self, value: int) -> str:
        """
        Carga un valor entero en un registro temporal y lo retorna.
        Valores pequeños (0..2047): addi rd, r0, value
        Valores grandes: lli byte por byte (preserva bytes no escritos en pos > 0)
        Valores negativos pequeños: addi con signo
        """
        r = self._alloc_reg()

        # Normalizar a 32 bits sin signo para el cálculo de bytes
        value32 = value & 0xFFFFFFFF

        # Si el valor cabe en 11 bits sin signo (0..1023), lo cargamos directamente con addi
        if 0 <= value < 1023:
            self._emit(f"addi {r}, r0, {value}")
            return r

        # Valores negativos que caben en 11 bits con signo (-1024..-1)
        if -1024 <= value < 0:
            self._emit(f"addi {r}, r0, {value}")
            return r

        # Valor grande: cargar byte a byte con lli
        # lli rd, imm8, 0  => rd[7:0]   = imm8  (limpia bits 31:8)
        # lli rd, imm8, 1  =>  rd[15:8]  = imm8  (resto sin cambio)
        # lli rd, imm8, 2  =>  rd[23:16] = imm8
        # lli rd, imm8, 3  =>  rd[31:24] = imm8
        bytes_list = [
            (value32 >>  0) & 0xFF,
            (value32 >>  8) & 0xFF,
            (value32 >> 16) & 0xFF,
            (value32 >> 24) & 0xFF,
        ]

        first = True

        # Para cada byte, si es no nulo o es el primer byte (para limpiar el registro), emitimos lli
        for i, byte in enumerate(bytes_list):
            if byte != 0 or (i == 0 and all(b == 0 for b in bytes_list)):
                self._emit(f"lli {r}, {byte}, {i}")
                first = False
            elif i == 0:
                # Primer byte es 0 pero hay bytes no nulos después:
                # lli con pos=0 limpia el registro, así que lo emitimos igual
                self._emit(f"lli {r}, 0, 0")
                first = False

        if first:
            # Si todos los bytes son 0, entonces addi 0
            self._emit(f"addi {r}, r0, 0")

        return r

    # Función principal de visita del AST: dispatch a métodos específicos por tipo de nodo
    def visit(self, node):
        method = getattr(self, f"visit_{node.__class__.__name__}", self.generic_visit)
        return method(node)

    def generic_visit(self, node):

        # Por defecto, visitamos recursivamente los hijos del nodo (si tiene atributo 'children')
        for child in getattr(node, "children", []):
            if child is not None:
                self.visit(child)

    # Programa y secciones: recorremos el cuerpo de cada sección o programa para generar código

    def visit_Program(self, node):
        for stmt in node.statements:
            self.visit(stmt)

    def visit_SectionBlock(self, node):
        # Las secciones @boveda y @code se tratan igual en el AsmGen:
        # la distinción semántica ya fue validada; aquí solo generamos código.
        for stmt in node.body:
            self.visit(stmt)

    def visit_ImportStatement(self, node):
        pass  # El enlazado de módulos queda fuera del scope de esta etapa

    # Literales: se cargan en registros temporales usando load_immediate o secuencias de instrucciones para valores grandes

    # Para IntLiteral
    def visit_IntLiteral(self, node) -> str:
        return self.load_immediate(node.value)

    # Para HexLiteral, convertimos a entero y luego usamos load_immediate
    def visit_HexLiteral(self, node) -> str:
        value = int(node.value, 16) if isinstance(node.value, str) else node.value
        return self.load_immediate(value)

    # Para RealLiteral, representamos como IEEE 754 de 32 bits (entero) y luego cargamos ese entero
    def visit_RealLiteral(self, node) -> str:
        # Representar como IEEE 754 de 32 bits (entero)
        import struct
        bits = struct.unpack('I', struct.pack('f', node.value))[0]
        return self.load_immediate(bits)

    # Para BoolLiteral, cargamos 1 para true y 0 para false
    def visit_BoolLiteral(self, node) -> str:
        return self.load_immediate(1 if node.value else 0)

    # Para los StringLiteral
    def visit_StringLiteral(self, node) -> str:
        # Las cadenas no se mapean a código binario en esta versión;
        # retornamos r0 (0) como placeholder
        r = self._alloc_reg()
        self._emit(f"addi {r}, r0, 0   # string literal (no soportado en binario)")
        return r

    # Para ListLiteral
    def visit_ListLiteral(self, node) -> str:
        # Los list literals se manejan dentro de VarDeclaration/ConstDeclaration
        # Si llegan aquí solos, retornamos r0
        r = self._alloc_reg()
        self._emit(f"addi {r}, r0, 0   # list literal (manejar en declaracion)")
        return r

    # Identificadores: pueden ser parámetros (en registros de argumento), variables locales (en el frame) o globales (en memoria absoluta)

    # Para Identifier, determinamos su contexto (parámetro, local o global) y generamos el código de carga correspondiente
    def visit_Identifier(self, node) -> str:
        name = node.name

        # Parámetro de función actual: registro a0-a3 directamente
        if name in self.current_params:
            idx = self.current_params.index(name)

            # No consumimos un temporal; el valor ya está en el registro de argumento
            r = self._alloc_reg()
            self._emit(f"add {r}, {ARG_REGS[idx]}, r0")
            return r

        # Variable local: Cargar desde el frame (offset relativo a SP)
        if name in self.current_locals:
            offset = self.current_locals[name]
            r = self._alloc_reg()
            self._emit(f"load {r}, {offset}(r2)")
            return r

        # Variable / constante global: Cargar desde memoria absoluta
        sym = self.semantic.symbol_table.lookup(name)
        addr = sym.address if sym else 0
        r_addr = self.load_immediate(addr * 4)
        r      = self._alloc_reg()
        self._emit(f"load {r}, 0({r_addr})")
        self._free_reg(r_addr)
        return r


    # IndexAccess: para arr[i], obtenemos la dirección base del arreglo y calculamos la dirección del 
    # elemento con desplazamiento (index * 4), luego cargamos el valor
    def visit_IndexAccess(self, node) -> str:
        
        # Caso especial para mem[i]: el identificador "mem" es un caso especial reservado para acceder a memoria absoluta
        if isinstance(node.target, Identifier) and node.target.name == "mem":
            r_addr = self.visit(node.indices[0])
            
            # Multiplicar por 4 para convertir dirección lógica a dirección de palabra
            r_addr4 = self._alloc_reg()
            r_shift = self._alloc_reg()
            self._emit(f"addi {r_shift}, r0, 2")
            self._emit(f"sll {r_addr4}, {r_addr}, {r_shift}")
            self._free_reg(r_shift)
            self._free_if_temp(r_addr)

            r_val = self._alloc_reg()
            self._emit(f"load {r_val}, 0({r_addr4})")
            self._free_reg(r_addr4)
            return r_val
        
        # Para otros casos de a arreglos, resolvemos la dirección base del arreglo (puede ser global o local) y luego calculamos la dirección del elemento con el índice
        r_base  = self._resolve_array_base(node.target)
        r_index = self.visit(node.indices[0])
        

        # Calcular offset = index * 4
        r_shift = self._alloc_reg()
        self._emit(f"addi {r_shift}, r0, 2")
        
        r_offset = self._alloc_reg()
        self._emit(f"sll {r_offset}, {r_index}, {r_shift}")
        self._free_reg(r_shift)      
        self._free_if_temp(r_index)  

        # addr = base + offset
        r_addr = self._alloc_reg()
        self._emit(f"add {r_addr}, {r_base}, {r_offset}")
        self._free_reg(r_offset)     
        self._free_if_temp(r_base)  

        # Cargar valor
        r_value = self._alloc_reg()
        self._emit(f"load {r_value}, 0({r_addr})")
        self._free_reg(r_addr)       

        return r_value

    # Helper para resolver la dirección base de un arreglo, manejando tanto variables globales como locales, y accesos anidados (matrix[i][j])
    def _resolve_array_base(self, node) -> str:
        """
        Retorna un registro con la dirección base de un arreglo.
        Maneja: Identifier (global o local) e IndexAccess anidado (matrix[i]).
        """

        # Si es un Identifier, puede ser local (offset en el frame) o global (dirección absoluta)
        if isinstance(node, Identifier):
            name = node.name

            # Primero verificamos si es una variable local (en el frame), si no, asumimos que es global (en memoria absoluta)
            if name in self.current_locals:

                # Arreglo local: Su dirección base = SP + offset
                offset = self.current_locals[name]
                r = self._alloc_reg()

                # Si el offset es 0, podemos cargar directamente con add (SP + 0 = SP)
                if offset == 0:
                    self._emit(f"add {r}, r2, r0")

                # Si el offset es positivo, usamos addi para cargar la dirección base (SP + offset)
                elif offset > 0:
                    self._emit(f"addi {r}, r2, {offset}")
                else:
                    # Offset negativo: usar addi con signo si cabe en 11 bits
                    # Si no, cargar con load_immediate y sumar
                    if offset >= -1024:
                        self._emit(f"addi {r}, r2, {offset}")
                    else:
                        r_off = self.load_immediate(offset)
                        self._emit(f"add {r}, r2, {r_off}")
                        self._free_reg(r_off)
                return r

            # Global: Dirección absoluta
            sym  = self.semantic.symbol_table.lookup(name)
            addr = sym.address if sym else 0
            r = self.load_immediate(addr * 4)
            return r

        if isinstance(node, IndexAccess):
            # matrix[i][j]: Primero obtenemos la dirección de la fila matrix[i]
            r_row_base = self._resolve_array_base(node.target) # Registro con la dirección base de matrix[i]
            r_index = self.visit(node.indices[0]) # Registro con el valor de j (índice de la columna)
            r_shift = self._alloc_reg() # Registro para el desplazamiento (j * 4)
            r_offset = self._alloc_reg() # Registro para la dirección del elemento (matrix[i] + j*4)
            
            self._emit(f"addi {r_shift}, r0, 2")
            self._emit(f"sll {r_offset}, {r_index}, {r_shift}")

            self._free_reg(r_shift) # Liberamos r_shift para tener uno disponible para r_addr
            r_addr = self._alloc_reg() # Registro para la dirección final del elemento (matrix[i][j])

            self._emit(f"add {r_addr}, {r_row_base}, {r_offset}")

            self._free_if_temp(r_index)
            self._free_reg(r_offset)
            self._free_if_temp(r_row_base)

            return r_addr

        # Si el nodo no es ni Identifier ni IndexAccess, no sabemos cómo resolverlo; retornamos 0
        r = self._alloc_reg()
        self._emit(f"addi {r}, r0, 0")
        return r

    # Expresiones binarias y unarias: generamos código para evaluar operandos y luego aplicamos la operación usando las instrucciones de la ISA
    

    def _contains_call(self, node) -> bool:
        """Retorna True si el nodo o alguno de sus descendientes es una FunctionCall."""
        from ast_nodes import FunctionCall
        if isinstance(node, FunctionCall):
            return True
        for child in getattr(node, 'children', []):
            if child and self._contains_call(child):
                return True
        return False


    # Para BinaryOp, manejamos operadores aritméticos, lógicos y de comparación. La multiplicación se emite como un 
    # loop de suma repetida (no hay instrucción MUL en el ISA).
    def visit_BinaryOp(self, node) -> str:
        # Multiplicación tiene su propio método que ya maneja el caso de FunctionCall
        if node.op == '*':
            return self._emit_mul(node)
        elif node.op == '/':
            return self._emit_div(node)
        elif node.op == '%':
            return self._emit_mod(node)
 
        # Evaluar lado izquierdo
        r1 = self.visit(node.left)
 
        # Si el lado derecho contiene una llamada a función, proteger r1 en el stack.
        # Las llamadas destruyen los registros temporales (r8-r11) durante su ejecución.
        right_has_call = self._contains_call(node.right)
 
        if right_has_call:
            # PUSH r1 al stack
            self._emit("addi r2, r2, -4")
            self._emit(f"store {r1}, 0(r2)")
            # Ajustar offsets de variables locales
            for k in self.current_locals:
                self.current_locals[k] += 4
            self.local_offset += 4
            self._free_if_temp(r1)
 
            # Evaluar lado derecho (puede llamar funciones)
            r2_val = self.visit(node.right)
 
            # POP r1 del stack
            r1 = self._alloc_reg()
            self._emit(f"load {r1}, 0(r2)")
            self._emit("addi r2, r2, 4")
            # Restaurar offsets de variables locales
            for k in self.current_locals:
                self.current_locals[k] -= 4
            self.local_offset -= 4
        else:
            r2_val = self.visit(node.right)
 
        r3 = self._alloc_reg()
 
        ISA_OPS = {
            '+':  f"add  {r3}, {r1}, {r2_val}",
            '-':  f"sub  {r3}, {r1}, {r2_val}",
            '&':  f"and  {r3}, {r1}, {r2_val}",
            '|':  f"or   {r3}, {r1}, {r2_val}",
            '^':  f"xor  {r3}, {r1}, {r2_val}",
            '<<': f"sll  {r3}, {r1}, {r2_val}",
            '>>': f"srl  {r3}, {r1}, {r2_val}",
        }
 
        if node.op in ISA_OPS:
            self._emit(ISA_OPS[node.op])
        elif node.op in ('==', '!=', '<', '>', '<=', '>=', 'and', 'or'):
            self._emit_comparison(r3, r1, r2_val, node.op)
        else:
            self._emit(f"add {r3}, {r1}, r0   # operador '{node.op}' no soportado")
 
        self._free_if_temp(r1)
        self._free_if_temp(r2_val)
        return r3


    # Para UnaryOp, manejamos operadores unarios como negación, NOT lógico y NOT a nivel de bits. 
    # Se mapean a instrucciones de la ISA o se sintetizan con branches para el caso de NOT lógico.
    def _emit_comparison(self, r_dest: str, r1: str, r2: str, op: str):
        """
        Genera código para r_dest = (r1 op r2) ? 1 : 0
        usando branches del ISA.
        """

        lbl_true = f"cmp_true_{self.pc}" # Etiqueta para el caso verdadero (se salta si la comparación es cierta)
        lbl_end  = f"cmp_end_{self.pc}" # Etiqueta de fin (se salta al final después de establecer el resultado)

        self._emit(f"addi {r_dest}, r0, 1")   # Asumimos true

        if op == '==':
            self._emit(f"beq {r1}, {r2}, {lbl_end}")
        elif op == '!=':
            self._emit(f"bne {r1}, {r2}, {lbl_end}")
        elif op == '<':
            # r1 < r2  = r2 > r1  =  bgt r2, r1  salta si true
            self._emit(f"bgt {r2}, {r1}, {lbl_end}")
        elif op == '>':
            self._emit(f"bgt {r1}, {r2}, {lbl_end}")
        elif op == '<=':
            self._emit(f"bge {r2}, {r1}, {lbl_end}")
        elif op == '>=':
            self._emit(f"bge {r1}, {r2}, {lbl_end}")
        elif op == 'and':
            # true && true: Ambos deben ser != 0
            lbl_false = f"cmp_false_{self.pc}"
            self._emit(f"beq {r1}, r0, {lbl_false}")
            self._emit(f"bne {r2}, r0, {lbl_end}")
            self._emit_label(lbl_false)
            self._emit(f"addi {r_dest}, r0, 0")
            self._emit(f"jal r0, {lbl_end}")
        elif op == 'or':
            lbl_false = f"cmp_false_or_{self.pc}"
            self._emit(f"bne {r1}, r0, {lbl_end}")
            self._emit(f"bne {r2}, r0, {lbl_end}")
            self._emit(f"addi {r_dest}, r0, 0")

        self._emit_label(lbl_end)

    # Funcion de multiplicación: se emite como un loop de suma repetida (res = 0; while b != 0: res += a; b--)
    def _emit_mul(self, node) -> str:
        from ast_nodes import FunctionCall as FC

        r_a = self.visit(node.left)

        right_is_call = isinstance(node.right, FC)

        if right_is_call:
            self._emit("addi r2, r2, -4")
            self._emit(f"store {r_a}, 0(r2)")
            for k in self.current_locals:
                self.current_locals[k] += 4
            self.local_offset += 4
            self._free_if_temp(r_a)

            r_b = self.visit(node.right)

            r_a = self._alloc_reg()
            self._emit(f"load {r_a}, 0(r2)")
            self._emit("addi r2, r2, 4")
            for k in self.current_locals:
                self.current_locals[k] -= 4
            self.local_offset -= 4
        else:
            r_b = self.visit(node.right)

        r_res = self._alloc_reg()
        r_cnt = self._alloc_reg()

        # ANTES: liberaba r_b antes de usarlo en "add r_cnt, r_b, r0"
        # AHORA: guardamos el valor antes de liberar
        lbl_loop = f"mul_loop_{self._mul_count}"
        lbl_end  = f"mul_end_{self._mul_count}"
        self._mul_count += 1

        self._emit(f"addi {r_res}, r0, 0")
        self._emit(f"add  {r_cnt}, {r_b}, r0")  # usar r_b ANTES de liberar
        self._free_if_temp(r_b)                  # liberar DESPUÉS

        r_one = self._alloc_reg()
        self._emit(f"addi {r_one}, r0, 1")

        self._emit_label(lbl_loop)
        self._emit(f"beq  {r_cnt}, r0, {lbl_end}")
        self._emit(f"add  {r_res}, {r_res}, {r_a}")
        self._emit(f"sub  {r_cnt}, {r_cnt}, {r_one}")
        self._emit(f"jal  r0, {lbl_loop}")
        self._emit_label(lbl_end)

        self._free_if_temp(r_a)
        self._free_reg(r_one)
        self._free_reg(r_cnt)
        return r_res
    
    # Funcion de division: se emite como un loop de resta repetida (res = 0; while a >= b: a -= b; res++)
    def _emit_div(self, node) -> str:
        r_a = self.visit(node.left)
        r_b = self.visit(node.right)

        r_res = self._alloc_reg()
        r_cnt = self._alloc_reg()

        lbl_loop = f"div_loop_{self._mul_count}"
        lbl_end  = f"div_end_{self._mul_count}"
        lbl_body = f"div_body_{self._mul_count}"
        self._mul_count += 1

        self._emit(f"addi {r_res}, r0, 0")      # res = 0
        self._emit_label(lbl_loop)
        self._emit(f"bge {r_a}, {r_b}, {lbl_body}")  # si a >= b: sigue
        self._emit(f"jal r0, {lbl_end}")             # sino: fin
        self._emit_label(lbl_body)
        self._emit(f"sub {r_a}, {r_a}, {r_b}")   # a -= b
        self._emit(f"addi {r_res}, {r_res}, 1")  # res++
        self._emit(f"jal r0, {lbl_loop}")
        self._emit_label(lbl_end)

        self._free_if_temp(r_a)
        self._free_if_temp(r_b)
        self._free_reg(r_cnt)
        return r_res

    # Funcion de módulo: se emite como un loop de resta repetida (res = a; while res >= b: res -= b)
    def _emit_mod(self, node) -> str:
        r_a = self.visit(node.left)
        r_b = self.visit(node.right)

        lbl_loop = f"mod_loop_{self._mul_count}"
        lbl_end  = f"mod_end_{self._mul_count}"
        lbl_body = f"mod_body_{self._mul_count}"
        self._mul_count += 1

        self._emit_label(lbl_loop)
        self._emit(f"bge {r_a}, {r_b}, {lbl_body}")  # si a >= b: sigue
        self._emit(f"jal r0, {lbl_end}")              # sino: fin
        self._emit_label(lbl_body)
        self._emit(f"sub {r_a}, {r_a}, {r_b}")        # a -= b
        self._emit(f"jal r0, {lbl_loop}")
        self._emit_label(lbl_end)

        self._free_if_temp(r_b)
        return r_a  # el residuo queda en r_a


    # Para UnaryOp, manejamos operadores unarios como negación, NOT lógico y NOT a nivel de bits.
    def visit_UnaryOp(self, node) -> str:
        r_op = self.visit(node.operand) # Evaluar el operando unario
        r    = self._alloc_reg() # Registro para el resultado de la operación unaria

        # Negación aritmética: r = 0 - operand
        if node.op == '-':
            # neg = 0 - operand
            self._emit(f"sub {r}, r0, {r_op}")

        # NOT a nivel de bits: r = operand XOR 0xFFFFFFFF
        elif node.op == '~':
            # NOT a nivel de bits: xor con 0xFFFFFFFF
            r_mask = self.load_immediate(0xFFFFFFFF)
            self._emit(f"xor {r}, {r_op}, {r_mask}")
            self._free_reg(r_mask)

        # NOT lógico: r = (operand == 0) ? 1 : 0
        elif node.op == 'not':
            
            lbl_end = f"not_end_{self.pc}" # Etiqueta para el fin de la operación NOT lógico 
            self._emit(f"addi {r}, r0, 1") # Asumimos true (1)
            self._emit(f"beq  {r_op}, r0, {lbl_end}") # Si operand == 0, saltamos al final (dejando r=1)
            self._emit(f"addi {r}, r0, 0") # Si operand != 0, establecemos r=0 (false)
            self._emit_label(lbl_end) # Etiqueta de fin para el NOT lógico
        
        # Si el operador unario no es reconocido, emitimos un código que copia el operando (como fallback) y comentamos que no se soporta
        else:
            self._emit(f"add {r}, {r_op}, r0   # unary '{node.op}' no soportado")

        self._free_if_temp(r_op)
        return r

    
    #  Llamadas a función                                                  
    
    # Función principal para visitar llamadas a función: maneja tanto llamadas normales como 
    # instrucciones de bóveda (que se emiten directamente como mnemónicas ISA)
    def visit_FunctionCall(self, node) -> str:
        for k in self.current_locals:
            self.current_locals[k] += 4
        self.local_offset += 4

        self._emit("addi r2, r2, -4")
        self._emit("store r1, 0(r2)")

        for i, arg in enumerate(node.args):
            if i >= len(ARG_REGS):
                raise RuntimeError(
                    f"'{node.name}': máx {len(ARG_REGS)} args, "
                    f"se pasaron {len(node.args)}"
                )
            r_arg = self.visit(arg)
            self._emit(f"add {ARG_REGS[i]}, {r_arg}, r0")
            self._free_if_temp(r_arg)

        self._emit(f"jal r1, {node.name}")

        self._emit("load r1, 0(r2)")
        self._emit("addi r2, r2, 4")

        for k in self.current_locals:
            self.current_locals[k] -= 4
        self.local_offset -= 4

        # ANTES: siempre emitía add r_ret, r4, r0
        # AHORA: solo si la función no es void
        sym = self.semantic.symbol_table.lookup(node.name)
        is_void = (sym is not None and 
                hasattr(sym, 'return_type') and 
                sym.return_type == 'void')

        if is_void:
            return None  # no hay valor de retorno
        
        r_ret = self._alloc_reg()
        self._emit(f"add {r_ret}, r4, r0")
        return r_ret


    # Para las llamadas a función usadas como sentencias (sin usar el valor de retorno), manejamos las instrucciones de bóveda directamente 
    # y para llamadas normales, simplemente evaluamos la llamada sin usar el valor de retorno.
    def visit_ExpressionStatement(self, node):
        expr = node.expr

        if isinstance(expr, FunctionCall) and expr.name in VAULT_OPS:
            self._emit_vault_op(expr)
            return

        r = self.visit(expr)
        if r is not None:
            self._free_if_temp(r)

    
    #  Instrucciones de bóveda (@boveda)                                   

    def _emit_vault_op(self, node: FunctionCall):
        """
        Emite la mnemónica ISA correcta para cada instrucción de bóveda.

        Mapeo de argumentos según la ISA:
          login(uid, pwd)       = login rs2(uid), rs1(pwd)
          logout()              = logout
          setpwd(uid, pwd)      = setpwd rs2(uid), rs1(pwd)
          authchk()             = authchk
          authorize(token)      = authorize rs1(token)
          vkload(data, ki)      = vkload rs1(data), ki
          vkinv(ki)             = vkinv ki
        """
        name = node.name # Nombre de la función llamada (instrucción de bóveda)
        args = node.args # Argumentos de la llamada (pueden ser vacíos para logout() y authchk())

        if name == 'logout' or name == 'authchk':
            # Sin operandos de registro
            self._emit(name)

        elif name == 'login':
            # login(uid, pwd) = login rs2_uid, rs1_pwd
            r_uid = self.visit(args[0]) # El primer argumento (uid = id del usuario) se mapea a rs2
            r_pwd = self.visit(args[1]) # El segundo argumento (pwd = la contrasena del usuario) se mapea a rs1
            self._emit(f"login {r_uid}, {r_pwd}") 
            self._free_if_temp(r_uid)
            self._free_if_temp(r_pwd)

        elif name == 'setpwd':
            # setpwd(uid, pwd) = setpwd rs2_uid, rs1_pwd
            r_uid = self.visit(args[0]) # El primer argumento (uid = id del usuario) se mapea a rs2
            r_pwd = self.visit(args[1]) # El segundo argumento (pwd = la contrasena del usuario) se mapea a rs1
            self._emit(f"setpwd {r_uid}, {r_pwd}")
            self._free_if_temp(r_uid)
            self._free_if_temp(r_pwd)

        elif name == 'authorize':
            # authorize(uid, token)
            r_uid = self.visit(args[0])
            r_tok = self.visit(args[1])

            self._emit(f"authorize {r_uid}, {r_tok}")

            self._free_if_temp(r_uid)
            self._free_if_temp(r_tok)

        elif name == 'vkload':
            # vkload(data, ki) = vkload rs1_data, ki_literal
            r_data = self.visit(args[0]) # El primer argumento (data = llave de la boveda) se mapea a rs1
            ki = args[1].value if hasattr(args[1], 'value') else 0 # El segundo argumento (posicion en la boveda)
            self._emit(f"vkload {r_data}, {ki}")
            self._free_if_temp(r_data)

        elif name == 'vkinv':
            # vkinv(ki) = vkinv ki_literal
            ki = args[0].value if hasattr(args[0], 'value') else 0 # El argumento (posicion en la boveda)
            self._emit(f"vkinv {ki}")

        elif name == 'tea_add1':
            # tea_add1(rd_target, rs1, ki) = tea_add1 rd, rs1, ki
            # Operación: rd = (rs1 << 4) + K[ki]
            # rd es el destino: en la ISA V-type es un registro (rd field)
            # El caller pasa: tea_add1(resultado, fuente, ki_literal)
            r_src = self.visit(args[1])
            ki    = args[2].value if hasattr(args[2], 'value') else 0

            # Necesitamos un destino; si el primer arg es un Identifier, lo usamos
            # como destino directo; si no, usamos un temporal
            dest_node = args[0]

            # Si el destino es un Identifier que es una variable local, almacenamos el resultado en su offset del frame
            if isinstance(dest_node, Identifier) and dest_node.name in self.current_locals:
                r_dst = self._alloc_reg()
                self._emit(f"tea_add1 {r_dst}, {r_src}, {ki}")
                offset = self.current_locals[dest_node.name]
                self._emit(f"store {r_dst}, {offset}(r2)")
                self._free_reg(r_dst)

            # Si el destino es un Identifier que es un parámetro, lo almacenamos en el registro de argumento correspondiente (r4..r7)
            elif isinstance(dest_node, Identifier) and dest_node.name in self.current_params:
                idx   = self.current_params.index(dest_node.name)
                r_dst = ARG_REGS[idx]
                self._emit(f"tea_add1 {r_dst}, {r_src}, {ki}")

            # Si el destino no es un Identifier o no es una variable local ni parámetro, 
            # usamos un temporal para el resultado (aunque se pierde el valor después de esta instrucción)
            else:
                r_dst = self._alloc_reg()
                self._emit(f"tea_add1 {r_dst}, {r_src}, {ki}")
                self._free_reg(r_dst)
            self._free_if_temp(r_src)

        # tea_add2 es similar a tea_add1 pero con un desplazamiento diferente (rs1 >> 5 en lugar de rs1 << 4)
        elif name == 'tea_add2':
            # tea_add2(rd_target, rs1, ki) = tea_add2 rd, rs1, ki
            # Operación: rd = (rs1 >> 5) + K[ki]
            r_src = self.visit(args[1])
            ki    = args[2].value if hasattr(args[2], 'value') else 0
            dest_node = args[0]

            # Si el destino es un Identifier que es una variable local, almacenamos el resultado en su offset del frame
            if isinstance(dest_node, Identifier) and dest_node.name in self.current_locals:
                r_dst = self._alloc_reg()
                self._emit(f"tea_add2 {r_dst}, {r_src}, {ki}")
                offset = self.current_locals[dest_node.name]
                self._emit(f"store {r_dst}, {offset}(r2)")
                self._free_reg(r_dst)

            # Si el destino es un Identifier que es un parámetro, lo almacenamos en el registro de argumento correspondiente (r4..r7)
            elif isinstance(dest_node, Identifier) and dest_node.name in self.current_params:
                idx   = self.current_params.index(dest_node.name)
                r_dst = ARG_REGS[idx]
                self._emit(f"tea_add2 {r_dst}, {r_src}, {ki}")

            # Si el destino no es un Identifier o no es una variable local ni parámetro, 
            # usamos un temporal para el resultado (aunque se pierde el valor después de esta instrucción)
            else:
                r_dst = self._alloc_reg()
                self._emit(f"tea_add2 {r_dst}, {r_src}, {ki}")
                self._free_reg(r_dst)
            self._free_if_temp(r_src)

        # Si la función llamada no es una instrucción de bóveda reconocida, emitimos un comentario indicando que no se reconoce
        else:
            self._emit(f"# vault op '{name}' no reconocido")

    
    #  Declaraciones de variables y constantes: manejamos tanto variables globales (en memoria absoluta) 
    # como locales (en el frame de la función), y para arrays, almacenamos cada elemento contiguamente                                                    

    # Funcion para visitar declaraciones de variables (var) y constantes (const), que comparten lógica para determinar 
    # si la variable es global o local, y para manejar arrays
    def visit_VarDeclaration(self, node):
        self._declare_variable(node.name, node.value, is_const=False)

    def visit_ConstDeclaration(self, node):
        self._declare_variable(node.name, node.value, is_const=True)

    # Lógica compartida para declarar variables y constantes, que maneja tanto variables globales como locales, y arrays (list literals)
    def _declare_variable(self, name: str, value_node, is_const: bool):
        """Lógica compartida para var y const."""
        is_array = isinstance(value_node, ListLiteral)
        in_func  = bool(self.current_params is not None and
                        (self.current_locals is not None))
        # Distinguimos global de local por si hay una función activa
        is_local = (self.current_func_name is not None)

        # Si estamos dentro de una función (hay un current_func_name), declaramos como local; si no, declaramos como global.
        if is_local:
            self._declare_local(name, value_node, is_array)
        else:
            self._declare_global(name, value_node, is_array)

    # Para declarar una variable local, reservamos espacio en el stack (frame) de la función y almacenamos su valor inicial.
    def _declare_local(self, name: str, value_node, is_array: bool):
        """Declara y almacena una variable local en el frame de la función."""

        # Si es un array (list literal), reservamos espacio para todos sus elementos; 
        # si es una variable simple, reservamos espacio para un solo valor (WORD)
        if is_array:
            elements = value_node.elements
            size     = len(elements) * WORD
        else:
            size = WORD

        # Reservar espacio en stack (crece hacia abajo)
        self._emit(f"addi r2, r2, -{size}")

        # Offset = posición relativa desde SP (0 = tope actual)
        base_offset = 0
        self.current_locals[name] = base_offset
        # Reajustar todos los offsets anteriores cuando crece el frame
        # (Los anteriores están almacenados relativos al SP anterior;
        #  al mover SP hacia abajo, sus offsets aumentan en `size`)
        for k in list(self.current_locals.keys()):
            if k != name:
                self.current_locals[k] += size
        self.local_offset += size

        # Almacenar el valor inicial en el espacio reservado para la variable local
        if is_array:

            # Para un array, evaluamos cada elemento y lo almacenamos contiguamente en memoria (offset 0, 4, 8, ...)
            for i, elem in enumerate(elements):
                r = self.visit(elem)
                self._emit(f"store {r}, {i * WORD}(r2)")
                self._free_if_temp(r)
        # Para una variable simple, evaluamos su valor y lo almacenamos en el offset 0 del frame (donde se reservó espacio para esta variable)
        else:
            r = self.visit(value_node)
            self._emit(f"store {r}, 0(r2)")
            self._free_if_temp(r)

    # Para declarar una variable global, obtenemos su dirección absoluta en memoria y almacenamos su valor inicial allí. 
    # Para arrays, almacenamos cada elemento contiguamente.
    def _declare_global(self, name: str, value_node, is_array: bool):
        """Declara y almacena una variable global en memoria."""
        sym  = self.semantic.symbol_table.lookup(name)
        addr = sym.address if sym else 0

        # Si es un array (list literal), almacenamos cada elemento contiguamente en memoria (dirección base, base+4, base+8, ...)
        if is_array:
            # Para un array, evaluamos cada elemento y lo almacenamos contiguamente en memoria (dirección base, base+4, base+8, ...)
            for i, elem in enumerate(value_node.elements):
                r = self.visit(elem) # Evaluar el elemento del array y obtener su valor en un registro
                r_addr = self.load_immediate((addr + i) * 4)
                self._emit(f"store {r}, 0({r_addr})")
                self._free_if_temp(r)
                self._free_reg(r_addr)
        # Para una variable simple, evaluamos su valor y lo almacenamos en la dirección absoluta correspondiente en memoria
        else:
            r = self.visit(value_node) # Evaluar el valor de la variable y obtenerlo en un registro
            r_addr = self.load_immediate(addr * 4)
            self._emit(f"store {r}, 0({r_addr})")
            self._free_if_temp(r)
            self._free_reg(r_addr)

    # Asignación: para asignar un valor a una variable, primero evaluamos el valor a asignar, luego determinamos si el destino es 
    # una variable local (en cuyo caso almacenamos en el frame) o global (en cuyo caso almacenamos en memoria absoluta),
    # o si es un acceso a índice (arr[i] o matrix[i][j], en cuyo caso calculamos la dirección del elemento y almacenamos allí).
   
    def visit_Assignment(self, node):
        r_val = self.visit(node.value)

        # Si el destino es un Identifier, puede ser una variable local o global
        if isinstance(node.target, Identifier):
            name = node.target.name

            # Parámetro de función
            if name in self.current_params:
                idx = self.current_params.index(name)
                self._emit(f"add {ARG_REGS[idx]}, {r_val}, r0")
                self._free_if_temp(r_val)
                return

            # Variable local
            if name in self.current_locals:
                offset = self.current_locals[name]
                self._emit(f"store {r_val}, {offset}(r2)")
                self._free_if_temp(r_val)
                return

            # Variable global
            sym    = self.semantic.symbol_table.lookup(name)
            addr   = sym.address if sym else 0
            r_addr = self.load_immediate(addr * 4)
            self._emit(f"store {r_val}, 0({r_addr})")
            self._free_if_temp(r_val)
            self._free_reg(r_addr)

        # Si el destino es un acceso a índice, calculamos la dirección del elemento y almacenamos allí
        elif isinstance(node.target, IndexAccess):

            # Caso especial: si el acceso a índice es mem[i], entonces el destino es memoria absoluta y no un arreglo; 
            # calculamos la dirección directamente sin resolver base de arreglo
            if isinstance(node.target.target, Identifier) and node.target.target.name == "mem":
                r_addr = self.visit(node.target.indices[0])
                
                # Multiplicar por 4
                r_addr4 = self._alloc_reg()
                r_shift = self._alloc_reg()
                self._emit(f"addi {r_shift}, r0, 2")
                self._emit(f"sll {r_addr4}, {r_addr}, {r_shift}")
                self._free_reg(r_shift)
                self._free_if_temp(r_addr)

                self._emit(f"store {r_val}, 0({r_addr4})")
                self._free_if_temp(r_addr4)
                self._free_if_temp(r_val)
                return

            # Caso general: el destino es un acceso a índice de un arreglo o matriz (arr[i] o matrix[i][j]); calculamos la dirección del elemento y almacenamos allí

            # arr[i] = val  o  matrix[i][j] = val
            r_index = self.visit(node.target.indices[0]) # Registro con el valor del índice (i para arr[i], j para matrix[i][j])

            r_shift = self._alloc_reg() # Registro para el desplazamiento (índice * 4, ya que cada elemento ocupa 4 bytes)
            r_offset = self._alloc_reg() # Registro para la dirección del elemento (base + desplazamiento)
            

            self._emit(f"addi {r_shift}, r0, 2") 
            self._emit(f"sll  {r_offset}, {r_index}, {r_shift}")

            self._free_reg(r_shift)
            self._free_if_temp(r_index)

            r_base = self._resolve_array_base(node.target.target)  # Registro con la dirección base del arreglo (para arr[i]) o de la fila (para matrix[i][j])
            r_addr = self._alloc_reg() # Registro para la dirección final del elemento (donde se almacenará el valor)

            self._emit(f"add  {r_addr}, {r_base}, {r_offset}")
            self._emit(f"store {r_val}, 0({r_addr})")

            self._free_if_temp(r_val)
            self._free_reg(r_offset)
            self._free_reg(r_addr)
            self._free_if_temp(r_base)

    
    #  Estructuras de control: if, while, for. Para cada estructura de control, generamos etiquetas para los bloques de código 
    # correspondientes (then, else, end para if; start, end para while y for), y usamos branches para controlar el flujo de 
    # ejecución según las condiciones evaluadas.

    # Función auxiliar para emitir código de branch según la condición dada, que se reutiliza tanto en if como en while y for.
    def _emit_branch_condition(self, cond, lbl_false: str):
        """
        Evalúa cond y emite un branch al label lbl_false si la condición
        resulta falsa. Soporta BinaryOp con operadores de comparación y
        expresiones booleanas generales.
        """

        # Si la condición es una operación binaria de comparación o lógica, evaluamos ambos operandos y emitimos el branch correspondiente según el operador.
        if isinstance(cond, BinaryOp) and cond.op in ('<', '>', '==', '!=', '<=', '>=', 'and', 'or'):
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # Invertimos la condición para saber cuándo saltar al bloque falso
            INVERT = {'<': 'bge', '>': 'ble_sim', '==': 'bne', '!=': 'beq',
                      '<=': 'bgt_sim', '>=': 'blt_sim'}

            op = cond.op
            if op == '<':
                # saltar si r1 >= r2
                self._emit(f"bge {r1}, {r2}, {lbl_false}")
            elif op == '>':
                # saltar si r2 >= r1 (r1 <= r2)
                self._emit(f"bge {r2}, {r1}, {lbl_false}")
            elif op == '==':
                self._emit(f"bne {r1}, {r2}, {lbl_false}")
            elif op == '!=':
                self._emit(f"beq {r1}, {r2}, {lbl_false}")
            elif op == '<=':
                # saltar si r1 > r2  =  r2 < r1  =  bgt r1, r2
                self._emit(f"bgt {r1}, {r2}, {lbl_false}")
            elif op == '>=':
                # saltar si r1 < r2  =  bgt r2, r1
                self._emit(f"bgt {r2}, {r1}, {lbl_false}")
            elif op == 'and':
                # ambos deben ser true (!=0); si alguno es 0, saltar a falso
                self._emit(f"beq {r1}, r0, {lbl_false}")
                self._emit(f"beq {r2}, r0, {lbl_false}")
            elif op == 'or':
                # al menos uno debe ser true; si ambos son 0, saltar
                lbl_ok = f"or_ok_{self.pc}"
                self._emit(f"bne {r1}, r0, {lbl_ok}")
                self._emit(f"beq {r2}, r0, {lbl_false}")
                self._emit_label(lbl_ok)

            self._free_if_temp(r1)
            self._free_if_temp(r2)
        else:
            # Expresión booleana general
            r = self.visit(cond)
            self._emit(f"beq {r}, r0, {lbl_false}")
            self._free_if_temp(r)

    # Para if, generamos etiquetas para el bloque else (si existe) y el bloque de fin, y usamos branches para controlar el flujo entre then, else y end.
    def visit_IfStatement(self, node):
        lbl_else = node._lbl_else
        lbl_end  = node._lbl_end

        self._emit_branch_condition(node.condition, lbl_else)

        # Emitir código para el bloque then
        for stmt in node.then_block:
            self.visit(stmt)

        # Si hay un bloque else, saltamos al final después de ejecutar el then para evitar ejecutar el else; si no hay else, simplemente continuamos al final.
        if node.else_block:
            self._emit(f"jal r0, {lbl_end}")

        self._emit_label(lbl_else)

        # Emitir código para el bloque else (si existe)
        for stmt in node.else_block:
            self.visit(stmt)

        self._emit_label(lbl_end)

    # Para while, generamos etiquetas para el inicio del loop (donde se evalúa la condición) y el fin del loop, y usamos branches para controlar el flujo entre el inicio, el cuerpo del loop y el fin.
    def visit_WhileStatement(self, node):
        lbl_start = node._lbl_start
        lbl_end   = node._lbl_end

        self._emit_label(lbl_start)
        self._emit_branch_condition(node.condition, lbl_end)

        # Emitir código para el cuerpo del loop
        for stmt in node.body:
            self.visit(stmt)

        self._emit(f"jal r0, {lbl_start}")
        self._emit_label(lbl_end)

    # Para for, generamos etiquetas para el inicio del loop (donde se evalúa la condición) y el fin del loop, 
    # y usamos branches para controlar el flujo entre el inicio, el cuerpo del loop, la actualización y el fin.
    def visit_ForStatement(self, node):
        lbl_start = node._lbl_start
        lbl_end   = node._lbl_end

       # Pre-registrar la variable de control como local si no existe
        if isinstance(node.init, Assignment):
           from ast_nodes import Identifier as _Id
           target = node.init.target
           if isinstance(target, _Id):
                var_name = target.name
                if (var_name not in self.current_locals
                        and var_name not in self.current_params):
                    self._emit(f"addi r2, r2, -4")
                    for k in list(self.current_locals):
                        self.current_locals[k] += 4
                    self.current_locals[var_name] = 0
                    self.local_offset += 4
        self.visit(node.init)
        self._emit_label(lbl_start)
        self._emit_branch_condition(node.condition, lbl_end)

        for stmt in node.body:
           self.visit(stmt)

        self.visit(node.update)
        self._emit(f"jal r0, {lbl_start}")
        self._emit_label(lbl_end)



    
    #  Funciones: Para declarar una función, guardamos su contexto (parámetros, variables locales, offset del frame) y emitimos su etiqueta.

    def visit_FunctionDeclaration(self, node):
        # Guardar contexto externo (para funciones anidadas en el futuro)
        prev_params  = self.current_params # Parámetros de la función actual (lista de nombres de parámetros)
        prev_locals  = self.current_locals # Variables locales de la función actual (diccionario de nombre -> offset en el frame)
        prev_offset  = self.local_offset # Tamaño total del frame local usado por la función actual (para restaurar SP al retornar)
        prev_name    = getattr(self, 'current_func_name', None) # Nombre de la función actual 

        self.current_func_name = node.name # Nombre de la función que estamos declarando actualmente
        self.current_params    = [p[0] for p in node.params] # Lista de nombres de parámetros de la función actual (extraída de la lista de parámetros del nodo)
        self.current_locals    = {} # Diccionario para las variables locales de la función actual (nombre -> offset en el frame), inicialmente vacío
        self.local_offset      = 0 # Tamaño total del frame local usado por la función actual, inicialmente 0 (se incrementará a medida que se declaren variables locales)

        self._emit_label(node.name)

        has_explicit_return = False # Bandera para saber si la función tiene un return explícito

        # Emitir código para el cuerpo de la función
        for stmt in node.body:

            # Si encontramos un return explícito, lo manejamos y luego salimos del loop para no emitir código adicional después del return (que sería código muerto).
            result = self.visit(stmt)
            if result == "RETURN":
                has_explicit_return = True
                break

        # Epilogo implícito si no hubo return explícito
        if not has_explicit_return:
            # Restaurar SP si se usó frame local
            if self.local_offset > 0:
                self._emit(f"addi r2, r2, {self.local_offset}")
            self._emit("jr r1")

        # Restaurar contexto
        self.current_params    = prev_params
        self.current_locals    = prev_locals
        self.local_offset      = prev_offset
        self.current_func_name = prev_name

    # Para return, si hay un valor de retorno, lo evaluamos y lo colocamos en r4 (convención de retorno), 
    # luego restauramos SP si se usó frame local y saltamos a la dirección de retorno (jr r1).
    def visit_ReturnStatement(self, node) -> str:

        # Si hay un valor de retorno, lo evaluamos y lo colocamos en r4 (convención de retorno)
        if node.value is not None:
            r = self.visit(node.value)
            self._emit(f"add r4, {r}, r0")
            self._free_if_temp(r)

        # Restaurar SP del frame local antes de retornar
        if self.local_offset > 0:
            self._emit(f"addi r2, r2, {self.local_offset}")

        self._emit("jr r1")
        return "RETURN"