# idd01=10
# idd02=65
# idd2n1=3
# idd2n2=26.5
# idd3n1=3
# idd3n2=32
# idd4r=8.5
# idd4r2=420
# idd4w1=3
# idd4w2=435
# vdd1=1.8
# vdd2=1.1

tRAS = 68
tRP = 29
rho = 42.5 / 41.07
tRCD = 29
tCCD = 8
tRTP = 12
tWL = 14
tWR = 30
BL = 8

def energy():
    vdd = [1.8, 1.1]
    idd0 = [10, 65]
    idd2n = [3, 26.5]
    idd3n = [3, 32]
    idd4r = [8.5, 420]
    idd4w = [3, 435]
    tck = 0.625

    bg_pre_cycles = (
        (tRCD + 64 * tCCD + tRTP) * 2 + tRCD + 64 * tCCD + tWL + tWR + BL + 2
    )
    bg_act_cycles = (   
        (tRCD + 64 * tCCD + 2 * tRTP) * 2 + tRCD + 64 * tCCD + tWL + tWR + BL + 2 + tRP
    )
    total_energy = []
    for i in range(2):
        e_bg_pre = vdd[i] * idd2n[i] * bg_pre_cycles
        e_bg_act = idd3n[i] * vdd[i] * bg_act_cycles
        e_read = (vdd[i] * (idd4r[i] - idd3n[i])) * 8 * tck * 64 * 2
        e_write = (vdd[i] * (idd4w[i] - idd3n[i])) * 8 * tck * 64
        e_act_pre = idd0[i] * (tRAS + tRP) - idd2n[i] * tRP - idd3n[i] * tRAS * 3
        e_row_clone = e_act_pre * rho * (2 * tRAS + tRP)
        total_energy.append((
            e_bg_pre + e_bg_act + e_read + e_write + e_act_pre + e_row_clone
        )) 
    print("{},{}".format(total_energy[0],total_energy[1]))

energy()