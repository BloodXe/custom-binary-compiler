import re
import sys
import os


# palabras clave del lenguaje divididas por categoria
KEYWORDS_CTRL  = ["si", "sino", "mientras", "para", "retorna", "func", "var", "const", "importar"]
KEYWORDS_BOOL  = ["true", "false", "and", "or", "not"]
KEYWORDS_VAULT = ["login", "logout", "setpwd", "authchk", "authorize", "vkload", "vkinv"]
TYPES          = ["int", "uint", "bool", "string", "real", "void"]
ANNOTATIONS    = ["@code", "@boveda"]

# todas las palabras clave juntas para busqueda rapida
ALL_KW      = KEYWORDS_CTRL + KEYWORDS_BOOL + KEYWORDS_VAULT + TYPES + ANNOTATIONS
START_WORDS = KEYWORDS_CTRL + ANNOTATIONS


def scan_symbols(source: str) -> dict:
    """
    Escanea el codigo con el Lexer y extrae todos los simbolos declarados.
    Funciona aunque el codigo tenga errores
    Retorna: { nombre: {"kind": "var"|"const"|"func"|"param", "type": str} }
    """
    try:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if root not in sys.path:
            sys.path.insert(0, root)
        from compiler.lexer import Lexer, TokenType
    except Exception:
        return {}

    TYPE_NAMES = {"INT", "UINT", "BOOL", "STRING", "REAL", "VOID"}
    symbols = {}

    try:
        toks = Lexer(source).tokenize()
    except Exception:
        return {}

    n = len(toks)
    i = 0
    while i < n:
        t = toks[i]

        # detecto declaraciones: var nombre : tipo
        if t.type == TokenType.VAR and i + 3 < n:
            nt, ct, tt = toks[i+1], toks[i+2], toks[i+3]
            if (nt.type == TokenType.IDENTIFIER
                    and ct.type == TokenType.COLON
                    and tt.type.name in TYPE_NAMES):
                symbols[nt.value] = {"kind": "var", "type": tt.value}
            i += 1; continue

        # detecto constantes: const nombre : tipo
        if t.type == TokenType.CONST and i + 3 < n:
            nt, ct, tt = toks[i+1], toks[i+2], toks[i+3]
            if (nt.type == TokenType.IDENTIFIER
                    and ct.type == TokenType.COLON
                    and tt.type.name in TYPE_NAMES):
                symbols[nt.value] = {"kind": "const", "type": tt.value}
            i += 1; continue

        # detecto funciones: func nombre(params) :: rettype
        if t.type == TokenType.FUNC and i + 1 < n:
            nt = toks[i+1]
            if nt.type == TokenType.IDENTIFIER:
                # busco el tipo de retorno despues del cierre del parentesis
                ret = "void"
                j, depth = i + 2, 0
                while j < n:
                    if toks[j].type == TokenType.LPAREN:
                        depth += 1
                    elif toks[j].type == TokenType.RPAREN:
                        depth -= 1
                        if depth == 0:
                            if (j + 2 < n
                                    and toks[j+1].type == TokenType.OP_RETURN_TYPE
                                    and toks[j+2].type.name in TYPE_NAMES):
                                ret = toks[j+2].value
                            break
                    j += 1
                symbols[nt.value] = {"kind": "func", "type": f"func → {ret}"}

                # tambien registro los parametros de la funcion
                j = i + 2
                if j < n and toks[j].type == TokenType.LPAREN:
                    j += 1
                    while j < n and toks[j].type != TokenType.RPAREN:
                        p = toks[j]
                        if (p.type == TokenType.IDENTIFIER and j + 2 < n
                                and toks[j+1].type == TokenType.COLON
                                and toks[j+2].type.name in TYPE_NAMES):
                            symbols[p.value] = {"kind": "param", "type": toks[j+2].value}
                            j += 3
                        else:
                            j += 1
                        if j < n and toks[j].type == TokenType.COMMA:
                            j += 1
        i += 1

    return symbols


def _analyze_grammar(line_before_cursor: str):
    """
    Analiza la linea hasta el cursor usando el Lexer
    Despues determina que token se espera segun la gramatica del lenguaje
    Retorna: (hint, suggestions, exact)
      hint        : texto para mostrar como ayuda
      suggestions : lista de tokens a sugerir
      exact       : True si son tokens exactos (como ":" o "=")
    """
    try:
        root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        if root_path not in sys.path:
            sys.path.insert(0, root_path)
        from compiler.lexer import Lexer, TokenType
    except Exception:
        return None, [], False

    try:
        lex  = Lexer(line_before_cursor.rstrip() + "\n")
        toks = [t for t in lex.tokenize()
                if t.type not in (TokenType.EOF, TokenType.TERMINATOR)]
    except Exception:
        return None, [], False

    if not toks:
        return None, [], False

    TT        = TokenType
    types_set = {TT.INT, TT.UINT, TT.BOOL, TT.STRING, TT.REAL, TT.VOID}
    tok_types = [t.type for t in toks]
    last      = toks[-1]

    #declaracion de variable o constante
    if tok_types in ([TT.VAR], [TT.CONST]):
        return "esperando nombre de variable", [], False

    if len(toks) == 2 and toks[0].type in (TT.VAR, TT.CONST) and toks[1].type == TT.IDENTIFIER:
        return "se esperaba  :", [":"], True

    if len(toks) == 3 and toks[0].type in (TT.VAR, TT.CONST) \
            and toks[1].type == TT.IDENTIFIER and toks[2].type == TT.COLON:
        return "se esperaba tipo", TYPES, False

    if len(toks) == 4 and toks[0].type in (TT.VAR, TT.CONST) \
            and toks[1].type == TT.IDENTIFIER \
            and toks[2].type == TT.COLON \
            and toks[3].type in types_set:
        return "se esperaba  =", ["="], True

    if len(toks) == 5 and toks[0].type in (TT.VAR, TT.CONST) \
            and toks[2].type == TT.COLON \
            and toks[3].type in types_set \
            and toks[4].type == TT.ASSIGN:
        tipo = toks[3].value
        if tipo == "bool":
            return "se esperaba valor bool", ["true", "false"], False
        return "se esperaba valor", [], False

    #declaracion de funcion
    if tok_types == [TT.FUNC]:
        return "esperando nombre de función", [], False

    if tok_types == [TT.FUNC, TT.IDENTIFIER]:
        return "se esperaba  (", ["("], True

    if toks[0].type == TT.FUNC and len(toks) >= 3 and toks[2].type == TT.LPAREN:
        has_return_op = TT.OP_RETURN_TYPE in tok_types

        if has_return_op:
            if last.type == TT.OP_RETURN_TYPE:
                return "tipo de retorno", TYPES, False
            if last.type in types_set:
                return "se esperaba  {", ["{"], True
        else:
            if last.type in (TT.LPAREN, TT.COMMA):
                return "nombre de parámetro  o  )", [], False
            if last.type == TT.IDENTIFIER:
                return "se esperaba  :", [":"], True
            if last.type == TT.COLON:
                return "tipo del parámetro", TYPES, False
            if last.type in types_set:
                return "se esperaba  ,  o  )", [",", ")"], True
            if last.type == TT.RPAREN:
                return "se esperaba  ::", ["::"], True

    #si / mientras
    if tok_types in ([TT.SI], [TT.MIENTRAS]):
        return "se esperaba  (", ["("], True

    #retorna
    if tok_types == [TT.RETORNA]:
        return "expresión de retorno", [], False

    return None, [], False


class Autocomplete:

    def __init__(self, root, text):
        self.root     = root
        self.text     = text
        self.popup    = None   # listbox con las sugerencias
        self.tooltip  = None   # etiqueta con el tipo del simbolo
        self._symbols = {}     # cache de simbolos del archivo actual

        # conecto los eventos del editor
        self.text.bind("<KeyRelease>", self._on_key_release, add="+")
        self.text.bind("<Tab>",        self._on_tab,         add="+")
        self.text.bind("<Up>",         self._on_up,          add="+")
        self.text.bind("<Down>",       self._on_down,        add="+")
        self.text.bind("<Escape>",     self._on_escape,      add="+")
        self.root.bind("<Button-1>",   self._on_click,       add="+")

    #manejo de eventos teclas

    def _on_key_release(self, event):
        # ignoro las teclas de navegacion del popup
        if event.keysym in ("Tab", "Up", "Down", "Escape", "Return"):
            return
        try:
            self._refresh_symbols()
            word = self._current_word()

            # primero intento sugerencias basadas en la gramatica del lenguaje
            grammar_hint, grammar_suggs, grammar_exact = self._analyze_grammar_state()

            if grammar_suggs:
                if grammar_exact:
                    # tokens exactos como ":" o "=" 
                    self._show_popup_grammar(grammar_suggs, grammar_hint)
                else:
                    # tipos o valores 
                    if word:
                        filtered = [s for s in grammar_suggs if s.startswith(word)]
                        if filtered:
                            self._show_popup_grammar(filtered, grammar_hint)
                        else:
                            self._show_popup_grammar(grammar_suggs, grammar_hint)
                    else:
                        self._show_popup_grammar(grammar_suggs, grammar_hint)
                return

            elif grammar_hint:
                #hay ayuda pero sin sugerencias concretas muestro solo el hint
                self._show_hint_only(grammar_hint)
                if len(word) >= 1:
                    trigger = self._detect_trigger()
                    self._show_popup(word, trigger)
                return

            #si no hay sugerencias gramaticales uso autocompletado por prefijo
            trigger = self._detect_trigger()
            if trigger in ("colon", "double_colon", "equals"):
                self._show_popup(word, trigger)
            elif len(word) >= 1:
                self._show_popup(word, trigger)
            else:
                self._hide_popup()
        except Exception:
            pass  

    def _on_tab(self, event):
        # si el popup esta visible inserto la seleccion con Tab
        if self.popup and self.popup.winfo_exists():
            self._insert_selection()
            return "break"

    def _on_up(self, event):
        #navego hacia arriba en el popup sin mover el cursor del editor
        if self.popup and self.popup.winfo_exists():
            cur = self.popup.curselection()
            if cur:
                idx = max(0, cur[0] - 1)
                self.popup.selection_clear(0, "end")
                self.popup.selection_set(idx)
                self.popup.activate(idx)
                self.popup.see(idx)
                self._update_tooltip()
            return "break"

    def _on_down(self, event):
        if self.popup and self.popup.winfo_exists():
            cur = self.popup.curselection()
            if cur:
                idx = min(self.popup.size() - 1, cur[0] + 1)
                self.popup.selection_clear(0, "end")
                self.popup.selection_set(idx)
                self.popup.activate(idx)
                self.popup.see(idx)
                self._update_tooltip()
            return "break"

    def _on_escape(self, event):
        if self.popup and self.popup.winfo_exists():
            self._hide_popup()
            return "break"

    def _on_click(self, event):
        #cierro el popup si el click fue fuera de el
        if not self.popup or not self.popup.winfo_exists():
            return
        try:
            wx = self.popup.winfo_rootx()
            wy = self.popup.winfo_rooty()
            ww = self.popup.winfo_width()
            wh = self.popup.winfo_height()
            if wx <= event.x_root <= wx + ww and wy <= event.y_root <= wy + wh:
                return  #el click fue dentro del popup entonces no cierro
        except Exception:
            pass
        self._hide_popup()

    #analisis de contexto

    def _refresh_symbols(self):
        # actualizo la lista de simbolos del archivo
        try:
            self._symbols = scan_symbols(self.text.get("1.0", "end"))
        except Exception:
            pass

    def _current_word(self) -> str:
        #extraigo la palabra justo antes del cursor
        try:
            idx        = self.text.index("insert")
            line_start = idx.split(".")[0] + ".0"
            line_text  = self.text.get(line_start, idx)
            m = re.search(r"[@A-Za-z_][A-Za-z0-9_]*$", line_text)
            return m.group(0) if m else ""
        except Exception:
            return ""

    def _detect_trigger(self) -> str:
        """
        Detecta el contexto de la linea actual:
        'colon'         despues de ':'  (tipo de variable)
        'double_colon'  despues de '::' (tipo de retorno)
        'equals'        despues de '='  (valor de variable)
        'start'         inicio de linea
        'general'       cualquier otro caso
        """
        try:
            idx        = self.text.index("insert")
            line_start = idx.split(".")[0] + ".0"
            line       = self.text.get(line_start, idx)

            if re.search(r"::\s*\w*$", line):
                return "double_colon"
            if re.search(r"(?<!:):\s*\w*$", line):
                return "colon"
            if re.search(r"=\s*\w*$", line) and not re.search(r"==\s*\w*$", line):
                return "equals"
            if line.strip() == "" or re.match(r"^\s*[@]?\s*$", line):
                return "start"
            return "general"
        except Exception:
            return "general"

    def _candidates_for(self, trigger: str) -> list:
        #devuelvo los candidatos segun el tipo de contexto
        user_vars = [k for k, v in self._symbols.items() if v["kind"] in ("var", "const")]
        user_all  = list(self._symbols.keys())

        if trigger == "double_colon": return TYPES
        if trigger == "colon":        return TYPES
        if trigger == "equals":       return KEYWORDS_BOOL + user_vars + ["true", "false"]
        if trigger == "start":        return START_WORDS + ANNOTATIONS
        return ALL_KW + user_all

    #el popup de sugerencias

    def _show_popup(self, word: str, trigger: str):
        candidates = self._candidates_for(trigger)

        # filtro por prefijo, pero siempre muestro keywords aunque coincidan exacto
        if word:
            filtered = [c for c in candidates
                        if c.startswith(word) and (c != word or c in ALL_KW)]
        else:
            filtered = candidates

        # elimino duplicados sin perder el orden
        seen, unique = set(), []
        for c in filtered:
            if c not in seen:
                seen.add(c); unique.append(c)

        if not unique:
            self._hide_popup(); return

        self._hide_popup()

        from tkinter import Listbox, Label, END

        # creo el listbox del popup
        self.popup = Listbox(
            self.root,
            bg="#1C2128",
            fg="#E6EDF3",
            selectbackground="#388BFD",
            selectforeground="#FFFFFF",
            font=("Consolas", 10),
            height=min(8, len(unique)),
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightcolor="#388BFD",
            activestyle="none",
            exportselection=False,  
        )

        for item in unique:
            self.popup.insert(END, "  " + item)

        self.popup.selection_set(0)
        self.popup.activate(0)

        # posiciono el popup debajo del cursor
        bbox = self.text.bbox("insert")
        if bbox is None:
            self._hide_popup(); return

        bx, by, _, bh = bbox
        tx = self.text.winfo_x()
        ty = self.text.winfo_y()
        self.popup.place(x=tx + bx, y=ty + by + bh, width=220)

        # tooltip que muestra el tipo del simbolo seleccionado
        self.tooltip = Label(
            self.root,
            bg="#0D419D",
            fg="#E6EDF3",
            font=("Consolas", 9),
            anchor="w",
            padx=6,
            pady=2,
        )
        self.tooltip.place(x=tx + bx + 222, y=ty + by + bh, width=200, height=20)
        self._update_tooltip()

        self.popup.bind("<Return>",          lambda e: self._insert_selection())
        self.popup.bind("<Double-Button-1>", lambda e: self._insert_selection())
        self.popup.bind("<Escape>",          lambda e: self._hide_popup())
        self.popup.bind("<<ListboxSelect>>", lambda e: self._update_tooltip())

    def _update_tooltip(self):
        #actualizo el tooltip con informacion del simbolo seleccionado
        try:
            if not self.tooltip or not self.tooltip.winfo_exists():
                return
            if not self.popup or not self.popup.winfo_exists():
                return
            cur = self.popup.curselection()
            if not cur:
                self.tooltip.config(text=""); return
            raw = self.popup.get(cur[0]).strip()
            sym = self._symbols.get(raw)
            if sym:
                lbl = {"var": "var", "const": "const", "func": "func", "param": "param"}.get(sym["kind"], "")
                self.tooltip.config(text=f"  {lbl}  {sym['type']}")
            elif raw in TYPES:
                self.tooltip.config(text="  tipo primitivo")
            elif raw in KEYWORDS_CTRL:
                self.tooltip.config(text="  palabra reservada")
            elif raw in KEYWORDS_VAULT:
                self.tooltip.config(text="  API bóveda")
            else:
                self.tooltip.config(text="")
        except Exception:
            pass

    #plantillas para insertar estructuras de control completas

    _STRUCTURES = {
        "si":       ("si () {\n    \n}",       -6),
        "sino":     ("sino {\n    \n}",         -2),
        "mientras": ("mientras () {\n    \n}", -6),
        "para":     ("para (i = 0' i < n' i = i + 1') {\n    \n}", -2),
        "func":     ("func nombre()::void {\n    \n}", -17),
    }

    def _insert_selection(self):
        try:
            if not self.popup or not self.popup.winfo_exists():
                return
            cur = self.popup.curselection()
            if not cur:
                return
            selected = self.popup.get(cur[0]).strip()
            word = self._current_word()

            #borro la palabra parcial que ya escribio el usuario
            if word:
                self.text.delete(f"insert-{len(word)}c", "insert")

            if selected in self._STRUCTURES:
                #inserto la estructura completa con indentacion correcta
                template, cursor_offset = self._STRUCTURES[selected]

                idx       = self.text.index("insert")
                line_num  = int(idx.split(".")[0])
                line_text = self.text.get(f"{line_num}.0", f"{line_num}.end")
                indent    = len(line_text) - len(line_text.lstrip())

                # aplico la indentacion a las lineas internas de la plantilla
                lines = template.split("\n")
                indented_lines = []
                for i, ln in enumerate(lines):
                    if i == 0:
                        indented_lines.append(ln)
                    else:
                        indented_lines.append(" " * indent + ln)
                template = "\n".join(indented_lines)

                self.text.insert("insert", template)
                if cursor_offset < 0:
                    self.text.mark_set("insert", f"insert{cursor_offset}c")
            else:
                # insercion normal para variables, funciones, etc.
                self.text.insert("insert", selected)

            self._hide_popup()
            self.text.focus_set()
        except Exception:
            pass

    def _analyze_grammar_state(self):
        # analizo la linea actual hasta el cursor para sugerencias gramaticales
        try:
            idx       = self.text.index("insert")
            line_num  = int(idx.split(".")[0])
            col       = int(idx.split(".")[1])
            line_text = self.text.get(f"{line_num}.0", f"{line_num}.end")
            before_cursor = line_text[:col]
        except Exception:
            return None, [], False

        return _analyze_grammar(before_cursor)

    def _show_popup_grammar(self, suggestions: list, hint: str):
        # popup para sugerencias gramaticales (sin filtrar por prefijo)
        from tkinter import Listbox, Label, END

        if not suggestions:
            self._hide_popup()
            return

        self._hide_popup()

        self.popup = Listbox(
            self.root,
            bg="#1C2128",
            fg="#E6EDF3",
            selectbackground="#388BFD",
            selectforeground="#FFFFFF",
            font=("Consolas", 10),
            height=min(8, len(suggestions)),
            bd=1,
            relief="solid",
            highlightthickness=1,
            highlightcolor="#388BFD",
            activestyle="none",
            exportselection=False,
        )

        for item in suggestions:
            self.popup.insert(END, item)

        self.popup.selection_set(0)
        self.popup.activate(0)

        bbox = self.text.bbox("insert")
        if bbox is None:
            self._hide_popup(); return

        bx, by, _, bh = bbox
        tx = self.text.winfo_x()
        ty = self.text.winfo_y()
        self.popup.place(x=tx + bx, y=ty + by + bh, width=220)

        # tooltip con el hint gramatical
        self.tooltip = Label(
            self.root,
            bg="#0D419D",
            fg="#E6EDF3",
            font=("Consolas", 9),
            anchor="w",
            padx=6,
            pady=2,
            text=f"  ▸ {hint}" if hint else "",
        )
        self.tooltip.place(x=tx + bx + 222, y=ty + by + bh, width=240, height=20)

        self.popup.bind("<Return>",          lambda e: self._insert_grammar_selection())
        self.popup.bind("<Double-Button-1>", lambda e: self._insert_grammar_selection())
        self.popup.bind("<Escape>",          lambda e: self._hide_popup())

    def _insert_grammar_selection(self):
        #inserto la seleccion gramatical (no borro palabra previa)
        try:
            if not self.popup or not self.popup.winfo_exists():
                return
            cur = self.popup.curselection()
            if not cur:
                return
            selected = self.popup.get(cur[0]).strip()
            self.text.insert("insert", selected + " ")
            self._hide_popup()
            self.text.focus_set()
        except Exception:
            pass

    def _show_hint_only(self, hint: str):
        #muestro solo el tooltip sin popup cuando no hay sugerencias especificas
        from tkinter import Label
        try:
            if self.tooltip and self.tooltip.winfo_exists():
                self.tooltip.config(text=f"  ▸ {hint}")
                return
            bbox = self.text.bbox("insert")
            if bbox is None:
                return
            bx, by, _, bh = bbox
            tx = self.text.winfo_x()
            ty = self.text.winfo_y()
            if self.popup and self.popup.winfo_exists():
                return
            self.tooltip = Label(
                self.root,
                bg="#0D419D",
                fg="#E6EDF3",
                font=("Consolas", 9),
                anchor="w",
                padx=6,
                pady=2,
                text=f"  ▸ {hint}",
            )
            self.tooltip.place(x=tx + bx, y=ty + by + bh, width=300, height=20)
        except Exception:
            pass

    def _hide_popup(self):
        #cierro el popup y el tooltip
        for w in (self.popup, self.tooltip):
            if w:
                try:
                    w.destroy()
                except Exception:
                    pass
        self.popup   = None
        self.tooltip = None


def setup(root, text):
    #punto de entrada para inicializar el autocompletado
    Autocomplete(root, text)
