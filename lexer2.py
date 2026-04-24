# Produce la lista de tokens que consume el parser.
#Esta implementacion es con la libreria re

import re
from typing import List, Tuple, Any
from enum import Enum, auto


# TokenType - todos los tipos de token del lenguaje

class TokenType(Enum):
    # Palabras reservadas de control y flujo
    SI = auto(); SINO = auto(); MIENTRAS = auto(); PARA = auto()
    RETORNA = auto(); FUNC = auto(); VAR = auto(); CONST = auto()
    TRUE = auto(); FALSE = auto(); AND = auto(); OR = auto()
    NOT = auto(); IMPORTAR = auto()

    # Tipos de dato
    INT = auto(); UINT = auto(); BOOL = auto(); STRING = auto()
    REAL = auto(); VOID = auto()

    # Palabras reservadas de bóveda - mapean directamente a instrucciones V-Type del ISA
    LOGIN = auto() # LOGIN
    LOGOUT = auto() # LOGOUT
    SETPWD = auto() # SETPWD
    AUTHCHK = auto() # AUTHCHK
    AUTHORIZE = auto() # AUTHORIZE
    VKLOAD = auto() # VKLOAD
    VKINV = auto() # VKINV 

    # Anotaciones: @boveda o @code
    ANNOTATION = auto()

    # Identificadores y literales
    IDENTIFIER = auto()
    INTEGER = auto() # 42
    INTEGER_U = auto() # 42u
    HEXADECIMAL = auto() # 0xFF
    HEXADECIMAL_U = auto() # 0xFFu
    REAL_NUMBER = auto() # 3.14
    STRING_LITERAL = auto() # "hola"

    # Operadores de dos caracteres (deben ir antes que los de uno en el regex)
    OP_EQ = auto() # ==
    OP_NE = auto() # !=
    OP_LE = auto() # <=
    OP_GE = auto() # >=
    OP_LSHIFT = auto() # <<
    OP_RSHIFT = auto() # >>
    OP_POW = auto() # **
    OP_RETURN_TYPE = auto() # ::

    # Operadores de un carácter
    OP_PLUS = auto()# +
    OP_MINUS = auto() # -
    OP_MUL = auto() # *
    OP_DIV = auto() # /
    OP_MOD = auto() # %
    OP_XOR = auto() # ^
    OP_BIT_NOT = auto() # ~
    OP_BIT_AND = auto() # &
    OP_BIT_OR = auto() # |
    OP_LT = auto() # <
    OP_GT = auto() # >

    # Delimitadores
    ASSIGN = auto() # =
    LPAREN = auto() # (
    RPAREN = auto() # )
    LBRACE = auto() # {
    RBRACE = auto() # }
    LBRACKET = auto() # [
    RBRACKET = auto() # ]
    COLON = auto() # :
    COMMA = auto() # ,
    TERMINATOR = auto() # '

    # Especiales
    ERROR = auto()
    EOF = auto()


# Token - par (tipo, valor) con información de posición
class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type_: TokenType, value: Any, line: int, col: int):
        self.type  = type_
        self.value = value
        self.line  = line
        self.col   = col

    def __repr__(self):
        return (
            f"Token({self.type.name:<20} "
            f"{repr(self.value):<25} "
            f"{self.line}:{self.col})"
        )


# Lexer - convierte en una lista de tokens
class Lexer:
    # Tabla de palabras reservadas - si el identificador está aquí
    # se retorna el TokenType correspondiente en vez de IDENTIFIER
    KEYWORDS = {
        # Control de flujo
        'si': TokenType.SI, 'sino': TokenType.SINO,
        'mientras': TokenType.MIENTRAS, 'para': TokenType.PARA,
        'retorna': TokenType.RETORNA, 'func': TokenType.FUNC,
        'var': TokenType.VAR, 'const': TokenType.CONST,
        'importar': TokenType.IMPORTAR,
        # Literales booleanos y lógicos
        'true': TokenType.TRUE, 'false': TokenType.FALSE,
        'and': TokenType.AND, 'or': TokenType.OR,
        'not': TokenType.NOT,
        # Tipos
        'int': TokenType.INT, 'uint': TokenType.UINT,
        'bool': TokenType.BOOL, 'string': TokenType.STRING,
        'real': TokenType.REAL, 'void': TokenType.VOID,
        # Bóveda de llaves
        'login': TokenType.LOGIN, 'logout': TokenType.LOGOUT,
        'setpwd': TokenType.SETPWD, 'authchk': TokenType.AUTHCHK,
        'authorize': TokenType.AUTHORIZE, 'vkload': TokenType.VKLOAD,
        'vkinv': TokenType.VKINV,
    }

    # Anotaciones del lenguaje
    VALID_ANNOTATIONS = {'boveda', 'code'}
    TOKEN_REGEX = [
        # Comentarios y espacios - se descartan, no producen tokens
        ('BLOCK_COMMENT', r'\#\#[\s\S]*?\#\#'),  # ## ... ##
        ('LINE_COMMENT', r'\#[^\n]*'),  # # hasta fin de línea
        ('WHITESPACE', r'[ \t\r\n]+'),

        # Anotaciones de sección
        ('ANNOTATION',     r'@[A-Za-z_][A-Za-z0-9_]*'),

        # Literales numéricos - hex antes que int para que 0xFF no se parta en 0 y xFF
        # Con sufijo 'u' primero para que 42u no se parta en 42 e IDENTIFIER 'u'
        ('HEXADECIMAL_U', r'-?0[xX][0-9a-fA-F]+u'),
        ('HEXADECIMAL', r'-?0[xX][0-9a-fA-F]+'),
        ('REAL_NUMBER', r'-?[0-9]+\.[0-9]+'),
        ('INTEGER_U', r'-?[0-9]+u'),
        ('INTEGER', r'-?[0-9]+'),

        # Cadenas de texto con soporte de secuencias de escape
        ('STRING_LITERAL', r'"([^"\\\n]|\\["\\ntr])*"'),

        # Operadores de dos caracteres 
        ('OP_POW', r'\*\*'), # ** antes de *
        ('OP_EQ', r'=='), # == antes de =
        ('OP_NE', r'!='),
        ('OP_LE', r'<='), # <= antes de <
        ('OP_GE', r'>='), # >= antes de >
        ('OP_LSHIFT', r'<<'), # << antes de <
        ('OP_RSHIFT', r'>>'), # >> antes de >
        ('OP_RETURN_TYPE', r'::'),  # :: antes de :

        # Operadores de un carácter
        ('OP_PLUS', r'\+'), ('OP_MINUS', r'-'),
        ('OP_MUL', r'\*'), ('OP_DIV', r'/'),
        ('OP_MOD', r'%'),  ('OP_XOR',  r'\^'),
        ('OP_BIT_NOT', r'~'),  ('OP_BIT_AND', r'&'),
        ('OP_BIT_OR', r'\|'), ('OP_LT',  r'<'),
        ('OP_GT', r'>'),  ('ASSIGN', r'='),

        # Delimitadores
        ('LPAREN', r'\('), ('RPAREN', r'\)'),
        ('LBRACE', r'\{'), ('RBRACE', r'\}'),
        ('LBRACKET', r'\['), ('RBRACKET', r'\]'),
        ('COLON', r':'),  ('COMMA', r','),
        ('TERMINATOR', r"'"),

        ('IDENTIFIER', r'[A-Za-z_][A-Za-z0-9_]*'),
    ]

    MASTER_REGEX = re.compile(
        '|'.join(f'(?P<{name}>{pattern})' for name, pattern in TOKEN_REGEX)
    )

    def __init__(self, source: str):
        self.source = source
        self.pos    = 0
        self.line   = 1
        self.col    = 1
        self.errors: List[Tuple[int, int, str]] = []

    def update_position(self, text: str):
        """Actualiza línea y columna después de consumir `text`."""
        for ch in text:
            if ch == '\n':
                self.line += 1
                self.col = 1
            else:
                self.col += 1

    def make_token(self, type: str, lexeme: str, line: int, col: int) -> Token:
        """Convierte un lexema en un Token con el tipo y valor."""

        # Identificadores: buscar en KEYWORDS, si no está es IDENTIFIER
        if type == 'IDENTIFIER':
            token_type = self.KEYWORDS.get(lexeme, TokenType.IDENTIFIER)
            return Token(token_type, lexeme, line, col)

        # Anotaciones: validar que sea @boveda o @code
        if type == 'ANNOTATION':
            name = lexeme[1:]   # quitar el '@'
            if name not in self.VALID_ANNOTATIONS:
                self.errors.append((line, col, f"Anotación '{lexeme}' no reconocida"))
                return Token(TokenType.ERROR, lexeme, line, col)
            return Token(TokenType.ANNOTATION, lexeme, line, col)

        # Literales numéricos 
        if type == 'INTEGER':
            return Token(TokenType.INTEGER, int(lexeme), line, col)

        if type == 'INTEGER_U':
            return Token(TokenType.INTEGER_U, int(lexeme[:-1]), line, col) # quitar 'u'

        if type == 'REAL_NUMBER':
            return Token(TokenType.REAL_NUMBER, float(lexeme), line, col)

        if type == 'HEXADECIMAL':
            sign  = -1 if lexeme.startswith('-') else 1
            clean = lexeme[1:] if sign == -1 else lexeme
            return Token(TokenType.HEXADECIMAL, sign * int(clean, 16), line, col)

        if type == 'HEXADECIMAL_U':
            raw   = lexeme[:-1]   # quitar 'u'
            sign  = -1 if raw.startswith('-') else 1
            clean = raw[1:] if sign == -1 else raw
            return Token(TokenType.HEXADECIMAL_U, sign * int(clean, 16), line, col)

        # Cadenas: quitar comillas y resolver secuencias de escape
        if type == 'STRING_LITERAL':
            value = lexeme[1:-1]
            value = (
                value.replace(r'\n', '\n')
                     .replace(r'\t', '\t')
                     .replace(r'\r', '\r')
                     .replace(r'\"', '"')
                     .replace(r'\\', '\\')
            )
            return Token(TokenType.STRING_LITERAL, value, line, col)

        # Todos los demás tokens (operadores, delimitadores) - el lexema es el valor
        return Token(TokenType[type], lexeme, line, col)

    def next_token(self) -> Token:
        """Retorna el siguiente token. Salta espacios y comentarios automáticamente."""
        while self.pos < len(self.source):
            match = self.MASTER_REGEX.match(self.source, self.pos)

            if not match:
                # Carácter no reconocido - reportar error y avanzar (panic mode)
                ch = self.source[self.pos]
                line, col = self.line, self.col
                self.errors.append((line, col, f"Carácter no reconocido: '{ch}'"))
                self.pos += 1
                self.update_position(ch)
                return Token(TokenType.ERROR, ch, line, col)

            type   = match.lastgroup
            lexeme = match.group()
            line, col = self.line, self.col

            self.pos = match.end()
            self.update_position(lexeme)

            # Espacios y comentarios se descartan sin producir token
            if type in ('WHITESPACE', 'LINE_COMMENT', 'BLOCK_COMMENT'):
                continue

            return self.make_token(type, lexeme, line, col)

        return Token(TokenType.EOF, None, self.line, self.col)

    def tokenize(self) -> List[Token]:
        """Consume todo el fuente y retorna la lista completa de tokens."""
        tokens = []
        while True:
            tok = self.next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                break
        return tokens

    def print_tokens(self, tokens: List[Token]) -> None:
        """Muestra los tokens en formato tabla."""
        ancho = 72

        print("-" * ancho)
        print("TOKENS".center(ancho))
        print("-" * ancho)
        print(f"  #     TIPO                    VALOR                     LIN:COL")
        print("  " + "-" * (ancho - 2))

        for i, tok in enumerate(tokens):
            if tok.type == TokenType.EOF:
                continue
            print(
                f"  {i:<5} {tok.type.name:<22} "
                f"{repr(tok.value):<25} {tok.line}:{tok.col}"
            )

        total = len(tokens) - 1
        print(f"Total: {total} token{'s' if total != 1 else ''}")

        if self.errors:
            print(f"\n  Error {len(self.errors)} error(es) léxico(s):")
            for linea, col, msg in self.errors:
                print(f"     Línea {linea}, columna {col}: {msg}")
        else:
            print("\nFunciona acachete")