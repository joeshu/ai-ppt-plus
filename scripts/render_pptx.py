#!/usr/bin/env python3
"""Render PPTX through discovered LibreOffice and Poppler.

Usage: render_pptx.py DECK --output-dir DIR [--pages 1,3-5] [--report JSON]
Exit 0 rendered, 2 unavailable/failed. Only its `slide-*.png` outputs and report
are replaced; repeated runs are idempotent. Requires soffice/libreoffice and
pdftoppm. It never reports success when either tool fails.
"""
import argparse, hashlib, json, os, shutil, subprocess, tempfile
from pathlib import Path
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter); ap.add_argument('pptx'); ap.add_argument('--output-dir',required=True); ap.add_argument('--dpi',type=int,default=144); ap.add_argument('--pages',help='comma-separated pages/ranges, e.g. 1,3-5'); ap.add_argument('--font-dir',help='task-local TTF/OTF/TTC directory'); ap.add_argument('--report'); a=ap.parse_args()
    src=Path(a.pptx).resolve(); out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    soffice=shutil.which('soffice') or shutil.which('libreoffice'); pdftoppm=shutil.which('pdftoppm'); errors=[]; pages=[]
    if not soffice: errors.append('LibreOffice/soffice not found')
    if not pdftoppm: errors.append('pdftoppm not found')
    if not src.exists(): errors.append('PPTX not found')
    font_dir=Path(a.font_dir).resolve() if a.font_dir else None
    if font_dir and not font_dir.is_dir(): errors.append('font directory not found')
    selected=None
    if a.pages:
        try:
            selected=set()
            for part in a.pages.split(','):
                if '-' in part:
                    lo,hi=map(int,part.split('-',1));selected.update(range(lo,hi+1))
                else:selected.add(int(part))
        except Exception:errors.append('invalid --pages expression')
    if not errors:
        for old in out.glob('slide-*.png'):old.unlink()
        with tempfile.TemporaryDirectory() as td:
            profile=(Path(td)/'lo-profile').resolve()
            profile.mkdir()
            env=os.environ.copy()
            if font_dir:
                conf=Path(td)/'fonts.conf'; conf.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{font_dir}</dir><include ignore_missing="yes">/etc/fonts/fonts.conf</include></fontconfig>',encoding='utf-8'); env['FONTCONFIG_FILE']=str(conf)
            cp=subprocess.run([soffice,f'-env:UserInstallation={profile.as_uri()}','--headless','--convert-to','pdf','--outdir',td,str(src)],capture_output=True,text=True,env=env)
            pdf=Path(td)/(src.stem+'.pdf')
            if cp.returncode or not pdf.exists(): errors.append('LibreOffice conversion failed: '+(cp.stderr or cp.stdout).strip())
            else:
                prefix=out/'slide'; rp=subprocess.run([pdftoppm,'-png','-r',str(a.dpi),str(pdf),str(prefix)],capture_output=True,text=True)
                if rp.returncode: errors.append('pdftoppm failed: '+rp.stderr.strip())
                all_pages=sorted(out.glob('slide-*.png'),key=lambda x:int(x.stem.split('-')[-1])); pages=[str(x.resolve()) for i,x in enumerate(all_pages,1) if selected is None or i in selected]
                if selected and len(pages)!=len(selected):errors.append('one or more requested pages do not exist')
    digest=None
    if src.is_file():
        h=hashlib.sha256()
        with src.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
        digest=h.hexdigest()
    report={'schema':'ai-ppt-plus/render/v1','ok':not errors and bool(pages),'source':str(src),'deck_sha256':digest,'renderer':'LibreOffice+Poppler','font_dir':str(font_dir) if font_dir else None,'dpi':a.dpi,'selected_pages':sorted(selected) if selected else 'all','pages':pages,'errors':errors}
    if a.report:
        Path(a.report).parent.mkdir(parents=True,exist_ok=True)
        Path(a.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False)); return 0 if report['ok'] else 2
if __name__=='__main__': raise SystemExit(main())
