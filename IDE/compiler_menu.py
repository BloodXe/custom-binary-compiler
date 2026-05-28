#menu del compilador con deteccion de errores en tiempo real


import re
import sys
import os
from tkinter import Menu, END

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from IDE.compiler_logic import compile_source, run_live_check



_STYLES = {
    "lex":      {"background": "#4D2600", "foreground": "#FFA657", "underline": True},  
    "parse":    {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True}, 
    "semantic": {"background": "#3D3800", "foreground": "#E3B341", "underline": True},  
    "codegen":  {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True},
    "error":    {"background": "#5A1E1E", "foreground": "#FF6B6B", "underline": True},
    "autofix":  {"background": "#1F2D3D", "foreground": "#79C0FF", "underline": True},  
}

_ERR_PREFIX = "cmperr_"

#busca problemas que se pueden corregir automaticamente terminadores faltantes y llaves/parentesis sin cerrar
def _find_autofix_issues(source: str) -> list:

    try:
        from compiler.lexer import Lexer, TokenType
    except ImportError:
        return []

    issues = []
    NEEDS_TERM = re.compile(
        r"^\s*(var\s|const\s|retorna\b|[A-Za-z_]\w*(\s*\[.*?\])?\s*=(?!=))"
    )
    NO_TERM_END = {"'", "{", "}", "(", ")", ",", "\\"}

    #revisa cada linea buscando terminadores faltantes
    for i, raw in enumerate(source.split("\n"), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped[-1] in NO_TERM_END:
            continue
        if NEEDS_TERM.match(stripped):
            issues.append({
                "kind": "missing_terminator",
                "line": i, "col": len(raw.rstrip()) + 1,
                "msg":  f"Línea {i}: falta terminador (') al final",
                "fix":  "'",
            })

    #uso del lexer para detectar llaves y parentesis sin cerrar
    try:
        toks   = Lexer(source).tokenize()
        braces = []
        parens = []
        for tok in toks:
            n = tok.type.name
            if   n == "LBRACE":  braces.append((tok.line, tok.col))
            elif n == "RBRACE":
                if braces: braces.pop()
                else: issues.append({"kind": "unbalanced_brace", "line": tok.line, "col": tok.col,
                                     "msg": f"Línea {tok.line}, col {tok.col}: '}}' sin apertura", "fix": None})
            elif n == "LPAREN":  parens.append((tok.line, tok.col))
            elif n == "RPAREN":
                if parens: parens.pop()
                else: issues.append({"kind": "unbalanced_paren", "line": tok.line, "col": tok.col,
                                     "msg": f"Línea {tok.line}, col {tok.col}: ')' sin apertura", "fix": None})
        for ln, col in braces:
            issues.append({"kind": "unbalanced_brace", "line": ln, "col": col,
                           "msg": f"Línea {ln}, col {col}: '{{' sin cierre", "fix": None})
        for ln, col in parens:
            issues.append({"kind": "unbalanced_paren", "line": ln, "col": col,
                           "msg": f"Línea {ln}, col {col}: '(' sin cierre", "fix": None})
    except Exception:
        pass

    return issues


class CompilerMenu:

    def __init__(self, text, console):
        self.text      = text
        self.console   = console
        self._err_tags = []  #guardo los tags de error activos para poder borrarlos

    def _write(self, msg: str):
        #limpio la consola y escribo el nuevo mensaje
        self.console.config(state="normal")
        self.console.delete("1.0", END)
        self.console.insert("1.0", msg)

    def compile_code(self):
        #compilo el codigo del editor y muestro el resultado
        source = self.text.get("1.0", END)
        self.clear_errors()
        result = compile_source(source)

        if result["success"]:
            out = "Compilación exitosa.\n\n"
            if result.get("asm"):
                out += " ASM GENERADO\n\n" + result["asm"] + "\n\n"
            if result.get("resolved_asm"):
                out += "ASM RESUELTO \n\n" + result["resolved_asm"]
            self._write(out)
        else:
            errors = result.get("errors", [])
            phase  = result.get("phase", "error")
            self._mark_errors(errors)

            #nombre legible de la fase que fallo
            label = {"lex": "léxico", "parse": "sintáctico", "semantic": "semántico",
                     "codegen": "generación de código"}.get(phase, "compilación")
            header = f"Error {label}  —  {len(errors)} error(es) detectado(s)\n{'─'*50}\n\n"
            self._write(header + result.get("message", ""))

    def autofix_code(self):
        #intenta corregir automaticamente los problemas q
        source = self.text.get("1.0", END)
        issues = _find_autofix_issues(source)
        self.clear_errors()

        if not issues:
            self._write("No se encontraron problemas autocorregibles")
            return

        fixed    = []  # lineas donde agregue terminador
        warnings = []  # problemas que no puedo corregir automaticamente
        entries  = []
        for iss in issues:
            entries.append({"line": iss["line"], "col": iss["col"],
                            "msg": iss["msg"], "phase": "autofix"})
            if iss["kind"] == "missing_terminator" and iss.get("fix"):
                fixed.append(iss["line"])
            else:
                warnings.append(iss["msg"])

        self._mark_errors(entries)

        # agrego los terminadores faltantes (de abajo hacia arriba para no desplazar lineas)
        for ln in sorted(fixed, reverse=True):
            end_pos  = self.text.index(f"{ln}.end")
            line_txt = self.text.get(f"{ln}.0", end_pos)
            if not line_txt.rstrip().endswith("'"):
                self.text.insert(end_pos, "'")

        # armo el reporte de lo que se hizo
        report = ""
        if fixed:
            report += f"✓ {len(fixed)} terminador(es) añadido(s) en líneas: " \
                      + ", ".join(str(l) for l in sorted(fixed)) + "\n\n"
        if warnings:
            report += f"⚠ {len(warnings)} advertencia(s) — corrección manual requerida:\n"
            for w in warnings:
                report += f"  • {w}\n"
        self._write(report)

    def live_check(self, event=None):
        # revision en tiempo real al escribir (lexico + parser + semantico)
        # si falla en alguna fase, para ahi para no saturar con errores
        self.clear_errors()
        try:
            source = self.text.get("1.0", END)
            errors = run_live_check(source)
            if errors:
                self._mark_errors(errors)
                # muestro solo el primer error en la consola
                first = errors[0]
                phase_label = {"lex": "Léxico", "parse": "Sintáctico",
                               "semantic": "Semántico"}.get(first["phase"], "Error")
                self._write(f"{phase_label}: {first['msg']}\n"
                            + (f"  ({len(errors)-1} error(es) más...)" if len(errors) > 1 else ""))
        except Exception:
            pass  # nunca rompo el editor por un error en la revision

    def _mark_errors(self, errors: list):
        # pinto las lineas con error usando tags cmperr_*
        # no toco los tags hl_* del highlighting de sintaxis
        for err in errors:
            ln    = err.get("line", 1)
            col   = err.get("col",  1)
            phase = err.get("phase", "error")
            style = _STYLES.get(phase, _STYLES["error"])

            tag = f"{_ERR_PREFIX}{ln}_{col}_{phase}"
            self.text.tag_configure(tag, **style)

            start     = f"{ln}.{max(0, col - 1)}"
            end       = f"{ln}.end"
            line_text = self.text.get(f"{ln}.0", end)
            if not line_text.strip() or col <= 1:
                start = f"{ln}.0"

            self.text.tag_add(tag, start, end)
            self.text.tag_raise(tag)
            self._err_tags.append(tag)

        # muevo la vista al primer error
        if errors:
            self.text.see(f"{errors[0]['line']}.0")

    def clear_errors(self):
        # borro solo los tags de error, los de highlighting no los toco
        for tag in self._err_tags:
            try:
                self.text.tag_remove(tag, "1.0", END)
                self.text.tag_delete(tag)
            except Exception:
                pass
        self._err_tags = []


def main(root, text, console, menubar):
    obj = CompilerMenu(text, console)

    # creo el menu del compilador
    m = Menu(menubar, tearoff=0, bg="#161B22", fg="white",
             activebackground="#000000", activeforeground="white")
    m.add_command(label="Compilar",       command=obj.compile_code, accelerator="F5")
    m.add_separator()
    m.add_command(label="Auto-corregir",  command=obj.autofix_code, accelerator="F6")
    m.add_command(label="Limpiar marcas", command=obj.clear_errors)
    menubar.add_cascade(label="Compilador", menu=m)

    # atajos de teclado
    root.bind("<F5>", lambda e: obj.compile_code())
    root.bind("<F6>", lambda e: obj.autofix_code())
    root.config(menu=menubar)

    # revision en tiempo real al soltar una tecla
    text.bind("<KeyRelease>", lambda e: obj.live_check(), add="+")

    return obj
