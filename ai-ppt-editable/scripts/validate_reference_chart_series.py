#!/usr/bin/env python3
"""Check the point/segment/label ledger of editable chart primitives.

The author gives every object a stable name:
  chart-<id>-<series>-marker-<month>, -label-<month>,
  chart-<id>-<series>-segment-<ending-month-minus-one>.
This verifies completeness and partial-year boundaries without inventing
source data or claiming a native chart workbook exists.
"""
import argparse
import json
import sys
import zipfile
from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def inspect(pptx, ledger):
    issues = []
    with zipfile.ZipFile(pptx) as archive:
        slide = f"ppt/slides/slide{ledger.get('slide', 1)}.xml"
        root = etree.fromstring(archive.read(slide))
    named = {}
    for obj in root.xpath(".//p:sp", namespaces={"p": P}):
        prop = obj.find(f"{{{P}}}nvSpPr/{{{P}}}cNvPr")
        if prop is None:
            continue
        name = prop.get("name", "")
        actual = "".join(obj.xpath(".//a:t/text()", namespaces={"a": A}))
        named[name] = actual
    for chart in ledger['charts']:
        for series in chart['series']:
            prefix = f"chart-{chart['id']}-{series['id']}"
            values = [str(x) for x in series['labels']]
            for index, expected in enumerate(values, 1):
                for kind in ('marker', 'label'):
                    key = f"{prefix}-{kind}-{index}"
                    if key not in named:
                        issues.append(f"missing: {key}")
                    elif kind == 'label' and named[key] != expected:
                        issues.append(f"label mismatch: {key}: {named[key]!r} != {expected!r}")
                if index > 1 and f"{prefix}-segment-{index-1}" not in named:
                    issues.append(f"missing segment: {prefix}-segment-{index-1}")
            for kind in ('marker', 'label', 'segment'):
                found = [key for key in named if key.startswith(f"{prefix}-{kind}-")]
                expected_count = len(values) - (kind == 'segment')
                if len(found) != expected_count:
                    issues.append(f"count: {prefix}-{kind}: {len(found)} != {expected_count}")
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('pptx')
    parser.add_argument('ledger', help='JSON chart ids and series id/labels')
    args = parser.parse_args()
    issues = inspect(args.pptx, json.load(open(args.ledger, encoding='utf-8')))
    print(json.dumps({'ok': not issues, 'issues': issues}, ensure_ascii=False))
    return bool(issues)


if __name__ == '__main__':
    sys.exit(main())
