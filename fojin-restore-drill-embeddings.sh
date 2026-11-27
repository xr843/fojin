#!/bin/bash
# 用法（host 上）：bash fojin-restore-drill-embeddings.sh <备份日期 YYYYMMDD> ["part_0000 part_0007"]
# 向量备份恢复演练：从 OSS 取 schema + 两段，解密、核 sha256，导入一次性 pgvector 容器，与生产逐行比对。生产库只读。
set -uo pipefail
STAMP=$1; PARTS="${2:-part_0000 part_0007}"
B="oss://fojin-prod-backup/embeddings/${STAMP}"; D=/home/admin/backups/restore_drill
rm -rf "$D"; mkdir -p "$D"; cd "$D" || exit 1
for f in schema.sql manifest.tsv $(for p in $PARTS; do echo "$p.copy.gz"; done); do
  /usr/local/bin/ossutil cp -f "$B/$f.gpg" "$f.gpg" >/dev/null && gpg --batch -q -d -o "$f" "$f.gpg" && rm -f "$f.gpg" || { echo "FAIL fetch/decrypt $f"; exit 1; }
done
for p in $PARTS; do
  want=$(awk -F'\t' -v n="$p.copy.gz" '$1==n{print $6}' manifest.tsv); got=$(sha256sum "$p.copy.gz" | cut -d' ' -f1)
  [ "$want" = "$got" ] && echo "sha256 OK $p" || { echo "sha256 MISMATCH $p"; exit 1; }
done
docker rm -f -v emb-restore-drill >/dev/null 2>&1
docker run -d --name emb-restore-drill -m 2g -e POSTGRES_PASSWORD=drill pgvector/pgvector:pg15 >/dev/null
for i in $(seq 1 30); do docker exec emb-restore-drill pg_isready -U postgres >/dev/null 2>&1 && break; sleep 2; done
q() { docker exec -i emb-restore-drill psql -U postgres -v ON_ERROR_STOP=0 -q "$@"; }
q -c "create role fojin; create extension vector;" >/dev/null 2>&1
grep -v "CREATE INDEX" schema.sql | q >/dev/null 2>&1   # 演练只验数据，不建 HNSW 索引
q -At -c "select count(*) from information_schema.tables where table_name='text_embeddings'"
for p in $PARTS; do
  gzip -dc "$p.copy.gz" | q -c "\copy text_embeddings from stdin"
  rows=$(awk -F'\t' -v n="$p.copy.gz" '$1==n{print $4}' manifest.tsv)
  lo=$(awk -F'\t' -v n="$p.copy.gz" '$1==n{print $2}' manifest.tsv); hi=$(awk -F'\t' -v n="$p.copy.gz" '$1==n{print $3}' manifest.tsv)
  got=$(q -At -c "select count(*) from text_embeddings where id between $lo and $hi")
  echo "$p rows restored $got / manifest $rows"
  # 抽 200 行：文字与向量逐字比对生产
  ids=$(q -At -c "select string_agg(id::text, ',') from (select id from text_embeddings where id between $lo and $hi order by random() limit 200) s")
  a=$(q -At -c "select md5(string_agg(id||chunk_text||embedding::text, '|' order by id)) from text_embeddings where id in ($ids)")
  b=$(cd /home/admin/fojin && docker compose exec -T postgres psql -U fojin -d fojin -At -c "select md5(string_agg(id||chunk_text||embedding::text, '|' order by id)) from text_embeddings where id in ($ids)")
  [ "$a" = "$b" ] && echo "$p 200 行与生产逐字相同" || echo "$p 与生产不同！ $a $b"
done
docker rm -f -v emb-restore-drill >/dev/null; cd /; rm -rf "$D"; echo DRILL_DONE
