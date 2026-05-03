# Fase 5: Cálculo de Saltos y Resolución de Referencias

class Resolver:
    def __init__(self, asm):
        self.asm = asm.splitlines() # El string se separa a lista de las lineas
        self.labels = {}
        self.instruction_size = 4 # Tamaño de las instrucciones

    def labels_direction(self):
        # Recorre el ASM y guarda la dirección de cada etiqueta
        address = 0

        # Se cicla para cada linea del codigo de asembly
        for i in self.asm:
            i = i.strip()   # .strip elimina espacios antes o despues del string

            if i == "":     # Si está vacío solo sigue
                continue

            if i.endswith(":"):  # Si termina con : significa que es un label
                label = i[:-1]    # Quita el : del string y ese es el nombre del label
                self.labels[label] = address     # Guarda la dirección del label, con su nombre
            else:
                address += self.instruction_size     # Si no es label solo sigue, sumando 4 cada vez que lee una linea

    # Segunda pasada por las instrucciones  
    def labels_rewrite(self):
        new_code = []
        actual_pc = 0

        for i in self.asm:
            i = i.strip()

            if i == "":
                continue

            if i.endswith(":"):
                continue

            for label, address in self.labels.items():  # Se cicla por label y su dirección
                if label in i:        # Si se reconoce el label en i (actual linea)
                    offset = (address - actual_pc) // self.instruction_size  # Calcula el offset dividiendo la diferencia de direcciones entre el tamaño de la instrucción
                    i = i.replace(label, str(offset))    # Intercambia el i, y el label por su offset
            
            new_code.append(i)     # mete a la lista nueva la linea leída ya sea con el cambio o no
            actual_pc += self.instruction_size   # Suma el tamaño de la instrucción para la siguiente iteración
            
        return new_code
    
    def resolve(self):
        # Ejecuta las dos pasadas 
        self.labels_direction()
        return "\n".join(self.labels_rewrite())
