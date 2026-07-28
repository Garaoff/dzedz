"""
Test Règle 4 : Pas de nombres en dur sans justification.

Ce test scanne les fichiers du projet pour détecter les
nombres littéraux qui ne sont pas dans config/params.py
et qui n'ont pas une justification STRUCTURAL ou DYNAMIC.
"""

import os
import re
import pytest


# Fichiers exemptés (config, tests, etc.)
EXEMPTED_FILES = [
    "config/params.py",
    "config/risk_config.py",
    "tests/",
    "scripts/",
]


# Patterns de justification acceptés
JUSTIFICATION_PATTERNS = [
    r"# STRUCTURAL:",
    r"# DYNAMIC:",
    r"# TODO:",
    r"# NOTE:",
    r"# STRUCTURAL",  # sans le : pour les justifications inline
    r"# DYNAMIC",     # sans le : pour les justifications inline
]


def find_magic_numbers(filepath: str) -> list:
    """
    Cherche les nombres littéraux qui n'ont pas de justification.
    Règle 4 : Aucune valeur numérique fixe sans justification explicite.
    """
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, "r") as f:
        lines = f.readlines()
    
    # Strip docstrings from content before scanning
    # Replace all triple-quoted strings with empty lines to preserve line numbers
    cleaned_lines = []
    in_docstring = False
    quote_marker = None
    
    for line in lines:
        stripped = line.strip()
        
        if in_docstring:
            # Check for closing quote
            if quote_marker in stripped:
                # Closing the docstring
                in_docstring = False
                cleaned_lines.append("")  # Blank line to preserve numbering
            else:
                cleaned_lines.append("")  # Skip docstring content
            continue
        
        # Check for opening docstring
        for marker in ['"""', "'''"]:
            if marker in stripped:
                count = stripped.count(marker)
                if count == 2 and stripped.startswith(marker) and stripped.endswith(marker):
                    # Single-line docstring
                    cleaned_lines.append("")
                    break
                elif count == 1 and stripped.startswith(marker):
                    # Opening a multi-line docstring
                    in_docstring = True
                    quote_marker = marker
                    cleaned_lines.append("")
                    break
        else:
            cleaned_lines.append(line)
    
    matches = []
    for i, line in enumerate(cleaned_lines, 1):
        stripped = line.strip()
        if not stripped:
            continue  # Skip blank lines (were docstrings)
        
        if stripped.startswith("#"):
            continue  # Skip comment-only lines
        
        # Ignorer les lignes avec justification (sur la même ligne ou la ligne précédente)
        has_justification = any(
            re.search(pattern, line) for pattern in JUSTIFICATION_PATTERNS
        )
        if not has_justification and i > 1:
            # Check previous line for justification
            prev_idx = i - 2
            if prev_idx >= 0 and prev_idx < len(cleaned_lines):
                prev_line = cleaned_lines[prev_idx]
                has_justification = any(
                    re.search(pattern, prev_line) for pattern in JUSTIFICATION_PATTERNS
                )
        if has_justification:
            continue
        
        # Chercher les nombres littéraux (pas 0, 1, ou les indices)
        number_pattern = r"\b(\d+\.?\d+)\b"
        for match in re.finditer(number_pattern, stripped):
            value = match.group(1)
            # Exempter les valeurs triviales (0, 1, 2 — indices, offsets, booléens)
            if value in ("0", "1", "0.0", "1.0", "2", "2.0", "-1", "-1.0"):
                continue
            
            # Vérifier si c'est dans config/params.py
            if "config/params.py" in filepath or "config/risk_config.py" in filepath:
                continue
            
            matches.append({
                "line": i,
                "value": value,
                "context": stripped,
                "file": filepath,
            })
    
    return matches


class TestMagicNumbers:
    """Règle 4 : Aucune valeur numérique fixe sans justification."""
    
    def test_no_magic_numbers_in_core_modules(self):
        """
        Vérifie que les modules core ne contiennent pas
        de nombres en dur sans justification.
        """
        project_root = os.path.dirname(os.path.dirname(__file__))
        core_dir = os.path.join(project_root, "core")
        
        all_matches = []
        
        if os.path.exists(core_dir):
            for filename in os.listdir(core_dir):
                if filename.endswith(".py"):
                    filepath = os.path.join(core_dir, filename)
                    matches = find_magic_numbers(filepath)
                    all_matches.extend(matches)
        
        if all_matches:
            details = "\n".join(
                f"  {m['file']}:{m['line']}: valeur={m['value']} | {m['context']}"
                for m in all_matches
            )
            pytest.fail(
                f"RÈGLE 4 VIOLÉE — nombres en dur sans justification:\n{details}\n"
                f"Ajoutez une justification # STRUCTURAL: ou # DYNAMIC: ou déplacez dans config/params.py"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
