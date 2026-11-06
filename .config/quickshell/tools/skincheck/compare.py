"""compare.py BASELINE_DIR NEW_DIR: print one line per render that's missing or differs (pixels whose channels
differ by more than 2; more than 0.05 % of them counts), nothing if all match."""
import sys
from pathlib import Path
from PIL import Image, ImageChops

base, new = Path(sys.argv[1]), Path(sys.argv[2])
for b in sorted(base.glob("*.png")):
    n = new / b.name
    if not n.exists():
        print(f"{b.name}: not rendered"); continue
    x, y = Image.open(b).convert("RGBA"), Image.open(n).convert("RGBA")
    if x.size != y.size:
        print(f"{b.name}: size {y.size} vs baseline {x.size}"); continue
    d = ImageChops.difference(x, y)
    data = d.get_flattened_data() if hasattr(d, "get_flattened_data") else d.getdata()
    bad = sum(1 for px in data if max(px) > 2)
    if bad > x.size[0] * x.size[1] * 0.0005:
        print(f"{b.name}: {bad} pixels differ")
