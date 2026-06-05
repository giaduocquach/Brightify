"""F1 — Unified validation runner (V22).

V22 adds NC (Negative Control) gate after editorial eval was found tautological
(shuffle-test 2026-06-04: Qprec unchanged under random song_va).

Tests and what they actually prove (honest labels):
  L1  Colour→V-A bridge fidelity vs ICEAS human norms — EXTERNAL, valid
  T1  Monotonicity — internal consistency of V-A NN-lookup (not proof of quality)
  T2  Commensurability — scale-mismatch detector (idem)
  T3  Distribution audit — catalog skew diagnostic
  ED  Editorial grouped eval — Qprec = internal consistency (tautological for V-A
      retrieval, proven by shuffle). P@k = external metric but genre-playlist GT
      is noisy (playlist songs ≠ mood-specific songs).
  L3  Discriminant validity — PoLL panel, partly circular (Gemini = labeler+judge)
  NC  Negative control — falsification: shuffle song_va, Qprec should DROP.
      If not → metric is tautological (already proven; this documents it explicitly).

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

    results['L1_bridge']        = run('L1 — Bridge fidelity (colour→V-A vs ICEAS)', 'tools.color_bridge_metrics')
    results['T1T2T3_structural'] = run('T1/T2/T3 — Structural battery', 'tools.color_structural_battery', TOP_K)
    results['ED_editorial']     = run('ED — Editorial grouped eval (Qprec=consistency diagnostic)', 'tools.color_editorial_grouped', TOP_K)
    results['L3_discriminant']  = run('L3 — Discriminant validity (PoLL panel, partly circular)', 'tools.color_discriminant_metrics')
    results['NC_negative_ctrl'] = run('NC — Negative control (shuffled-label falsification)', 'tools.color_negative_control', TOP_K)
    results['SEQ_journey']      = run('SEQ — Journey sequencing (2-colour A→B smoothness)', 'tools.color_journey_sequencing')

    print(f'\n{"="*60}')
    print('F1 VALIDATION SUMMARY (V22)')
    print(f'{"="*60}')
    # Labels clarifying what each test proves
    labels = {
        'L1_bridge':        'L1 — EXTERNAL: colour→V-A vs human ICEAS norms',
        'T1T2T3_structural':'T1/T2/T3 — INTERNAL consistency (NN-lookup sanity)',
        'ED_editorial':     'ED — INTERNAL: Qprec tautological (see NC below)',
        'L3_discriminant':  'L3 — DISCRIMINANT (partly circular, κ=0.19)',
        'NC_negative_ctrl': 'NC — FALSIFICATION: shuffle→Qprec should drop',
        'SEQ_journey':      'SEQ — JOURNEY: 2-colour order smoother than shuffle',
    }
    for name, ok in results.items():
        label = labels.get(name, name)
        print(f'  {label:<52} {"PASS ✓" if ok else "FAIL/NOTE ✗"}')
    all_pass = all(results.values())

    print()
    if not results.get('NC_negative_ctrl'):
        print('  ⚠ NC FAIL: Qprec does not drop when song_va is shuffled.')
        print('    This confirms Qprec=tautological. L1 is the only strong external')
        print('    evidence. Design is science-grounded; end-to-end validation')
        print('    without human labels is not achievable with genre-based playlists.')
    print(f'\n  L1 (external): {"PASS ✓" if results.get("L1_bridge") else "FAIL ✗"} — this is the strongest external evidence')
    print(f'{"="*60}')

    summary = {'tests': results, 'all_pass': all_pass}
    out = 'var/runtime/backtest/reports/f1_summary.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(summary, open(out,'w'), indent=2)
    print(f'\nsaved → {out}')
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
