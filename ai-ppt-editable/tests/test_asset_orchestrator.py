from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from PIL import Image

from reconstruction.asset_orchestrator import AssetGenerationError, bind_generated_asset, validate_generated_asset


def _deck():
    return {"units":"fraction","slides":[{"icons":[{"object_id":"icon","x":0.8,"y":0.1,"w":0.08,"h":0.08,"file":"old.png"}]}]}

def _request(mode="transparent"):
    return {"finding_id":"f1","object_id":"icon","generation_prompt":"matching line icon","background_mode":mode,"preserve_geometry":{"x":0.8,"y":0.1,"w":0.08,"h":0.08}}

def _png(path:Path,mode:str):
    if mode=="transparent":
        image=Image.new("RGBA",(32,32),(0,0,0,0)); bg=None
    elif mode=="green":
        image=Image.new("RGB",(32,32),(0,255,0)); bg="green"
    elif mode=="red":
        image=Image.new("RGB",(32,32),(255,0,0)); bg="red"
    for x in range(8,24):
        for y in range(8,24): image.putpixel((x,y),(255,255,255,255) if image.mode=="RGBA" else (255,255,255))
    image.save(path,format="PNG")

def test_transparent_asset_validates_and_binds_without_geometry_drift():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"icon.png"; _png(path,"transparent"); digest=hashlib.sha256(path.read_bytes()).hexdigest()
        result=validate_generated_asset(_request(),{"object_id":"icon","file":str(path),"background_mode":"transparent","sha256":digest})
        assert result.visible_alpha_bbox==[0.25,0.25,0.75,0.75]; assert result.alpha_centroid==[0.5,0.5]
        bound=bind_generated_asset(_deck(),_request(),result); icon=bound["deck"]["slides"][0]["icons"][0]
        assert icon["file"]==str(path.resolve()); assert icon["source_sha256"]==digest
        assert icon["x"]==0.8 and icon["y"]==0.1 and icon["w"]==0.08 and icon["h"]==0.08
        assert icon["generation_provenance"]["kind"]=="native_image_generation"

def test_alpha_visible_bbox_alignment_delegates_uniform_transform_without_slot_drift():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"asymmetric.png"; image=Image.new("RGBA",(100,100),(0,0,0,0))
        for x in range(20,60):
            for y in range(10,70): image.putpixel((x,y),(255,255,255,255))
        image.save(path,format="PNG"); request=_request(); request["align_visible_alpha"]=True
        result=validate_generated_asset(request,{"object_id":"icon","file":str(path),"background_mode":"transparent"})
        assert result.visible_alpha_bbox==[0.2,0.1,0.6,0.7]; assert result.alpha_centroid==[0.4,0.4]
        bound=bind_generated_asset(_deck(),request,result); icon=bound["deck"]["slides"][0]["icons"][0]
        assert (icon["x"],icon["y"],icon["w"],icon["h"])==(0.8,0.1,0.08,0.08)
        assert icon["placement_mode"]=="alpha-centroid-fit" and icon["align_by_alpha"] is True
        assert bound["report"]["placement_transform"]=="alpha-centroid-fit"
        assert bound["report"]["intended_visible_slot"]==request["preserve_geometry"]
        assert bound["report"]["local_crop_bbox"] is not None
        assert icon["generation_provenance"]["alpha_centroid"]==[0.4,0.4]

def test_green_and_red_key_backgrounds_are_accepted_and_get_foreground_geometry():
    with tempfile.TemporaryDirectory() as tmp:
        for mode in ("green","red"):
            path=Path(tmp)/f"{mode}.png"; _png(path,mode)
            result=validate_generated_asset(_request(mode),{"object_id":"icon","file":str(path),"background_mode":mode})
            assert result.background_mode==mode; assert result.visible_alpha_bbox==[0.25,0.25,0.75,0.75]

def test_background_mismatch_and_bad_hash_fail_closed():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"green.png"; _png(path,"green")
        try: validate_generated_asset(_request("transparent"),{"object_id":"icon","file":str(path),"background_mode":"green"})
        except AssetGenerationError as exc: assert "background_mode mismatch" in str(exc)
        else: raise AssertionError("expected background mode mismatch")
        try: validate_generated_asset(_request("green"),{"object_id":"icon","file":str(path),"background_mode":"green","sha256":"0"*64})
        except AssetGenerationError as exc: assert "sha256" in str(exc)
        else: raise AssertionError("expected hash mismatch")

def test_transparent_asset_rejects_opaque_matte_corners():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"fake-transparent.png"; image=Image.new("RGBA",(32,32),(255,255,255,255))
        for x in (15,16):
            for y in (15,16): image.putpixel((x,y),(255,255,255,0))
        image.save(path,format="PNG")
        try: validate_generated_asset(_request("transparent"),{"object_id":"icon","file":str(path),"background_mode":"transparent"})
        except AssetGenerationError as exc: assert "corners" in str(exc)
        else: raise AssertionError("expected opaque matte corners to fail transparent validation")

def test_object_binding_mismatch_fails_closed():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/"icon.png"; _png(path,"transparent")
        try: validate_generated_asset(_request(),{"object_id":"other","file":str(path),"background_mode":"transparent"})
        except AssetGenerationError as exc: assert "object_id" in str(exc)
        else: raise AssertionError("expected object id mismatch")

if __name__=="__main__":
    for name,value in sorted(globals().items()):
        if name.startswith("test_") and callable(value): value()
    print("Asset orchestrator tests passed")
