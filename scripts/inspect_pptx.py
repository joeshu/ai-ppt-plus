#!/usr/bin/env python3
"""Inspect PPTX OOXML without modifying it or requiring python-pptx.

Usage: inspect_pptx.py DECK.pptx --report report.json
Output: structural JSON. Exit 0 no blockers, 2 blocker/critical, 3 runtime error.
Idempotent; stdlib only. Geometry overlap/overflow findings are heuristics and
must be confirmed from renders. Example/test: python inspect_pptx.py deck.pptx -r out.json
"""
import argparse,hashlib,json,re,zipfile
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
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);ap.add_argument('pptx');ap.add_argument('--report','-r',required=True);a=ap.parse_args();p=Path(a.pptx);issues=[];slides=[]
    try:
        if not p.is_file() or not zipfile.is_zipfile(p):raise ValueError('missing or invalid OOXML zip package')
        with zipfile.ZipFile(p) as z:
            names=set(z.namelist()); required={'[Content_Types].xml','ppt/presentation.xml'}
            if not required<=names:raise ValueError('required PPTX parts missing')
            pres=ET.fromstring(z.read('ppt/presentation.xml')); size=pres.find('p:sldSz',NS); sw=int(size.get('cx')) if size is not None else 0; sh=int(size.get('cy')) if size is not None else 0
            embedded_font_parts=sorted(n for n in names if n.startswith('ppt/fonts/') or n.startswith('ppt/font/'))
            embedded_font_declared=pres.find('.//p:embeddedFontLst',NS) is not None
            slide_names=sorted((n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)),key=lambda n:int(re.search(r'\d+',n).group()))
            for n,name in enumerate(slide_names,1):
                root=ET.fromstring(z.read(name)); shapes=root.findall('.//p:sp',NS); pics=root.findall('.//p:pic',NS); frames=root.findall('.//p:graphicFrame',NS); texts=[''.join(t.itertext()).strip() for t in shapes]; boxes=[]; rec={'slide':n,'shapes':len(shapes)+len(pics)+len(frames),'text_objects':sum(bool(t) for t in texts),'pictures':len(pics),'graphic_frames':len(frames),'charts':0,'tables':0,'off_canvas':0,'overlap_risks':0,'overflow_risks':0,'fonts':sorted({x.get('typeface') for x in root.findall('.//a:latin',NS) if x.get('typeface')})}
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
        ratio=sw/sh if sh else None;out={'schema':'ai-ppt-plus/pptx-inspection/v1','ok':not any(i['severity'] in {'blocker','critical'} for i in issues),'file':str(p.resolve()),'slide_count':len(slides),'width_emu':sw,'height_emu':sh,'ratio':ratio,'is_16_9':bool(ratio and abs(ratio-16/9)<.01),'slides':slides,'embedded_fonts':{'present':bool(embedded_font_parts and embedded_font_declared),'declared':embedded_font_declared,'parts':embedded_font_parts},'issues':issues,'limitations':['overlap and text overflow are heuristics; confirm from renders','semantic correctness and native editability require artifact/user review','embedded font detection follows OOXML font parts/declarations and does not prove every glyph is covered']}
    except Exception as e:out={'schema':'ai-ppt-plus/pptx-inspection/v1','ok':False,'issues':[{'severity':'blocker','code':'inspection_error','message':f'{type(e).__name__}: {e}'}]}
    out['deck_sha256']=sha256(p) if p.is_file() else None
    Path(a.report).parent.mkdir(parents=True,exist_ok=True);Path(a.report).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'ok':out['ok'],'issues':len(out['issues'])}));return 0 if out['ok'] else 2
if __name__=='__main__':raise SystemExit(main())
