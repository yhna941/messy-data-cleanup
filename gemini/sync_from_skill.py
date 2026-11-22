"""Build the Gemini CLI extension's skill from the one canonical skill.

The engine lives once, in ../skill/messy-data-cleanup/. This script copies it
byte-for-byte into skills/messy-data-cleanup/ (the folder Gemini CLI loads
from an extension). No file is edited, so there is no second copy of logic to
drift. `--check` exits 1 if the copy differs from the source (run_demo.sh runs it).
"""
import filecmp, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "skill" / "messy-data-cleanup"
DST = HERE / "skills" / "messy-data-cleanup"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def files(root):
    return sorted(p.relative_to(root) for p in root.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")


def drift():
    if not DST.exists():
        return ["missing " + str(DST)]
    a, b = files(SRC), files(DST)
    out = [f"only in source: {p}" for p in sorted(set(a) - set(b))]
    out += [f"only in gemini copy: {p}" for p in sorted(set(b) - set(a))]
    out += [f"differs: {p}" for p in sorted(set(a) & set(b))
            if not filecmp.cmp(SRC / p, DST / p, shallow=False)]
    return out


if __name__ == "__main__":
    if "--check" in sys.argv:
        d = drift()
        print("GEMINI SKILL IN SYNC" if not d else "GEMINI SKILL DRIFT:\n  " + "\n  ".join(d))
        sys.exit(1 if d else 0)
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST, ignore=IGNORE)
    print(f"copied {len(files(DST))} files -> {DST.relative_to(HERE.parent)}")
