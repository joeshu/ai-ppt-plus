# PPTX last-mile compatibility and preservation

Some WPS/mobile viewers are less tolerant of root-relative OOXML relationship
targets such as Target="/ppt/slides/slide1.xml". Repair those targets at the
ZIP/XML layer only:

    python3 scripts/normalize_ooxml_relationships.py \
      authored.pptx compatible.pptx \
      --report qa/ooxml-normalization.json
    python3 scripts/validate_repackaging_invariants.py \
      authored.pptx compatible.pptx \
      --report qa/repackaging-invariants.json

Never open and re-save the authored deck through python-pptx as a last-mile
compatibility step. A second semantic authoring pass can silently change
rich-text runs, per-run color/weight/size, gradient fills, extension elements,
or independent image relationships.

The preservation gate must show unchanged:

- independent picture count and media bytes;
- text-run count and run-style digest;
- gradient-fill count; and
- slide part set.

Changing only relationship URI spelling is allowed. A technical pass is not a
human visual approval; render the compatible output and compare it again.
