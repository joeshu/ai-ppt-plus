#!/usr/bin/env python3
"""Probe only real local capabilities before choosing an AI PPT Plus backend.

Usage: probe_environment.py --output environment-report.json
Output: machine-readable capability report. Exit 0 always when the report is
written; consumers must inspect each capability's `available` value. This is
read-only and idempotent. Standard library only.
Example/test: python probe_environment.py --output environment-report.json
"""
import argparse, importlib.util, json, os, shutil, sys
from datetime import datetime, timezone
from pathlib import Path

def command(name):
    path=shutil.which(name)
    return {'available':bool(path),'path':path,'evidence':'PATH lookup'}
def module(name):
    spec=importlib.util.find_spec(name)
    return {'available':spec is not None,'path':getattr(spec,'origin',None),'evidence':'Python import discovery'}
def ppt_master():
    raw=os.environ.get('PPT_MASTER_SKILL_DIR')
    path=Path(raw).expanduser() if raw else None
    valid=bool(path and path.is_dir() and (path/'SKILL.md').is_file())
    return {'available':valid,'path':str(path) if path else None,'evidence':'PPT_MASTER_SKILL_DIR plus SKILL.md check','reason':None if valid else 'set PPT_MASTER_SKILL_DIR to an installed PPT Master skill directory'}
def authoring_runtime():
    node=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE')
    modules=os.environ.get('CODEX_PRIMARY_RUNTIME_NODE_MODULES')
    node_path=Path(node).expanduser() if node else None
    modules_path=Path(modules).expanduser() if modules else None
    node_ok=bool(node_path and node_path.is_file() and os.access(node_path,os.X_OK))
    package=modules_path/'@oai'/'artifact-tool'/'package.json' if modules_path else None
    package_ok=bool(package and package.is_file())
    return {'available':node_ok and package_ok,'node':str(node_path) if node_path else None,'modules':str(modules_path) if modules_path else None,'artifact_tool_package':str(package) if package else None,'evidence':'runtime node executable plus @oai/artifact-tool package check','reason':None if node_ok and package_ok else 'runtime node and @oai/artifact-tool must both be discoverable'}
def main():
    ap=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter);ap.add_argument('--output','-o',required=True);a=ap.parse_args()
    caps={
      'pptx_authoring_runtime': authoring_runtime(),
      'libreoffice_renderer': command('soffice'),
      'poppler_renderer': command('pdftoppm'),
      'pdf_text_extractor': command('pdftotext'),
      'pandoc_converter': command('pandoc'),
      'pymupdf': module('fitz'), 'docx_reader': module('docx'), 'xlsx_reader': module('openpyxl'), 'image_reader': module('PIL'), 'ppt_master':ppt_master()}
    backend='artifact-tool' if caps['pptx_authoring_runtime']['available'] else 'interface_only'
    rendering='libreoffice+poppler' if caps['libreoffice_renderer']['available'] and caps['poppler_renderer']['available'] else 'unavailable'
    out={'schema':'ai-ppt-plus/environment-report/v1','generated_at':datetime.now(timezone.utc).isoformat(),'python':sys.version.split()[0],'capabilities':caps,'selection':{'authoring_backend':backend,'rendering_backend':rendering,'ppt_master_adapter':'enabled' if caps['ppt_master']['available'] else 'not_selected','active_backend':backend+' + '+rendering},'rules':['Use only capabilities marked available.','Use PPT Master only after explicit directory discovery and its own documented integrity check.','Unavailable capability requires compatible adapter, declared fallback, or blocked/interface-only state.']}
    Path(a.output).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(out,ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
