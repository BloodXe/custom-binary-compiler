# ============================================================
# TEA Encrypt — TEA-ISA 23-bit
# Entrada : r4 = dirección base (en palabras) del bloque a cifrar
#           mem[r4]   = v0  (palabra baja)
#           mem[r4+1] = v1  (palabra alta)
# Llave   : cargada en la bóveda (ki=0..3)
# Salida  : mem[r4] y mem[r4+1] cifrados in-place
# Convención: r2=SP, r1=RA, r4-r7=args, r8-r11=temps
# ============================================================

tea_cifrar:

    # --- Prólogo: reservar frame local ---
    # Necesitamos en el stack:
    #   [SP+0]  = v0
    #   [SP+4]  = v1
    #   [SP+8]  = suma
    #   [SP+12] = i (contador del loop)
    #   [SP+16] = addr_base (guardar r4 para usarlo al final)
    addi r2, r2, -20        # reservar 5 palabras

    # Guardar dirección base (r4) para restaurar al final
    store r4, 16(r2)        # addr_base = r4

    # --- Cargar v0 = mem[addr_base] ---
    # El procesador recibe dirección en bytes → addr_base * 4
    addi r9, r0, 2
    sll  r8, r4, r9         # r8 = addr_base * 4 (dirección en bytes)
    load r8, 0(r8)          # r8 = mem[addr_base]
    store r8, 0(r2)         # v0 = r8

    # --- Cargar v1 = mem[addr_base + 1] ---
    addi r9, r4, 1          # r9 = addr_base + 1
    addi r10, r0, 2
    sll  r9, r9, r10        # r9 = (addr_base+1) * 4
    load r9, 0(r9)          # r9 = mem[addr_base+1]
    store r9, 4(r2)         # v1 = r9

    # --- suma = 0 ---
    addi r8, r0, 0
    store r8, 8(r2)         # suma = 0

    # --- i = 0 ---
    addi r8, r0, 0
    store r8, 12(r2)        # i = 0

    # ============================================================
    # Autenticación y carga de llaves en la bóveda
    # TOKEN  = 0xDDAABBCF
    # UID    = 0
    # PWD    = 1234
    # Llaves = 0x01234567, 0x89ABCDEF, 0xFEDCBA98, 0x76543210
    # ============================================================

    # authorize(uid=0, token=0xDDAABBCF)
    addi r8, r0, 0          # uid = 0
    lli  r9, 0xCF, 0        # token byte 0
    lli  r9, 0xBB, 1        # token byte 1
    lli  r9, 0xAA, 2        # token byte 2
    lli  r9, 0xDD, 3        # token byte 3  → r9 = 0xDDAABBCF
    authorize r8, r9        # authorize(uid, token)

    # setpwd(uid=0, pwd=1234)
    addi r8, r0, 0          # uid = 0
    lli  r9, 0xD2, 0        # 1234 = 0x04D2, byte 0 = 0xD2
    lli  r9, 0x04, 1        # byte 1 = 0x04  → r9 = 1234
    setpwd r8, r9           # setpwd(uid, pwd)

    # login(uid=0, pwd=1234)
    addi r8, r0, 0          # uid = 0
    lli  r9, 0xD2, 0        # pwd byte 0
    lli  r9, 0x04, 1        # pwd byte 1  → r9 = 1234
    login r8, r9            # login(uid, pwd)

    # --- Cargar llave k0 = 0x01234567 en ki=0 ---
    lli  r8, 0x67, 0
    lli  r8, 0x45, 1
    lli  r8, 0x23, 2
    lli  r8, 0x01, 3        # r8 = 0x01234567
    vkload r8, 0            # K[0] = r8

    # --- Cargar llave k1 = 0x89ABCDEF en ki=1 ---
    lli  r8, 0xEF, 0
    lli  r8, 0xCD, 1
    lli  r8, 0xAB, 2
    lli  r8, 0x89, 3        # r8 = 0x89ABCDEF
    vkload r8, 1            # K[1] = r8

    # --- Cargar llave k2 = 0xFEDCBA98 en ki=2 ---
    lli  r8, 0x98, 0
    lli  r8, 0xBA, 1
    lli  r8, 0xDC, 2
    lli  r8, 0xFE, 3        # r8 = 0xFEDCBA98
    vkload r8, 2            # K[2] = r8

    # --- Cargar llave k3 = 0x76543210 en ki=3 ---
    lli  r8, 0x10, 0
    lli  r8, 0x32, 1
    lli  r8, 0x54, 2
    lli  r8, 0x76, 3        # r8 = 0x76543210
    vkload r8, 3            # K[3] = r8

    # ============================================================
    # Loop principal TEA: 32 rondas
    # suma += DELTA  (DELTA = 0x9E3779B9)
    # v0  += tea_add1(v1,0) ^ (v1+suma) ^ tea_add2(v1,1)
    # v1  += tea_add1(v0,2) ^ (v0+suma) ^ tea_add2(v0,3)
    # ============================================================

tea_cifrar_loop:

    # --- Chequear condición: i < 32 ---
    load r8, 12(r2)         # r8 = i
    addi r9, r0, 32
    bge  r8, r9, tea_cifrar_fin   # si i >= 32: salir

    # --- suma += DELTA (0x9E3779B9) ---
    load r8, 8(r2)          # r8 = suma
    lli  r9, 0xB9, 0        # DELTA byte 0
    lli  r9, 0x79, 1        # DELTA byte 1
    lli  r9, 0x37, 2        # DELTA byte 2
    lli  r9, 0x9E, 3        # DELTA byte 3  → r9 = 0x9E3779B9
    add  r8, r8, r9         # suma += DELTA
    store r8, 8(r2)         # guardar suma

    # --- Calcular parte de v0 ---
    # t1 = tea_add1(v1, ki=0)  →  (v1 << 4) + K[0]
    load  r9, 4(r2)         # r9 = v1
    tea_add1 r8, r9, 0      # r8 = (v1<<4) + K[0]

    # t2 = tea_add2(v1, ki=1)  →  (v1 >> 5) + K[1]
    load  r9, 4(r2)         # r9 = v1
    tea_add2 r10, r9, 1     # r10 = (v1>>5) + K[1]

    # t3 = v1 + suma
    load  r9, 4(r2)         # r9 = v1
    load  r11, 8(r2)        # r11 = suma
    add   r9, r9, r11       # r9 = v1 + suma

    # v0 += t1 ^ t3 ^ t2
    xor   r8, r8, r9        # r8 = t1 ^ t3
    xor   r8, r8, r10       # r8 = t1 ^ t3 ^ t2
    load  r9, 0(r2)         # r9 = v0
    add   r9, r9, r8        # v0 += (t1^t3^t2)
    store r9, 0(r2)         # guardar v0

    # --- Calcular parte de v1 ---
    # t4 = tea_add1(v0, ki=2)  →  (v0 << 4) + K[2]
    load  r9, 0(r2)         # r9 = v0 (ya actualizado)
    tea_add1 r8, r9, 2      # r8 = (v0<<4) + K[2]

    # t5 = tea_add2(v0, ki=3)  →  (v0 >> 5) + K[3]
    load  r9, 0(r2)         # r9 = v0
    tea_add2 r10, r9, 3     # r10 = (v0>>5) + K[3]

    # t6 = v0 + suma
    load  r9, 0(r2)         # r9 = v0
    load  r11, 8(r2)        # r11 = suma
    add   r9, r9, r11       # r9 = v0 + suma

    # v1 += t4 ^ t6 ^ t5
    xor   r8, r8, r9        # r8 = t4 ^ t6
    xor   r8, r8, r10       # r8 = t4 ^ t6 ^ t5
    load  r9, 4(r2)         # r9 = v1
    add   r9, r9, r8        # v1 += (t4^t6^t5)
    store r9, 4(r2)         # guardar v1

    # --- i++ ---
    load  r8, 12(r2)        # r8 = i
    addi  r8, r8, 1         # i++
    store r8, 12(r2)        # guardar i

    jal r0, tea_cifrar_loop # siguiente ronda

tea_cifrar_fin:

    # --- Escribir resultados en memoria ---
    # mem[addr_base]   = v0
    load r8, 0(r2)          # r8 = v0
    load r9, 16(r2)         # r9 = addr_base
    addi r10, r0, 2
    sll  r10, r9, r10       # r10 = addr_base * 4
    store r8, 0(r10)        # mem[addr_base] = v0

    # mem[addr_base+1] = v1
    load r8, 4(r2)          # r8 = v1
    addi r9, r9, 1          # r9 = addr_base + 1
    addi r10, r0, 2
    sll  r10, r9, r10       # r10 = (addr_base+1)*4
    store r8, 0(r10)        # mem[addr_base+1] = v1

    # --- Epílogo: restaurar SP y retornar ---
    addi r2, r2, 20
    jr   r1