#para usar en temrinal: python lexer.py tea.yeison -v      (o sin -v)

import sys
from typing import List, Tuple, Any
from enum import Enum, auto


class TokenType(Enum):
    #Palabras reservadas
    SI = auto();       SINO = auto();     MIENTRAS = auto(); PARA = auto()
    RETORNA = auto();  FUNC = auto();     VAR = auto();      CONST = auto()
    TRUE = auto();     FALSE = auto();    AND = auto();      OR = auto()
    NOT = auto();      IMPORTAR = auto()

    #Tipos de dato
    INT = auto();  UINT = auto();  BOOL = auto();  STRING = auto()
    REAL = auto(); VOID = auto()

    #Autenticación
    LOGIN    = auto()   # login(pwd)'   
    LOGOUT   = auto()   # logout()'      
    SETPWD   = auto()   # setpwd(pwd)'  
    AUTHCHK  = auto()   # authchk()'
    AUTHORIZE = auto()
    VKLOAD   = auto()   # vkload(slot, key)
    VKINV    = auto()   # vkinv(slot)

    #Anotaciones
    ANNOTATION = auto()  # @boveda  @code

    #Identificadores
    IDENTIFIER     = auto()
    INTEGER        = auto()      # 42
    INTEGER_U      = auto()      # 42u
    HEXADECIMAL    = auto()      # 0xFF     
    HEXADECIMAL_U  = auto()      # 0xFFu   
    REAL_NUMBER    = auto()      # 3.14     
    STRING_LITERAL = auto()      # "hola"

    #Operadores multi-char
    OP_EQ          = auto()   # ==
    OP_NE          = auto()   # !=
    OP_LE          = auto()   # <=
    OP_GE          = auto()   # >=
    OP_LSHIFT      = auto()   # <<
    OP_RSHIFT      = auto()   # >>
    OP_POW         = auto()   # **
    OP_RETURN_TYPE = auto()   # ::


    #Operadores de un carácter
    OP_PLUS    = auto()   # +
    OP_MINUS   = auto()   # -
    OP_MUL     = auto()   # *
    OP_DIV     = auto()   # /
    OP_MOD     = auto()   # %
    OP_XOR     = auto()   # ^
    OP_BIT_NOT = auto()   # ~
    OP_BIT_AND = auto()   # &
    OP_BIT_OR  = auto()   # |
    OP_LT      = auto()   # <
    OP_GT      = auto()   # >

    #Delimitadores
    ASSIGN     = auto()   # =
    LPAREN     = auto()   # (
    RPAREN     = auto()   # )
    LBRACE     = auto()   # {
    RBRACE     = auto()   # }
    LBRACKET   = auto()   # [
    RBRACKET   = auto()   # ]
    COLON      = auto()   # :
    COMMA      = auto()   # ,
    TERMINATOR = auto()   # '

    #Especiales para errores
    ERROR = auto()
    EOF   = auto()


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, type_: TokenType, value: Any, line: int, col: int):
        self.type  = type_
        self.value = value   #ya convertido: int, float, str
        self.line  = line
        self.col   = col

    def __repr__(self):
        return (f"Token({self.type.name:<20} "
                f"{repr(self.value):<25} "
                f"{self.line}:{self.col})")


class Lexer:

    #Constante de clase
    KEYWORDS = {
        #Flujo de control
        'si':       TokenType.SI,       'sino':     TokenType.SINO,
        'mientras': TokenType.MIENTRAS, 'para':     TokenType.PARA,
        'retorna':  TokenType.RETORNA,  'func':     TokenType.FUNC,
        'var':      TokenType.VAR,      'const':    TokenType.CONST,
        'importar': TokenType.IMPORTAR,
        #Literales booleanos y lógicos
        'true':  TokenType.TRUE,  'false': TokenType.FALSE,
        'and':   TokenType.AND,   'or':    TokenType.OR,
        'not':   TokenType.NOT,
        #Tipos
        'int':    TokenType.INT,    'uint':   TokenType.UINT,
        'bool':   TokenType.BOOL,   'string': TokenType.STRING,
        'real':   TokenType.REAL,   'void':   TokenType.VOID,
        #Boveda de llaves
        'login': TokenType.LOGIN,'logout': TokenType.LOGOUT,
        'setpwd': TokenType.SETPWD,'authchk': TokenType.AUTHCHK,
        'authorize': TokenType.AUTHORIZE,'vkload': TokenType.VKLOAD,
        'vkinv': TokenType.VKINV,
    }

    #Anotaciones válidas
    VALID_ANNOTATIONS = {'boveda', 'code'}

    #Caracteres de sincronización para panic mode
    SYNC = set(
        " \t\n\r'{}()[]#\"@_"
        "0123456789"
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    )

    def __init__(self, source: str):
        self.source = source + '\0\0'   #centinelas como en el libro para evitar chequeos de bounds
        self.pos    = 0
        self.line   = 1
        self.col    = 1
        self.errors: List[Tuple[int, int, str]] = []

    #Primitivas del DFA
    def current(self) -> str:
        return self.source[self.pos]

    def peek(self, n: int = 1) -> str:
        return self.source[self.pos + n]

    def advance(self) -> str:
        ch = self.source[self.pos]
        if ch == '\n':
            self.line += 1
            self.col = 0
        self.pos += 1
        self.col += 1
        return ch

    #Espacios y comentarios

    def skip_whitespace(self):
        while self.current() in ' \t\n\r':
            self.advance()

    def skip_line_comment(self):
        """Descarta desde # hasta fin de línea (sin consumir el \\n)."""
        while self.current() not in '\n\0':
            self.advance()

    def skip_block_comment(self):
        """
        Descarta ## ... ##
        """
        self.advance(); self.advance()          #consume ##
        while not (self.current() == '#' and self.peek() == '#'):
            if self.current() == '\0':
                self.errors.append(
                    (self.line, self.col, "Comentario de bloque no cerrado"))
                return
            self.advance()
        self.advance(); self.advance()          #consume ## de cierre

    def skip(self):
        """Salta espacioos en blanco y comentarios hasta encontrar texto"""
        while True:
            if self.current() in ' \t\n\r':
                self.skip_whitespace()
            elif self.current() == '#' and self.peek() == '#':
                self.skip_block_comment()
            elif self.current() == '#':
                self.skip_line_comment()
            else:
                break

    #Subautomata: identificadores/palabras clave
    #Estado INICIO[a-zA-Z_] hacia IDENT[a-zA-Z0-9_]* hacia ACEPTAR
    #En ACEPTAR: buscar en KEYWORDS hacia tipo especifico o IDENTIFIER

    def read_identifier(self) -> Token:
        sl, sc = self.line, self.col
        name = ''
        while self.current().isalnum() or self.current() == '_':
            name += self.advance()
        return Token(self.KEYWORDS.get(name, TokenType.IDENTIFIER), name, sl, sc)

    #Subautomata: literales numéricos
    #INICIO'0x'a HEX [0-9a-fA-F]+ a ['u'?] a ACEPTAR
    #INICIOdígito a INTdígito* a ['u'?] a ACEPTAR
    def read_number(self) -> Token:
        sl, sc = self.line, self.col

        #Hexadecimal: 0x[0-9a-fA-F]+[u?]
        if self.current() == '0' and self.peek() in ('x', 'X'):
            self.advance(); self.advance()      #consume 0x
            digits = ''
            while self.current() in '0123456789abcdefABCDEF':
                digits += self.advance()
            if not digits:
                self.errors.append((sl, sc, "Hexadecimal sin dígitos después de '0x'"))
                return Token(TokenType.ERROR, '0x', sl, sc)
            val = int(digits, 16)
            if self.current() == 'u':
                self.advance()
                return Token(TokenType.HEXADECIMAL_U, val, sl, sc)
            return Token(TokenType.HEXADECIMAL, val, sl, sc)

        #Entero o real
        digits = ''
        while self.current().isdigit():
            digits += self.advance()

        #es real solo si sigue '.' y luego un dígito, evita "3..5"
        if self.current() == '.' and self.peek().isdigit():
            digits += self.advance()            # consume '.'
            while self.current().isdigit():
                digits += self.advance()
            return Token(TokenType.REAL_NUMBER, float(digits), sl, sc)

        val = int(digits)
        if self.current() == 'u':
            self.advance()
            return Token(TokenType.INTEGER_U, val, sl, sc)
        return Token(TokenType.INTEGER, val, sl, sc)

    #Subautmata: cadenas
    #INICIO'"' a CADENA[^"\n\0]* a '"' a ACEPTAR
    def read_string(self) -> Token:
        sl, sc = self.line, self.col
        self.advance()                          #consume "
        val = ''
        while self.current() != '"' and self.current() != '\0':
            if self.current() == '\n':
                self.errors.append((sl, sc, "Cadena sin cerrar (salto de línea)"))
                return Token(TokenType.ERROR, val, sl, sc)
            if self.current() == '\\' and self.peek() in ('"', '\\', 'n', 't', 'r'):
                self.advance()
                val += {'n': '\n', 't': '\t', 'r': '\r',
                        '"': '"', '\\': '\\'}.get(self.current(), self.current())
                self.advance()
            else:
                val += self.advance()
        if self.current() == '\0':
            self.errors.append((sl, sc, "Cadena sin cerrar (fin de archivo)"))
            return Token(TokenType.ERROR, val, sl, sc)
        self.advance()                          # consume "
        return Token(TokenType.STRING_LITERAL, val, sl, sc)

    #Subautomata: anotaciones  @boveda  @code
    #INICIO'@' a NOMBRE[a-z]+ a ACEPTAR
    def read_annotation(self) -> Token:
        sl, sc = self.line, self.col
        self.advance()                          #consume @
        name = ''
        while self.current().isalnum() or self.current() == '_':
            name += self.advance()
        if not name:
            self.errors.append((sl, sc, "Anotación vacía después de '@'"))
            return Token(TokenType.ERROR, '@', sl, sc)
        if name not in self.VALID_ANNOTATIONS:
            self.errors.append((sl, sc, f"Anotación '@{name}' no reconocida"))
            return Token(TokenType.ERROR, '@' + name, sl, sc)
        return Token(TokenType.ANNOTATION, '@' + name, sl, sc)

    #SubautOmata: operadores y delimitadores
    def read_operator(self) -> Token:
        sl, sc = self.line, self.col
        ch  = self.current()
        nxt = self.peek()

        # Operadores de dos caracteres
        two = {
            '**': TokenType.OP_POW,
            '==': TokenType.OP_EQ,          '!=': TokenType.OP_NE,
            '<=': TokenType.OP_LE,          '>=': TokenType.OP_GE,
            '<<': TokenType.OP_LSHIFT,      '>>': TokenType.OP_RSHIFT,
            '::': TokenType.OP_RETURN_TYPE,
        }
        pair = ch + nxt
        if pair in two:
            self.advance(); self.advance()
            return Token(two[pair], pair, sl, sc)

        #Operadores de un carácter
        one = {
            '+': TokenType.OP_PLUS,    '-': TokenType.OP_MINUS,
            '*': TokenType.OP_MUL,     '/': TokenType.OP_DIV,
            '%': TokenType.OP_MOD,     '^': TokenType.OP_XOR,
            '~': TokenType.OP_BIT_NOT, '&': TokenType.OP_BIT_AND,
            '|': TokenType.OP_BIT_OR,  '<': TokenType.OP_LT,
            '>': TokenType.OP_GT,      '=': TokenType.ASSIGN,
            '(': TokenType.LPAREN,     ')': TokenType.RPAREN,
            '{': TokenType.LBRACE,     '}': TokenType.RBRACE,
            '[': TokenType.LBRACKET,   ']': TokenType.RBRACKET,
            ':': TokenType.COLON,      ',': TokenType.COMMA,
            "'": TokenType.TERMINATOR,
        }
        if ch in one:
            self.advance()
            return Token(one[ch], ch, sl, sc)

        return self.panic_mode()

    #Recuperación de errores
    def panic_mode(self) -> Token:
        sl, sc = self.line, self.col
        bad    = self.current()
        while self.current() not in self.SYNC and self.current() != '\0':
            self.advance()
        self.errors.append((sl, sc, f"Carácter no reconocido: '{bad}'"))
        return Token(TokenType.ERROR, bad, sl, sc)

    
    #funciones de uso publico
    def next_token(self) -> Token:
        """Retorna el siguiente token. Llamar en bucle hasta EOF."""
        self.skip()
        ch = self.current()
        if ch == '\0':                return Token(TokenType.EOF, None, self.line, self.col)
        if ch.isalpha() or ch == '_': return self.read_identifier()
        if ch.isdigit():              return self.read_number()
        if ch == '"':                 return self.read_string()
        if ch == '@':                 return self.read_annotation()
        return self.read_operator()

    def tokenize(self) -> List[Token]:
        """Consume todo y retorna la lista completa de tokens."""
        tokens = []
        while True:
            tok = self.next_token()
            tokens.append(tok)
            if tok.type == TokenType.EOF:
                break
        return tokens

    def print_tokens(self, tokens: List[Token]) -> None:
        """Muestra los tokens en formato tabla"""
        
        ancho = 72
        
        #Titulos
        print("-" * ancho)
        print("TOKENS".center(ancho))
        print("-" * ancho)
        
        print(f"  #     TIPO                    VALOR                     LIN:COL")
        print("  " + "-" * (ancho - 2))
        
        #Listado de tokens sin EOF
        for i, tok in enumerate(tokens):
            if tok.type == TokenType.EOF:
                continue
                
            print(f"  {i:<5} {tok.type.name:<22} {repr(tok.value):<25} {tok.line}:{tok.col}")
        
       
  
        total_tokens = len(tokens) - 1
        print(f"Total: {total_tokens} token{'s' if total_tokens != 1 else ''}")
        
        #Errores
        if self.errors:
            print(f"\n  Error {len(self.errors)} error(es) léxico(s):")
            for linea, col, msg in self.errors:
                print(f"     Línea {linea}, columna {col}: {msg}")
        else:
            print("\nFunciona acachete")
        



def main():
    import argparse
    ap = argparse.ArgumentParser(description="Lexer Yeison")
    ap.add_argument("archivo", help="Archivo fuente .yeison")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Mostrar tabla completa de tokens")
    args = ap.parse_args()

    try:
        with open(args.archivo, encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: no se encontró '{args.archivo}'")
        return 1

    lexer  = Lexer(source)
    tokens = lexer.tokenize()

    if args.verbose:
        lexer.print_tokens(tokens)
    else:
        total  = len(tokens) - 1
        status = "Bien" if not lexer.errors else "mal"
        print(f"{status}  {total} tokens  |  {len(lexer.errors)} errores  |  {args.archivo}")

    return 0 if not lexer.errors else 1


if __name__ == "__main__":
    sys.exit(main())