import os
import sys
import re

#Esto para que el main pueda ejecutarse directamente desde el IDE de Visual sin importar todo el tema de los imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tkinter import *
from tkinter.scrolledtext import ScrolledText

import IDE.file_menu      as file_menu
import IDE.edit_menu      as edit_menu
import IDE.help_menu      as help_menu
import IDE.compiler_menu  as compiler_menu
import IDE.autocomplete   as autocomplete


#Ventana principals

root = Tk()
root.title("COMPILADOR YEISON")
root.geometry("900x650+150+80")
root.minsize(500, 400)
root.configure(bg="#0D1117")

# panel divisor que separa el editor de la consola
paned = PanedWindow(root, orient=VERTICAL, sashwidth=6, bg="#30363D", bd=0)
paned.pack(fill=BOTH, expand=True)


#frame del editor de texto

editor_frame = Frame(paned, bg="#0D1117")

#scrollbar vertical del editor
scrollbar_v = Scrollbar(editor_frame, orient=VERTICAL, bg="#30363D",
                        troughcolor="#0D1117", width=12)
scrollbar_v.pack(side=RIGHT, fill=Y)

#widget de numeros de linea 
line_numbers = Text(
    editor_frame,
    width=4,
    padx=6,
    pady=10,
    bg="#161B22",
    fg="#4D5566",
    font=("Consolas", 12),
    state="disabled",
    wrap="none",
    cursor="arrow",
    relief="flat",
    bd=0,
    selectbackground="#161B22",
    highlightthickness=0,
    takefocus=False,
    exportselection=False,
)
line_numbers.pack(side=LEFT, fill=Y)

#linea separadora entre numeros y codigo
separator = Frame(editor_frame, width=1, bg="#30363D")
separator.pack(side=LEFT, fill=Y)

#area de texto principal donde se escribe el codigo
text = Text(
    editor_frame,
    state="normal",
    bg="#0D1117",
    fg="#E6EDF3",
    insertbackground="white",
    selectbackground="#264F78",
    wrap="none",
    undo=True,
    font=("Consolas", 12),
    padx=10,
    pady=10,
    tabs=("1c",),
    relief="flat",
    bd=0,
    highlightthickness=0,
    yscrollcommand=scrollbar_v.set,
)
text.pack(side=LEFT, fill=BOTH, expand=True)
text.focus_set()

scrollbar_v.config(command=text.yview)

paned.add(editor_frame, minsize=250)


#funciones de numeros de linea

def update_line_numbers(event=None):
    #cuento cuantas lineas tiene el texto
    total_lines = int(text.index("end-1c").split(".")[0])

    #si hay mas de 999 lineas se amplia el ancho del widget
    needed_width = max(3, len(str(total_lines)) + 1)
    if line_numbers.cget("width") != needed_width:
        line_numbers.config(width=needed_width)

    #genero los numeros como texto separado por saltos de linea
    numbers = "\n".join(str(i) for i in range(1, total_lines + 1))

    line_numbers.config(state="normal")
    line_numbers.delete("1.0", END)
    line_numbers.insert("1.0", numbers)
    line_numbers.config(state="disabled")

    # sincronizo el scroll con el editor
    line_numbers.yview_moveto(text.yview()[0])


def sync_line_numbers_scroll(*args):
  
    line_numbers.yview_moveto(args[0])
    scrollbar_v.set(*args)


#reconecto el la barrita para desplazar para que sincronice los numeros de linea
text.config(yscrollcommand=sync_line_numbers_scroll)

#evito que el usuario pueda scrollear los numeros de forma independiente
line_numbers.bind("<MouseWheel>", lambda e: text.event_generate("<MouseWheel>", delta=e.delta))
line_numbers.bind("<Button-4>",   lambda e: text.yview_scroll(-1, "units"))
line_numbers.bind("<Button-5>",   lambda e: text.yview_scroll(1,  "units"))

#tag para resaltar el numero de linea donde esta el cursor
_current_line_tag = "current_line_num"
line_numbers.tag_configure(_current_line_tag, foreground="#C9D1D9")


def highlight_current_line_number(event=None):
    #quito el resaltado anterior y pongo el nuevo en la linea del cursor
    line_numbers.tag_remove(_current_line_tag, "1.0", END)
    try:
        current = int(text.index("insert").split(".")[0])
        line_numbers.tag_add(_current_line_tag, f"{current}.0", f"{current}.end")
    except Exception:
        pass
    line_numbers.yview_moveto(text.yview()[0])


#Consola de resultados

console = ScrolledText(
    paned,
    height=10,
    bg="#161B22",
    fg="#E6EDF3",
    insertbackground="white",
    font=("Consolas", 10),
    padx=10,
    pady=8,
    state="normal",
)
console.insert("1.0", "Panel de información\n")

paned.add(console, minsize=100)


#colores de palabras

_HL_TAGS = {
    "hl_keyword":    {"foreground": "#F5746B", "font": ("Consolas", 12, "bold")},
    "hl_type":       {"foreground": "#7ABFFC", "font": ("Consolas", 12)},
    "hl_boolean":    {"foreground": "#56CF64", "font": ("Consolas", 12)},
    "hl_operator":   {"foreground": "#FA7B72", "font": ("Consolas", 12, "bold")},
    "hl_vault":      {"foreground": "#D2A9FD", "font": ("Consolas", 12)},
    "hl_annotation": {"foreground": "#FCA356", "font": ("Consolas", 12, "bold")},
    "hl_string":     {"foreground": "#A3D6FF", "font": ("Consolas", 12)},
    "hl_comment":    {"foreground": "#8E96A0", "font": ("Consolas", 12, "italic")},
    "hl_number":     {"foreground": "#EEC75E", "font": ("Consolas", 12)},
    "hl_terminator": {"foreground": "#727983", "font": ("Consolas", 12)},
}

#estilos al widget de texto
for _tag, _cfg in _HL_TAGS.items():
    text.tag_configure(_tag, **_cfg)

#lista de patrones con su tag correspondiente (el orde importa, van comentarios primero)
_HL_COMPILED = [
    ("hl_comment",    re.compile(r"##[\s\S]*?##",         re.MULTILINE)),
    ("hl_comment",    re.compile(r"#[^\n]*",              re.MULTILINE)),
    ("hl_string",     re.compile(r'"(?:[^"\\]|\\.)*"',   re.MULTILINE)),
    ("hl_number",     re.compile(r"0[xX][0-9a-fA-F]+u?", re.MULTILINE)),
    ("hl_number",     re.compile(r"\b\d+\.\d+\b",        re.MULTILINE)),
    ("hl_number",     re.compile(r"\b\d+u?\b",           re.MULTILINE)),
    ("hl_annotation", re.compile(r"@(?:boveda|code)\b",  re.MULTILINE)),
    ("hl_type",       re.compile(r"\b(?:int|uint|bool|string|real|void)\b", re.MULTILINE)),
    ("hl_boolean",    re.compile(r"\b(?:true|false)\b",  re.MULTILINE)),
    ("hl_operator",   re.compile(r"\b(?:and|or|not)\b",  re.MULTILINE)),
    ("hl_vault",      re.compile(r"\b(?:login|logout|setpwd|authchk|authorize|vkload|vkinv)\b", re.MULTILINE)),
    ("hl_keyword",    re.compile(r"\b(?:si|sino|mientras|para|retorna|func|var|const|importar)\b", re.MULTILINE)),
    ("hl_terminator", re.compile(r"'",                   re.MULTILINE)),
]


def apply_highlighting(event=None):
    try:
        content = text.get("1.0", "end-1c")
        #limpio los tags de color antes de repintar
        for tag in _HL_TAGS:
            text.tag_remove(tag, "1.0", "end")
        #se aplican los colores
        for tag, pattern in _HL_COMPILED:
            for m in pattern.finditer(content):
                text.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
      
        for tag in text.tag_names():
            if tag.startswith("cmperr_"):
                try:
                    text.tag_raise(tag)
                except Exception:
                    pass
    except Exception:
        pass


def on_content_change(event=None):
    #updatea todo cuando se modifica algo o cambia algo
    update_line_numbers()
    highlight_current_line_number()
    apply_highlighting()


text.bind("<KeyRelease>",   on_content_change, add="+")
text.bind("<<Paste>>",      lambda e: root.after(10, on_content_change), add="+")
text.bind("<ButtonRelease>", highlight_current_line_number, add="+")
text.bind("<Configure>",    lambda e: root.after(5, update_line_numbers), add="+")


#auto agregar el terminador en ciertas lineas cuando se le da al enter

#patron de lineas que necesitan terminador
_NEEDS_TERM    = re.compile(
    r"^\s*(var\s|const\s|retorna\b|[A-Za-z_][\w.]*(\ s*\[.*?\])?\s*=(?!=))"
)
#patron de lineas que NO necesitan terminador (estructuras de control)
_NO_TERM_START = re.compile(
    r"^\s*(si\b|sino\b|mientras\b|para\b|func\b|#|@)"
)
_NO_TERM_END   = frozenset({"'", "{", "}", "(", ")", ",", "\\"})


def _line_needs_terminator(line_text: str) -> bool:
    s = line_text.strip()
    if not s:
        return False
    if s[-1] in _NO_TERM_END:
        return False
    if _NO_TERM_START.match(s):
        return False
    if _NEEDS_TERM.match(s):
        return True
    return False


def on_return(event):
    try:
        idx       = text.index("insert")
        line_num  = int(idx.split(".")[0])
        line_text = text.get(f"{line_num}.0", f"{line_num}.end")

        # si la linea lo necesita, agrego el terminador antes del salto
        if _line_needs_terminator(line_text):
            text.insert(f"{line_num}.end", "'")

        # mantengo la indentacion de la linea anterior
        indent     = len(line_text) - len(line_text.lstrip())
        indent_str = " " * indent

        text.insert("insert", "\n" + indent_str)
        root.after(5, on_content_change)
        return "break"
    except Exception:
        return


text.bind("<Return>", on_return, add="+")


# autocierre de delimitadores ()

def _char_after_cursor() -> str:
    #devuelve el caracter inmediatamente despues del cursor
    try:
        return text.get("insert", "insert+1c")
    except Exception:
        return ""


def on_open_paren(event):
    try:
        after = _char_after_cursor()
        if not after or after in (" ", "\n", "\t", ")", "]", "}", "'"):
            text.insert("insert", "()")
            text.mark_set("insert", "insert-1c")
            return "break"
    except Exception:
        pass


def on_open_bracket(event):
    try:
        after = _char_after_cursor()
        if not after or after in (" ", "\n", "\t", ")", "]", "}", "'"):
            text.insert("insert", "[]")
            text.mark_set("insert", "insert-1c")
            return "break"
    except Exception:
        pass


def on_close_paren(event):
    #si el siguiente caracter ya es ), solo muevo el cursor
    try:
        if _char_after_cursor() == ")":
            text.mark_set("insert", "insert+1c")
            return "break"
    except Exception:
        pass


def on_close_bracket(event):
    try:
        if _char_after_cursor() == "]":
            text.mark_set("insert", "insert+1c")
            return "break"
    except Exception:
        pass


def on_open_brace(event):
    try:
        idx       = text.index("insert")
        line_num  = int(idx.split(".")[0])
        line_text = text.get(f"{line_num}.0", f"{line_num}.end")
        # calculo la indentacion para el bloque
        indent = len(line_text) - len(line_text.lstrip())
        inner  = " " * (indent + 4)
        outer  = " " * indent
        after  = _char_after_cursor()
        if not after or after in (" ", "\n", "\t", "'"):
            text.insert("insert", "{\n" + inner + "\n" + outer + "}")
            text.mark_set("insert", f"{line_num + 1}.end")
            root.after(5, on_content_change)
            return "break"
    except Exception:
        pass


def on_close_brace(event):
    try:
        if _char_after_cursor() == "}":
            text.mark_set("insert", "insert+1c")
            return "break"
    except Exception:
        pass


text.bind("(", on_open_paren,    add="+")
text.bind("[", on_open_bracket,  add="+")
text.bind(")", on_close_paren,   add="+")
text.bind("]", on_close_bracket, add="+")
text.bind("{", on_open_brace,    add="+")
text.bind("}", on_close_brace,   add="+")


#menus

menubar = Menu(root)

# compiler_menu se inicializa primero para tener la referencia a clear_errors
cm = compiler_menu.main(root, text, console, menubar)

# file_menu recibe los callbacks para actualizar el IDE al abrir/crear archivos
file_menu.main(root, text, menubar,
               on_content_change=on_content_change,
               clear_errors=cm.clear_errors)

edit_menu.main(root, text, menubar)
help_menu.main(root, text, menubar)
autocomplete.setup(root, text)

root.config(menu=menubar)

# llamo on_content_change al inicio para que se vea bien desde el principio
root.after(200, on_content_change)

root.mainloop()