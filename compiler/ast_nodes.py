# Abstract Syntax Tree (AST) node definitions.
from typing import List, Optional

# Base class
class AstNode:
    """Base class for all AST nodes.

    Subclasses must override `children` to expose their child nodes so that
    generic tree traversals (walk, print_ast) work automatically.
    """

    @property
    def children(self) -> list:
        """Returns the direct child nodes of this node."""
        return []

    def walk(self):
        """Depth-first pre-order traversal — yields self, then every descendant."""
        yield self
        for child in self.children:
            if isinstance(child, AstNode):
                yield from child.walk()
            elif isinstance(child, list):
                for item in child:
                    if isinstance(item, AstNode):
                        yield from item.walk()

    def accept(self, visitor):
        method = f'visit_{type(self).__name__}'
        return getattr(visitor, method, visitor.visit_default)(self)

    def __repr__(self):
        return self.__class__.__name__
    
# Root node
class Program(AstNode):
    """Nodo raíz del AST — contiene todas las sentencias de nivel superior en orden."""
    def __init__(self, statements: list):
        self.statements = statements # List[AstNode]

    @property
    def children(self):
        return self.statements

# Literals
class IntLiteral(AstNode):
    """Integer constant, e.g. 42 or 42u (unsigned)."""

    def __init__(self, value: int, unsigned: bool = False):
        self.value = value # Python int
        self.unsigned = unsigned # True cuando el sufijo 'u' está presente

    def __repr__(self):
        return f'IntLiteral({self.value}{"u" if self.unsigned else ""})'


class RealLiteral(AstNode):
    """Floating-point constant, e.g. 3.14."""

    def __init__(self, value: float):
        self.value = value   # Python float

    def __repr__(self):
        return f'RealLiteral({self.value})'


class BoolLiteral(AstNode):
    """Boolean constant - true or false."""

    def __init__(self, value: bool):
        self.value = value   # Python bool

    def __repr__(self):
        return f'BoolLiteral({self.value})'


class StringLiteral(AstNode):
    """String constant, e.g. "hello"."""

    def __init__(self, value: str):
        self.value = value # Python str

    def __repr__(self):
        return f'StringLiteral({repr(self.value)})'


class HexLiteral(AstNode):
    """Hexadecimal constant, e.g. 0xFF or 0xFFu.
    """

    def __init__(self, value: int, unsigned: bool = False):
        self.value    = value
        self.unsigned = unsigned

    def __repr__(self):
        return f'HexLiteral(0x{self.value:X}{"u" if self.unsigned else ""})'


class ListLiteral(AstNode):
    """Array literal, e.g. [1, 2, 3] or [[1, 2], [3, 4]]."""

    def __init__(self, elements: list):
        self.elements = elements   # List[AstNode]

    @property
    def children(self):
        return self.elements

    def __repr__(self):
        return f'ListLiteral({len(self.elements)} elems)'

# Type annotation
class TypeNode(AstNode):
    """Anotación de tipo: int, uint, [3]int, [2][3]int, etc.
    `base` -nombre del tipo primitivo: 'int', 'uint', 'real', 'bool', 'string', 'void'
    `dims` -lista de tamaños para dimensiones de arreglo, vacía para escalares
    """

    def __init__(self, base: str, dims: list = None):
        self.base = base
        self.dims = dims or []

    def __repr__(self):
        dims = ''.join(f'[{d}]' for d in self.dims)
        return f'Type({dims}{self.base})'

# Name references
class Identifier(AstNode):
    """Nombre de variable o función, e.g. x or suma."""

    def __init__(self, name: str):
        self.name = name   # lexema como string

    def __repr__(self):
        return f'Identifier({self.name})'


class IndexAccess(AstNode):
    """Acceso por índice, e.g. arr[i] or matrix[i][j].

    `target`- el arreglo siendo indexado 
    `indices`- lista con una expresión por dimensión accedida
    """

    def __init__(self, target: AstNode, indices: list):
        self.target  = target
        self.indices = indices# List[AstNode]

    @property
    def children(self):
        return [self.target] + self.indices

    def __repr__(self):
        return 'IndexAccess'

# Expressions
class BinaryOp(AstNode):
    """Operación binaria, e.g. a + b, x << 4, v0 ^ v1.
    `op`- el operador exactamente como aparece en el fuente
    """

    def __init__(self, left: AstNode, op: str, right: AstNode):
        self.left  = left
        self.op    = op
        self.right = right

    @property
    def children(self):
        return [self.left, self.right]

    def __repr__(self):
        return f'BinaryOp({self.op})'


class UnaryOp(AstNode):
    """Operación unaria, e.g. -x or ~mask.

    `op`- operador ('-' o '~')
    `operand`- la expresión sobre la que opera
    """

    def __init__(self, op: str, operand: AstNode):
        self.op      = op
        self.operand = operand

    @property
    def children(self):
        return [self.operand]

    def __repr__(self):
        return f'UnaryOp({self.op})'

class FunctionCall(AstNode):
    """Llamada a función, e.g. suma(a, b) or imprimir("ok").

    `name`- nombre de la función llamada
    `args`- lista de expresiones argumento (puede estar vacía)
    """

    def __init__(self, name: str, args: list):
        self.name = name
        self.args = args # List[AstNode]

    @property
    def children(self):
        return self.args

    def __repr__(self):
        return f'FunctionCall({self.name})'

# Statements

class VarDeclaration(AstNode):
    """Declaración de variable: var nombre : tipo = expr '"""

    def __init__(self, name: str, type_: TypeNode, value: AstNode):
        self.name = name
        self.type_ = type_
        self.value = value

    @property
    def children(self):
        return [self.type_, self.value]

    def __repr__(self):
        return f'VarDeclaration({self.name})'


class ConstDeclaration(AstNode):
    """Declaración de constante: const nombre : tipo = expr '"""

    def __init__(self, name: str, type_: TypeNode, value: AstNode):
        self.name = name
        self.type_ = type_
        self.value = value

    @property
    def children(self):
        return [self.type_, self.value]

    def __repr__(self):
        return f'ConstDeclaration({self.name})'


class Assignment(AstNode):
    """Asignación: target = value '
    `target` puede ser un Identifier o un IndexAccess.
    """

    def __init__(self, target: AstNode, value: AstNode):
        self.target = target
        self.value = value

    @property
    def children(self):
        return [self.target, self.value]

    def __repr__(self):
        return 'Assignment'


class ExpressionStatement(AstNode):
    """Llamada a función usada como sentencia (valor de retorno descartado)."""

    def __init__(self, expr: AstNode):
        self.expr = expr

    @property
    def children(self):
        return [self.expr]

    def __repr__(self):
        return 'ExpressionStatement'


class FunctionDeclaration(AstNode):
    """Declaración de función: func nombre(params) :: tipo_retorno { cuerpo }

    `params` - lista de tuplas (nombre_param: str, tipo_param: TypeNode)
    `return_type` - tipo de retorno de la función
    `body` - lista de sentencias dentro del bloque de la función
    """

    def __init__(self, name: str, params: list, return_type: TypeNode, body: list):
        self.name = name
        self.params = params # List[Tuple[str, TypeNode]]
        self.return_type = return_type
        self.body = body # List[AstNode]

    @property
    def children(self):
        # return_type de primero para que aparezca al inicio en la impresión del árbol
        return [self.return_type] + self.body

    def __repr__(self):
        return f'FunctionDeclaration({self.name})'
    

class SectionBlock(AstNode):
    """Bloque de sección marcado con @boveda o @code.
    
    El código sin anotación explícita al inicio del archivo pertenece a @code por defecto.
    Las secciones pueden alternarse varias veces en el mismo archivo.
    """

    def __init__(self, annotation: str, body: list):
        self.annotation = annotation
        self.body       = body

    @property
    def children(self):
        return self.body

    def __repr__(self):
        return f'SectionBlock({self.annotation})'


class IfStatement(AstNode):
    """Condicional: si (cond) { then } [sino { else }]

    `else_block` - lista vacía cuando no hay rama sino
    """

    def __init__(self, condition: AstNode, then_block: list, else_block: list = None):
        self.condition  = condition
        self.then_block = then_block   # List[AstNode]
        self.else_block = else_block or []

    @property
    def children(self):
        return [self.condition] + self.then_block + self.else_block

    def __repr__(self):
        return 'IfStatement'


class WhileStatement(AstNode):
    """Ciclo mientras: mientras (cond) { body }"""

    def __init__(self, condition: AstNode, body: list):
        self.condition = condition
        self.body = body # List[AstNode]

    @property
    def children(self):
        return [self.condition] + self.body

    def __repr__(self):
        return 'WhileStatement'


class ForStatement(AstNode):
    """Ciclo para: para (init ' cond ' update ') { body }

    Las tres partes se separan con el terminador de instrucción (').
    """

    def __init__(self, init: AstNode, condition: AstNode, update: AstNode, body: list):
        self.init = init # nodo Assignment
        self.condition = condition # nodo expresión
        self.update = update  # nodo Assignment
        self.body = body  # List[AstNode]

    @property
    def children(self):
        return [self.init, self.condition, self.update] + self.body

    def __repr__(self):
        return 'ForStatement'


class ReturnStatement(AstNode):
    """Sentencia retorna: retorna [expr] '

    `value` es None para funciones void que usan un retorna ' sin expresión.
    """

    def __init__(self, value: AstNode = None):
        self.value = value

    @property
    def children(self):
        return [self.value] if self.value else []

    def __repr__(self):
        return 'ReturnStatement'


class ImportStatement(AstNode):
    """Importación de módulo: importar nombre_modulo '"""

    def __init__(self, module: str):
        self.module = module # nombre del módulo como string

    def __repr__(self):
        return f'ImportStatement({self.module})'


class SaveStatement(AstNode):
    """Marca una variable como observable para DCE: save(nombre) '
    Cualquier definición que contribuya al valor de 'name' se considera viva.
    """

    def __init__(self, name: str):
        self.name = name  # nombre de la variable a preservar

    @property
    def children(self):
        return []

    def __repr__(self):
        return f'SaveStatement({self.name})'