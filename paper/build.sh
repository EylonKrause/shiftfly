#!/bin/sh
# Build the paper.
#
#     cd paper && sh build.sh
#
# LaTeX resolves cross-references and citations by writing them to .aux on one
# pass and reading them back on the next, so a SINGLE pdflatex run always
# reports every \ref and \cite as undefined.  That is not an error; it means
# the run has not happened enough times yet.  Three passes settle it.
#
# shiftfly.bbl is committed, so BibTeX is optional.  Run it only after editing
# shiftfly.bib, and commit the regenerated .bbl -- arXiv does not run BibTeX.

set -e
cd "$(dirname "$0")"

TEX=${TEX:-pdflatex}
BIB=${BIB:-bibtex}

if [ "$1" = "--with-bibtex" ]; then
  "$TEX" -interaction=nonstopmode shiftfly.tex > /dev/null || true
  "$BIB" shiftfly || true
fi

for pass in 1 2 3; do
  printf 'pass %s... ' "$pass"
  "$TEX" -interaction=nonstopmode shiftfly.tex > build.log 2>&1 || true
  echo done
done

echo
echo "errors:                $(grep -cE '^!' build.log)"
echo "undefined references:  $(grep -c 'Reference.*undefined' build.log)"
echo "undefined citations:   $(grep -c 'Citation.*undefined' build.log)"
echo "missing figures:       $(grep -c 'not found' build.log)"
grep 'Output written' build.log || {
  echo
  echo "No PDF produced. First real error:"
  grep -A4 -m1 -E '^!' build.log
  exit 1
}
