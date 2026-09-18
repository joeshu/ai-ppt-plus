#!/usr/bin/env python3
"""Strict native-ImageGen handoff with alpha geometry and placement binding."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib
from pathlib import Path
from typing import Any

ALLOWED_BACKGROUND_MODES={"transparent","green","red","magenta","opaque","source"}
class AssetGenerationError(ValueError): pass

@dataclass(frozen=True)
class GeneratedAssetResult:
    object_id:str; file:str; sha256:str; width:int; height:int; background_mode:str
    visible_alpha_bbox:list[float]; alpha_centroid:list[float]; validation:dict[str,Any]

def _sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def _locate(deck:dict[str,Any],object_id:str)->tuple[str,dict[str,Any]]:
    matches=[]
    for slide in deck.get("slides",[]) or []:
        if not isinstance(slide,dict): continue
        for collection in ("icons","panels"):
            for item in slide.get(collection,[]) or []:
                if not isinstance(item,dict): continue
                ids={str(v) for v in (item.get("object_id"),item.get("id"),item.get("name"),item.get("panel_id")) if v}
                if object_id in ids: matches.append((collection,item))
    if not matches: raise AssetGenerationError(f"asset object {object_id!r} not found")
    if len(matches)>1: raise AssetGenerationError(f"asset object {object_id!r} is ambiguous")
    return matches[0]

def _is_green(p):
    r,g,b=p[:3]; return g>=180 and g>=r+55 and g>=b+55
def _is_red(p):
    r,g,b=p[:3]; return r>=180 and r>=g+55 and r>=b+55
def _is_magenta(p):
    r,g,b=p[:3]; return r>=180 and b>=180 and g+55<=min(r,b)

def _weight(pixel,mode):
    if mode=="transparent": return pixel[3]/255.0
    if mode=="green": return 0.0 if _is_green(pixel) else 1.0
    if mode=="red": return 0.0 if _is_red(pixel) else 1.0
    if mode=="magenta": return 0.0 if _is_magenta(pixel) else 1.0
    return pixel[3]/255.0

def _visible_geometry(rgba,mode):
    w,h=rgba.size; left,top,right,bottom=w,h,-1,-1; total=wx=wy=0.0; px=rgba.load()
    for y in range(h):
        for x in range(w):
            a=_weight(px[x,y],mode)
            if a<=0.05: continue
            left=min(left,x); top=min(top,y); right=max(right,x); bottom=max(bottom,y)
            total+=a; wx+=(x+0.5)*a; wy+=(y+0.5)*a
    if right<left or bottom<top or total<=0: raise AssetGenerationError("generated asset has no visible foreground")
    bbox=[left/w,top/h,(right+1)/w,(bottom+1)/h]; centroid=[wx/total/w,wy/total/h]
    return [round(v,8) for v in bbox],[round(v,8) for v in centroid]

def _image_evidence(path:Path,mode:str)->dict[str,Any]:
    try: from PIL import Image
    except ImportError as exc: raise AssetGenerationError("Pillow is required for generated-asset validation") from exc
    try:
        with Image.open(path) as image:
            image.load(); w,h=image.size; fmt=image.format; original_mode=image.mode; rgba=image.convert("RGBA")
            alpha=rgba.getchannel("A"); extrema=alpha.getextrema(); hist=alpha.histogram(); total=max(1,w*h)
            corners=[rgba.getpixel((0,0)),rgba.getpixel((w-1,0)),rgba.getpixel((0,h-1)),rgba.getpixel((w-1,h-1))]
            bbox,centroid=_visible_geometry(rgba,mode)
    except AssetGenerationError: raise
    except Exception as exc: raise AssetGenerationError(f"generated asset is not a readable image: {path}") from exc
    if w<=0 or h<=0: raise AssetGenerationError("generated asset dimensions must be positive")
    return {"format":fmt,"mode":original_mode,"width":w,"height":h,"alpha_min":int(extrema[0]),"alpha_max":int(extrema[1]),"transparent_fraction":sum(hist[:16])/total,"opaque_fraction":sum(hist[240:])/total,"corners":[list(p) for p in corners],"visible_alpha_bbox":bbox,"alpha_centroid":centroid}

def _local_crop_bbox(target:dict[str,Any],padding_ratio:float=0.25):
    if any(k not in target for k in ("x","y","w","h")): return None
    x,y,w,h=(float(target[k]) for k in ("x","y","w","h")); px,py=w*padding_ratio,h*padding_ratio
    return [round(max(0,x-px),8),round(max(0,y-py),8),round(min(1,x+w+px),8),round(min(1,y+h+py),8)]

def validate_generated_asset(request:dict[str,Any],response:dict[str,Any],*,base_dir:Path|None=None)->GeneratedAssetResult:
    object_id=str(request.get("object_id") or "").strip()
    if not object_id: raise AssetGenerationError("generation request object_id is required")
    if str(response.get("object_id") or "").strip()!=object_id: raise AssetGenerationError("generated asset object_id does not match request")
    expected=str(request.get("background_mode") or "transparent"); actual=str(response.get("background_mode") or expected)
    if expected not in ALLOWED_BACKGROUND_MODES or actual not in ALLOWED_BACKGROUND_MODES: raise AssetGenerationError("unsupported generated asset background_mode")
    if actual!=expected: raise AssetGenerationError(f"generated asset background_mode mismatch: expected {expected}, got {actual}")
    raw=response.get("file")
    if not isinstance(raw,str) or not raw: raise AssetGenerationError("generated asset response file is required")
    path=Path(raw); path=(base_dir/path if not path.is_absolute() and base_dir is not None else path).resolve()
    if not path.is_file(): raise AssetGenerationError(f"generated asset file does not exist: {path}")
    ev=_image_evidence(path,expected)
    if ev["format"]!="PNG": raise AssetGenerationError("generated asset must be PNG at the deterministic handoff boundary")
    corners=ev["corners"]
    if expected=="transparent":
        if ev["alpha_min"]>=250 or ev["transparent_fraction"]<0.001: raise AssetGenerationError("transparent asset has no meaningful alpha transparency")
        if any(p[3]>32 for p in corners): raise AssetGenerationError("transparent asset corners are not transparent")
    if expected=="green" and not all(_is_green(p) for p in corners): raise AssetGenerationError("green-background asset does not have green key-color corners")
    if expected=="red" and not all(_is_red(p) for p in corners): raise AssetGenerationError("red-background asset does not have red key-color corners")
    if expected=="magenta" and not all(_is_magenta(p) for p in corners): raise AssetGenerationError("magenta-background asset does not have magenta key-color corners")
    digest=_sha256(path); declared=response.get("sha256")
    if declared not in (None,"") and str(declared).lower()!=digest: raise AssetGenerationError("generated asset sha256 does not match file bytes")
    return GeneratedAssetResult(object_id,str(path),digest,int(ev["width"]),int(ev["height"]),expected,list(ev["visible_alpha_bbox"]),list(ev["alpha_centroid"]),ev)

def bind_generated_asset(deck:dict[str,Any],request:dict[str,Any],result:GeneratedAssetResult)->dict[str,Any]:
    """Bind validated bytes while preserving the semantic slot.

    When align_visible_alpha is enabled the deck keeps the immutable slot x/y/w/h
    and records placement_mode=alpha-centroid-fit.  asset_placement.py then
    computes the real outer image rectangle in slide EMUs using a uniform scale,
    so transparent padding is compensated without distorting the icon.
    """
    repaired=deepcopy(deck); _,item=_locate(repaired,result.object_id)
    before={k:item.get(k) for k in ("x","y","w","h","rotation") if k in item}; expected=dict(request.get("preserve_geometry") or {})
    for k,v in expected.items():
        if k in before and before[k]!=v: raise AssetGenerationError(f"asset geometry changed before bind for {k}")
    item["file"]=result.file; item["source_sha256"]=result.sha256; item["background_mode"]=result.background_mode
    if request.get("align_visible_alpha") is True:
        if any(k not in expected for k in ("x","y","w","h")): raise AssetGenerationError("alpha-aligned placement requires preserve_geometry x/y/w/h")
        item["placement_mode"]="alpha-centroid-fit"; item["align_by_alpha"]=True
        item["alpha_threshold"]=int(request.get("alpha_threshold",8)); item["visible_contain"]=float(request.get("visible_contain",1.0))
    after={k:item.get(k) for k in before}
    if after!=before: raise AssetGenerationError("asset bind mutated semantic slot geometry")
    placement_slot=[item.get("x"),item.get("y"),item.get("w"),item.get("h")]
    item["generation_provenance"]={"kind":"native_image_generation","finding_id":request.get("finding_id"),"generation_prompt":request.get("generation_prompt"),"generation_action":request.get("generation_action","generate"),"fallback_level":request.get("fallback_level","direct-alpha"),"cache_key":request.get("cache_key"),"sha256":result.sha256,"width":result.width,"height":result.height,"visible_alpha_bbox":result.visible_alpha_bbox,"alpha_centroid":result.alpha_centroid,"placement_slot_bbox":placement_slot,"placement_mode":item.get("placement_mode","slot-bbox")}
    return {"deck":repaired,"report":{"schema":"ai-ppt-plus/generated-asset-bind/v3","valid":True,"object_id":result.object_id,"asset":asdict(result),"intended_visible_slot":expected if request.get("align_visible_alpha") is True else None,"placement_slot_bbox":placement_slot,"placement_transform":"alpha-centroid-fit" if request.get("align_visible_alpha") is True else "none","local_crop_bbox":_local_crop_bbox(expected),"preserved_geometry":after}}
