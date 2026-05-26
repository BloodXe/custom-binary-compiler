import os
import sys

#Esto para que el main pueda ejecutarse directamente desde el IDE de Visual sin importar todo el tema de los imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tkinter import *
from tkinter.scrolledtext import ScrolledText

import IDE.file_menu as file_menu
import IDE.edit_menu as edit_menu
import IDE.help_menu as help_menu
import IDE.compiler_menu as compiler_menu

root = Tk()
root.title("TEA-ISA IDE - Untitled")
root.geometry("600x500+300+200")
root.minsize(width=400, height=400)
root.configure(bg="#0D1117")


paned = PanedWindow(
    root,
    orient=VERTICAL,
    sashwidth=6,
    bg="#30363D",
    bd=0
)

paned.pack(fill=BOTH, expand=True)


text = ScrolledText(
    paned,
    state='normal',
    bg="#0D1117",        
    fg="#E6EDF3",      
    insertbackground="white", 
    selectbackground="#264F78",
    wrap='word',
    undo=True,
    font=("Consolas", 12),
    padx=10,
    pady=10
)
text.focus_set()

console = ScrolledText(
    paned,
    height=10,
    bg="#161B22",
    fg="#E6EDF3",
    insertbackground="white",
    font=("Consolas", 10),
    padx=10,
    pady=8
)

console.insert("1.0", "TEA-ISA IDE Console\n")


paned.add(text, minsize=250)
paned.add(console, minsize=100)


menubar = Menu(root)

file_menu.main(root, text, menubar)
edit_menu.main(root, text, menubar)
help_menu.main(root, text, menubar)
compiler_menu.main(root, text, console, menubar)

root.mainloop()
