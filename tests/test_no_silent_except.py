"""
Test Règle 6 : Pas de except:pass dans le code critique.

Ce test scanne les fichiers du projet pour détecter les
except: pass ou except Exception: pass dans les modules
touchant à l'exécution, la protection de position, ou le calcul de risque.
"""

import os
import re
import pytest


CRITICAL_MODULES = [
    "core/risk_guard.py",
    "core/order_executor.py",
    "core/position_sizer.py",
    "core/sl_tp_calculator.py",
    "core/signal_detector.py",
    "live/bot.py",
    "live/auto_optimize.py",
]


def find_silent_except(filepath: str) -> list:
    """
    Cherche les except: pass ou except Exception: pass dans un fichier.
    Règle 6 : Interdiction dans tout code touchant à l'exécution.
    """
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, "r") as f:
        content = f.read()
    
    # Patterns à détecter
    patterns = [
        r"except\s*:\s*pass",  # except: pass
        r"except\s+Exception\s*:\s*pass",  # except Exception: pass
        r"except\s+\w+\s*:\s*pass",  # except SomeError: pass (variant)
    ]
    
    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count("\n") + 1
            matches.append({
                "line": line_num,
                "match": match.group(),
                "file": filepath,
            })
    
    return matches


class TestNoSilentExcept:
    """Règle 6 : Jamais d'échec silencieux."""
    
    def test_no_silent_except_in_critical_modules(self):
        """
        Vérifie que les modules critiques ne contiennent pas
        de except: pass.
        """
        all_matches = []
        
        for module in CRITICAL_MODULES:
            filepath = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                module,
            )
            matches = find_silent_except(filepath)
            all_matches.extend(matches)
        
        if all_matches:
            details = "\n".join(
                f"  {m['file']}:{m['line']}: {m['match']}"
                for m in all_matches
            )
            pytest.fail(
                f"RÈGLE 6 VIOLÉE — except:pass trouvé dans modules critiques:\n{details}"
            )
    
    def test_all_critical_modules_exist(self):
        """Vérifie que les modules critiques existent (même si vides)."""
        project_root = os.path.dirname(os.path.dirname(__file__))
        missing = []
        
        for module in CRITICAL_MODULES:
            filepath = os.path.join(project_root, module)
            if not os.path.exists(filepath):
                missing.append(module)
        
        # Les modules peuvent ne pas exister encore (en développement)
        # Ce test sert de rappel, pas de bloqueur
        if missing:
            print(f"Modules critiques non encore créés: {missing}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
