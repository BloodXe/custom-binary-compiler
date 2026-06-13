import os
import sys
import re

from compiler.optimizer import optimize
from compiler.lexer import Lexer
from compiler.parser import Parser, ParseError
from compiler.ast_nodes import AstNode
from compiler.semantic import SemanticAnalyzer
from compiler.asmgen import AsmGen
from compiler.asmgen2 import AsmGen2
from compiler.resolver import Resolver
from compiler.binary_gen import BinaryGen
from compiler.IRGen import IRGen
from compiler.basic_blocks import build_basic_blocks, format_blocks
from compiler.cfg import build_cfg


# Para extraer linea y columna de mensajes de error
_RE_LINECOL = re.compile(r'[Ll][íi]nea\s*(\d+)[,\s]+col(?:umna)?\s*(\d+)', re.IGNORECASE)
_RE_LINE = re.compile(r'[Ll][íi]nea\s*(\d+)', re.IGNORECASE)


def _sacar_posicion(mensaje):

    m = _RE_LINECOL.search(mensaje)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = _RE_LINE.search(mensaje)
    if m:
        return int(m.group(1)), 1
    return 1, 1


def _crear_error(mensaje, fase, linea=1, columna=1):
  
    return {
        "line": linea, 
        "col": columna, 
        "msg": mensaje, 
        "phase": fase
    }

#Crea el diccionario de resultado cuando hay error
def _resultado_error(fase, mensaje, errores=None):
    
    if errores is None:
        errores = [_crear_error(mensaje, fase)]
    return {
        "success": False,
        "phase": fase,
        "message": mensaje,
        "errors": errores,
        "asm": None,
        "resolved_asm": None
    }

#crea el diccionario de resultado cuando todo sale bien
def _resultado_exito(asm_code, resolved_asm, ir_code=None, blocks_code=None, optimization=None, stats=None, cfg_json=None, cfg_summary=None):

    return {
        "success": True,
        "phase": "success",
        "message": "Compilación exitosa",
        "errors": [],
        "ir": ir_code,
        "blocks": blocks_code,
        "cfg_json": cfg_json,
        "cfg_summary": cfg_summary,
        "asm": asm_code,
        "resolved_asm": resolved_asm,
        "optimization": optimization,
        "stats": str(stats)
    }

#Compila codigo fuente y devuelve el resultado
def compile_source(source: str, opt_config: dict = None) -> dict:

    
    #ASE 1 LEXICO
    try:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
    except Exception as e:
        return _resultado_error("lex", str(e))
    
    # Si hay errores lexicos, los reportamos
    if lexer.errors:
        mensaje = f"Errores léxicos ({len(lexer.errors)}):\n"
        errores = []
        for ln, col, msg in lexer.errors:
            mensaje += f"  Línea {ln}, col {col}: {msg}\n"
            errores.append(_crear_error(msg, "lex", ln, col))
        return _resultado_error("lex", mensaje, errores)
    
    #FASE 2 PARSE
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        msg = str(e)
        ln, col = _sacar_posicion(msg)
        return _resultado_error("parse", msg, [_crear_error(msg, "parse", ln, col)])
    except Exception as e:
        return _resultado_error("parse", str(e))
    
    #FASE 3 SEMANTICO
    try:
        sem = SemanticAnalyzer()
        sem.visit(ast)
    except Exception as e:
        return _resultado_error("semantic", str(e))
    
    # Si hay errores semanticos
    if sem.errors:
        mensaje = f"Errores semánticos ({len(sem.errors)}):\n"
        errores = []
        for e in sem.errors:
            e_str = str(e)
            ln, col = _sacar_posicion(e_str)
            mensaje += f"  {e_str}\n"
            errores.append(_crear_error(e_str, "semantic", ln, col))
        return _resultado_error("semantic", mensaje, errores)
    
    #FASE 3.25 - REPRESENTACION INTERMEDIA Y BLOQUES BASICOS
    try:
        ir_code = IRGen().generate(ast)
        blocks = build_basic_blocks(ir_code)
        blocks_code = format_blocks(blocks)

        # Construir CFG y obtener su representación JSON y resumen
        cfg_obj = build_cfg(ir_code)
        cfg_json = cfg_obj.to_json()
        cfg_summary = cfg_obj.summary()
    except Exception as e:
        return _resultado_error("ir", str(e))
    
    # FASE 3.5 - OPTIMIZACION (Loop unrolling y renombramiento)
    try:
        cfg = opt_config or {}
        optimization, stats = optimize(
            ir_code,
            enable_unroll  = cfg.get("unroll",  True),
            unroll_factor  = cfg.get("factor",  4),
            total_unroll   = cfg.get("total",   False),
            enable_rename  = cfg.get("rename",  True),
            enable_dce     = cfg.get("dce",     True),
            enable_reorder = cfg.get("reorder", False),
        )
    except Exception as e:
        return _resultado_error("optimization", str(e))   
    
    #FASE 4 y 5 GENERACION DE CODIGO 
    try:
        # Si hay optimizaciones activas, usar asmgen2 que trabaja sobre el IR optimizado
        any_opt = any([
            cfg.get("unroll",  True),
            cfg.get("rename",  True),
            cfg.get("dce",     True),
            cfg.get("reorder", False),
        ])
        if any_opt and optimization:
            asm_code = AsmGen2().generate(optimization)
        else:
            gen = AsmGen(sem)
            asm_code = gen.generate(ast)
        resolver = Resolver(asm_code)
        resolved_asm = resolver.resolve()
        return _resultado_exito(asm_code, resolved_asm, ir_code, blocks_code, optimization, stats, cfg_json, cfg_summary)
    except Exception as e:
        return _resultado_error("codegen", str(e))


def run_live_check(source: str) -> list:
    #revision rapida
    
    if not source.strip():
        return []
    
    # Lexico
    try:
        lexer = Lexer(source)
        tokens = lexer.tokenize()
    except Exception:
        return []
    
    if lexer.errors:
        errores = []
        for ln, col, msg in lexer.errors:
            errores.append(_crear_error(msg, "lex", ln, col))
        return errores
    
    # Parser
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        msg = str(e)
        ln, col = _sacar_posicion(msg)
        return [_crear_error(msg, "parse", ln, col)]
    except Exception:
        return []
    
    # Semantico
    try:
        sem = SemanticAnalyzer()
        sem.visit(ast)
        errores = []
        for e in sem.errors:
            e_str = str(e)
            ln, col = _sacar_posicion(e_str)
            errores.append(_crear_error(e_str, "semantic", ln, col))
        return errores
    except Exception:
        return []


# === FUNCIONES AUXILIARES (para linea de comandos) ===

def print_ast(node: AstNode, last: bool = True, prefix: str = ''):
    """Imprime el arbol sintactico de forma bonita"""
    connector = '└── ' if last else '├── '
    child_prefix = prefix + ('    ' if last else '│   ')
    print(prefix + connector + repr(node))
    children = [c for c in node.children if isinstance(c, AstNode)]
    for i, child in enumerate(children):
        print_ast(child, last=(i == len(children) - 1), prefix=child_prefix)


def cargar_con_imports(archivo: str) -> str:
   #Carga un archivo y todos sus imports
    visitados = set()
    
    def _cargar(f: str, prefijo: str = None) -> str:
        f = os.path.abspath(f)
        if f in visitados:
            return ""
        visitados.add(f)
        
        if not os.path.exists(f):
            raise FileNotFoundError(f"Módulo no encontrado: '{f}'")
        
        base_dir = os.path.dirname(f)
        with open(f, encoding='utf-8') as fh:
            codigo = fh.read()
        
        # Encontrar simbolos definidos en este modulo
        simbolos = set()
        if prefijo:
            for linea in codigo.splitlines():
                ls = linea.strip()
                if ls.startswith("func "):
                    simbolos.add(ls.split()[1].split("(")[0])
                elif ls.startswith("var ") or ls.startswith("const "):
                    simbolos.add(ls.split()[1])
        
        # Procesar imports y prefijos
        resultado = []
        for linea in codigo.splitlines():
            ls = linea.strip()
            if ls.startswith("importar"):
                partes = ls.split()
                if len(partes) >= 2:
                    modulo = partes[1].replace("'", "").strip()
                    ruta_modulo = os.path.join(base_dir, modulo + ".yeison")
                    resultado.append(_cargar(ruta_modulo, prefijo=modulo))
                else:
                    resultado.append(linea)
            else:
                # Agregar prefijo a los simbolos si es necesario
                if prefijo:
                    for simbolo in sorted(simbolos, key=len, reverse=True):
                        # Reemplazar solo palabras completas
                        patron = r'(?<!\w)' + re.escape(simbolo) + r'(?!\w)'
                        # Evitar reemplazar si ya tiene prefijo
                        if prefijo + '.' + simbolo not in linea:
                            linea = re.sub(patron, f'{prefijo}.{simbolo}', linea)
                resultado.append(linea)
        
        return "\n".join(resultado)
    
    return _cargar(archivo)


def ejecutar_fases_1_a_3(source: str, args):

    
    # Lexico
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    
    if args.lexer:
        lexer.print_tokens(tokens)
    
    if lexer.errors:
        msg = f'\nErrores léxicos ({len(lexer.errors)}):\n'
        for ln, col, m in lexer.errors:
            msg += f'  Línea {ln}, col {col}: {m}\n'
        raise Exception(msg)
    
    # Parser
    try:
        ast = Parser(tokens).parse()
    except ParseError as e:
        raise Exception(f'Error sintáctico:\n{e}')
    
    if args.verbose:
        print('\n=== ÁRBOL SINTÁCTICO ===\n')
        print_ast(ast)
    
    # Semantico
    sem = SemanticAnalyzer()
    sem.visit(ast)
    
    if args.semantico:
        sem.symbol_table.print_table()
    if args.etiquetas:
        sem.print_labels()
    if args.memoria:
        sem.print_memory()
    
    if sem.errors:
        msg = f'\nErrores semánticos ({len(sem.errors)}):\n'
        for e in sem.errors:
            msg += f'  {e}\n'
        raise Exception(msg)
    
    return ast, sem


def main():
    import argparse
    
    # Configurar argumentos
    ap = argparse.ArgumentParser(description='Compilador Yeison → TEA-ISA binario')
    ap.add_argument('archivo')
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('-l', '--lexer', action='store_true')
    ap.add_argument('-s', '--semantico', action='store_true')
    ap.add_argument('-m', '--memoria', action='store_true')
    ap.add_argument('-e', '--etiquetas', action='store_true')
    ap.add_argument('-S', '--asm', action='store_true')
    ap.add_argument('-b', '--binario', action='store_true')
    ap.add_argument('-x', '--hex', action='store_true')
    ap.add_argument('-o', '--output')
    ap.add_argument('-a', '--all', action='store_true')
    ap.add_argument('-A', '--from-asm', action='store_true')
    args = ap.parse_args()
    
    # Activar todas las opciones si se pide
    if args.all:
        args.verbose = args.lexer = args.semantico = True
        args.memoria = args.etiquetas = args.asm = args.binario = args.hex = True
    
    nombre_base = args.output or os.path.splitext(args.archivo)[0]
    
    # Compilar desde archivo .asm o desde fuente
    if args.from_asm:
        try:
            with open(args.archivo, encoding='utf-8') as f:
                asm_code = f.read()
        except FileNotFoundError:
            print(f'Error: {args.archivo}')
            return 1
    else:
        try:
            source = cargar_con_imports(args.archivo)
        except FileNotFoundError as e:
            print(f'Error: {e}')
            return 1
        
        ast, sem = ejecutar_fases_1_a_3(source, args)
        gen = AsmGen(sem)
        asm_code = gen.generate(ast)
    
    # Mostrar ASM si se pide
    if args.asm:
        print('\n=== ASM GENERADO ===\n')
        print(asm_code)
    
    # Resolver etiquetas
    resolver = Resolver(asm_code)
    resolved_asm = resolver.resolve()
    
    if args.asm:
        print('\n=== ASM RESUELTO ===\n')
        print(resolved_asm)
        if args.etiquetas:
            print('\n=== TABLA DE ETIQUETAS ===')
            for lbl, addr in resolver.get_label_table().items():
                print(f'  {lbl:<30} 0x{addr:04X}')
    
    # Guardar ASM si se pide
    if args.output and args.asm:
        with open(nombre_base + '.asm', 'w', encoding='utf-8') as f:
            f.write(asm_code)
    
    # Generar binario
    if args.binario:
        bg = BinaryGen(resolved_asm)
        archivo_hex = (nombre_base + '.mem') if args.hex else None
        if not bg.generate(nombre_base + '.bin', archivo_hex):
            print('Falló generación binaria.')
            return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())