"""Private 18-game-screenshot reference atlas for the V6 new master sculpture.

Only geometric crops of the original camera pixels; no AI replacement, inpaint
or automatic claim of orthographic reconstruction. Never publish this output
to a public GitHub branch without explicit consent from the image owner.

Use: python scripts/build_v6_reference_atlas.py ORIGINALS --output-dir PRIVATE_DIR
"""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

CROPS={
    "01_FRONT":("1000133134.jpg",(594,115,1002,674)),
    "02_BACK":("1000133132.jpg",(470,83,967,671)),
    "03_LEFT":("1000133131.jpg",(623,117,1032,688)),
    "04_RIGHT":("1000133129.jpg",(594,119,1036,701)),
    "05_THREE_QUARTER":("1000133130.jpg",(574,121,1055,675)),
    "06_FACE_MACRO":("1000133508.jpg",(418,89,965,586)),
    "07_WING_ROOT":("1000133501.jpg",(261,0,1155,724)),
    "08_BACK_WING_STAR":("1000133502.jpg",(330,0,1210,688)),
    "09_HAIR_BACK":("1000133503.jpg",(343,1,1030,730)),
    "10_BOOTS_LACES":("1000133499.jpg",(520,0,1150,861)),
    "11_SLEEVES_STRAPS":("1000133497.jpg",(570,0,1170,810)),
    "12_SLEEVE_SIDE":("1000133500.jpg",(355,0,1155,836)),
    "13_HAIR_SIDE":("1000133504.jpg",(290,0,1020,751)),
    "14_BOOT_PROFILE":("1000133505.jpg",(320,0,935,851)),
    "15_FACE_3Q":("1000133498.jpg",(377,1,975,713)),
}
ALL_ORIGINALS={f"1000133{i}.jpg" for i in range(127,135)}
ALL_ORIGINALS.update({"1000133497.jpg","1000133498.jpg","1000133499.jpg",
                      "1000133500.jpg","1000133501.jpg","1000133502.jpg",
                      "1000133503.jpg","1000133504.jpg","1000133505.jpg","1000133508.jpg"})


def build(input_dir:Path,dest:Path,archive:bool=False):
    if dest.exists() and any(dest.iterdir()):
        raise ValueError("Reference output directory must be empty")
    missing=[f for f in sorted(ALL_ORIGINALS) if not (input_dir/f).is_file()]
    if missing:
        raise ValueError("Missing original in-game screenshot(s): "+str(missing))
    dest.mkdir(parents=True,exist_ok=True)
    originals=dest/"ORIGINALS"
    cuts=dest/"TRUTH_CROPS"
    originals.mkdir()
    cuts.mkdir()
    manifest={
        "dataset":"18 privately supplied ORIGINAL game screenshots",
        "not_orthographic":True,
        "original_game_mesh_available":False,
        "private_source_do_not_upload_public":True,
        "artistic_master_approved":False,
        "print_ready_certified":False,
        "originals":{},"views":{}
    }
    for fname in sorted(ALL_ORIGINALS):
        data=(input_dir/fname).read_bytes()
        im=Image.open(input_dir/fname)
        im.verify()
        Image.open(input_dir/fname).load()
        (originals/fname).write_bytes(data)
        manifest["originals"][fname]={
            "sha256":hashlib.sha256(data).hexdigest(),
            "size":list(Image.open(input_dir/fname).size)
        }
    atlas=Image.new("RGB",(1720,1100),(235,236,239))
    draw=ImageDraw.Draw(atlas)
    views=["01_FRONT","02_BACK","03_LEFT","04_RIGHT",
           "06_FACE_MACRO","08_BACK_WING_STAR","10_BOOTS_LACES","11_SLEEVES_STRAPS"]
    for label,(fname,bbox) in CROPS.items():
        original=Image.open(input_dir/fname).convert("RGB")
        if bbox[0]<0 or bbox[1]<0 or bbox[2]>original.width or bbox[3]>original.height:
            raise ValueError("Crop exceeds original frame: "+fname)
        crop=original.crop(bbox)
        path=cuts/(label+".png")
        crop.save(path,optimize=True)
        manifest["views"][label]={"filename":fname,"bbox_px":list(bbox),
                                 "exact_camera_crop_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                                 "camera_view_not_calibrated":True}
        if label in views:
            index=views.index(label)
            frame=crop.copy()
            frame.thumbnail((405,502),Image.Resampling.LANCZOS)
            x=index%4*430+(430-frame.width)//2
            y=index//4*550+32
            atlas.paste(frame,(x,y))
            draw.rectangle([index%4*430+8,index//4*550+4,
                            index%4*430+422,index//4*550+29],
                           fill=(35,37,43))
            draw.text((index%4*430+18,index//4*550+10),
                      label,fill=(249,250,255))
    atlas.save(dest/"V6_ATLAS_UNALTERED_CROPS.png",optimize=True)
    (dest/"REFERENCE_MANIFEST.json").write_text(
        json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
    (dest/"IMPORTANT_RU.txt").write_text(
        "V6: 18 настоящих скриншотов и 15 точных кропов, без AI-дорисовки.\n"
        "Эти изображения НЕ ортографические, перспектива и трава мешают точным "
        "измерениям. Только вспомогательные данные для новой мастер-скульптуры.\n"
        "НЕ публиковать приватный пакет в открытом GitHub без разрешения.\n"
        "AI-концепт не заменяет подлинный референс.\n",
        encoding="utf-8")
    if archive:
        zpath=dest.parent/(dest.name+"_PRIVATE.zip")
        with zipfile.ZipFile(zpath,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as zipfileout:
            for file in sorted(dest.rglob("*")):
                if file.is_file():
                    zipfileout.write(file,str(file.relative_to(dest)))
        return manifest,zpath
    return manifest,None


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("input_dir",type=Path)
    cli.add_argument("--output-dir",type=Path,required=True)
    cli.add_argument("--zip",action="store_true")
    args=cli.parse_args()
    result,location=build(args.input_dir,args.output_dir,args.zip)
    print("V6_ORIGINALS_PROCESSED",len(result["originals"]),
          "V6_TRUE_CAMERA_CROPS",len(result["views"]),"PRIVATE_ARCHIVE",location)


if __name__=="__main__":
    main()
