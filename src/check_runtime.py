"""Validate the selected Python runtime without installing packages or creating a venv."""
from __future__ import annotations

import argparse
import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME_MODULES = {
    "requests": "requests",
    "bs4": "beautifulsoup4",
    "openpyxl": "openpyxl",
}
DEV_MODULES = {
    "pytest": "pytest (only needed for the offline regression suite)",
}


def check_runtime(*, dev: bool = False) -> list[str]:
    """Check importable modules for a runtime-only or runtime+dev environment."""
    issues: list[str] = []
    if sys.version_info < (3, 10):
        issues.append(f"Python 3.10+ dibutuhkan; ditemukan {sys.version.split()[0]}.")

    try:
        prefix = Path(sys.prefix).resolve()
        project_root = ROOT.resolve()
        if prefix == project_root or project_root in prefix.parents:
            issues.append(
                "Interpreter yang terpilih berada di dalam folder proyek (kemungkinan venv lokal). "
                "Pilih Python instalasi utama lewat PROMO_PYTHON."
            )
    except OSError:
        pass

    modules = dict(RUNTIME_MODULES)
    if dev:
        modules.update(DEV_MODULES)
    for module_name, display_name in modules.items():
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # import errors can also be broken binary deps
            issues.append(f"Modul {display_name} tidak bisa diimpor ({type(exc).__name__}: {exc}).")

    if not issues:
        print(f"Python: {sys.version.split()[0]}")
        print(f"Executable: {sys.executable}")
        print(f"Prefix: {sys.prefix}")
        names = ", ".join(RUNTIME_MODULES)
        if dev:
            names += ", pytest"
        print(f"Modul tersedia: {names}")
        print("Tidak ada venv atau paket yang dibuat/diinstal.")
    return issues


def check_syntax() -> list[str]:
    errors: list[str] = []
    count = 0
    for path in sorted([*(ROOT / "src").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]):
        if path.name == "__init__.py":
            continue
        try:
            source = path.read_text(encoding="utf-8-sig")
            ast.parse(source, filename=str(path))
            count += 1
        except (OSError, SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    if not errors:
        print(f"Sintaks Python valid: {count} file.")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-syntax", action="store_true",
        help="parse all source and test Python files without writing bytecode",
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="also require development tools such as pytest (not needed for runtime-only check)",
    )
    args = parser.parse_args()

    issues = check_runtime(dev=args.dev)
    if args.check_syntax:
        issues.extend(check_syntax())
    if issues:
        print("\nPemeriksaan gagal:", file=sys.stderr)
        for issue in issues:
            print(f" - {issue}", file=sys.stderr)
        print(
            "\nLauncher tidak akan memasang paket otomatis. Gunakan interpreter Python yang pustakanya "
            "sudah lengkap, atau pasang dependensi secara manual pada interpreter itu jika memang diperlukan.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
