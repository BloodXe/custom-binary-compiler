DELTA = 0x9E3779B9
MASK  = 0xFFFFFFFF

def tea_encrypt(v0, v1, k):
    sum_ = 0
    for _ in range(32):
        sum_ = (sum_ + DELTA) & MASK

        v0 = (v0 + (
            ((v1 << 4) + k[0]) ^
            (v1 + sum_) ^
            ((v1 >> 5) + k[1])
        )) & MASK

        v1 = (v1 + (
            ((v0 << 4) + k[2]) ^
            (v0 + sum_) ^
            ((v0 >> 5) + k[3])
        )) & MASK

    return v0, v1


# datos de entrada (hexadecimal)
data_hex = [
    "616c6f48","74206120","736f646f","68430a20",
    "61206f61","646f7420","480a736f","20616c6f",
    "6f742061","0a736f64","6f616843","74206120",
    "736f646f","6c65480a","00006f6c"
]

# convertir a enteros
data = [int(x, 16) for x in data_hex]

# 🔑 llave
key = [
    0x01234567,
    0x89ABCDEF,
    0xFEDCBA98,
    0x76543210
]

print("=== CIFRADO ===")

for i in range(0, len(data), 2):

    v0 = data[i]
    v1 = data[i+1] if i+1 < len(data) else 0  # padding si falta

    c0, c1 = tea_encrypt(v0, v1, key)

    print(f"Bloque {i//2}:")
    print(f"  IN : {v0:08X} {v1:08X}")
    print(f"  OUT: {c0:08X} {c1:08X}")