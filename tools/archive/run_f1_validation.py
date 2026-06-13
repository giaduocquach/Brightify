"""F1 — Unified validation runner (V24).

V24 adds Phase-1 rigor suite (color_eval_rigor): V-A targeting error with
bootstrap CI, 5-baseline comparison, FDR-corrected significance, journey
calibration. Replaces V22 labelling; honest test descriptions preserved.

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
  SEQ Journey sequencing — 2-colour A→B order smoother than shuffle (Iso-Principle)
  P1  Phase-1 rigor — V-A targeting error + CI + FDR + journey calibration
      (Dacrema 2021; Schnabel 2022; Benjamini-Hochberg 1995; Steck 2018)

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
    results['P1_rigor']         = run('P1 — Phase-1 rigor (targeting error + CI + FDR + journey calib)', 'tools.color_eval_rigor', TOP_K)
    # P2a: ViSoBERT + tabular XLM-R (offline models, slow first run)
    results['P2_valence_val']   = run('P2a — Valence corroboration (ViSoBERT + tabular XLM-R)', 'tools.valence_decoupled_validate')
    # P2b: GPT-4o-mini decoupled panel (needs OpenAI_API_KEY; uses cache after first run)
    results['P2b_gpt_val']      = run('P2b — GPT-4o-mini valence corroboration', 'tools.valence_gpt_validate')

    print(f'\n{"="*60}')
    print('F1 VALIDATION SUMMARY (V24)')
    print(f'{"="*60}')
    labels = {
        'L1_bridge':        'L1 — EXTERNAL: colour→V-A vs human ICEAS norms',
        'T1T2T3_structural':'T1/T2/T3 — INTERNAL consistency (NN-lookup sanity)',
        'ED_editorial':     'ED — INTERNAL: Qprec tautological (see NC below)',
        'L3_discriminant':  'L3 — DISCRIMINANT (partly circular, κ=0.19)',
        'NC_negative_ctrl': 'NC — FALSIFICATION: shuffle→Qprec should drop',
        'SEQ_journey':      'SEQ — JOURNEY: 2-colour order smoother than shuffle',
        'P1_rigor':         'P1 — RIGOR: targeting error < all 5 baselines + FDR + CI',
        'P2_valence_val':   'P2a — VALENCE: ViSoBERT+tabular XLM-R (ρ≥0.25)',
        'P2b_gpt_val':      'P2b — VALENCE: GPT-4o-mini decoupled (ρ≥0.55 strong)',
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

    # Load P1 report for inline summary if available
    p1_rpt = 'var/runtime/backtest/reports/color_eval_rigor.json'
    if os.path.exists(p1_rpt):
        try:
            p1 = json.load(open(p1_rpt))
            te = p1.get('va_targeting_error', {})
            prod = te.get('production', {}).get('euclidean', {})
            fdr  = p1.get('fdr_analysis', {}).get('results', [])
            n_sig = sum(r['reject_H0'] for r in fdr)
            n_b   = len(fdr)
            jc   = p1.get('journey_calibration', {})
            l1   = p1.get('l1_bridge_fisher_z', {})
            print(f'\n  P1 inline:')
            print(f'    TE prod Euclidean: {prod.get("mean","?")} CI{prod.get("ci95","?")}')
            print(f'    FDR: {n_sig}/{n_b} baselines significantly beaten (α=0.05 BH)')
            print(f'    Journey KS: {jc.get("mean_ks_stat","?")} (gate <0.40)')
            v_ci = l1.get("valence", {})
            print(f'    L1 valence r={v_ci.get("r","?")} CI{v_ci.get("ci95_fisher_z","?")}')
        except Exception:
            pass

    # Load P2 report inline if available
    p2_rpt = 'var/runtime/backtest/reports/valence_decoupled_validate.json'
    if os.path.exists(p2_rpt):
        try:
            p2 = json.load(open(p2_rpt))
            panel = p2.get('models', {}).get('panel', {})
            print(f'\n  P2 inline:')
            print(f'    Panel ρ={panel.get("spearman_rho","?")}  κ={panel.get("cohens_kappa","?")}')
            print(f'    Quadrant agree={panel.get("quadrant_agreement","?")}')
            pct = p2.get("disagreements",{}).get("pct_flagged", 0)
            print(f'    Disagreements: {float(pct)*100:.1f}% flagged')
            print(f'    Verdict: {p2.get("verdict","?")}')
        except Exception:
            pass

    print(f'\n  L1 (external): {"PASS ✓" if results.get("L1_bridge") else "FAIL ✗"} — strongest external evidence')
    print(f'  P1 (rigor):    {"PASS ✓" if results.get("P1_rigor") else "FAIL ✗"} — beats 5 baselines + FDR + journey')
    print(f'  P2a (valence): {"PASS ✓" if results.get("P2_valence_val") else "FAIL ✗"} — XLM-R corroboration')
    # Load P2b inline
    p2b_rpt = 'var/runtime/backtest/reports/valence_gpt_validate.json'
    if os.path.exists(p2b_rpt):
        try:
            p2b = json.load(open(p2b_rpt))
            m = p2b.get('metrics', {})
            print(f'  P2b (GPT):     {"PASS ✓" if results.get("P2b_gpt_val") else "FAIL ✗"} — '
                  f'rho={m.get("spearman_rho","?")}  kappa={m.get("cohens_kappa","?")}')
        except Exception:
            print(f'  P2b (GPT):     {"PASS ✓" if results.get("P2b_gpt_val") else "FAIL ✗"}')
    print(f'{"="*60}')

    summary = {'tests': results, 'all_pass': all_pass}
    out = 'var/runtime/backtest/reports/f1_summary.json'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(summary, open(out,'w'), indent=2)
    print(f'\nsaved → {out}')
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
