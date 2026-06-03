"""F1 — Unified validation runner (V19).

Runs the full non-circular validation stack:
  L1  Color→V-A bridge fidelity vs ICEAS human norms
  T1  Monotonicity of V-A match
  T2  Commensurability (scale-mismatch detector)
  T3  Distribution audit (catalog skew + neutral-query check)
  ED  Editorial mood playlist, artist-grouped, macro balanced
  L3  Discriminant validity (opposite colours separate)

Usage: python -m tools.run_f1_validation [top_k]
"""
from __future__ import annotations
import os, sys, subprocess, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TOP_K = sys.argv[1] if len(sys.argv) > 1 else '10'


def run(label, module, *args):
    cmd = [sys.executable, '-m', module] + list(args)
    print(f'\n{"="*60}\n{label}\n{"="*60}')
    r = subprocess.run(cmd, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return r.returncode == 0


def main() -> int:
    results = {}

    results['L1_bridge']       = run('L1 — Bridge fidelity (colour→V-A vs ICEAS)', 'tools.color_bridge_metrics')
    results['T1T2T3_structural']= run('T1/T2/T3 — Structural battery', 'tools.color_structural_battery', TOP_K)
    results['ED_editorial']    = run('ED — Editorial grouped eval', 'tools.color_editorial_grouped', TOP_K)
    results['L3_discriminant'] = run('L3 — Discriminant validity', 'tools.color_discriminant_metrics')

    print(f'\n{"="*60}')
    print('F1 VALIDATION SUMMARY')
    print(f'{"="*60}')
    for name, ok in results.items():
        print(f'  {name:<26} {"PASS ✓" if ok else "FAIL ✗"}')
    all_pass = all(results.values())
    print(f'\n  Overall: {"ALL PASS ✓" if all_pass else "SOME FAIL — review above"}')
    print(f'{"="*60}')

    summary = {'tests': results, 'all_pass': all_pass}
    out = 'var/runtime/backtest/reports/f1_summary.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(summary, open(out,'w'), indent=2)
    print(f'\nsaved → {out}')
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
