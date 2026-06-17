#!/usr/bin/env bash
# A/B gate for model-bakeoff candidates. Swaps each candidate signal in, rebuilds the V-A
# label chain (fast — reads precomputed JSONs), runs the END-METRIC gates (colour-TE +
# similar-song coherence), then restores the active production signals. Reports absolute
# numbers so the winner is decided by end-metric, not the backbone's own benchmark.
set -uo pipefail
cd "$(dirname "$0")/.."
export HF_CACHE_DIR=var/volumes/hf_cache TOKENIZERS_PARALLELISM=false

EMO=data/emobank_valence.json
VNSENT=data/vnsent_grounded_valence.json
cp "$EMO" /tmp/emo_active.json
cp "$VNSENT" /tmp/vnsent_active.json

rebuild() { python -m tools.build_v6h_labels >/dev/null 2>&1; python -m tools.build_v6i_labels >/dev/null 2>&1; }
colorTE() { python -m tools.color_eval_rigor --emotions-file data/emotion_labels_v6i.json 2>&1 \
            | awk '/\[Euclidean\]/{e=1} e&&/production/{print "  color-TE="$2"  CI["$3","$4"]"; e=0}' | head -1; }
similar() { python -m tools.eval_similar_intrinsic --quiet 2>&1 \
            | grep -E "MoodCoherence|Symmetry|TempoCoherence|SelfConsistency" | sed 's/^/  /'; }

echo "===================== BASELINE (active grounded signals) ====================="
rebuild; colorTE; similar

echo "===================== [A] emobank → mDeBERTa-v3 ====================="
if [ -f data/emobank_mdeberta_valence.json ]; then
  cp data/emobank_mdeberta_valence.json "$EMO"; rebuild; colorTE; similar
  cp /tmp/emo_active.json "$EMO"
else echo "  (artifact missing)"; fi

echo "===================== [B] vn_sent → PhoBERT-large ====================="
if [ -f data/vnsent_phobertL_valence.json ]; then
  cp data/vnsent_phobertL_valence.json "$VNSENT"; rebuild; colorTE; similar
  cp /tmp/vnsent_active.json "$VNSENT"
else echo "  (artifact missing)"; fi

# restore active V-A
rebuild

echo "===================== [C] lyrics-SBERT swaps (similar-song only) ====================="
echo "--- baseline vnsbert (dangvantuan/vietnamese-embedding) ---"
EMBEDDINGS_FILE=data/vnsbert_embeddings.npy similar
if [ -f data/lyrics_bgem3.npy ]; then echo "--- BGE-M3 ---"; EMBEDDINGS_FILE=data/lyrics_bgem3.npy similar; fi
if [ -f data/lyrics_e5large.npy ]; then echo "--- multilingual-e5-large ---"; EMBEDDINGS_FILE=data/lyrics_e5large.npy similar; fi

echo "===================== GATES DONE ====================="
