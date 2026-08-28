#!/usr/bin/env python3
"""Check font-family availability and CJK fallback before PPTX generation.

Usage: probe_fonts.py --output font-report.json [--font-dir DIR] [--font "Noto Sans CJK SC"]...
Output: JSON report. Exit 0 if probe completed, 2 if fontconfig is unavailable.
Read-only and idempotent. Requires fc-match from fontconfig.
Example: probe_fonts.py -o font-report.json --font "Noto Sans CJK SC"
"""
import argparse, json, os, shutil, subprocess, tempfile
from datetime import datetime, timezone
from pathlib import Path
from atomic_output import atomic_write_json
# Keep the probe's implicit route on redistributable/open families.  A
# proprietary family can still be requested explicitly with --font after the
# caller has established its license and device availability.
DEFAULT=['Noto Sans CJK SC','Noto Sans SC','WenQuanYi Zen Hei']
def license_status(font_dir):
    if not font_dir or not font_dir.is_dir():
        return {'status':'not_applicable','files':[]}
    names={'license','licence','copying','notice','readme'}
    files=sorted(str(x) for x in font_dir.rglob('*') if x.is_file() and x.name.lower().split('.')[0] in names)
    return {'status':'declared' if files else 'unverified','files':files}
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);ap.add_argument('--output','-o',required=True);ap.add_argument('--font-dir');ap.add_argument('--font',action='append',default=[]);ap.add_argument('--require-cjk',action='store_true',help='return a failing exit code when no CJK-capable family resolves');a=ap.parse_args(); tool=shutil.which('fc-match')
    if not tool:
        out={'schema':'ai-ppt-plus/font-report/v1','ok':False,'error':'fc-match not found','fonts':[]};atomic_write_json(Path(a.output), out);print(json.dumps(out,ensure_ascii=False));return 2
    font_dir=Path(a.font_dir).resolve() if a.font_dir else None
    font_env=os.environ.copy(); temp_config=None
    if font_dir and font_dir.is_dir():
        temp_config=tempfile.TemporaryDirectory(prefix='ai-ppt-fontconfig-')
        config=Path(temp_config.name)/'fonts.conf'
        config.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><dir>{font_dir}</dir><include ignore_missing="yes">/etc/fonts/fonts.conf</include></fontconfig>',encoding='utf-8')
        font_env['FONTCONFIG_FILE']=str(config)
    local_files=sorted(str(x) for x in font_dir.rglob('*') if x.suffix.lower() in {'.ttf','.otf','.ttc'} ) if font_dir and font_dir.is_dir() else []
    local_families=[]
    scan=shutil.which('fc-scan')
    for f in local_files:
        cp=subprocess.run([scan,'-f','%{family}\n',f],capture_output=True,text=True,env=font_env) if scan else None
        local_families.extend(x for x in (cp.stdout.splitlines() if cp and cp.returncode==0 else []) if x)
    records=[]
    requested_fonts=list(a.font)
    if not requested_fonts and local_families:
        discovered=sorted({family.split(',')[0].strip() for family in local_families if family.strip()})
        requested_fonts=discovered+DEFAULT
    for requested in requested_fonts or DEFAULT:
        cp=subprocess.run([tool,'-f','%{family}\n',requested],capture_output=True,text=True,env=font_env); resolved=cp.stdout.strip().split('\n')[0] if cp.returncode==0 else None
        exact=bool((resolved and requested.lower() in resolved.lower()) or any(requested.lower() in x.lower() for x in local_families))
        records.append({'requested':requested,'resolved':resolved,'exact_or_family_match':exact,'cjk_ready':exact})
    cjk_supported=any(x['cjk_ready'] for x in records)
    license_info=license_status(font_dir)
    out={'schema':'ai-ppt-plus/font-report/v1','ok':True,'generated_at':datetime.now(timezone.utc).isoformat(),'font_dir':str(font_dir) if font_dir else None,'local_font_files':local_files,'local_font_families':sorted(set(local_families)),'fonts':records,'cjk_delivery_supported':cjk_supported,'font_status':{'files_found':bool(local_files),'family_discovered':bool(local_families),'glyph_route_available':cjk_supported,'render_review':'required','license':license_info['status'],'license_files':license_info['files'],'redistribution':'unverified' if license_info['status']!='declared' else 'requires_project_review'},'rule':'Do not declare Chinese render validation passed unless cjk_delivery_supported is true and rendered pages are visually reviewed. Do not imply redistribution permission from font discovery.'}
    if a.require_cjk and not cjk_supported:
        out['ok']=False
        out['error']='cjk_font_unresolved'
    atomic_write_json(Path(a.output), out);print(json.dumps(out,ensure_ascii=False));
    if temp_config: temp_config.cleanup()
    return 0 if out.get('ok') is True else 2
if __name__=='__main__':raise SystemExit(main())
