# ============================================================
# TEA Decrypt — TEA-ISA 23-bit
# Entrada : r4 = dirección base (en palabras) del bloque a descifrar
# Llave   : misma que en cifrado, ya en la bóveda
# Salida  : mem[r4] y mem[r4+1] descifrados in-place
# NOTA    : asume que la bóveda ya está autenticada y las llaves
#           cargadas (se llama después de tea_cifrar en la misma sesión)
#           Si no, repetir la sección de auth y vkload de tea_cifrar.
# ============================================================

tea_descifrar:

    # --- Prólogo: reservar frame ---
    # [SP+0]  = v0
    # [SP+4]  = v1
    # [SP+8]  = suma  (empieza en DELTA*32 = 0x9E3779B9 * 32)
    # [SP+12] = i
    # [SP+16] = addr_base
    addi r2, r2, -20

    # Guardar addr_base
    store r4, 16(r2)

    # --- Cargar v0 y v1 desde memoria ---
    addi r9, r0, 2
    sll  r8, r4, r9         # r8 = addr_base * 4
    load r8, 0(r8)
    store r8, 0(r2)         # v0 = mem[addr_base]

    addi r9, r4, 1
    addi r10, r0, 2
    sll  r9, r9, r10        # r9 = (addr_base+1)*4
    load r9, 0(r9)
    store r9, 4(r2)         # v1 = mem[addr_base+1]

    # --- suma = DELTA * 32 = 0x9E3779B9 * 32 ---
    # 0x9E3779B9 * 32 = 0xC6EF3720  (resultado truncado a 32 bits)
    lli  r8, 0x20, 0
    lli  r8, 0x37, 1
    lli  r8, 0xEF, 2
    lli  r8, 0xC6, 3        # r8 = 0xC6EF3720
    store r8, 8(r2)         # suma = 0xC6EF3720

    # --- i = 0 ---
    addi r8, r0, 0
    store r8, 12(r2)

    # ============================================================
    # Loop principal TEA decrypt: 32 rondas
    # v1  -= tea_add1(v0,2) ^ (v0+suma) ^ tea_add2(v0,3)
    # v0  -= tea_add1(v1,0) ^ (v1+suma) ^ tea_add2(v1,1)
    # suma -= DELTA
    # ============================================================

tea_descifrar_loop:

    # --- Chequear condición: i < 32 ---
    load r8, 12(r2)
    addi r9, r0, 32
    bge  r8, r9, tea_descifrar_fin

    # --- Calcular parte de v1 (se actualiza primero en decrypt) ---
    # t4 = tea_add1(v0, ki=2)
    load  r9, 0(r2)         # r9 = v0
    tea_add1 r8, r9, 2      # r8 = (v0<<4) + K[2]

    # t5 = tea_add2(v0, ki=3)
    load  r9, 0(r2)         # r9 = v0
    tea_add2 r10, r9, 3     # r10 = (v0>>5) + K[3]

    # t6 = v0 + suma
    load  r9, 0(r2)         # r9 = v0
    load  r11, 8(r2)        # r11 = suma
    add   r9, r9, r11       # r9 = v0 + suma

    # v1 -= t4 ^ t6 ^ t5
    xor   r8, r8, r9        # r8 = t4 ^ t6
    xor   r8, r8, r10       # r8 = t4 ^ t6 ^ t5
    load  r9, 4(r2)         # r9 = v1
    sub   r9, r9, r8        # v1 -= (t4^t6^t5)
    store r9, 4(r2)

    # --- Calcular parte de v0 ---
    # t1 = tea_add1(v1, ki=0)
    load  r9, 4(r2)         # r9 = v1 (ya actualizado)
    tea_add1 r8, r9, 0      # r8 = (v1<<4) + K[0]

    # t2 = tea_add2(v1, ki=1)
    load  r9, 4(r2)         # r9 = v1
    tea_add2 r10, r9, 1     # r10 = (v1>>5) + K[1]

    # t3 = v1 + suma
    load  r9, 4(r2)         # r9 = v1
    load  r11, 8(r2)        # r11 = suma
    add   r9, r9, r11       # r9 = v1 + suma

    # v0 -= t1 ^ t3 ^ t2
    xor   r8, r8, r9        # r8 = t1 ^ t3
    xor   r8, r8, r10       # r8 = t1 ^ t3 ^ t2
    load  r9, 0(r2)         # r9 = v0
    sub   r9, r9, r8        # v0 -= (t1^t3^t2)
    store r9, 0(r2)

    # --- suma -= DELTA ---
    load r8, 8(r2)          # r8 = suma
    lli  r9, 0xB9, 0
    lli  r9, 0x79, 1
    lli  r9, 0x37, 2
    lli  r9, 0x9E, 3        # r9 = DELTA
    sub  r8, r8, r9         # suma -= DELTA
    store r8, 8(r2)

    # --- i++ ---
    load  r8, 12(r2)
    addi  r8, r8, 1
    store r8, 12(r2)

    jal r0, tea_descifrar_loop

tea_descifrar_fin:

    # --- Escribir resultados ---
    load r8, 0(r2)          # v0
    load r9, 16(r2)         # addr_base
    addi r10, r0, 2
    sll  r10, r9, r10       # addr_base * 4
    store r8, 0(r10)

    load r8, 4(r2)          # v1
    addi r9, r9, 1
    addi r10, r0, 2
    sll  r10, r9, r10       # (addr_base+1)*4
    store r8, 0(r10)

    addi r2, r2, 20
    jr   r1


# ============================================================
# Main: cifra y descifra 13 bloques de 64 bits
# Dirección base en palabras: 0x1000
# Bloques: mem[0x1000..0x101A] (13 bloques × 2 palabras)
# ============================================================

main:

    # --- Inicializar SP ---
    lli r2, 0x00, 0
    lli r2, 0xE0, 1         # SP = 0xE000

    # --- Autenticación y carga de llaves (una sola vez) ---
    addi r8, r0, 0          # uid = 0
    lli  r9, 0xCF, 0
    lli  r9, 0xBB, 1
    lli  r9, 0xAA, 2
    lli  r9, 0xDD, 3        # token = 0xDDAABBCF
    authorize r8, r9

    addi r8, r0, 0
    lli  r9, 0xD2, 0
    lli  r9, 0x04, 1        # pwd = 1234
    setpwd r8, r9

    addi r8, r0, 0
    lli  r9, 0xD2, 0
    lli  r9, 0x04, 1
    login r8, r9

    lli  r8, 0x67, 0
    lli  r8, 0x45, 1
    lli  r8, 0x23, 2
    lli  r8, 0x01, 3
    vkload r8, 0

    lli  r8, 0xEF, 0
    lli  r8, 0xCD, 1
    lli  r8, 0xAB, 2
    lli  r8, 0x89, 3
    vkload r8, 1

    lli  r8, 0x98, 0
    lli  r8, 0xBA, 1
    lli  r8, 0xDC, 2
    lli  r8, 0xFE, 3
    vkload r8, 2

    lli  r8, 0x10, 0
    lli  r8, 0x32, 1
    lli  r8, 0x54, 2
    lli  r8, 0x76, 3
    vkload r8, 3

    # --- Reservar frame de main ---
    # [SP+0] = addr (dirección actual del bloque)
    # [SP+4] = final (dirección límite)
    addi r2, r2, -8

    # addr = 0x1000
    lli  r8, 0x00, 0
    lli  r8, 0x10, 1        # r8 = 0x1000
    store r8, 0(r2)

    # final = 0x1000 + 13*2 = 0x101A
    lli  r8, 0x1A, 0
    lli  r8, 0x10, 1        # r8 = 0x101A
    store r8, 4(r2)

    # ============================================================
    # Loop de cifrado
    # ============================================================

cifrado_loop:

    load r8, 0(r2)          # r8 = addr
    load r9, 4(r2)          # r9 = final
    bge  r8, r9, cifrado_fin

    # Llamar tea_cifrar(addr)
    load r4, 0(r2)          # r4 = addr (argumento)
    addi r2, r2, -4
    store r1, 0(r2)         # PUSH ra
    jal  r1, tea_cifrar
    load r1, 0(r2)          # POP ra
    addi r2, r2, 4

    # addr += 2
    load  r8, 0(r2)
    addi  r8, r8, 2
    store r8, 0(r2)

    jal r0, cifrado_loop

cifrado_fin:

    # ============================================================
    # Loop de descifrado (recorre los mismos bloques)
    # ============================================================

    # Reiniciar addr = 0x1000
    lli  r8, 0x00, 0
    lli  r8, 0x10, 1
    store r8, 0(r2)

descifrado_loop:

    load r8, 0(r2)
    load r9, 4(r2)
    bge  r8, r9, descifrado_fin

    load r4, 0(r2)
    addi r2, r2, -4
    store r1, 0(r2)
    jal  r1, tea_descifrar
    load r1, 0(r2)
    addi r2, r2, 4

    load  r8, 0(r2)
    addi  r8, r8, 2
    store r8, 0(r2)

    jal r0, descifrado_loop

descifrado_fin:

    # --- Logout y halt ---
    logout
    addi r2, r2, 8          # liberar frame de main
    halt