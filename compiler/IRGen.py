## Generación de Representación Intermedia
from compiler.ast_nodes import IndexAccess

class IRGen:
    def __init__(self):
        self.code        = []   # lista de strings, una instrucción por elemento
        self.temp_count  = 0  
        self.label_count = 0    


    ############# Funciones básicas generales #############

    # Crea un nombre de temporal único cada vez que se llama
    def new_temp(self):
        self.temp_count += 1
        return f"t{self.temp_count}"

    # Crea un nombre de etiqueta único cada vez que se llama
    def new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def emit(self, line):
        self.code.append(line)   # Agrega la linea al código resultado

    # Punto de entrada: recibe el AST completo y retorna el código IR como string
    def generate(self, ast):
        self.code        = []
        self.temp_count  = 0
        self.label_count = 0
        self.visit(ast)
        return "\n".join(self.code)

    # Busca el método visit_NombreClase sino usa generic_visit
    def visit(self, node):
        method = getattr(self, f"visit_{node.__class__.__name__}", self.generic_visit)
        return method(node)   # Va al método que encontro con el getattr

    def generic_visit(self, node):
        # Fallback para nodos sin método propio: simplemente visita los hijos
        # No emite ninguna instrucción, solo deja pasar el recorrido
        for child in getattr(node, "children", []):
            if child is not None:
                self.visit(child)

    ############# Nodos raíz y secciones #############

    # Solo recorre los hijos, no emite nada propio
    def visit_Program(self, node):
        for stmt in node.statements:
            if stmt is not None:
                self.visit(stmt)

    # La anotación no produce código IR, solo se recorre el contenido
    def visit_SectionBlock(self, node):
        for stmt in node.body:
            if stmt is not None:
                self.visit(stmt)

    ############# Literales #############
    # Los literales no emiten instrucciones, solo retornan su valor como string

    def visit_IntLiteral(self, node):
        return str(node.value)         

    def visit_RealLiteral(self, node):
        return str(node.value)         

    def visit_BoolLiteral(self, node):
        return "true" if node.value else "false"

    def visit_StringLiteral(self, node):
        return f'"{node.value}"'       

    def visit_HexLiteral(self, node):
        return f"0x{node.value:X}"      

    def visit_Identifier(self, node):
        return node.name

    ############# Expresiones #############

    # Evalúa ambos lados de la operación primero
    # Luego guarda el resultado en un temporal y emite la instrucción
    def visit_BinaryOp(self, node):
        left  = self.visit(node.left)
        right = self.visit(node.right)
        temp  = self.new_temp()
        self.emit(f"{temp} = {left} {node.op} {right}")
        return temp

    # Igual que BinaryOp pero con un solo operando
    def visit_UnaryOp(self, node):
        value = self.visit(node.operand)
        temp  = self.new_temp()
        self.emit(f"{temp} = {node.op} {value}")
        return temp

    # Lee el arreglo según el índice y guarda el resultado en una temporal
    def visit_IndexAccess(self, node):
        base = self.visit(node.target)
        idx  = self.visit(node.indices[0])
        temp = self.new_temp()
        self.emit(f"{temp} = {base}[{idx}]")
        return temp

    # Reserva espacio con alloc y luego escribe cada elemento por índice
    def visit_ListLiteral(self, node):
        temp = self.new_temp()
        self.emit(f"{temp} = alloc {len(node.elements)}")
        for i, elem in enumerate(node.elements):
            val = self.visit(elem)
            self.emit(f"{temp}[{i}] = {val}")
        return temp


    ############# Declaraciones y asignaciones #############

    # Evalúa la expresión del lado derecho y asigna al nombre de la variable
    def visit_VarDeclaration(self, node):
        value = self.visit(node.value)
        self.emit(f"{node.name} = {value}")

    def visit_ConstDeclaration(self, node):
        value = self.visit(node.value)
        self.emit(f"{node.name} = {value}")

    def visit_Assignment(self, node):
        value = self.visit(node.value)

        # Evalúa el valor primero, luego decide cómo escribirlo
        if isinstance(node.target, IndexAccess):
            # El target es un acceso a arreglo: necesita base e índice por separado
            base = self.visit(node.target.target)
            idx  = self.visit(node.target.indices[0])
            self.emit(f"{base}[{idx}] = {value}")
        else:
            # El target es una variable simple
            target = self.visit(node.target)
            self.emit(f"{target} = {value}")

    def visit_ExpressionStatement(self, node):
        # Llamada a función usada como sentencia (su valor de retorno se descarta)
        # Ejemplo: modulo(n, d)'  →  se emiten los param y call pero no se guarda t
        self.visit(node.expr)


    ############# Funciones #############

    # Delimita la función con begin_func / end_func
    def visit_FunctionDeclaration(self, node):
        self.emit(f"begin_func {node.name}")
        for pname, _ in node.params:
            self.emit(f"fparam {pname}")        # declara cada parámetro recibido
        for stmt in node.body:
            if stmt is not None:
                self.visit(stmt)
        self.emit(f"end_func {node.name}")

    # Tira un parametro por cada argumento, luego hace el call y guarda el resultado en una temporal
    def visit_FunctionCall(self, node):
        for arg in node.args:
            value = self.visit(arg)
            self.emit(f"param {value}")
        temp = self.new_temp()
        self.emit(f"{temp} = call {node.name}, {len(node.args)}")
        return temp

    def visit_ReturnStatement(self, node):
        if node.value is None:
            self.emit("return")
        else:
            value = self.visit(node.value)
            self.emit(f"return {value}")


    ############# Estructuras de control #############

    def visit_IfStatement(self, node):

        # Crea las etiquetas para cada caso
        l_true  = self.new_label()
        l_false = self.new_label()
        l_end   = self.new_label()

        # Evalúa la condición y salta a la etiqueta que es
        cond = self.visit(node.condition)
        self.emit(f"if {cond} goto {l_true}")
        self.emit(f"goto {l_false}")

        self.emit(f"{l_true}:")
        for stmt in node.then_block:
            self.visit(stmt)
        self.emit(f"goto {l_end}")

        self.emit(f"{l_false}:")
        for stmt in node.else_block:   # lista vacía si no hay sino → no emite nada
            self.visit(stmt)

        self.emit(f"{l_end}:")

    def visit_WhileStatement(self, node):

        # Crea las etiquetas necesarias
        l_start = self.new_label()
        l_body  = self.new_label()
        l_end   = self.new_label()

        # Si se cumple alguna hace el salto, si no se cumple salta al final
        self.emit(f"{l_start}:")
        cond = self.visit(node.condition)
        self.emit(f"if {cond} goto {l_body}")
        self.emit(f"goto {l_end}")

        self.emit(f"{l_body}:")
        for stmt in node.body:
            self.visit(stmt)
        self.emit(f"goto {l_start}")

        self.emit(f"{l_end}:")

    def visit_ForStatement(self, node):
        # Crea las etiquetas necesarias
        l_start = self.new_label()
        l_end   = self.new_label()

        if node.init is not None:
            self.visit(node.init)

        self.emit(f"{l_start}:")

        if node.condition is not None:
            cond = self.visit(node.condition)
            self.emit(f"iffalse {cond} goto {l_end}")   # sale si la condición es falsa

        for stmt in node.body:
            if stmt is not None:
                self.visit(stmt)

        if node.update is not None:
            self.visit(node.update)

        self.emit(f"goto {l_start}")
        self.emit(f"{l_end}:")