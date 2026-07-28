"""
Linter : détecte les nombres en dur sans justification.

Règle 4 : Aucune valeur numérique fixe sans justification explicite.

Usage: python scripts/check_magic_numbers.py
"""

import os
import re
import sys


JUSTIFICATION_PATTERNS = [
    r"# STRUCTURAL:",
    r"# DYNAMIC:",
    r"# TODO:",
    r"# NOTE:",
    r"# STRUCTURAL",
    r"# DYNAMIC",
]

TRIVIAL_VALUES = {"0", "1", "0.0", "1.0", "2", "2.0", "-1", "-1.0"}


def strip_docstrings(lines: list) -> list:
    """Remove docstring content from lines, preserving line numbers."""
    cleaned = []
    in_docstring = False
    quote_marker = None
    
    for line in lines:
        stripped = line.strip()
        
        if in_docstring:
            if quote_marker in stripped:
                in_docstring = False
                cleaned.append("")
            else:
                cleaned.append("")
            continue
        
        for marker in ['"""', "'''"]:
            if marker in stripped:
                count = stripped.count(marker)
                if count == 2 and stripped.startswith(marker) and stripped.endswith(marker):
                    cleaned.append("")
                    break
                elif count == 1 and stripped.startswith(marker):
                    in_docstring = True
                    quote_marker = marker
                    cleaned.append("")
                    break
        else:
            cleaned.append(line)
    
    return cleaned


def scan_file(filepath: str) -> list:
    """Cherche les nombres en dur sans justification."""
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    cleaned = strip_docstrings(lines)
    matches = []
    
    for i, line in enumerate(cleaned, 1):
        stripped = line.strip()
        if not stripped:
            continue
        
        if stripped.startswith("#"):
            continue
        
        has_justification = any(
            re.search(pattern, line) for pattern in JUSTIFICATION_PATTERNS
        )
        if not has_justification and i > 1:
            prev_idx = i - 2
            if prev_idx >= 0 and prev_idx < len(cleaned):
                prev_line = cleaned[prev_idx]
                has_justification = any(
                    re.search(pattern, prev_line) for pattern in JUSTIFICATION_PATTERNS
                )
        if has_justification:
            continue
        
        for match in re.finditer(r"\b(\d+\.?\d+)\b", stripped):
            value = match.group(1)
            if value in TRIVIAL_VALUES:
                continue
            
            matches.append({
                "file": filepath,
                "line": i,
                "value": value,
                "context": stripped,
            })
    
    return matches


def main():
    project_root = os.path.dirname(os.path.dirname(__file__))
    
    # Scan core/, live/, backtest/, data/ (pas config/, tests/, scripts/)
    scan_dirs = ["core", "live", "backtest", "data"]
    
    all_matches = []
    for scan_dir in scan_dirs:
        dirpath = os.path.join(project_root, scan_dir)
        if not os.path.exists(dirpath):
            continue
        
        for filename in os.listdir(dirpath):
            if not filename.endswith(".py"):
                continue
            
            filepath = os.path.join(dirpath, filename)
            matches = scan_file(filepath)
            all_matches.extend(matches)
    
    if all_matches:
        print("❌ RÈGLE 4 VIOLÉE — nombres en dur sans justification:")
        for m in all_matches:
            print(f"  {m['file']}:{m['line']}: valeur={m['value']} | {m['context']}")
        print("\nAjoutez # STRUCTURAL: ou # DYNAMIC: ou déplacez dans config/params.py")
        sys.exit(1)
    else:
        print("✅ RÈGLE 4 OK — tous les nombres sont justifiés ou dans config")
        sys.exit(0)


if __name__ == "__main__":
    main()
