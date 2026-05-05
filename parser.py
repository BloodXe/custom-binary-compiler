# Análisis sintáctico 
from typing import List
from lexer import Token, TokenType
from ast_nodes import (
    Program, TypeNode, Identifier, IndexAccess,
    IntLiteral, RealLiteral, BoolLiteral, StringLiteral, HexLiteral, ListLiteral,
    BinaryOp, UnaryOp, FunctionCall,VarDeclaration, ConstDeclaration, Assignment, ExpressionStatement, FunctionDeclaration,
    IfStatement, WhileStatement, ForStatement, ReturnStatement, ImportStatement, SectionBlock
)


class ParseError(Exception):
    def __init__(self, msg: str, token: Token = None):
        loc = f' (línea {token.line}, col {token.col})' if token else ''
        super().__init__(msg + loc)


class Parser:
    # Conjunto de TokenTypes que representan tipos de dato válidos del lenguaje
    TYPE_TOKENS = {
        TokenType.INT, TokenType.UINT, TokenType.REAL,
        TokenType.BOOL, TokenType.STRING, TokenType.VOID,
    }

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos    = 0

    # Primitivas

    def current(self) -> Token:
        """Retorna el token actual sin consumirlo."""
        return self.tokens[self.pos]

    def peek(self, offset: int = 1) -> Token:
        """Mira un token adelante sin consumirlo. Útil para decisiones de lookahead."""
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else self.tokens[-1]

    def eat(self, expected: TokenType) -> Token:
        """Consume el token actual si es del tipo esperado, o lanza ParseError."""
        tok = self.current()
        if tok.type != expected:
            raise ParseError(
                f'Se esperaba {expected.name}, se encontró {tok.type.name} ({repr(tok.value)})',
                tok)
        self.pos += 1
        return tok

    def match(self, *types: TokenType) -> bool:
        """Retorna True si el token actual es alguno de los tipos dados, sin consumirlo."""
        return self.current().type in types

    def eat_terminator(self):
        """Consume el terminador de instrucción (')."""
        self.eat(TokenType.TERMINATOR)


    # Punto de entrada

    def parse(self) -> Program:
        """Parsea el programa completo y retorna el nodo raíz del AST."""
        sections = []
        current_annotation = '@code'  # defecto
        current_body       = []

        while not self.match(TokenType.EOF):
            if self.match(TokenType.ANNOTATION):
                if current_body:
                    sections.append(SectionBlock(current_annotation, current_body))
                current_annotation = self.eat(TokenType.ANNOTATION).value
                current_body       = []
            else:
                current_body.append(self.parse_statement())

        if current_body:
            sections.append(SectionBlock(current_annotation, current_body))

        return Program(sections)

    # Sentencias
    def parse_statement(self):
        """Decide qué tipo de sentencia parsear según el token actual."""
        tok = self.current()
        if tok.type == TokenType.ANNOTATION:
            self.eat(TokenType.ANNOTATION)
            return None  # las anotaciones no generan nodo AST, solo cambian el contexto de sección
        if tok.type == TokenType.VAR:      
            return self.parse_var_decl()
        if tok.type == TokenType.CONST:    
            return self.parse_const_decl()
        if tok.type == TokenType.FUNC:     
            return self.parse_func_decl()
        if tok.type == TokenType.SI:       
            return self.parse_if()
        if tok.type == TokenType.MIENTRAS: 
            return self.parse_while()
        if tok.type == TokenType.PARA:     
            return self.parse_for()
        if tok.type == TokenType.RETORNA:  
            return self.parse_return()
        if tok.type == TokenType.IMPORTAR: 
            return self.parse_import()
        if tok.type == TokenType.IDENTIFIER: 
            return self.parse_ident_statement()
        
        BOVEDA_CALLS = {
            TokenType.LOGIN, TokenType.LOGOUT, TokenType.AUTHORIZE,
            TokenType.SETPWD, TokenType.VKLOAD, TokenType.VKINV, TokenType.AUTHCHK,
        }
        
        if tok.type in BOVEDA_CALLS:
            return self.parse_boveda_call()
        raise ParseError(f'Sentencia inesperada: {tok.type.name}', tok)

    def parse_block(self) -> list:
        """Parsea un bloque de sentencias delimitado por llaves { }."""
        self.eat(TokenType.LBRACE)
        stmts = []
        while not self.match(TokenType.RBRACE, TokenType.EOF):
            if self.match(TokenType.ANNOTATION):
                ann = self.eat(TokenType.ANNOTATION).value
                print(f"DEBUG: SectionBlock({ann})")  # ← agregar
                body = []
                while not self.match(TokenType.ANNOTATION, TokenType.RBRACE, TokenType.EOF):
                    stmt = self.parse_statement()
                    if stmt is not None:
                        body.append(stmt)
                stmts.append(SectionBlock(ann, body))
                print(f"DEBUG: SectionBlock body size = {len(body)}")  # ← agregar
            else:
                stmt = self.parse_statement()
                if stmt is not None:
                    stmts.append(stmt)
        self.eat(TokenType.RBRACE)
        return stmts


    # Declaraciones
    def parse_var_decl(self) -> VarDeclaration:
        """Parsea: var nombre : tipo = expr '"""
        self.eat(TokenType.VAR)
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat(TokenType.COLON)
        type_ = self.parse_type()
        self.eat(TokenType.ASSIGN)
        value = self.parse_expr()
        self.eat_terminator()
        return VarDeclaration(name, type_, value)

    def parse_const_decl(self) -> ConstDeclaration:
        """Parsea: const nombre : tipo = expr '"""
        self.eat(TokenType.CONST)
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat(TokenType.COLON)
        type_ = self.parse_type()
        self.eat(TokenType.ASSIGN)
        value = self.parse_expr()
        self.eat_terminator()
        return ConstDeclaration(name, type_, value)

    def parse_type(self) -> TypeNode:
        """Parsea una anotación de tipo, incluyendo dimensiones de arreglo.
        Ejemplos: int, uint, [3]int, [2][3]int
        """
        dims = []
        while self.match(TokenType.LBRACKET):
            self.eat(TokenType.LBRACKET)
            size = self.eat(TokenType.INTEGER).value
            self.eat(TokenType.RBRACKET)
            dims.append(size)
        tok = self.current()
        if tok.type not in self.TYPE_TOKENS:
            raise ParseError(f'Tipo esperado, se encontró {tok.type.name}', tok)
        self.pos += 1
        return TypeNode(tok.value, dims)


    # Funciones
    def parse_func_decl(self) -> FunctionDeclaration:
        """Parsea: func nombre(params) :: tipo_retorno { cuerpo }"""
        self.eat(TokenType.FUNC)
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat(TokenType.LPAREN)
        params = [] if self.match(TokenType.RPAREN) else self.parse_params()
        self.eat(TokenType.RPAREN)
        self.eat(TokenType.OP_RETURN_TYPE)
        return_type = self.parse_type()
        body = self.parse_block()
        return FunctionDeclaration(name, params, return_type, body)

    def parse_params(self) -> list:
        """Parsea la lista de parámetros: nombre : tipo, nombre : tipo, ..."""
        params = []
        while True:
            pname = self.eat(TokenType.IDENTIFIER).value
            self.eat(TokenType.COLON)
            ptype = self.parse_type()
            params.append((pname, ptype))
            if not self.match(TokenType.COMMA):
                break
            self.eat(TokenType.COMMA)
        return params


    # Estructuras de control
    def parse_if(self) -> IfStatement:
        """Parsea: si (cond) { then } [sino { else }]"""
        self.eat(TokenType.SI)
        self.eat(TokenType.LPAREN)
        cond = self.parse_expr()
        self.eat(TokenType.RPAREN)
        then_block = self.parse_block()
        else_block = []
        if self.match(TokenType.SINO):
            self.eat(TokenType.SINO)
            else_block = self.parse_block()
        return IfStatement(cond, then_block, else_block)

    def parse_while(self) -> WhileStatement:
        """Parsea: mientras (cond) { cuerpo }"""
        self.eat(TokenType.MIENTRAS)
        self.eat(TokenType.LPAREN)
        cond = self.parse_expr()
        self.eat(TokenType.RPAREN)
        body = self.parse_block()
        return WhileStatement(cond, body)

    def parse_for(self) -> ForStatement:
        """Parsea: para (init ' cond ' update ') { cuerpo }
        Las tres partes se separan con el terminador de instrucción (').
        """
        self.eat(TokenType.PARA)
        self.eat(TokenType.LPAREN)
        init = self.parse_assign_raw()
        self.eat_terminator()
        cond = self.parse_expr()
        self.eat_terminator()
        update = self.parse_assign_raw()
        self.eat_terminator()
        self.eat(TokenType.RPAREN)
        body = self.parse_block()
        return ForStatement(init, cond, update, body)

    def parse_assign_raw(self) -> Assignment:
        """Parsea una asignación sin terminator. Solo se usa dentro del para."""
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat(TokenType.ASSIGN)
        value = self.parse_expr()
        return Assignment(Identifier(name), value)

    def parse_return(self) -> ReturnStatement:
        self.eat(TokenType.RETORNA)
        # Si el siguiente token es el terminador, es un retorno sin valor (void)
        value = None if self.match(TokenType.TERMINATOR) else self.parse_expr()
        self.eat_terminator()
        return ReturnStatement(value)

    def parse_import(self) -> ImportStatement:
        """Parsea: importar nombre '"""
        self.eat(TokenType.IMPORTAR)
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat_terminator()
        return ImportStatement(name)

    def parse_ident_statement(self):
        """Parsea una sentencia que empieza con un identificador.
        Puede ser una llamada a función o una asignación.
        Se usa lookahead de 1 token para decidir cuál es.
        """
        # Si el siguiente token es '(' es una llamada a función como sentencia
        if self.peek().type == TokenType.LPAREN:
            node = self.parse_func_call()
            self.eat_terminator()
            return ExpressionStatement(node)
        
        # Si no, es una asignación: nombre [indices] = expr '
        name = self.eat(TokenType.IDENTIFIER).value
        target = Identifier(name)

        # Maneja asignaciones a índices: arr[i] = x' o matrix[i][j] = x'
        while self.match(TokenType.LBRACKET):
            self.eat(TokenType.LBRACKET)
            idx = self.parse_expr()
            self.eat(TokenType.RBRACKET)
            target = IndexAccess(target, [idx])
        self.eat(TokenType.ASSIGN)
        value = self.parse_expr()
        self.eat_terminator()
        return Assignment(target, value)

    def parse_func_call(self) -> FunctionCall:
        """Parsea una llamada a función: nombre(arg1, arg2, ...)"""
        name = self.eat(TokenType.IDENTIFIER).value
        self.eat(TokenType.LPAREN)
        args = []
        if not self.match(TokenType.RPAREN):
            args.append(self.parse_expr())
            while self.match(TokenType.COMMA):
                self.eat(TokenType.COMMA)
                args.append(self.parse_expr())
        self.eat(TokenType.RPAREN)
        return FunctionCall(name, args)
    
    #boveda
    def parse_boveda_call(self) -> ExpressionStatement:
        name = self.current().value
        self.pos += 1
        self.eat(TokenType.LPAREN)
        args = []
        if not self.match(TokenType.RPAREN):
            args.append(self.parse_expr())
            while self.match(TokenType.COMMA):
                self.eat(TokenType.COMMA)
                args.append(self.parse_expr())
        self.eat(TokenType.RPAREN)
        self.eat_terminator()
        return ExpressionStatement(FunctionCall(name, args))

    # Expresiones - precedencia de menor a mayor:
    #   or  and  not  comparación  bits  suma  termino  potencia  negacion  átomo
    def parse_expr(self):
        """Punto de entrada para parsear cualquier expresión."""
        return self.parse_or()
        

    def parse_or(self):
        """1 operador lógico: or"""
        left = self.parse_and()
        while self.match(TokenType.OR):
            op = self.eat(TokenType.OR).value
            left = BinaryOp(left, op, self.parse_and())
        return left


    def parse_and(self):
        """2 operador lógico: and"""
        left = self.parse_not()
        while self.match(TokenType.AND):
            op = self.eat(TokenType.AND).value
            left = BinaryOp(left, op, self.parse_not())
        return left


    def parse_not(self):
        """3 operador lógico unario: not"""
        if self.match(TokenType.NOT):
            op = self.eat(TokenType.NOT).value
            return UnaryOp(op, self.parse_not())
        return self.parse_comparison()


    def parse_comparison(self):
        """4 operadores relacionales: == != < > <= >="""
        COMP = {
            TokenType.OP_EQ, TokenType.OP_NE,
            TokenType.OP_LT, TokenType.OP_GT,
            TokenType.OP_LE, TokenType.OP_GE
        }

        left = self.parse_bits()

        while self.match(*COMP):
            op = self.current().value
            self.pos += 1
            left = BinaryOp(left, op, self.parse_bits())

        return left

    def parse_bits(self):
        """5 operadores a nivel de bits: << >> & | ^"""
        BIT = {
            TokenType.OP_LSHIFT, TokenType.OP_RSHIFT,
            TokenType.OP_BIT_AND, TokenType.OP_BIT_OR,
            TokenType.OP_XOR
        }
        left = self.parse_suma()
        while self.match(*BIT):
            op = self.current().value
            self.pos += 1
            left = BinaryOp(left, op, self.parse_suma())
        return left
    
    def parse_suma(self):
        """6 operadores suma y resta: + -"""
        left = self.parse_termino()

        while self.match(TokenType.OP_PLUS, TokenType.OP_MINUS):
            op = self.current().value
            self.pos += 1
            left = BinaryOp(left, op, self.parse_termino())

        return left


    def parse_termino(self):
        """7 operadores multiplicativos: * / %"""
        left = self.parse_potencia()

        while self.match(TokenType.OP_MUL, TokenType.OP_DIV, TokenType.OP_MOD):
            op = self.current().value
            self.pos += 1
            left = BinaryOp(left, op, self.parse_potencia())

        return left


    def parse_potencia(self):
        """8 potencia: ** asociativo a la derecha"""
        base = self.parse_negacion()

        if self.match(TokenType.OP_POW):
            op = self.eat(TokenType.OP_POW).value
            return BinaryOp(base, op, self.parse_potencia())

        return base


    def parse_negacion(self):
        """9 operadores unarios: - y ~"""
        if self.match(TokenType.OP_BIT_NOT, TokenType.OP_MINUS):
            op = self.current().value
            self.pos += 1
            return UnaryOp(op, self.parse_negacion())

        return self.parse_atom()

    def parse_atom(self):
        """10 atomo: es el de mayor precedencia.
        Puede ser un literal, un identificador, una llamada a función,
        un acceso a índice o una subexpresión entre paréntesis. """
        tok = self.current()
        # Subexpresión entre paréntesis: (expr)
        if tok.type == TokenType.LPAREN:
            self.eat(TokenType.LPAREN)
            expr = self.parse_expr()
            self.eat(TokenType.RPAREN)
            return expr
         # Literales numéricos
        if tok.type == TokenType.INTEGER:
            self.pos += 1; return IntLiteral(tok.value)
        if tok.type == TokenType.INTEGER_U:
            self.pos += 1; return IntLiteral(tok.value, unsigned=True)
        if tok.type == TokenType.HEXADECIMAL:
            self.pos += 1; return HexLiteral(tok.value)
        if tok.type == TokenType.HEXADECIMAL_U:
            self.pos += 1; return HexLiteral(tok.value, unsigned=True)
        if tok.type == TokenType.REAL_NUMBER:
            self.pos += 1; return RealLiteral(tok.value)
        
        # Literales de texto y booleanos
        if tok.type == TokenType.STRING_LITERAL:
            self.pos += 1; return StringLiteral(tok.value)
        if tok.type == TokenType.TRUE:
            self.pos += 1; return BoolLiteral(True)
        if tok.type == TokenType.FALSE:
            self.pos += 1; return BoolLiteral(False)
        
         # Literal de arreglo: [expr, expr, ...]
        if tok.type == TokenType.LBRACKET:
            return self.parse_list_literal()

         # Identificador: puede ser variable, llamada a función o acceso a índice
        if tok.type == TokenType.IDENTIFIER:
            # Lookahead: si sigue '(' es una llamada a función
            if self.peek().type == TokenType.LPAREN:
                return self.parse_func_call()
            name = self.eat(TokenType.IDENTIFIER).value
            node = Identifier(name)
            # Acceso a índice: nombre[i] o nombre[i][j]
            while self.match(TokenType.LBRACKET):
                self.eat(TokenType.LBRACKET)
                idx = self.parse_expr()
                self.eat(TokenType.RBRACKET)
                node = IndexAccess(node, [idx])
            return node

        raise ParseError(f'Expresión inesperada: {tok.type.name} ({repr(tok.value)})', tok)

    def parse_list_literal(self) -> ListLiteral:
        """Parsea un literal de arreglo: [expr, expr, ...]
        Soporta arreglos de arreglos: [[1, 2], [3, 4]]
        """
        self.eat(TokenType.LBRACKET)
        elements = []
        if not self.match(TokenType.RBRACKET):
            elements.append(self.parse_expr())
            while self.match(TokenType.COMMA):
                self.eat(TokenType.COMMA)
                elements.append(self.parse_expr())
        self.eat(TokenType.RBRACKET)
        return ListLiteral(elements)