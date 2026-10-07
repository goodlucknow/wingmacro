# WING docs vs console tree

Console: WING Rack fw 3.1.1, walked 2026-10-07 with `tools/walk_tree.py` (one instance of each numbered node, numbers → `N`;
raw tree in `wing-tree-3.1.1.jsonl`). Doc paths: extracted from the Remote Protocols PDF v3.1 (`wing-doc-paths-3.1.json`).

**Findings**
- 1437 of 1504 doc paths exist on the console. The 67 doc-only ones are mostly PDF-extraction noise (page numbers glued on:
  `thr26`, `lg24`; truncations: `outpu`, `errormessag`, `$spill1/i`; typo `cgf` for `cfg`), plus a few real gaps
  (`/$ctl/midi/en*`, `/$ctl/OSC`, `/$ctl/layer/*/N/N/val`, `/rec/path` → console has `/rec/$path`, `/cfg/talk/$lvl` → `lvl`).
- **Matrix sends are undocumented**: `/{ch,aux,bus,main}/N/send/MX1..MX8/{on,lvl,pan,mode,plink,pon}` (doc only has `send/N`).
- Model-dependent nodes differ by what is loaded on the walked instance: `/aux/N/eq` (4-band `1f/1g/1q…`), `/aux/N/dyn`,
  `/aux/N/gate` (absent on the console for aux 1), FX params on `/fx/1`. These are expected; the app reads them via `0xdd`.
- Other undocumented: `/io/in/SC/*`, `/$syscfg/tcplock`, `/$syscfg/eth_cfg`, `/cards/wmadi`, `/$globals/custsync/b`, ~95 `/$ctl` entries.

- doc paths: 1504; console: 1511 params + 312 nodes
- in both: 1437; doc only: 67; console-only params: 310

## Doc only (not on console)

### /$ctl (42)

- `/$ctl/$globals/$filesort`
- `/$ctl/OSC`
- `/$ctl/OSC/ronly`
- `/$ctl/cfg/rta55`
- `/$ctl/cgf/autosel_CMPCT`
- `/$ctl/cgf/autosel_EXT`
- `/$ctl/cgf/autosel_RCK`
- `/$ctl/cgf/autosel_VRT`
- `/$ctl/cgf/fdrbanking`
- `/$ctl/cgf/fdrscrnlink`
- `/$ctl/layer/C/$spill/N/val`
- `/$ctl/layer/C/$spill1/i`
- `/$ctl/layer/C/N/N/val`
- `/$ctl/layer/CMPCT/$spill/N/typ`
- `/$ctl/layer/CMPCT/$spill/N/val`
- `/$ctl/layer/CMPCT/$spill/nam`
- `/$ctl/layer/CMPCT/$spill1/i`
- `/$ctl/layer/CMPCT/N/N/val`
- `/$ctl/layer/EXT/$spill/N/val`
- `/$ctl/layer/EXT/$spill1/i`
- `/$ctl/layer/EXT/N/N/val`
- `/$ctl/layer/L/$spill/N/val`
- `/$ctl/layer/L/$spill1/i`
- `/$ctl/layer/L/N/N/val`
- `/$ctl/layer/R/$spill/N/val`
- `/$ctl/layer/R/$spill1/i`
- `/$ctl/layer/R/N/N/val`
- `/$ctl/layer/RCK/$spill/N/val`
- `/$ctl/layer/RCK/$spill1/i`
- `/$ctl/layer/RCK/N/N/val`
- `/$ctl/layer/VRT/$spill/N/val`
- `/$ctl/layer/VRT/$spill1/i`
- `/$ctl/layer/VRT/N/N/val`
- `/$ctl/midi/enchctl`
- `/$ctl/midi/encustctl`
- `/$ctl/midi/enfxctl`
- `/$ctl/midi/enmidicc`
- `/$ctl/midi/enscenes`
- `/$ctl/midi/enscenetx`
- `/$ctl/midi/enshowctl`
- `/$ctl/midi/ensysex`
- `/$ctl/safes/outpu/A`

### /$syscfg (2)

- `/$syscfg/$chwversion`
- `/$syscfg/eth/cfg`

### /aux (7)

- `/aux/N/gate/acc`
- `/aux/N/gate/att`
- `/aux/N/gate/hld`
- `/aux/N/gate/range`
- `/aux/N/gate/ratio`
- `/aux/N/gate/rel`
- `/aux/N/gate/thr32`

### /bus (2)

- `/bus/N/dyn/thr37`
- `/bus/N/eq/lg35`

### /cards (1)

- `/cards/wlive/N/$stat/errormessag`

### /cfg (1)

- `/cfg/talk/$lvl`

### /ch (4)

- `/ch/N/dyn/thr26`
- `/ch/N/eq/lg24`
- `/ch/N/flt/tilt21`
- `/ch/N/gate/thr23`

### /io (2)

- `/io/in/USR/N/user/lr19`
- `/io/in/USR/N/user/tap18`

### /main (2)

- `/main/N/dyn/thr42`
- `/main/N/eq/lg40`

### /mtx (2)

- `/mtx/N/dyn/thr46`
- `/mtx/N/eq/lg44`

### /play51 (1)

- `/play51`

### /rec (1)

- `/rec/path`

## Console only (undocumented params)

### /$ctl (95)

- `/$ctl/$globals/datefmt` — enum  DATE FORMAT
- `/$ctl/$globals/filesort` — enum  FILE ORDER
- `/$ctl/cfg/autosel_CMPCT` — int
- `/$ctl/cfg/autosel_EXT` — int
- `/$ctl/cfg/autosel_RCK` — int
- `/$ctl/cfg/autosel_VRT` — int
- `/$ctl/cfg/fdrbanking` — int  FADER PAGING
- `/$ctl/cfg/fdrscrnlink` — int  FADER/SCREEN LAYER LINK
- `/$ctl/cfg/muteovr` — int  MUTEGROUP/SIP OVERRIDE
- `/$ctl/cfg/rta/chflttap` — enum  RTA TAP
- `/$ctl/daw/$on` — int ro  DAW ON
- `/$ctl/layer/C/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/CMPCT/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/CMPCT/$spill/N/type` — enum  TYPE
- `/$ctl/layer/CMPCT/$spill/name` — str  NAME
- `/$ctl/layer/EXT/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/L/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/R/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/RCK/$spill/N/i` — int  FDR INDEX
- `/$ctl/layer/VRT/$spill/N/i` — int  FDR INDEX
- `/$ctl/midi/dinchctl` — int
- `/$ctl/midi/dincustctl` — int
- `/$ctl/midi/dinfxctl` — int
- `/$ctl/midi/dinmidicc` — int
- `/$ctl/midi/dinscenes` — int
- `/$ctl/midi/dinscenetx` — int
- `/$ctl/midi/dinshowctl` — int
- `/$ctl/midi/dinsysex` — int
- `/$ctl/midi/usbchctl` — int
- `/$ctl/midi/usbcustctl` — int
- `/$ctl/midi/usbfxctl` — int
- `/$ctl/midi/usbmidicc` — int
- `/$ctl/midi/usbscenes` — int
- `/$ctl/midi/usbscenetx` — int
- `/$ctl/midi/usbshowctl` — int
- `/$ctl/midi/usbsysex` — int
- `/$ctl/osc/ronly` — int  READ ONLY
- `/$ctl/safes/area/EXTERN` — str
- `/$ctl/safes/area/RIGHT` — str
- `/$ctl/safes/area/VIRTUAL` — str
- `/$ctl/safes/output/A` — str  AES50 A
- `/$ctl/user/D1/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/D1/N/bu/mode` — enum  MODE
- `/$ctl/user/D1/N/bu/name` — str  NAME
- `/$ctl/user/D1/N/col` — int  COLOR
- `/$ctl/user/D1/N/led` — int  LED
- `/$ctl/user/D2/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/D2/N/bu/mode` — enum  MODE
- `/$ctl/user/D2/N/bu/name` — str  NAME
- `/$ctl/user/D2/N/col` — int  COLOR
- `/$ctl/user/D2/N/led` — int  LED
- `/$ctl/user/D3/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/D3/N/bu/mode` — enum  MODE
- `/$ctl/user/D3/N/bu/name` — str  NAME
- `/$ctl/user/D3/N/col` — int  COLOR
- `/$ctl/user/D3/N/led` — int  LED
- `/$ctl/user/D4/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/D4/N/bu/mode` — enum  MODE
- `/$ctl/user/D4/N/bu/name` — str  NAME
- `/$ctl/user/D4/N/col` — int  COLOR
- `/$ctl/user/D4/N/led` — int  LED
- `/$ctl/user/MM/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/MM/N/bu/mode` — enum  MODE
- `/$ctl/user/MM/N/bu/name` — str  NAME
- `/$ctl/user/MM/N/col` — int  COLOR
- `/$ctl/user/MM/N/led` — int  LED
- `/$ctl/user/N/N/bu/ch` — int  CHANNEL
- `/$ctl/user/U1/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/U1/N/bu/mode` — enum  MODE
- `/$ctl/user/U1/N/bu/name` — str  NAME
- `/$ctl/user/U1/N/col` — int  COLOR
- `/$ctl/user/U1/N/led` — int  LED
- `/$ctl/user/U2/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/U2/N/bu/mode` — enum  MODE
- `/$ctl/user/U2/N/bu/name` — str  NAME
- `/$ctl/user/U2/N/col` — int  COLOR
- `/$ctl/user/U2/N/led` — int  LED
- `/$ctl/user/U3/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/U3/N/bu/mode` — enum  MODE
- `/$ctl/user/U3/N/bu/name` — str  NAME
- `/$ctl/user/U3/N/col` — int  COLOR
- `/$ctl/user/U3/N/led` — int  LED
- `/$ctl/user/U4/N/bu/$fname` — str ro  FUNCTION NAME
- `/$ctl/user/U4/N/bu/mode` — enum  MODE
- `/$ctl/user/U4/N/bu/name` — str  NAME
- `/$ctl/user/U4/N/col` — int  COLOR
- `/$ctl/user/U4/N/led` — int  LED
- `/$ctl/user/daw1/N/bd/btn` — enum  DAW BUTTON
- `/$ctl/user/daw1/N/bu/btn` — enum  DAW BUTTON
- `/$ctl/user/daw2/N/bd/btn` — enum  DAW BUTTON
- `/$ctl/user/daw2/N/bu/btn` — enum  DAW BUTTON
- `/$ctl/user/daw3/N/bd/btn` — enum  DAW BUTTON
- `/$ctl/user/daw3/N/bu/btn` — enum  DAW BUTTON
- `/$ctl/user/daw4/N/bd/btn` — enum  DAW BUTTON
- `/$ctl/user/daw4/N/bu/btn` — enum  DAW BUTTON

### /$globals (3)

- `/$globals/custsync/a` — int  AES50 A CUST
- `/$globals/custsync/b` — int  AES50 B CUST
- `/$globals/custsync/c` — int  AES50 C CUST

### /$syscfg (3)

- `/$syscfg/$hwversion` — str ro  HARDWARE VERSION
- `/$syscfg/eth_cfg` — enum  NETWORK CONFIG
- `/$syscfg/tcplock` — int  TCP REMOTE LOCK

### /aux (78)

- `/aux/N/dyn/cmode` — enum  CMODE
- `/aux/N/dyn/cpeak` — linf  PEAK
- `/aux/N/dyn/depth` — linf dB DEPTH
- `/aux/N/dyn/fast` — int  FAST
- `/aux/N/dyn/ingain` — linf  GAIN
- `/aux/N/dyn/peak` — int  PEAK
- `/aux/N/dyn/thr` — linf dB THR
- `/aux/N/eq/$solo` — int  EQ SOLO
- `/aux/N/eq/$solobd` — int  SOLO BAND
- `/aux/N/eq/1f` — logf Hz FREQ 1
- `/aux/N/eq/1g` — linf dB GAIN 1
- `/aux/N/eq/1q` — logf  Q 1
- `/aux/N/eq/2f` — logf Hz FREQ 2
- `/aux/N/eq/2g` — linf dB GAIN 2
- `/aux/N/eq/2q` — logf  Q 2
- `/aux/N/eq/3f` — logf Hz FREQ 3
- `/aux/N/eq/3g` — linf dB GAIN 3
- `/aux/N/eq/3q` — logf  Q 3
- `/aux/N/eq/4f` — logf Hz FREQ 4
- `/aux/N/eq/4g` — linf dB GAIN 4
- `/aux/N/eq/4q` — logf  Q 4
- `/aux/N/eq/heq` — enum  EQ H
- `/aux/N/eq/hf` — logf Hz FREQ H
- `/aux/N/eq/hg` — linf dB GAIN H
- `/aux/N/eq/hq` — logf  Q H
- `/aux/N/eq/leq` — enum  EQ L
- `/aux/N/eq/lf` — logf Hz FREQ L
- `/aux/N/eq/lg` — linf dB GAIN L
- `/aux/N/eq/lq` — logf  Q L
- `/aux/N/eq/mix` — linf % MIX
- `/aux/N/send/MX1/lvl` — fader dB SEND LVL
- `/aux/N/send/MX1/mode` — enum  SEND MODE
- `/aux/N/send/MX1/on` — int  ON
- `/aux/N/send/MX1/pan` — linf  PAN
- `/aux/N/send/MX1/plink` — int  PAN LINK
- `/aux/N/send/MX1/pon` — int  PRE ON
- `/aux/N/send/MX2/lvl` — fader dB SEND LVL
- `/aux/N/send/MX2/mode` — enum  SEND MODE
- `/aux/N/send/MX2/on` — int  ON
- `/aux/N/send/MX2/pan` — linf  PAN
- `/aux/N/send/MX2/plink` — int  PAN LINK
- `/aux/N/send/MX2/pon` — int  PRE ON
- `/aux/N/send/MX3/lvl` — fader dB SEND LVL
- `/aux/N/send/MX3/mode` — enum  SEND MODE
- `/aux/N/send/MX3/on` — int  ON
- `/aux/N/send/MX3/pan` — linf  PAN
- `/aux/N/send/MX3/plink` — int  PAN LINK
- `/aux/N/send/MX3/pon` — int  PRE ON
- `/aux/N/send/MX4/lvl` — fader dB SEND LVL
- `/aux/N/send/MX4/mode` — enum  SEND MODE
- `/aux/N/send/MX4/on` — int  ON
- `/aux/N/send/MX4/pan` — linf  PAN
- `/aux/N/send/MX4/plink` — int  PAN LINK
- `/aux/N/send/MX4/pon` — int  PRE ON
- `/aux/N/send/MX5/lvl` — fader dB SEND LVL
- `/aux/N/send/MX5/mode` — enum  SEND MODE
- `/aux/N/send/MX5/on` — int  ON
- `/aux/N/send/MX5/pan` — linf  PAN
- `/aux/N/send/MX5/plink` — int  PAN LINK
- `/aux/N/send/MX5/pon` — int  PRE ON
- `/aux/N/send/MX6/lvl` — fader dB SEND LVL
- `/aux/N/send/MX6/mode` — enum  SEND MODE
- `/aux/N/send/MX6/on` — int  ON
- `/aux/N/send/MX6/pan` — linf  PAN
- `/aux/N/send/MX6/plink` — int  PAN LINK
- `/aux/N/send/MX6/pon` — int  PRE ON
- `/aux/N/send/MX7/lvl` — fader dB SEND LVL
- `/aux/N/send/MX7/mode` — enum  SEND MODE
- `/aux/N/send/MX7/on` — int  ON
- `/aux/N/send/MX7/pan` — linf  PAN
- `/aux/N/send/MX7/plink` — int  PAN LINK
- `/aux/N/send/MX7/pon` — int  PRE ON
- `/aux/N/send/MX8/lvl` — fader dB SEND LVL
- `/aux/N/send/MX8/mode` — enum  SEND MODE
- `/aux/N/send/MX8/on` — int  ON
- `/aux/N/send/MX8/pan` — linf  PAN
- `/aux/N/send/MX8/plink` — int  PAN LINK
- `/aux/N/send/MX8/pon` — int  PRE ON

### /bus (26)

- `/bus/N/dyn/thr` — linf dB THR
- `/bus/N/eq/lg` — linf dB GAIN L
- `/bus/N/send/MX1/lvl` — fader dB SEND LVL
- `/bus/N/send/MX1/on` — int  ON
- `/bus/N/send/MX1/pre` — int  PRE
- `/bus/N/send/MX2/lvl` — fader dB SEND LVL
- `/bus/N/send/MX2/on` — int  ON
- `/bus/N/send/MX2/pre` — int  PRE
- `/bus/N/send/MX3/lvl` — fader dB SEND LVL
- `/bus/N/send/MX3/on` — int  ON
- `/bus/N/send/MX3/pre` — int  PRE
- `/bus/N/send/MX4/lvl` — fader dB SEND LVL
- `/bus/N/send/MX4/on` — int  ON
- `/bus/N/send/MX4/pre` — int  PRE
- `/bus/N/send/MX5/lvl` — fader dB SEND LVL
- `/bus/N/send/MX5/on` — int  ON
- `/bus/N/send/MX5/pre` — int  PRE
- `/bus/N/send/MX6/lvl` — fader dB SEND LVL
- `/bus/N/send/MX6/on` — int  ON
- `/bus/N/send/MX6/pre` — int  PRE
- `/bus/N/send/MX7/lvl` — fader dB SEND LVL
- `/bus/N/send/MX7/on` — int  ON
- `/bus/N/send/MX7/pre` — int  PRE
- `/bus/N/send/MX8/lvl` — fader dB SEND LVL
- `/bus/N/send/MX8/on` — int  ON
- `/bus/N/send/MX8/pre` — int  PRE

### /cards (1)

- `/cards/wlive/N/$stat/errormessage` — str ro  SD ERROR MESSAGE

### /cfg (1)

- `/cfg/talk/lvl` — fader dB TALK LVL

### /ch (53)

- `/ch/N/dyn/thr` — linf dB THR
- `/ch/N/dynxo/f` — logf Hz FREQ
- `/ch/N/eq/lg` — linf dB GAIN L
- `/ch/N/flt/tilt` — linf dB TILT
- `/ch/N/gate/thr` — linf dB THR
- `/ch/N/send/MX1/lvl` — fader dB SEND LVL
- `/ch/N/send/MX1/mode` — enum  SEND MODE
- `/ch/N/send/MX1/on` — int  ON
- `/ch/N/send/MX1/pan` — linf  PAN
- `/ch/N/send/MX1/plink` — int  PAN LINK
- `/ch/N/send/MX1/pon` — int  PRE ON
- `/ch/N/send/MX2/lvl` — fader dB SEND LVL
- `/ch/N/send/MX2/mode` — enum  SEND MODE
- `/ch/N/send/MX2/on` — int  ON
- `/ch/N/send/MX2/pan` — linf  PAN
- `/ch/N/send/MX2/plink` — int  PAN LINK
- `/ch/N/send/MX2/pon` — int  PRE ON
- `/ch/N/send/MX3/lvl` — fader dB SEND LVL
- `/ch/N/send/MX3/mode` — enum  SEND MODE
- `/ch/N/send/MX3/on` — int  ON
- `/ch/N/send/MX3/pan` — linf  PAN
- `/ch/N/send/MX3/plink` — int  PAN LINK
- `/ch/N/send/MX3/pon` — int  PRE ON
- `/ch/N/send/MX4/lvl` — fader dB SEND LVL
- `/ch/N/send/MX4/mode` — enum  SEND MODE
- `/ch/N/send/MX4/on` — int  ON
- `/ch/N/send/MX4/pan` — linf  PAN
- `/ch/N/send/MX4/plink` — int  PAN LINK
- `/ch/N/send/MX4/pon` — int  PRE ON
- `/ch/N/send/MX5/lvl` — fader dB SEND LVL
- `/ch/N/send/MX5/mode` — enum  SEND MODE
- `/ch/N/send/MX5/on` — int  ON
- `/ch/N/send/MX5/pan` — linf  PAN
- `/ch/N/send/MX5/plink` — int  PAN LINK
- `/ch/N/send/MX5/pon` — int  PRE ON
- `/ch/N/send/MX6/lvl` — fader dB SEND LVL
- `/ch/N/send/MX6/mode` — enum  SEND MODE
- `/ch/N/send/MX6/on` — int  ON
- `/ch/N/send/MX6/pan` — linf  PAN
- `/ch/N/send/MX6/plink` — int  PAN LINK
- `/ch/N/send/MX6/pon` — int  PRE ON
- `/ch/N/send/MX7/lvl` — fader dB SEND LVL
- `/ch/N/send/MX7/mode` — enum  SEND MODE
- `/ch/N/send/MX7/on` — int  ON
- `/ch/N/send/MX7/pan` — linf  PAN
- `/ch/N/send/MX7/plink` — int  PAN LINK
- `/ch/N/send/MX7/pon` — int  PRE ON
- `/ch/N/send/MX8/lvl` — fader dB SEND LVL
- `/ch/N/send/MX8/mode` — enum  SEND MODE
- `/ch/N/send/MX8/on` — int  ON
- `/ch/N/send/MX8/pan` — linf  PAN
- `/ch/N/send/MX8/plink` — int  PAN LINK
- `/ch/N/send/MX8/pon` — int  PRE ON

### /fx (11)

- `/fx/N/damp` — logf Hz DAMPING
- `/fx/N/dcy` — logf s DECAY
- `/fx/N/diff` — int  DIFFUSION
- `/fx/N/hc` — logf Hz HI CUT
- `/fx/N/lc` — logf Hz LO CUT
- `/fx/N/mspd` — int  MOD SPD
- `/fx/N/mult` — logf  BASS MULT
- `/fx/N/pdel` — int ms PRE DLY
- `/fx/N/shp` — linf  SHAPE
- `/fx/N/size` — int  SIZE
- `/fx/N/sprd` — int  SPREAD

### /io (9)

- `/io/in/SC/N/$ha` — int ro  HA TYPE
- `/io/in/SC/N/$ract` — int ro  ACT REMOTE
- `/io/in/SC/N/$rdest` — str ro  REMOTE SRC
- `/io/in/SC/N/g` — linf dB GAIN
- `/io/in/SC/N/rcvc` — int  RCV CUSTOMIZATION
- `/io/in/SC/N/rmt` — enum  HA REMOTE
- `/io/in/SC/N/vph` — int  PHANTOM
- `/io/in/USR/N/user/lr` — enum  SIGNAL
- `/io/in/USR/N/user/tap` — enum  TAP POINT

### /main (27)

- `/main/N/dyn/thr` — linf dB THR
- `/main/N/eq/lg` — linf dB GAIN L
- `/main/N/send/MX1/lvl` — fader dB SEND LVL
- `/main/N/send/MX1/on` — int  ON
- `/main/N/send/MX1/pre` — int  PRE
- `/main/N/send/MX2/lvl` — fader dB SEND LVL
- `/main/N/send/MX2/on` — int  ON
- `/main/N/send/MX2/pre` — int  PRE
- `/main/N/send/MX3/lvl` — fader dB SEND LVL
- `/main/N/send/MX3/on` — int  ON
- `/main/N/send/MX3/pre` — int  PRE
- `/main/N/send/MX4/lvl` — fader dB SEND LVL
- `/main/N/send/MX4/on` — int  ON
- `/main/N/send/MX4/pre` — int  PRE
- `/main/N/send/MX5/lvl` — fader dB SEND LVL
- `/main/N/send/MX5/on` — int  ON
- `/main/N/send/MX5/pre` — int  PRE
- `/main/N/send/MX6/lvl` — fader dB SEND LVL
- `/main/N/send/MX6/on` — int  ON
- `/main/N/send/MX6/pre` — int  PRE
- `/main/N/send/MX7/lvl` — fader dB SEND LVL
- `/main/N/send/MX7/on` — int  ON
- `/main/N/send/MX7/pre` — int  PRE
- `/main/N/send/MX8/lvl` — fader dB SEND LVL
- `/main/N/send/MX8/on` — int  ON
- `/main/N/send/MX8/pre` — int  PRE
- `/main/N/tags` — str  TAGS

### /mtx (2)

- `/mtx/N/dyn/thr` — linf dB THR
- `/mtx/N/eq/lg` — linf dB GAIN L

### /rec (1)

- `/rec/$path` — str  REC PATH
