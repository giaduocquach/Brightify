"""E-AUDIO-CLEAN — does dropping the degenerate Essentia scalar signals
(timbral, rhythmic, tonal) from recommend_by_song help?

Re-optimizes the 8-signal MERT config with timbral/rhythmic/tonal FROZEN at 0,
then paired-bootstrap (cluster CI95) on the full editorial GT vs the current
production weights. update_config=True ⇔ CI95 entirely positive.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.backtest_v2.catalog import Catalog
from tools.backtest_v2.ground_truth.editorial import GT_FILE, load_editorial_gt, build_query_gt_mapping
from tools.backtest_v2.improve.weight_opt import optimize_weights

print("[E-AUDIO-CLEAN] loading catalog (v4 labels)…")
cat = Catalog.load()
baseline_ild = 0.07834
import json
p = "var/runtime/backtest/reports/iter_0_baseline/report.json"
if os.path.exists(p):
    try:
        e = json.load(open(p)).get("systems", {}).get("brightify_v7.2", {}).get("ild_lyrics", {})
        if isinstance(e, dict) and e.get("value"): baseline_ild = float(e["value"])
    except Exception: pass

pls = load_editorial_gt(GT_FILE)
res = optimize_weights(cat, pls, baseline_ild=baseline_ild, top_k=10,
                       max_opt_queries=120, verbose=True, mert=True,
                       freeze_idx=[0, 1, 2])   # drop timbral, rhythmic, tonal

print("\n================ E-AUDIO-CLEAN RESULT ================")
print("signals       :", res.signals)
print("baseline w    :", [round(x,3) for x in res.baseline_weights])
print("clean w (opt) :", [round(x,3) for x in res.optimal_weights])
print("full-GT bootstrap:", res.full_bootstrap if hasattr(res,'full_bootstrap') else '(see above)')
