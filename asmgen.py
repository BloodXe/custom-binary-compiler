# Assembly Generator

from platform import node
import sys
from ast_nodes import BinaryOp, Identifier, IndexAccess, IntLiteral

# Compila el AST a código ensamblador
class AsmGen:

    def __init__(self, semantic):
        self.semantic = semantic # El análisis semántico ya ha sido realizado
        self.code = [] # Lista de instrucciones ensambladoras generadas
        self.temp_regs = ["r8", "r9", "r10", "r11"] # Registros temporales disponibles para cálculos intermedios
        self.reg_index = 0 # Indice para rastrear el siguiente registro temporal disponible

    # Genera código ensamblador a partir del AST
    def generate(self, ast):
        self.visit(ast)
        return "\n".join(self.code) # Devuelve el código ensamblador generado
    
    def visit(self, node):
        # Busca el método de visita específico para el tipo de nodo, o usa generic_visit si no existe
        method = getattr(self, f"visit_{node.__class__.__name__}", self.generic_visit)

        return method(node) # Llama al método de visita específico o al genérico
    
    # Método de visita genérico para nodos sin un método específico
    def generic_visit(self, node):
        for child in getattr(node, "children", []):
            if child:
                self.visit(child) # Visita cada hijo del nodo
    

    # Helpers

    # Metodo para obtener la dirección de una variable a partir de su nombre
    def get_address(self, name):
        sym = self.semantic.symbol_table.lookup(name) # Busca la variable en la tabla de símbolos
        return sym.address # Devuelve la dirección de la variable en memoria
    
    # Método para generar un nuevo registro temporal
    def new_reg(self):
        reg = self.temp_regs[self.reg_index] # Obtiene el siguiente registro temporal disponible
        self.reg_index = (self.reg_index + 1) % len(self.temp_regs) # Incrementa el índice del registro temporal, volviendo al inicio si se alcanza el final de la lista
        return reg # Devuelve el registro temporal generado

    # Literales

    # Metodo para visitar un nodo de literal entero y generar código ensamblador para cargar su valor en un registro temporal
    def visit_IntLiteral(self, node):
        reg = self.new_reg()
        self.code.append(f"addi {reg}, r0, {node.value}") # Carga el valor entero en un registro temporal
        return reg # Devuelve el registro temporal que contiene el valor entero
    
    # Metodo para identificadores o variables, genera código ensamblador para cargar su valor en un registro temporal
    def visit_Identifier(self, node):
        reg = self.new_reg()
        addr = self.get_address(node.name) # Obtiene la dirección de la variable
        self.code.append(f"load {reg}, {addr}") # Carga el valor de la variable en un registro temporal
        return reg # Devuelve el registro temporal que contiene el valor de la variable
    
    # Metodo para visitar un nodo de asignación, genera código ensamblador para evaluar el valor de la asignación y almacenarlo en la dirección de la variable 
    def visit_Assignment(self, node):
        reg = self.visit(node.value) # Genera código para evaluar el valor de la asignación

        if isinstance(node.target, Identifier): # Si el objetivo de la asignación es un identificador, genera código para almacenar el valor en la dirección de la variable
            addr = self.get_address(node.target.name) # Obtiene la dirección de la variable
            self.code.append(f"store {reg}, {addr}") # Almacena el valor en la dirección de la variable

        elif isinstance(node.target, IndexAccess):
            # Dirección base del arreglo
            target = node.target.children[0]
            base_addr = self.get_address(target.name)

            # Indice del acceso al arreglo
            idx_node = node.target.children[1]
            r_index = self.visit(idx_node)

            # Despues camiar a sizeof, por ahora asumiendo que cada elemento del arreglo ocupa 4 bytes, calculamos el tamaño de cada elemento
            r_shift = self.new_reg()
            self.code.append(f"addi {r_shift}, r0, 2")  # shift = 2
            
            # Calculamos el offset con: offset = índice * tamaño_elemento
            r_offset = self.new_reg()
            self.code.append(f"sll {r_offset}, {r_index}, {r_shift}")

            # Calculamos la dirección del elemento accedido con: addr = base + offset
            r_base = self.new_reg()
            self.code.append(f"addi {r_base}, r0, {base_addr}")

            r_addr = self.new_reg()
            self.code.append(f"add {r_addr}, {r_base}, {r_offset}")

            # Almacena el valor en la dirección del elemento accedido del arreglo
            self.code.append(f"store {reg}, {r_addr}")


    # Metodo para visitar un nodo de operación binaria, genera código ensamblador para evaluar ambos operandos y realizar la operación correspondiente
    def visit_BinaryOp(self, node):
        r1 = self.visit(node.left) # Genera código para evaluar el operando izquierdo
        r2 = self.visit(node.right) # Genera código para evaluar el operando derecho

        r3 = self.new_reg() # Genera un nuevo registro temporal para almacenar el resultado de la operación

        if node.op == '+':
            self.code.append(f"add {r3}, {r1}, {r2}") # Genera código para sumar los operandos y almacenar el resultado en r3
        elif node.op == '-':
            self.code.append(f"sub {r3}, {r1}, {r2}") # Genera código para restar los operandos y almacenar el resultado en r3
        elif node.op == '*':
            # r1 = a, r2 = b

            r_res = self.new_reg()
            self.code.append(f"addi {r_res}, r0, 0")  # res = 0

            # labels únicos
            loop_lbl = f"mul_loop_{len(self.code)}"
            end_lbl  = f"mul_end_{len(self.code)}"

            # copia de b (porque lo vamos a modificar)
            r_b = self.new_reg()
            self.code.append(f"add {r_b}, {r2}, r0")

            self.code.append(f"{loop_lbl}:")

            # if b == 0 → salir
            self.code.append(f"beq {r_b}, r0, {end_lbl}")

            # res += a
            self.code.append(f"add {r_res}, {r_res}, {r1}")

            # b = b - 1
            r_one = self.new_reg()
            self.code.append(f"addi {r_one}, r0, 1")
            self.code.append(f"sub {r_b}, {r_b}, {r_one}")

            # loop
            self.code.append(f"jal r0, {loop_lbl}")

            self.code.append(f"{end_lbl}:")

            return r_res
        elif node.op == '<<':
            self.code.append(f"sll {r3}, {r1}, {r2}") # Genera código para desplazar a la izquierda el operando izquierdo por el número de bits especificado en el operando derecho y almacenar el resultado en r3
        elif node.op == '>>':
            self.code.append(f"srl {r3}, {r1}, {r2}") # Genera código para desplazar a la derecha el operando izquierdo por el número de bits especificado en el operando derecho y almacenar el resultado en r3
        elif node.op == '^':
            self.code.append(f"xor {r3}, {r1}, {r2}") # Genera código para realizar una operación XOR entre los operandos y almacenar el resultado en r3
        
        return r3 # Devuelve el registro temporal que contiene el resultado de la operación binaria


    # Metodo para If statements, genera código ensamblador para evaluar la condición del if y saltar al bloque else si la condición es falsa, o ejecutar el bloque then si la condición es verdadera. 
    # Al final del bloque then, genera código para saltar al final del bloque if después de ejecutar el bloque then. Luego genera código para el bloque else y el final del bloque if.
    def visit_IfStatement(self, node):
        # Etiquetas únicas para el bloque else y el final del bloque if
        else_label = node._lbl_else
        end_label  = node._lbl_end

        # Evaluamos la condición del if
        cond = node.condition

        # Caso: condición con operador de comparación (e.g. i < N, i == N, etc.)
        if isinstance(cond, BinaryOp):

            # Generamos código para evaluar ambos operandos de la condición
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # Si la condición es falsa, saltamos al bloque else
            if cond.op == '<':
                self.code.append(f"bge {r1}, {r2}, {else_label}")

            elif cond.op == '>':
                self.code.append(f"bge {r2}, {r1}, {else_label}")

            elif cond.op == '==':
                self.code.append(f"bne {r1}, {r2}, {else_label}")

            elif cond.op == '!=':
                self.code.append(f"beq {r1}, {r2}, {else_label}")

            else:
                raise Exception(f"Operador no soportado en if: {cond.op}")

        # Caso: Con booleanos o variables booleanas, evaluamos la condición y saltamos al bloque else si el resultado es falso (0)
        else:
            
            r = self.visit(cond)
            self.code.append(f"beq {r}, r0, {else_label}")

        # Bloque then
        for stmt in node.then_block:
            self.visit(stmt)

        # Al final del bloque then, saltamos al final del bloque if para evitar ejecutar el bloque else
        self.code.append(f"jal r0, {end_label}")

        # Bloque else
        self.code.append(f"{else_label}:")
        for stmt in node.else_block:
            self.visit(stmt)

        # Final del bloque if
        self.code.append(f"{end_label}:")


    # Metodo para While statements, genera código ensamblador para evaluar la condición del while al inicio de cada iteración y saltar al final del bloque while si la condición es falsa, o ejecutar el bloque while si la condición es verdadera. 
    # Al final del bloque while, genera código para saltar al inicio del bloque while para evaluar la condición nuevamente.
    def visit_WhileStatement(self, node):
        # Etiquetas únicas para el inicio y el final del bloque while
        start = node._lbl_start
        end   = node._lbl_end
        
        # Se etiqueta el inicio del bloque while
        self.code.append(f"{start}:")

        # Evaluamos la condición del while
        cond = node.condition

        # Caso: condición con operador de comparación (e.g. i < N, i == N, etc.)
        if isinstance(cond, BinaryOp):

            # Generamos código para evaluar ambos operandos de la condición
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # Si la condicion es falsa, saltamos al final del bloque while
            if cond.op == '<':
                self.code.append(f"bge {r1}, {r2}, {end}")

            elif cond.op == '>':
                self.code.append(f"bge {r2}, {r1}, {end}")

            elif cond.op == '==':
                self.code.append(f"bne {r1}, {r2}, {end}")

            elif cond.op == '!=':
                self.code.append(f"beq {r1}, {r2}, {end}")

            else:
                raise Exception(f"Operador no soportado en while: {cond.op}")

        # Caso: Con booleanos o variables booleanas, evaluamos la condición y saltamos al final del bloque while si el resultado es falso (0)
        else:
            r = self.visit(cond)
            self.code.append(f"beq {r}, r0, {end}")

        # Bloque del while
        for stmt in node.body:
            self.visit(stmt)

        self.code.append(f"jal r0, {start}")

        # Se etiqueta el final del bloque while
        self.code.append(f"{end}:")


    # Metodo para For statements, genera código ensamblador para evaluar la condición del for al inicio de cada iteración y saltar al final del bloque for si la condición es falsa, o ejecutar el bloque for si la condición es verdadera. 
    # Al final del bloque for, genera código para ejecutar la actualización del for y luego saltar al inicio del bloque for para evaluar la condición nuevamente.
    def visit_ForStatement(self, node):
        start = node._lbl_start # Etiqueta para el inicio del bloque for
        end   = node._lbl_end # Etiqueta para el final del bloque for

        # Inicialización del for
        self.visit(node.init)

        # Se etiqueta el inicio del bloque for
        self.code.append(f"{start}:")

        # Evaluación de la condición del for
        cond = node.condition

        # Caso: i < N
        if cond.op == '<':
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # si i >= N, salir
            self.code.append(f"bge {r1}, {r2}, {end}")

        # Caso: i > N
        elif cond.op == '>':
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # si i <= N, salir
            self.code.append(f"bge {r2}, {r1}, {end}")

        # Caso: i == N
        elif cond.op == '==':
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # si NO son iguales, salir
            self.code.append(f"bne {r1}, {r2}, {end}")

        # Caso: i != N
        elif cond.op == '!=':
            r1 = self.visit(cond.left)
            r2 = self.visit(cond.right)

            # si son iguales, salir
            self.code.append(f"beq {r1}, {r2}, {end}")

        else:
            raise Exception(f"Operador no soportado en for: {cond.op}")

        # Bloque del for
        for stmt in node.body:
            self.visit(stmt)

        # Actualización del for
        self.visit(node.update)

        # Se vuelve al inicio del bloque for para evaluar la condición nuevamente
        self.code.append(f"jal r0, {start}")

        # Se etiqueta el final del bloque for
        self.code.append(f"{end}:")
    
    # Metodo para visitar un nodo de declaración de variable, genera código ensamblador para evaluar el valor inicial de la variable y almacenarlo en la dirección de la variable. 
    # Si la variable es un arreglo, se reserva espacio para el arreglo en memoria y se inicializa cada elemento del arreglo con su valor correspondiente.
    def visit_VarDeclaration(self, node):

        addr = self.get_address(node.name)

        # Si la variable es un arreglo, se reserva espacio para el arreglo en memoria y se inicializa cada elemento del arreglo con su valor correspondiente
        if node.value.__class__.__name__ == "ListLiteral":
            base_addr = addr

            for i, elem in enumerate(node.value.children):
                # Evaluar elemento
                r = self.visit(elem)

                # offset = i * 4
                offset = i * 4
                final_addr = base_addr + offset

                self.code.append(f"store {r}, {final_addr}")

            return

        # Evaluamos el valor inicial de la variable
        reg = self.visit(node.value) # Genera código para evaluar el valor inicial de la variable

        # Obtenemos la dirección de la variable
        addr = self.get_address(node.name) 

        # Almacenamos el valor inicial de la variable en su dirección de memoria
        self.code.append(f"store {reg}, {addr}") # Genera código para almacenar el valor inicial de la variable en su dirección de memoria

    # Metodo para visitar un nodo de asignación, genera código ensamblador para evaluar el valor de la asignación y almacenarlo en la dirección de la variable o del elemento accedido del arreglo
    def visit_IndexAccess(self, node):
        
        # Obtenemos la dirección base del arreglo
        target = node.children[0]
        base_addr = self.get_address(target.name)

        # Evaluamos el índice del acceso al arreglo
        idx_node = node.children[1]
        r_index = self.visit(idx_node)


        # Despues camiar a sizeof, por ahora asumiendo que cada elemento del arreglo ocupa 4 bytes, calculamos el tamaño de cada elemento
        # Asumiendo que cada elemento del arreglo ocupa 4 bytes, calculamos el tamaño de cada elemento
        r_size = self.new_reg()
        self.code.append(f"addi {r_size}, r0, 4")

        # Calculamos el offset con: offset = índice * tamaño_elemento
        r_offset = self.new_reg()
        self.code.append(f"addi {r_size}, r0, 2")
        self.code.append(f"sll {r_offset}, {r_index}, {r_size}")

        # Calculamos la dirección del elemento accedido con: addr = base + offset
        r_base = self.new_reg()
        self.code.append(f"addi {r_base}, r0, {base_addr}")

        r_addr = self.new_reg()
        self.code.append(f"add {r_addr}, {r_base}, {r_offset}")

        # Cargamos el valor del elemento accedido del arreglo en un registro temporal
        r_value = self.new_reg()
        self.code.append(f"load {r_value}, {r_addr}")

        return r_value