#!/usr/bin/env bash
# FAIR re-run: give every candidate its OWN optimal settings before judging (the project lesson).
#   (a) MuQ-MuLan  — gate as audio backbone WITH audio-weight sweep (not MuQ's 0.76)
#   (b) PhoBERT-large — rebuild WITH word-segmentation (pyvi), then gate
#   (c) mDeBERTa  — re-encode WITH mean-pool (not [CLS]), then gate
#   (d) e5-large  — lyrics-weight sweep (find its best, not vnsbert's)
# Each: swap signal in → rebuild fast V-A chain → end-metric (colour-TE + similar-song) → restore.
set -uo pipefail
cd "$(dirname "$0")/.."
export HF_CACHE_DIR=var/volumes/hf_cache TOKENIZERS_PARALLELISM=false
NF='INFO|MERT|Loaded|it/s|Loading|pooler|lm_head|UNEXPECTED|MISSING|^Key |Notes:|^-|can be ignored|newly init|tqdm|Warning|warn|Downloading|safetensors|spiece|sentencepiece|added_tokens|special_tokens'

rebuild() { python -m tools.build_v6h_labels >/dev/null 2>&1; python -m tools.build_v6i_labels >/dev/null 2>&1; }
colorTE() { python -m tools.color_eval_rigor --emotions-file data/emotion_labels_v6i.json 2>&1 \
            | awk '/\[Euclidean\]/{e=1} e&&/production/{print "  color-TE="$2"  CI["$3","$4"]"; e=0}' | head -1; }
similar() { python -m tools.eval_similar_intrinsic --n-seeds 200 --quiet 2>&1 \
            | grep -E "MoodCoherence|Symmetry|TempoCoherence|SelfConsistency" | sed 's/^/  /'; }

echo "############### FAIR RE-RUN ###############"

# ---------- (c) mDeBERTa mean-pool: re-encode + probe ----------
echo "===== build (c) mDeBERTa mean-pool ====="
EMOBANK_BACKBONE=microsoft/mdeberta-v3-base EMOBANK_POOL=mean \
  EMOBANK_OUT=data/emobank_mdeberta_mean_valence.json \
  python -m tools.emobank_valence_probe all 2>&1 | grep -vE "$NF" | grep -iE "CV R|held-out|best|catalog V|Gate"

# ---------- (b) PhoBERT-large + segmentation: rebuild ----------
echo "===== build (b) PhoBERT-large + word-segmentation ====="
VN_SENT_BACKBONE=vinai/phobert-large VN_SENT_SEGMENT=1 \
  VN_SENT_OUT=data/vnsent_phobertL_seg_valence.json \
  python -m tools.build_grounded_vnsent 2>&1 | grep -vE "$NF" | grep -iE "Ridge|held-out|scored|valence mean|ρ vs"

# ================= GATES =================
EMO=data/emobank_valence.json; VNSENT=data/vnsent_grounded_valence.json
MUQ=data/muq_embeddings.npy; MUQMETA=data/muq_metadata.json
cp "$EMO" /tmp/emo_act.json; cp "$VNSENT" /tmp/vns_act.json
cp "$MUQ" /tmp/muq_act.npy; cp "$MUQMETA" /tmp/muq_act.json
restore_all() { cp /tmp/emo_act.json "$EMO"; cp /tmp/vns_act.json "$VNSENT"; \
                cp /tmp/muq_act.npy "$MUQ"; cp /tmp/muq_act.json "$MUQMETA"; rebuild; }
trap restore_all EXIT

echo "===== BASELINE (active) ====="; rebuild; colorTE; similar

echo "===== (c) mDeBERTa mean-pool [gate] ====="
cp data/emobank_mdeberta_mean_valence.json "$EMO"; rebuild; colorTE; similar
cp /tmp/emo_act.json "$EMO"

echo "===== (b) PhoBERT-large+seg [gate] ====="
cp data/vnsent_phobertL_seg_valence.json "$VNSENT"; rebuild; colorTE; similar
cp /tmp/vns_act.json "$VNSENT"; rebuild

echo "===== (d) e5-large lyrics-weight SWEEP (similar-song) ====="
SWEEP='{"e5_lyr0.08":[0,0,0,0.08,0.16,0,0,0.76],"e5_lyr0.12":[0,0,0,0.12,0.14,0,0,0.74],"e5_lyr0.16":[0,0,0,0.16,0.12,0,0,0.72],"e5_lyr0.20":[0,0,0,0.20,0.10,0,0,0.70]}'
echo "--- vnsbert (baseline) at same sweep ---"
EMBEDDINGS_FILE=data/vnsbert_embeddings.npy BRIGHTIFY_EVAL_CONFIGS="$SWEEP" \
  python -m tools.eval_similar_intrinsic --n-seeds 200 --quiet 2>&1 | grep -vE "$NF" | grep -E "MoodCoherence|Symmetry|SelfConsistency|TempoCoherence|^Config|e5_lyr" | sed 's/^/  /'
echo "--- e5-large at same sweep ---"
EMBEDDINGS_FILE=data/lyrics_e5large.npy BRIGHTIFY_EVAL_CONFIGS="$SWEEP" \
  python -m tools.eval_similar_intrinsic --n-seeds 200 --quiet 2>&1 | grep -vE "$NF" | grep -E "MoodCoherence|Symmetry|SelfConsistency|TempoCoherence|^Config|e5_lyr" | sed 's/^/  /'

echo "===== (a) MuQ-MuLan [gate] with audio-weight SWEEP ====="
python - <<'PY'
import json, pandas as pd, config as cfg
tids = pd.read_csv(cfg.PROCESSED_FILE)["track_id"].astype(str).tolist()
json.dump({"done_track_ids": tids}, open("data/muq_metadata.json", "w"))   # MuLan npy is in df order
PY
cp data/mulan_embeddings.npy "$MUQ"
MSWEEP='{"mulan_a0.70":[0,0,0,0.10,0.20,0,0,0.70],"mulan_a0.76":[0,0,0,0.08,0.16,0,0,0.76],"mulan_a0.82":[0,0,0,0.06,0.12,0,0,0.82],"mulan_a0.88":[0,0,0,0.04,0.08,0,0,0.88]}'
echo "--- MuLan colour-TE (audio backbone for coherence too) ---"; colorTE
echo "--- MuLan similar-song audio-weight sweep ---"
BRIGHTIFY_EVAL_CONFIGS="$MSWEEP" python -m tools.eval_similar_intrinsic --n-seeds 200 --quiet 2>&1 | grep -vE "$NF" | grep -E "MoodCoherence|Symmetry|SelfConsistency|TempoCoherence|mulan_a" | sed 's/^/  /'
echo "--- MuQ baseline same sweep (reference) ---"
cp /tmp/muq_act.npy "$MUQ"; cp /tmp/muq_act.json "$MUQMETA"
BRIGHTIFY_EVAL_CONFIGS="$MSWEEP" python -m tools.eval_similar_intrinsic --n-seeds 200 --quiet 2>&1 | grep -vE "$NF" | grep -E "MoodCoherence|Symmetry|SelfConsistency|TempoCoherence|mulan_a" | sed 's/^/  /'

echo "############### FAIR RE-RUN DONE ###############"
