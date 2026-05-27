from tkinter import Listbox, END
import re

# Palabras reservadas generales del lenguaje.
# Estas son las que se pueden sugerir mientras el usuario escribe.
KEYWORDS = [
    "var", "const", "func", "si", "sino", "mientras", "para",
    "retorna", "importar", "true", "false", "and", "or", "not",
    "login", "logout", "setpwd", "authchk", "authorize", "vkload", "vkinv",
    "@code", "@boveda"
]

# Tipos de datos del lenguaje.
# Se usan especialmente después de ":" o "::"
TYPES = ["int", "uint", "bool", "string", "real", "void"]

# Palabras que normalmente pueden iniciar una instrucción.
START_STATEMENTS = [
    "var", "const", "func", "si", "mientras", "para",
    "retorna", "importar", "@code", "@boveda"
]


class Autocomplete:

    def __init__(self, root, text):
        self.root = root
        self.text = text

        # popup será la ventanita con las sugerencias
        self.popup = None

        # Cada vez que se presiona una tecla revisamos si hay que sugerir algo
        self.text.bind("<KeyRelease>", self.on_key_release)

    def on_key_release(self, event):

        # Estas teclas que no recalculan sugerencias
        if event.keysym in ["Up", "Down", "Return", "Escape"]:
            return

        # Obtenemos la palabra actual donde está el cursor
        word = self.current_word()

        if len(word) >= 1:
            self.show_suggestions()

        else:
            self.hide_popup()

    def current_word(self):

        # Posición actual del cursor
        index = self.text.index("insert")

        # Inicio de la línea actual
        line_start = index.split(".")[0] + ".0"

        # Texto desde el inicio de la línea hasta el cursor
        current_line = self.text.get(line_start, index)

        # Buscar la última palabra válida
        match = re.search(r"[@A-Za-z_][A-Za-z0-9_]*$", current_line)

        if match:
            return match.group(0)
        else:
            return ""

    def get_context_suggestions(self):

        # Obtener la línea actual donde se está escribiendo
        index = self.text.index("insert")
        line_start = index.split(".")[0] + ".0"

        current_line = self.text.get(line_start, index).strip()

        # Si la línea está vacía o empieza con @
        # sugerimos instrucciones iniciales
        if current_line == "" or current_line.startswith("@"):
            return START_STATEMENTS

        # Después de ":" normalmente va un tipo
        if current_line.endswith(":") or current_line.endswith("::"):
            return TYPES

        # Caso específico:
        # var edad :
        if re.match(r"^(var|const)\s+\w+\s*:$", current_line):
            return TYPES

        # Si está escribiendo una función sugerimos tipos y "{"
        if current_line.startswith("func"):
            return TYPES + ["{"]

        # Caso general:
        return KEYWORDS + TYPES

    def show_suggestions(self, event=None):

        # Obtener palabra actual
        word = self.current_word()

        # Obtener sugerencias según contexto
        suggestions = self.get_context_suggestions()

        # Filtrar solo las que empiezan con lo escrito
        if word:
            suggestions = [s for s in suggestions if s.startswith(word)]

        # Si no hay sugerencias, cerrar popup
        if not suggestions:
            self.hide_popup()
            return "break"

        # Cerrar popup anterior antes de crear otro
        self.hide_popup()

        # Crear la lista visual de sugerencias
        self.popup = Listbox(
            self.root,
            bg="#161B22",
            fg="#E6EDF3",
            selectbackground="#264F78",
            font=("Consolas", 10),

            # Altura máxima del popup
            height=min(6, len(suggestions))
        )

        # Insertar cada sugerencia en la lista
        for item in suggestions:
            self.popup.insert(END, item)

        self.popup.selection_set(0)

        bbox = self.text.bbox("insert")

        if bbox is None:
            return "break"

        x, y, _, h = bbox

        # Colocar popup debajo del cursor
        self.popup.place(
            x=self.text.winfo_x() + x,
            y=self.text.winfo_y() + y + h
        )

        # Enter inserta la sugerencia
        self.popup.bind("<Return>", self.insert_selection)

        # Doble click también
        self.popup.bind("<Double-Button-1>", self.insert_selection)

        # Escape cierra popup
        self.popup.bind("<Escape>", lambda e: self.hide_popup())

        return "break"

    def insert_selection(self, event=None):

        # Si no existe popup, salir
        if not self.popup:
            return "break"

        # Obtener elemento seleccionado
        selected = self.popup.get(self.popup.curselection())

        # Obtener palabra actual escrita
        word = self.current_word()

        # Borrar palabra parcial
        if word:
            self.text.delete(f"insert-{len(word)}c", "insert")

        # Insertar sugerencia completa
        self.text.insert("insert", selected)

        # Cerrar popup
        self.hide_popup()

        return "break"

    def hide_popup(self):

        # Destruir popup si existe
        if self.popup:
            self.popup.destroy()
            self.popup = None


# Función simple para inicializar el autocomplete desde main.py
def setup(root, text):
    Autocomplete(root, text)