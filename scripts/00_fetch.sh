#!/bin/bash
# Downloads the two source corpora (~3.3 GB) into data/raw/.
# curl rather than the datasets library: it is markedly faster here and resumable.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p data/raw && cd data/raw

IVA="https://huggingface.co/datasets/mvasiliniuc/iva-swift-codeint/resolve/main/data"
for i in 0 1 2 3 4 5 6; do
  f="rawdump_swift00000000000$i.json.gz"
  [ -s "$f" ] || curl -sL --retry 3 -o "$f" "$IVA/$f" &
done
wait

SE="https://huggingface.co/datasets/hongliu9903/stack_edu_swift/resolve/main/data"
for i in 0 1 2 3 4; do
  f="stackedu-0000$i.parquet"
  [ -s "$f" ] || curl -sL --retry 3 -o "$f" "$SE/train-0000$i-of-00005.parquet" &
done
wait

echo "fetched:"; du -sh .
