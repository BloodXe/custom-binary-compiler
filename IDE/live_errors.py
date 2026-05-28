import threading

# ─────────────────────────────────────────────────────────────
#  Detección de errores en vivo
#
#  Estrategia:
#    - Debounce de 600 ms tras la última tecla.
#    - Análisis en hilo de fondo (no bloquea la UI).
#    - Corre Lexer -> Parser -> Semántico en cascada:
#        · Si hay error léxico  -> para ahí y marca esa línea.
#        · Si hay error sintác. -> para ahí y marca esa línea.
#        · Si hay errores semán.-> marca todas las líneas afectadas.
#    - Tooltip con el mensaje aparece al pasar el mouse por
#      una línea marcada.
# ─────────────────────────────────────────────────────────────

DEBOUNCE_MS = 600


class LiveErrorDetector:

    def __init__(self, root, text):
        self.root  = root  # referencia para agendar tareas en el hilo principal
        self.text  = text  # widget Text donde se muestra el código fuente
        self._timer = None # referencia al timer de debounce (None si no hay timer activo)
        self._tooltip = None # referencia al tooltip actual (None si no hay tooltip visible)
        # { "line.col_start" : "mensaje" }  para tooltip
        self._error_msgs = {}

        # add="+" para no pisar el binding de autocomplete.py que usa el mismo evento
        self.text.bind("<KeyRelease>", self._on_key,              add="+") # Evento de tecla: reinicia el debounce (salvo para teclas de navegación o modificadoras)
        self.text.bind("<Motion>",     self._on_mouse_move,       add="+") # Evento de movimiento del mouse: mostrar tooltip si hay error en esa línea
        self.text.bind("<Leave>",      lambda e: self._hide_tooltip(), add="+") # Evento de salida del widget: ocultar tooltip

        # Tag: subrayado rojo para errores
        self.text.tag_configure(
            "live_error",
            underline=True,
            foreground="#FF6B6B",
        )

    # Evento de tecla: reinicia el debounce (salvo para teclas de navegación o modificadoras) 

    def _on_key(self, event):
        if event.keysym in (
            "Up", "Down", "Left", "Right",
            "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
            "Alt_L", "Alt_R", "Caps_Lock", "Escape",
            "F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
        ):
            return
        self._schedule()

    # Agendar el análisis para dentro de DEBOUNCE_MS ms, cancelando cualquier análisis previamente agendado.
    def _schedule(self):
        if self._timer is not None:
            self.root.after_cancel(self._timer)
        self._timer = self.root.after(DEBOUNCE_MS, self._run_in_thread)

    # Analizar el código fuente en un hilo de fondo para no bloquear la UI. Al terminar, aplicar las marcas de error en el hilo principal.

    def _run_in_thread(self):

        source = self.text.get("1.0", "end") # Obtener el código fuente actual del widget Text
        # Iniciar el análisis en un hilo de fondo para no bloquear la UI. El análisis correrá las fases de compilación en cascada y recolectará los errores encontrados. 
        # Al finalizar, programará la aplicación de las marcas de error en el hilo principal.
        thread = threading.Thread( 
            target=self._analyze, args=(source,), daemon=True
        )
        thread.start()

    # Función de análisis que corre en el hilo de fondo. Corre las fases de compilación en cascada y recolecta los errores encontrados. 
    # Al finalizar, programa la aplicación de las marcas de error en el hilo principal.
    def _analyze(self, source):
        """
        Retorna lista de (line, col, msg) normalizados.
        Corre fases en cascada; se detiene en la primera que falla.
        """
        errors = []
        try:
            from compiler.lexer   import Lexer
            from compiler.parser  import Parser, ParseError
            from compiler.semantic import SemanticAnalyzer

            # Fase 1: léxico 
            lexer  = Lexer(source)
            tokens = lexer.tokenize()

            if lexer.errors:
                errors = [(ln, col, msg) for ln, col, msg in lexer.errors]
                self.root.after(0, lambda e=errors: self._apply_marks(e))
                return

            # Fase 2: sintáctico 
            try:
                ast = Parser(tokens).parse()
            except ParseError as e:
                # ParseError lleva la línea en el mensaje: "... (línea N, col M)"
                import re
                m = re.search(r'l[íi]nea\s*(\d+)', str(e), re.IGNORECASE)
                m2 = re.search(r'col\s*(\d+)', str(e), re.IGNORECASE)
                ln  = int(m.group(1))  if m  else 1
                col = int(m2.group(1)) if m2 else 1
                errors = [(ln, col, str(e))]
                self.root.after(0, lambda e=errors: self._apply_marks(e))
                return

            # Fase 3: semántico 
            sem = SemanticAnalyzer()
            sem.visit(ast)

            if sem.errors:
                import re
                for msg in sem.errors:
                    m = re.search(r'[Ll]inea\s*(\d+)', msg)
                    ln = int(m.group(1)) if m else 1
                    errors.append((ln, 1, msg))

        except Exception:
            # Cualquier fallo inesperado -> no marcamos nada
            pass

        self.root.after(0, lambda e=errors: self._apply_marks(e))

    # Marca las líneas con error dentro del widget Text usando el tag "live_error". 
    # Guarda los mensajes de error para mostrar en el tooltip al pasar el mouse.

    def _apply_marks(self, errors):
        self.text.tag_remove("live_error", "1.0", "end") # Limpiar marcas anteriores
        self._error_msgs.clear() # Limpiar mensajes anteriores

        # Marcar cada línea con error y guardar su mensaje para el tooltip. Se asume que 'errors' es una lista de tuplas (line, col, msg).
        for line, col, msg in errors:
            col0  = max(col - 1, 0) # Convertir a índice 0-based para el widget Text
            start = f"{line}.{col0}" # Índice de inicio de la marca (línea.col)
            end   = self._word_end(line, col0) # Índice de fin de la marca (al final de la palabra donde ocurrió el error)
            self.text.tag_add("live_error", start, end) # Marcar el rango del error con el tag "live_error"
            # Guardar mensaje indexado por línea para el tooltip
            self._error_msgs[line] = msg

    # Función auxiliar para encontrar el final de la palabra donde ocurrió el error, para marcar toda la palabra en lugar de sólo el punto del error. 
    # Si no se puede determinar, marca al menos el siguiente carácter para asegurar que algo quede marcado.
    def _word_end(self, line, col):
        try:
            line_text = self.text.get(f"{line}.0", f"{line}.end") # Obtener el texto completo de la línea
            i = col

            # Avanzar hasta el final de la palabra (o hasta el final de la línea) para marcar toda la palabra del error, 
            # o al menos un carácter si no se puede determinar.
            while i < len(line_text) and not line_text[i].isspace():
                i += 1
            return f"{line}.{max(i, col + 1)}"
        except Exception:
            return f"{line}.{col + 1}"

    # Evento de movimiento del mouse: mostrar tooltip si hay error en esa línea. Se asume que el mouse se mueve dentro del widget Text.
    def _on_mouse_move(self, event):
        try:
            idx   = self.text.index(f"@{event.x},{event.y}") # Obtener el índice de texto bajo el mouse (en formato "line.col")
            line  = int(idx.split(".")[0]) # Extraer la línea del índice

            # Si hay un mensaje de error para esa línea, mostrar el tooltip con el mensaje. Si no, ocultar cualquier tooltip visible. 
            # Se asume que los mensajes de error están indexados por número de línea en self._error_msgs.
            if line in self._error_msgs:
                self._show_tooltip(event.x_root, event.y_root,
                                   self._error_msgs[line])
            else:
                self._hide_tooltip()
        except Exception:
            self._hide_tooltip()

    # Funciones para mostrar y ocultar el tooltip. El tooltip es una ventana Toplevel que se posiciona cerca del mouse y muestra el mensaje de error correspondiente. 
    # Se asegura de destruir cualquier tooltip anterior antes de mostrar uno nuevo, y de manejar excepciones para evitar que errores en la gestión del tooltip afecten
    # la estabilidad del IDE.
    def _show_tooltip(self, x, y, msg):
        self._hide_tooltip()
        try:
            import tkinter as tk
            tw = tk.Toplevel(self.root)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x + 12}+{y + 16}")
            lbl = tk.Label(
                tw,
                text=msg,
                justify="left",
                background="#2D1B1B",
                foreground="#FF9090",
                relief="solid",
                borderwidth=1,
                font=("Consolas", 9),
                wraplength=420,
                padx=6,
                pady=4,
            )
            lbl.pack()
            self._tooltip = tw
        except Exception:
            pass
    
    # Función para ocultar el tooltip, destruyendo la ventana Toplevel si existe. Se maneja cualquier excepción para evitar 
    # que errores en esta función afecten la estabilidad del IDE.
    def _hide_tooltip(self):
        if self._tooltip:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    # Función pública para limpiar todas las marcas de error y mensajes asociados, por ejemplo al abrir un nuevo archivo o al guardar.
    def clear(self):
        self.text.tag_remove("live_error", "1.0", "end")
        self._error_msgs.clear()
        self._hide_tooltip()
        if self._timer is not None:
            self.root.after_cancel(self._timer)
            self._timer = None

# Función de setup para integrar el LiveErrorDetector en el IDE. Retorna una instancia de LiveErrorDetector que se 
# puede usar para limpiar errores al abrir/guardar archivos, etc.
def setup(root, text):
    return LiveErrorDetector(root, text)