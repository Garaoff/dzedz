"""
Linter : détecte les except:pass dans tout le projet.

Règle 6 : Interdiction du except:pass dans tout code touchant à
l'exécution, la protection de position, ou le calcul de risque.

Usage: python scripts/check_silent_except.py
"""

import os
import re
import sys


def scan_directory(root: str) -> list:
    """Scan tous les fichiers .py pour except:pass."""
    matches = []
    
    for dirpath, dirnames, filenames in os.walk(root):
        # Ignorer tests et scripts
        if "tests" in dirpath or "scripts" in dirpath:
            continue
        
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            
            filepath = os.path.join(dirpath, filename)
            with open(filepath, "r") as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                patterns = [
                    r"except\s*:\s*pass",
                    r"except\s+Exception\s*:\s*pass",
                ]
                
                for pattern in patterns:
                    if re.search(pattern, stripped):
                        matches.append({
                            "file": filepath,
                            "line": i,
                            "content": stripped,
                        })
    
    return matches


def main():
    project_root = os.path.dirname(os.path.dirname(__file__))
    matches = scan_directory(project_root)
    
    if matches:
        print("❌ RÈGLE 6 VIOLÉE — except:pass trouvé:")
        for m in matches:
            print(f"  {m['file']}:{m['line']}: {m['content']}")
        sys.exit(1)
    else:
        print("✅ RÈGLE 6 OK — aucun except:pass trouvé")
        sys.exit(0)


if __name__ == "__main__":
    main()
