#!/usr/bin/env python3
"""Inspect PPTX OOXML without modifying it or requiring python-pptx.

Usage: inspect_pptx.py DECK.pptx --report report.json
Output: structural JSON. Exit 0 no blockers, 2 blocker/critical, 3 runtime error.
Idempotent; stdlib only. Geometry overlap/overflow findings are heuristics and
must be confirmed from renders. Example/test: python inspect_pptx.py deck.pptx -r out.json
"""
import argparse,hashlib,json,posixpath,re,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','pr':'http://schemas.openxmlformats.org/package/2006/relationships'}
def box(node):
    off=node.find('.//a:xfrm/a:off',NS); ext=node.find('.//a:xfrm/a:ext',NS)
    if off is None or ext is None:return None
    try:return tuple(int(off.get(k)) for k in ('x','y'))+tuple(int(ext.get(k)) for k in ('cx','cy'))
    except Exception:return None
def overlap(a,b):
    x,y,w,h=a;X,Y,W,H=b; inter=max(0,min(x+w,X+W)-max(x,X))*max(0,min(y+h,Y+H)-max(y,Y)); return inter/max(1,w*h,W*H)
def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def eot_info(data):
    """Validate the EOT envelope used by PowerPoint .fntdata parts."""
    info = {
        'valid': False,
        'version': None,
        'eot_size': None,
        'font_data_size': None,
        'font_data_offset': None,
        'font_data_signature': None,
        'issues': [],
    }
    if len(data) < 82:
        info['issues'].append('eot_header_truncated')
        return info

    eot_size = int.from_bytes(data[0:4], 'little')
    font_data_size = int.from_bytes(data[4:8], 'little')
    version = int.from_bytes(data[8:12], 'little')
    magic = int.from_bytes(data[34:36], 'little')
    info.update({'version': hex(version), 'eot_size': eot_size, 'font_data_size': font_data_size})
    if version not in {0x00010000, 0x00020001, 0x00020002}:
        info['issues'].append('unsupported_eot_version')
    if magic != 0x504C:
        info['issues'].append('eot_magic_mismatch')

    offset = 82
    try:
        for _ in range(4):
            if offset + 2 > len(data):
                raise ValueError('eot_name_length_truncated')
            size = int.from_bytes(data[offset:offset + 2], 'little')
            end = offset + 2 + size + 2
            if end > len(data):
                raise ValueError('eot_name_exceeds_part')
            offset = end
        if offset + 2 > len(data):
            raise ValueError('eot_root_length_truncated')
        root_size = int.from_bytes(data[offset:offset + 2], 'little')
        offset += 2 + root_size
        if offset > len(data):
            raise ValueError('eot_root_exceeds_part')
        if version == 0x00020002:
            if offset + 10 > len(data):
                raise ValueError('eot_v2_extra_header_truncated')
            offset += 10
            if offset + 2 > len(data):
                raise ValueError('eot_signature_length_truncated')
            signature_size = int.from_bytes(data[offset:offset + 2], 'little')
            offset += 2 + signature_size + 4
            if offset + 4 > len(data):
                raise ValueError('eot_eudc_length_truncated')
            eudc_size = int.from_bytes(data[offset:offset + 4], 'little')
            offset += 4 + eudc_size
            if offset > len(data):
                raise ValueError('eot_eudc_exceeds_part')
    except ValueError as exc:
        info['issues'].append('eot_variable_header_truncated')
        info['header_issue'] = str(exc)

    end = offset + font_data_size
    info['font_data_offset'] = offset
    if eot_size != len(data):
        info['issues'].append('eot_size_mismatch')
    if font_data_size <= 0:
        info['issues'].append('empty_font_data')
    if offset > len(data) or end > len(data) or end > eot_size:
        info['issues'].append('font_data_exceeds_part')
    elif end != len(data):
        info['issues'].append('font_data_not_at_end')
    else:
        info['font_data_signature'] = data[offset:offset + 4].hex()
    info['valid'] = not info['issues']
    return info
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);ap.add_argument('pptx');ap.add_argument('--report','-r',required=True);a=ap.parse_args();p=Path(a.pptx);issues=[];slides=[]
    try:
        if not p.is_file() or not zipfile.is_zipfile(p):raise ValueError('missing or invalid OOXML zip package')
        with zipfile.ZipFile(p) as z:
            names=set(z.namelist()); required={'[Content_Types].xml','ppt/presentation.xml'}
            vector_assets=sorted(n for n in names if n.casefold().endswith('.svg'))
            if not required<=names:raise ValueError('required PPTX parts missing')
            pres=ET.fromstring(z.read('ppt/presentation.xml')); content_types=ET.fromstring(z.read('[Content_Types].xml')); size=pres.find('p:sldSz',NS); sw=int(size.get('cx')) if size is not None else 0; sh=int(size.get('cy')) if size is not None else 0
            default_content_types={node.get('Extension','').casefold():node.get('ContentType') for node in content_types if node.tag.endswith('Default')}
            override_content_types={node.get('PartName','').lstrip('/'):node.get('ContentType') for node in content_types if node.tag.endswith('Override')}
            embedded_font_parts=sorted(n for n in names if n.startswith('ppt/fonts/') or n.startswith('ppt/font/'))
            embedded_font_list=pres.find('.//p:embeddedFontLst',NS)
            embedded_font_declared=embedded_font_list is not None
            presentation_font_relationships={}
            rels_name='ppt/_rels/presentation.xml.rels'
            if rels_name in names:
                rels_root=ET.fromstring(z.read(rels_name))
                for rel in rels_root:
                    rel_type=rel.get('Type','')
                    if rel_type.endswith('/font'):
                        target=posixpath.normpath(posixpath.join('ppt',rel.get('Target','')))
                        presentation_font_relationships[rel.get('Id','')]=target
            declared_font_relationships=[]
            if embedded_font_list is not None:
                for node in embedded_font_list.findall('.//p:embeddedFont',NS):
                    for child in node:
                        rid=child.get('{%s}id' % NS['r'])
                        if rid:
                            declared_font_relationships.append(rid)
            resolved_declared_fonts=sorted({presentation_font_relationships[rid] for rid in declared_font_relationships if rid in presentation_font_relationships})
            missing_font_relationships=sorted(set(declared_font_relationships)-set(presentation_font_relationships))
            missing_font_parts=sorted(set(resolved_declared_fonts)-names)
            orphan_font_parts=sorted(set(embedded_font_parts)-set(resolved_declared_fonts))
            font_part_content_types={name:override_content_types.get(name,default_content_types.get(name.rsplit('.',1)[-1].casefold())) for name in embedded_font_parts}
            invalid_font_content_types={name:ctype for name,ctype in font_part_content_types.items() if ctype != 'application/x-fontdata'}
            if invalid_font_content_types: issues.append({'severity':'blocker','code':'invalid_embedded_font_content_type','parts':invalid_font_content_types})
            if embedded_font_declared and not declared_font_relationships: issues.append({'severity':'blocker','code':'embedded_font_declaration_incomplete','message':'embeddedFontLst has no font relationships'})
            if missing_font_relationships: issues.append({'severity':'blocker','code':'missing_embedded_font_relationship','ids':missing_font_relationships})
            if missing_font_parts: issues.append({'severity':'blocker','code':'missing_embedded_font_part','parts':missing_font_parts})
            if orphan_font_parts: issues.append({'severity':'blocker','code':'orphan_embedded_font_part','parts':orphan_font_parts})
            embedded_font_parts_evidence=[{'path':name,**eot_info(z.read(name))} for name in resolved_declared_fonts if name in names]
            malformed_font_parts=[item for item in embedded_font_parts_evidence if not item.get('valid')]
            if malformed_font_parts: issues.append({'severity':'blocker','code':'malformed_embedded_font_part','parts':malformed_font_parts})
            embedded_font_present=bool(embedded_font_declared and declared_font_relationships and not missing_font_relationships and not missing_font_parts and not orphan_font_parts and not invalid_font_content_types and resolved_declared_fonts and not malformed_font_parts)
            slide_names=sorted((n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'\d+',n).group()))
            for n,name in enumerate(slide_names,1):
                root=ET.fromstring(z.read(name)); shapes=root.findall('.//p:sp',NS); pics=root.findall('.//p:pic',NS); frames=root.findall('.//p:graphicFrame',NS); groups=root.findall('.//p:grpSp',NS); texts=[''.join(t.itertext()).strip() for t in shapes]; boxes=[]; rec={'slide':n,'shapes':len(shapes)+len(pics)+len(frames),'groups':len(groups),'text_objects':sum(bool(t) for t in texts),'pictures':len(pics),'graphic_frames':len(frames),'gradient_fills':z.read(name).count(b'<a:gradFill'),'charts':0,'tables':0,'off_canvas':0,'overlap_risks':0,'overflow_risks':0,'fonts':sorted({x.get('typeface') for x in root.findall('.//a:latin',NS) if x.get('typeface')})}
                xml=z.read(name)
                rec['charts']=xml.count(b'chart');rec['tables']=xml.count(b'<a:tbl')
                for node in shapes+pics+frames:
                    b=box(node)
                    if b:
                        x,y,w,h=b;boxes.append(b)
                        if x<0 or y<0 or x+w>sw or y+h>sh:rec['off_canvas']+=1
                for i,b in enumerate(boxes):
                    for c in boxes[i+1:]:
                        if overlap(b,c)>.65:rec['overlap_risks']+=1
                for text,node in zip(texts,shapes):
                    b=box(node)
                    if b and len(text)>max(40,int((b[2]/914400)*(b[3]/914400)*22)):rec['overflow_risks']+=1
                if rec['shapes']==0:issues.append({'slide':n,'severity':'critical','code':'empty_slide'})
                if rec['pictures']==1 and rec['text_objects']==0 and rec['shapes']==1:issues.append({'slide':n,'severity':'critical','code':'possible_full_slide_flattening'})
                if rec['off_canvas']:issues.append({'slide':n,'severity':'critical','code':'off_canvas','count':rec['off_canvas']})
                if rec['overlap_risks']:issues.append({'slide':n,'severity':'warning','code':'possible_overlap','count':rec['overlap_risks']})
                if rec['overflow_risks']:issues.append({'slide':n,'severity':'warning','code':'possible_text_overflow','count':rec['overflow_risks']})
                slides.append(rec)
        ratio=sw/sh if sh else None;out={'schema':'ai-ppt-plus/pptx-inspection/v1','ok':not any(i['severity'] in {'blocker','critical'} for i in issues),'file':str(p.resolve()),'slide_count':len(slides),'width_emu':sw,'height_emu':sh,'ratio':ratio,'is_16_9':bool(ratio and abs(ratio-16/9)<.01),'slides':slides,'vector_assets':vector_assets,'embedded_fonts':{'present':embedded_font_present,'declared':embedded_font_declared,'parts':embedded_font_parts,'declared_relationship_ids':sorted(set(declared_font_relationships)),'resolved_parts':resolved_declared_fonts,'part_evidence':embedded_font_parts_evidence,'content_types':font_part_content_types,'invalid_content_types':invalid_font_content_types,'missing_relationship_ids':missing_font_relationships,'missing_parts':missing_font_parts,'orphan_parts':orphan_font_parts},'issues':issues,'limitations':['overlap and text overflow are heuristics; confirm from renders','semantic correctness and native editability require artifact/user review','embedded font detection verifies declaration, font relationships, content types, EOT envelopes and package parts; it does not prove every glyph is covered or that a target application will honor embedding']}
    except Exception as e:out={'schema':'ai-ppt-plus/pptx-inspection/v1','ok':False,'issues':[{'severity':'blocker','code':'inspection_error','message':f'{type(e).__name__}: {e}'}]}
    out['deck_sha256']=sha256(p) if p.is_file() else None
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':out['ok'],'issues':len(out['issues'])}));return 0 if out['ok'] else 2
if __name__=='__main__':raise SystemExit(main())
