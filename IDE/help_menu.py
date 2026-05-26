from tkinter import Menu
from tkinter.messagebox import showinfo


class Help:
    def about(self):
        showinfo(title="About", message="Simple text editor made with Python and Tkinter")


def main(root, text, menubar):
    help_obj = Help()

    helpMenu = Menu(menubar, tearoff=0,
        bg="#161B22",
        fg="white",
        activebackground="#000000",
        activeforeground="white"
    )
    helpMenu.add_command(label="About", command=help_obj.about)
    menubar.add_cascade(label="Help", menu=helpMenu)

    root.config(menu=menubar)


if __name__ == "__main__":
    print("Please run 'main.py'")
