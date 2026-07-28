"""
Linter : détecte les fonctions non appelées dans le pipeline.

Règle 2 : Aucune fonction écrite sans preuve qu'elle est appelée.

Usage: python scripts/check_dead_code.py
"""

import os
import ast
import sys


PIPELINE_ENTRY_POINTS = [
    "live/bot.py",
    "backtest/engine.py",
    "core/order_executor.py",
]


def extract_imports_and_calls(filepath: str) -> set:
    """Extract les imports et appels de fonction dans un fichier."""
    if not os.path.exists(filepath):
        return set()
    
    with open(filepath, "r") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()
    
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    
    return called


def extract_defined_functions(filepath: str) -> dict:
    """Extract les fonctions définies dans un fichier."""
    if not os.path.exists(filepath):
        return {}
    
    with open(filepath, "r") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {}
    
    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if not node.name.startswith("_") and not node.name.startswith("test_"):
                functions[node.name] = filepath
    
    return functions


def main():
    project_root = os.path.dirname(os.path.dirname(__file__))
    
    # Collecter toutes les fonctions définies dans core/
    core_dir = os.path.join(project_root, "core")
    all_functions = {}
    
    if os.path.exists(core_dir):
        for filename in os.listdir(core_dir):
            if not filename.endswith(".py"):
                continue
            filepath = os.path.join(core_dir, filename)
            functions = extract_defined_functions(filepath)
            all_functions.update(functions)
    
    # Collecter les appels dans les pipelines
    all_calls = set()
    for entry in PIPELINE_ENTRY_POINTS:
        filepath = os.path.join(project_root, entry)
        calls = extract_imports_and_calls(filepath)
        all_calls.update(calls)
    
    # Vérifier que chaque fonction est appelée
    uncalled = []
    for func_name, filepath in all_functions.items():
        if func_name not in all_calls:
            uncalled.append({
                "name": func_name,
                "file": filepath,
            })
    
    if uncalled:
        print("⚠️ RÈGLE 2 — fonctions potentiellement non branchées:")
        for f in uncalled:
            print(f"  {f['file']}::{f['name']}")
        print("\nMontrez la ligne exacte qui appelle cette fonction,")
        print("ou marquez-la # TODO: NOT WIRED")
        sys.exit(1)
    else:
        print("✅ RÈGLE 2 OK — toutes les fonctions sont appelées dans le pipeline")
        sys.exit(0)


if __name__ == "__main__":
    main()
