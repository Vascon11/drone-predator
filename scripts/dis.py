import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
path, pat = sys.argv[1], sys.argv[2]
maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 400
f = open(path, 'rb'); elf = ELFFile(f)
syms = {}
for sec in ('.dynsym', '.symtab'):
    s = elf.get_section_by_name(sec)
    if s:
        for sym in s.iter_symbols():
            if sym['st_value'] and sym['st_info']['type'] == 'STT_FUNC':
                syms[sym.name] = (sym['st_value'], sym['st_size'])
addr2name = {v[0]: k for k, v in syms.items()}
# PLT names
relplt = elf.get_section_by_name('.rela.plt'); dyn = elf.get_section_by_name('.dynsym')
plt = elf.get_section_by_name('.plt')
pltmap = {}
if relplt and plt:
    for i, r in enumerate(relplt.iter_relocations()):
        pltmap[plt['sh_addr'] + 32 + i * 16] = dyn.get_symbol(r['r_info_sym']).name
text = elf.get_section_by_name('.text')
data = text.data(); base = text['sh_addr']
md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
for name, (a, sz) in sorted(syms.items(), key=lambda x: x[1][0]):
    if pat not in name: continue
    print(f"\n### {name} @ {a:#x} size {sz}")
    code = data[a - base: a - base + min(sz, maxn * 4)]
    for ins in md.disasm(code, a):
        extra = ''
        if ins.mnemonic in ('bl', 'b') and ins.op_str.startswith('#'):
            t = int(ins.op_str[1:], 16); extra = '  ; ' + (pltmap.get(t) or addr2name.get(t, ''))
        print(f"{ins.address:#x}: {ins.mnemonic} {ins.op_str}{extra}")
