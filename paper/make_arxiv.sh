#!/bin/sh
# Assemble a flat arXiv submission tarball.
#
# arXiv does not run BibTeX, so the generated .bbl must be shipped; and it
# unpacks into a single directory, so the figures have to sit beside the
# source rather than one level up.  \graphicspath in shiftfly.tex resolves
# both layouts, so the same file builds here and there.
#
#     cd paper && sh make_arxiv.sh
#
# Then upload arxiv/shiftfly-arxiv.tar.gz.

set -e
cd "$(dirname "$0")"

if [ ! -f shiftfly.bbl ]; then
  echo "shiftfly.bbl is missing - run pdflatex, bibtex, pdflatex first" >&2
  exit 1
fi

OUT=arxiv
rm -rf "$OUT"
mkdir -p "$OUT/bundle"

cp shiftfly.tex shiftfly.bbl "$OUT/bundle/"
for f in $(grep -o 'includegraphics\[[^]]*\]{[^}]*}' shiftfly.tex \
           | sed 's/.*{\(.*\)}/\1/'); do
  cp "../figures/$f" "$OUT/bundle/"
done

# arXiv reads the compile order from 00README.XXX when there is ambiguity
printf '%s\n' 'shiftfly.tex toplevelfile' > "$OUT/bundle/00README.XXX"

( cd "$OUT/bundle" && tar czf ../shiftfly-arxiv.tar.gz ./* )

echo "wrote $OUT/shiftfly-arxiv.tar.gz"
echo
echo "contents:"
tar tzf "$OUT/shiftfly-arxiv.tar.gz" | sed 's/^/  /'
echo
echo "Before uploading, verify it builds standalone:"
echo "  cd $OUT/bundle && pdflatex shiftfly && pdflatex shiftfly"
echo "(no bibtex run - the .bbl is already there, which is the point)"
