#para probar python semantic.py tea.yeison -v
"""
REGLAS SEMANTICAS (RS)

RS-01: Todo identificador debe existir. No se puede usar una variable o función si no fue declarada antes

RS-02: No se pueden repetir nombres. No se puede declarar dos veces la misma variable, función en el mismo ambito

RS-03: Las constantes no se pueden cambiar. Si una variable es const, no se le puede asignar otro valor

RS-04: Cantidad de argumentos correcta. Las funciones deben llamarse con la cantidad de parametros que esperan

RS-05: Tipos compatibles. No se pueden mezclar tipos incorrectos en asignaciones, a excepción de int y uint

RS-06: Operadores numéricos y de bits. Los operadores matemáticos usan números. Los operadores de bits solo usan enteros

RS-07: Operadores booleanos: and, or, not solo funcionan con valores booleanos

RS-08: Return correcto: Una función debe retornar el tipo que dijo. Si es void no debe retornar nada

RS-09: Indices de arreglos: Solo se pueden usar enteros para acceder a arreglos

RS-10: Funciones de bóveda: Algunas funciones especiales solo se pueden usar dentro de @boveda.

"""

import sys
from lexer import Lexer
from parser import Parser, ParseError
from ast_nodes import *

#direcciones de memoria
DATA_BASE  = 0x0100
STACK_BASE = 0xFFFC
WORD = 1


#funciones de la boveda que solo se pueden llamar en @boveda
VAULT_API = {'login', 'logout', 'setpwd', 'authchk', 'authorize', 'vkload', 'vkinv'}


#tipos y helpers
def type_str(t):
    if isinstance(t, TypeNode):
        dims = ''.join(f'[{d}]' for d in t.dims)
        return dims + t.base
    if isinstance(t, str):
        return t
    return '?'

#obtiene el tipo de un array
def base_type(t):
    i = 0
    while i < len(t) and t[i] == '[':
        i = t.index(']', i) + 1
    return t[i:]

#obtiene el tamaño en memoria de un tipo
def size_of(t):
    if not isinstance(t, TypeNode):
        return WORD
    total = WORD
    for d in t.dims:
        try:
            total *= int(d)
        except:
            pass
    return total

#alinea la direccion al siguiente multiplo de 4
def align(address, alignment=WORD):
    remainder = address % alignment
    if remainder == 0:
        return address
    return address + (alignment - remainder)



#tabla de simbolos
class Symbol:
    def __init__(self, name, kind, type_str, scope, address):
        self.name     = name
        self.kind     = kind      # var, const, func, param, label
        self.type_str = type_str
        self.scope    = scope
        self.address  = address

    def __repr__(self):
        addr = f'0x{self.address:04X}' if self.address >= 0 else 'N/A'
        return f'  {self.name:<20} {self.kind:<8} {self.type_str:<18} {self.scope:<15} {addr}'


class FuncSymbol(Symbol):
    def __init__(self, name, params, ret, scope):
        super().__init__(name, 'func', ret, scope, -1)
        self.params   = params    #lista de (nombre, tipo_str)
        self.ret_type = ret

    def __repr__(self):
        ps = ', '.join(f'{n}:{t}' for n, t in self.params)
        return f'  {self.name:<20} func     ({ps}) -> {self.ret_type:<12} {self.scope:<15} N/A'


class SymbolTable:
    def __init__(self):
        #pila de diccionarios, uno por ambito
        self.stack    = [{}]
        self.names    = ['global']
        self.closed   = []  #ambitos que ya se cerraron

    def open_scope(self, name):
        self.stack.append({})
        self.names.append(name)

    def close_scope(self):
        name = self.names.pop()
        d = self.stack.pop()
        self.closed.append((name, d))

    def current_scope(self):
        return self.names[-1]

    def define(self, s):
        #retorna false si ya existia en este ambito (error RS-02)
        if s.name in self.stack[-1]:
            return False
        self.stack[-1][s.name] = s
        return True

    def lookup(self, name):
        #busca de adentro hacia afuera (lexical scoping, RS-01)
        for d in reversed(self.stack):
            if name in d:
                return d[name]
        return None

    def print_table(self):
        print(f"\n{'TABLA DE SIMBOLOS'}")
        print('-' * 70)
        print(f"  {'NOMBRE':<20} {'KIND':<8} {'TIPO':<18} {'AMBITO':<15} DIRECCION")
        

        for name, d in zip(self.names, self.stack):
            if d:
                print(f'\nambito: {name}')
                for s in d.values():
                    print(repr(s))

        for name, d in self.closed:
            if d:
                print(f'\nambito: {name} (local)')
                for s in d.values():
                    print(repr(s))
        print()



#analizador semantico usando visitor
class SemanticAnalyzer:

    def __init__(self):
        self.symbol_table = SymbolTable()
        self.errors       = []
        self.labels       = {}
        self.data_ptr     = DATA_BASE
        self.local_ptr    = 0
        self.label_count  = 0
        self.current_func = None   #nombre de la funcion donde estamos
        self.current_ret  = None   #tipo de retorno de esa funcion
        self.section      = '@code' # @code o @boveda

    

    def visit(self, node):
        method_name = 'visit_' + node.__class__.__name__
        method = getattr(self, method_name, self.visit_default)
        return method(node)

    def visit_default(self, node):
        for child in getattr(node, 'children', []):
            if child is not None:
                self.visit(child)


    def error(self, msg, node=None):
        line = getattr(node, 'line', None)
        if line:
            self.errors.append(f'Linea {line}: {msg}')
        else:
            self.errors.append(msg)

#genera etiquetas de saltos
    def new_label(self, prefix):
        name = f'{prefix}_{self.label_count}'
        self.label_count += 1
        self.labels[name] = -1
        self.symbol_table.define(Symbol(name, 'label', 'label', self.current_func or 'global', -1))
        return name
    
    #alinea la direccion a multiplo de WORD antes de asignar
    #reserva memoria global
    def alloc_global(self, size):
        
        self.data_ptr = align(self.data_ptr)
        addr = self.data_ptr
        self.data_ptr += size 
        return addr
    
    #igual que global pero con offset relativo al frame pointer
    def alloc_local(self, size):    
        self.local_ptr = align(self.local_ptr)
        addr = self.local_ptr
        self.local_ptr += size
        return addr
    
    #verificar operadores y asignaciones
    def infer_type(self, node):
        
        if isinstance(node, (IntLiteral, HexLiteral)):
            return 'uint'
        if isinstance(node, RealLiteral):
            return 'real'
        if isinstance(node, BoolLiteral):
            return 'bool'
        if isinstance(node, StringLiteral):
            return 'string'
        if isinstance(node, Identifier):
            if node.name == "mem":
                return '[*]uint'   # array infinito de uint (conceptual)
            s = self.symbol_table.lookup(node.name)
            return s.type_str if s else '?'
        if isinstance(node, IndexAccess):
            return base_type(self.infer_type(node.target))
        if isinstance(node, FunctionCall):
            s = self.symbol_table.lookup(node.name)
            if isinstance(s, FuncSymbol):
                return s.ret_type
            return '?'
        if isinstance(node, BinaryOp):
            cmp_ops  = {'==', '!=', '<', '>', '<=', '>='}
            bool_ops = {'and', 'or'}
            if node.op in cmp_ops or node.op in bool_ops:
                return 'bool'
            return self.infer_type(node.left)
        if isinstance(node, UnaryOp):
            return self.infer_type(node.operand)
        return '?'
    
    #RS-05: int y uint son compatibles entre si
    def are_compatible(self, a, b):    
        integers = {'int', 'uint'}
        if a == b:
            return True
        if a in integers and b in integers:
            return True
        if '?' in (a, b):
            return True  #ya se reporto el error antes
        return False

    #visitors
    def visit_Program(self, n):
        for stmt in n.statements:
            self.visit(stmt)

    def visit_SectionBlock(self, n):
        #RS-10 guardamos la seccion activa para saber si se puede llamar boveda
        previous = self.section
        self.section = n.annotation  # actualiza a @boveda o @code
        for stmt in n.body:
            self.visit(stmt)
        self.section = previous      # restaura al salir

    def visit_FunctionDeclaration(self, n):
        params = [(pname, type_str(ptype)) for pname, ptype in n.params]
        ret = type_str(n.return_type)

        #RS-02: no puede haber dos funciones con el mismo nombre
        sym = FuncSymbol(n.name, params, ret, 'global')
        if not self.symbol_table.define(sym):
            self.error(f"RS-02: la funcion '{n.name}' ya fue declarada", n)

        #abrimos ambito nuevo para los parametros y variables locales
        self.symbol_table.open_scope(n.name)
        self.current_func = n.name
        self.current_ret  = ret
        self.local_ptr   = 0

        #registramos los parametros en el ambito local
        for pname, ptype in n.params:
            sz = size_of(ptype)
            s = Symbol(pname, 'param', type_str(ptype), n.name, self.alloc_local(sz))
            if not self.symbol_table.define(s):
                self.error(f"RS-02: el parametro '{pname}' esta duplicado en '{n.name}'", n)

        for stmt in n.body:
            print(f"DEBUG sem: {type(stmt).__name__}") 
            self.visit(stmt)

        self.symbol_table.close_scope()
        self.current_func = None
        self.current_ret  = None

    def visit_VarDeclaration(self, n):
        self.visit(n.value)
        t = type_str(n.type_)
        sz = size_of(n.type_)
        
        # Para evitar conflictos con la palabra reservada 'mem', que representa la memoria en el lenguaje, no permitimos declarar variables con ese nombre. 
        # Esto es parte de la regla semántica RS-02, que prohíbe repetir nombres, ya que 'mem' es un identificador especial reservado para acceder a la memoria
        if n.name == "mem":
            self.error("RS-02: 'mem' es reservado para memoria", n)
            return

        if self.current_func is None:
            addr  = self.alloc_global(sz)
            scope = 'global'
        else:
            addr  = self.alloc_local(sz)
            scope = self.current_func

        #RS-02
        s = Symbol(n.name, 'var', t, scope, addr)
        if not self.symbol_table.define(s):
            self.error(f"RS-02: '{n.name}' ya fue declarado en este ambito", n)

    def visit_ConstDeclaration(self, n):
        self.visit(n.value)
        t = type_str(n.type_)
        sz = size_of(n.type_)

        # Para evitar definir mem
        if n.name == "mem":
            self.error("RS-02: 'mem' es reservado para memoria", n)
            return
        if self.current_func is None:
            addr  = self.alloc_global(sz)
            scope = 'global'
        else:
            addr  = self.alloc_local(sz)
            scope = self.current_func

        #RS-02
        s = Symbol(n.name, 'const', t, scope, addr)
        if not self.symbol_table.define(s):
            self.error(f"RS-02: '{n.name}' ya fue declarado", n)

    def visit_ImportStatement(self, n):
        s = Symbol(n.module, 'import', 'module', 'global', -1)
        self.symbol_table.define(s)

    #Regla semantica 5 = los tipos tienen que ser compatibles
    def visit_Assignment(self, n):
        self.check_lvalue(n.target)
        self.visit(n.value)

        
        tl = self.infer_type(n.target)
        tr = self.infer_type(n.value)
        if not self.are_compatible(tl, tr):
            self.error(f"RS-05: no se puede asignar '{tr}' a '{tl}'", n)

    #regla semantica 1 = tiene que estar declarado
    #regla semantica 3 = no puede ser constante
    def check_lvalue(self, node): 
        # Permitir mem sin declarar, ya que es un identificador especial reservado para acceder a la memoria. 
        if isinstance(node, Identifier) and node.name == "mem":
            return
        if isinstance(node, Identifier):
            s = self.symbol_table.lookup(node.name)
            if s is None:
                self.error(f"RS-01: '{node.name}' no fue declarado", node)
            elif s.kind == 'const':
                self.error(f"RS-03: '{node.name}' es constante, no se puede asignar", node)
        elif isinstance(node, IndexAccess):
            self.check_lvalue(node.target)
            for idx in node.indices:
                self.visit(idx)

    def visit_IfStatement(self, n):
        n._lbl_else = self.new_label('else')
        n._lbl_end  = self.new_label('endif')
        self.visit(n.condition)
        for stmt in n.then_block:
            self.visit(stmt)
        for stmt in n.else_block:
            self.visit(stmt)

    def visit_WhileStatement(self, n):
        n._lbl_start = self.new_label('while_start')
        n._lbl_end   = self.new_label('while_end')
        self.visit(n.condition)
        for stmt in n.body:
            self.visit(stmt)

    def visit_ForStatement(self, n):
        n._lbl_start = self.new_label('for_start')
        n._lbl_end   = self.new_label('for_end')

        #si la variable de control no existe la declaramos automaticamente
        if isinstance(n.init, Assignment):
            base = n.init.target
            while isinstance(base, IndexAccess):
                base = base.target
            if isinstance(base, Identifier) and self.symbol_table.lookup(base.name) is None:
                scope = self.current_func or 'global'
                s = Symbol(base.name, 'var', 'int', scope, self.alloc_local(WORD))
                self.symbol_table.define(s)

        self.visit(n.init)
        self.visit(n.condition)
        self.visit(n.update)
        for stmt in n.body:
            self.visit(stmt)

    def visit_ReturnStatement(self, n):
        #RS-08: el tipo retornado tiene que coincidir con lo declarado
        if n.value is not None:
            self.visit(n.value)
            if self.current_ret == 'void':
                self.error("RS-08: funcion void no puede retornar un valor", n)
        else:
            if self.current_ret and self.current_ret != 'void':
                self.error(f"RS-08: '{self.current_func}' tiene que retornar '{self.current_ret}'", n)

    def visit_ExpressionStatement(self, n):
        self.visit(n.expr)

    def visit_FunctionCall(self, n):
        #RS-10: las funciones de boveda solo se pueden llamar en @boveda
        if n.name in VAULT_API and self.section != '@boveda':
            self.error(f"RS-10: '{n.name}' solo se puede llamar dentro de @boveda", n)

        #RS-04: verificamos que el numero de argumentos sea correcto
        s = self.symbol_table.lookup(n.name)
        if isinstance(s, FuncSymbol):
            if len(s.params) != len(n.args):
                self.error(f"RS-04: '{n.name}' espera {len(s.params)} argumento(s), "
                           f"se dieron {len(n.args)}", n)

        for arg in n.args:
            self.visit(arg)

    def visit_Identifier(self, n):
        if n.name == "mem":
            return  # permitir mem sin declarar
        #RS-01: tiene que estar declarado antes de usarse
        if self.symbol_table.lookup(n.name) is None:
            self.error(f"RS-01: '{n.name}' no fue declarado", n)

    def visit_BinaryOp(self, n):
        self.visit(n.left)
        self.visit(n.right)

        bit_ops   = {'<<', '>>', '^', '&', '|'}
        arith_ops = {'+', '-', '*', '/', '%', '**'}
        bool_ops  = {'and', 'or'}
        integers  = {'int', 'uint'}
        numerics  = {'int', 'uint', 'real'}

        t = self.infer_type(n.left)
        b = base_type(t)

        #RS-06: operadores de bit y aritmeticos requieren numeros
        if n.op in bit_ops and b not in integers:
            self.error(f"RS-06: '{n.op}' requiere entero, se obtuvo '{t}'", n)
        elif n.op in arith_ops and b not in numerics:
            self.error(f"RS-06: '{n.op}' requiere numerico, se obtuvo '{t}'", n)
        # RS-07: and/or requieren bool
        elif n.op in bool_ops and b != 'bool':
            self.error(f"RS-07: '{n.op}' requiere bool, se obtuvo '{t}'", n)

    def visit_UnaryOp(self, n):
        self.visit(n.operand)
        t = self.infer_type(n.operand)
        b = base_type(t)

        #RS-06: ~ requiere entero
        if n.op == '~' and b not in {'int', 'uint'}:
            self.error(f"RS-06: '~' requiere entero, se obtuvo '{t}'", n)
        #RS-07: not requiere bool
        if n.op == 'not' and b != 'bool':
            self.error(f"RS-07: 'not' requiere bool, se obtuvo '{t}'", n)

    def visit_IndexAccess(self, n):
        self.visit(n.target)
        for idx in n.indices:
            self.visit(idx)
            #RS-09: el indice tiene que ser entero
            t = self.infer_type(idx)
            if base_type(t) not in {'int', 'uint'}:
                self.error(f"RS-09: indice de arreglo debe ser entero, se obtuvo '{t}'", idx)

    def visit_ListLiteral(self, n):
        for e in n.elements:
            self.visit(e)

    #literales no necesitan verificacion
    def visit_IntLiteral(self, n):    pass
    def visit_RealLiteral(self, n):   pass
    def visit_BoolLiteral(self, n):   pass
    def visit_StringLiteral(self, n): pass
    def visit_HexLiteral(self, n):    pass
    def visit_TypeNode(self, n):      pass

    #prints
    def print_labels(self):
        print(f"\n{'ETIQUETAS DE SALTO':^50}")
        print('-' * 50)
        for name, addr in self.labels.items():
            status = f'0x{addr:04X}' if addr >= 0 else 'se resuelve en la otra etapa'
            print(f'  {name:<30} {status}')
        print()

    def print_memory(self):
        print(f"\n{'MAPA DE MEMORIA':^60}")
        print(f"  {'NOMBRE':<20} {'TIPO':<18} DIRECCION    AMBITO")
        print('-' * 60)

        all_scopes = list(self.symbol_table.stack) + [d for _, d in self.symbol_table.closed]
        for d in all_scopes:
            for s in d.values():
                if s.kind in ('var', 'const', 'param') and s.address >= 0:
                    lbl = 'global' if s.scope == 'global' else f'local ({s.scope})'
                    print(f'  {s.name:<20} {s.type_str:<18} 0x{s.address:04X}   {lbl}')

#main para pruebas
def main():
    if len(sys.argv) < 2:
        print('Uso: python semantic.py <archivo.yeison> [-s] [-l] [-m] [-v]')
        return

    file = sys.argv[1]
    flags   = sys.argv[2:]
    verbose     = '-v' in flags
    show_sym    = '-s' in flags or verbose
    show_labels = '-l' in flags or verbose
    show_mem    = '-m' in flags or verbose

    try:
        source = open(file, encoding='utf-8').read()
    except FileNotFoundError:
        print(f'No se encontro: {file}')
        return

    lex    = Lexer(source)
    tokens = lex.tokenize()

    if lex.errors:
        print(f'Errores lexicos: {len(lex.errors)}')
        for ln, col, msg in lex.errors:
            print(f'  Linea {ln}, col {col}: {msg}')
        return

    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        print(f'Error sintactico: {e}')
        return

    sem = SemanticAnalyzer()
    sem.visit(ast)

    if show_sym: sem.symbol_table.print_table()
    if show_labels: sem.print_labels()
    if show_mem: sem.print_memory()

    if sem.errors:
        print(f'Errores semanticos: {len(sem.errors)}')
        for e in sem.errors:
            print(f'  {e}')
    else:
        print(f'Sin errores en el semantico {file}')


if __name__ == '__main__':
    main()