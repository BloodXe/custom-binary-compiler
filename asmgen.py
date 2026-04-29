# Assembly Generator

from platform import node
import sys
from ast_nodes import Identifier

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
            self.code.append(f"mul {r3}, {r1}, {r2}") # Genera código para multiplicar los operandos y almacenar el resultado en r3
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
        else_label = node._lbl_else # Etiqueta para el bloque else
        end_label = node._lbl_end # Etiqueta para el final del bloque if

        reg = self.visit(node.condition) # Genera código para evaluar la condición del if

        # Si la condición es falsa, salta al bloque else
        self.code.append(f"beq {reg}, r0, {else_label}") # Genera código para saltar al bloque else si la condición es falsa
    
        for stmt in node.then_block: # Genera código para el bloque then
            self.visit(stmt)
        
        self.code.append(f"jal r0, {end_label}") # Genera código para saltar al final del bloque if después de ejecutar el bloque then

        # Genera código para el bloque else
        self.code.append(f"{else_label}:") # Etiqueta para el bloque else

        for stmt in node.else_block: # Genera código para el bloque else
            self.visit(stmt)
        
        self.code.append(f"{end_label}:") # Etiqueta para el final del bloque if
    
    # Metodo para While statements, genera código ensamblador para evaluar la condición del while al inicio de cada iteración y saltar al final del bloque while si la condición es falsa, o ejecutar el bloque while si la condición es verdadera. 
    # Al final del bloque while, genera código para saltar al inicio del bloque while para evaluar la condición nuevamente.
    def visit_WhileStatement(self, node):
        start = node._lbl_start # Etiqueta para el inicio del bloque while
        end = node._lbl_end # Etiqueta para el final del bloque while

        self.code.append(f"{start}:") # Etiqueta para el inicio del bloque while

        r = self.visit(node.condition) # Genera código para evaluar la condición del while

        # Si la condición es falsa, salta al final del bloque while
        self.code.append(f"beq {r}, r0, {end}") # Genera código para saltar al final del bloque while si la condición es falsa

        for stmt in node.body: # Genera código para el bloque while
            self.visit(stmt)
        
        # Se vuelve al inicio del bloque while para evaluar la condición nuevamente
        self.code.append(f"jal r0, {start}") # Genera código para saltar al inicio del bloque while para evaluar la condición nuevamente

        self.code.append(f"{end}:") # Etiqueta para el final del bloque while

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
    
    def visit_VarDeclaration(self, node):

        # Evaluamos el valor inicial de la variable
        reg = self.visit(node.value) # Genera código para evaluar el valor inicial de la variable

        # Obtenemos la dirección de la variable
        addr = self.get_address(node.name) 

        # Almacenamos el valor inicial de la variable en su dirección de memoria
        self.code.append(f"store {reg}, {addr}") # Genera código para almacenar el valor inicial de la variable en su dirección de memoria