"""V6 wing system: two handed, non-rotating, hidden double-pin mounts.

CAD engineering prototype only. Never substitute these test carriers for the
real character wings: AFTER master geometry approval the carriers must be
boolean-integrated into genuine wing and torso volumes.

Coordinates are local millimetres (X left/right, +Y backwards, Z up).
No physical fit/strength certification until printer and filament are known.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import json

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader


@dataclass(frozen=True)
class WingMountConfig:
    width_mm: float = 32.0
    height_mm: float = 12.5
    plate_thickness_mm: float = 3.4
    wing_center_offset_x_mm: float = 9.5
    body_to_wing_hub_gap_mm: float = 4.0
    peg_center_spacing_mm: float = 5.8
    peg_nominal_diameter_mm: float = 2.6
    peg_length_mm: float = 8.2
    radial_clearance_mm: float = .2
    hub_width_mm: float = 12.6
    hub_depth_mm: float = 8.2
    hub_height_mm: float = 11.2
    mating_bore_depth_mm: float = 5.6
    handed_second_peg_vertical_offset_mm: float = 2.6

    def validate(self):
        if not .1 <= self.radial_clearance_mm <= .35:
            raise ValueError("Radial clearance outside trial range")
        if not 2 <= self.peg_nominal_diameter_mm <= 4:
            raise ValueError("Peg diameter outside trial range")
        r = self.peg_nominal_diameter_mm/2 + self.radial_clearance_mm
        if self.peg_center_spacing_mm <= 2*r+1:
            raise ValueError("Bores too close")
        if self.hub_width_mm < self.peg_center_spacing_mm+2*r+2:
            raise ValueError("Hub X wall too thin")
        if self.hub_height_mm < 2*(abs(self.handed_second_peg_vertical_offset_mm)+r+1.5):
            raise ValueError("Hub Z wall too thin")
        if self.body_to_wing_hub_gap_mm <= 2:
            raise ValueError("Floating wing separation too low")
        penetration = self.peg_length_mm-self.body_to_wing_hub_gap_mm
        if penetration <= 3 or penetration + .3 > self.mating_bore_depth_mm:
            raise ValueError("Pin bottoming or insufficient engagement")
        if self.mating_bore_depth_mm + 1.5 > self.hub_depth_mm:
            raise ValueError("Blind socket punches through wall")


def cyl_y(radius, length, x, y, z):
    return cq.Solid.makeCylinder(radius, length, cq.Vector(x,y,z),
                                 cq.Vector(0,1,0))


def make_mount(config: WingMountConfig = WingMountConfig()):
    config.validate()
    c = config
    plate = cq.Workplane("XY").box(c.width_mm,c.plate_thickness_mm,
                                    c.height_mm).val()
    yface = c.plate_thickness_mm/2
    hub_front = yface+c.body_to_wing_hub_gap_mm
    parts = {}
    info = []
    for sign, name in ((-1,"LEFT"),(1,"RIGHT")):
        cx = sign*c.wing_center_offset_x_mm
        points = [(cx-c.peg_center_spacing_mm/2,0),
                  (cx+c.peg_center_spacing_mm/2,
                   sign*c.handed_second_peg_vertical_offset_mm)]
        for x,z in points:
            plate = plate.fuse(cyl_y(c.peg_nominal_diameter_mm/2,
                                     c.peg_length_mm,x,yface,z))
        hub = (cq.Workplane("XY")
                .box(c.hub_width_mm,c.hub_depth_mm,c.hub_height_mm)
                .translate((cx,hub_front+c.hub_depth_mm/2,0)).val())
        for x,z in points:
            hub = hub.cut(cyl_y(c.peg_nominal_diameter_mm/2 +
                                c.radial_clearance_mm,
                                c.mating_bore_depth_mm,x,hub_front,z))
        if not hub.isValid() or len(hub.Solids()) != 1:
            raise ValueError("Invalid wing-root socket carrier")
        parts["WING_"+name+"_KEYED_SOCKET_CARRIER"]=hub
        info.append({"side":name.lower(),
                     "peg_centres_xz_mm":[list(q) for q in points],
                     "pin_diameter_mm":c.peg_nominal_diameter_mm,
                     "bore_diameter_mm":c.peg_nominal_diameter_mm+2*c.radial_clearance_mm,
                     "body_to_hub_gap_mm":c.body_to_wing_hub_gap_mm,
                     "end_clearance_mm":c.mating_bore_depth_mm -
                                        (c.peg_length_mm-c.body_to_wing_hub_gap_mm),
                     "two_handed_non_collinear_keys":True})
    plate=plate.clean()
    if not plate.isValid() or len(plate.Solids()) != 1:
        raise ValueError("Invalid central mount")
    parts["CENTRAL_HIDDEN_BLACK_BRIDGE"]=plate
    for name,hub in parts.items():
        if name.startswith("WING_") and plate.intersect(hub).Volume() > .005:
            raise ValueError("Interfering pegs/holes: "+name)
    return parts,info


def export_fixture(output: Path, config: WingMountConfig=WingMountConfig()):
    """Export actual closed STEP/STL prototypes, not fake character files."""
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("No destructive overwrite")
    output.mkdir(parents=True,exist_ok=True)
    parts,info=make_mount(config)
    for folder in ("STL_PRINT","STL_ASSEMBLY","STEP_TFLEX18","CALIBRATION"):
        (output/folder).mkdir()
    scene=trimesh.Scene()
    summary={}
    for name,shape in sorted(parts.items()):
        source=output/"STL_ASSEMBLY"/(name+".stl")
        cq.exporters.export(shape,str(source),exportType="STL",
                            tolerance=.04,angularTolerance=.12)
        mesh=trimesh.load_mesh(source,force="mesh")
        if not(mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0):
            raise RuntimeError("CAD-to-STL regression "+name)
        preview=mesh.copy()
        rgba=(25,30,38,255) if name.startswith("CENTRAL") else (115,162,230,255)
        preview.visual.vertex_colors=np.tile(np.asarray(rgba,dtype=np.uint8),
                                              (len(preview.vertices),1))
        scene.add_geometry(preview,geom_name=name)
        bed=mesh.copy()
        bed.apply_translation([0,0,-float(bed.bounds[0][2])])
        bed.export(str(output/"STL_PRINT"/(name+"_ON_BED.stl")))
        cq.exporters.export(shape,str(output/"STEP_TFLEX18"/(name+".step")),
                            exportType="STEP")
        summary[name]={"faces":len(mesh.faces),"closed":bool(mesh.is_watertight),
                       "volume_mm3":round(float(mesh.volume),3)}
    assembly=output/"Wing_Mount_V6_TFLEX18_Assembly.step"
    cq.exporters.export(cq.Compound.makeCompound(list(parts.values())),
                        str(assembly),exportType="STEP")
    step=STEPControl_Reader()
    if step.ReadFile(str(assembly))!=IFSelect_RetDone or step.TransferRoots() <= 0:
        raise RuntimeError("STEP export cannot be read back")
    if not BRepCheck_Analyzer(step.OneShape()).IsValid():
        raise RuntimeError("STEP invalid when re-imported")
    scene.export(str(output/"Wing_Mount_V6_MOBILE_PREVIEW.glb"))
    for radial in (.15,.20,.25):
        diameter=config.peg_nominal_diameter_mm+2*radial
        coupon=(cq.Workplane("XY")
                .box(11,11,7,centered=(True,True,False))
                .cut(cq.Workplane("XY").circle(diameter/2).extrude(7)).val())
        filename=output/"CALIBRATION"/(f"SOCKET_TEST_{diameter:.2f}mm.stl")
        cq.exporters.export(coupon,str(filename),exportType="STL")
        if not trimesh.load_mesh(filename).is_volume:
            raise RuntimeError("Invalid fit coupon")
    pin=cyl_y(config.peg_nominal_diameter_mm/2,7,0,0,0)
    cq.exporters.export(pin,str(output/"CALIBRATION"/"SAMPLE_PIN_2.60mm.stl"),
                        exportType="STL")
    qa={
        "type":"wing-fastener-only/proof-of-concept",
        "not_a_real_character_model":True,
        "requires_accepted_V6_master_before_integrating_into_wings":True,
        "config":asdict(config),"parts":summary,"wing_joints":info,
        "geometry_watertight":True,"step_readback_valid":True,
        "print_ready_certified":False,
        "unverified":["true wing root placement","printer fit and creep",
                      "wing bending strength","support visibility",
                      "body interference","nozzle and filament"]
    }
    (output/"QA_MANIFEST.json").write_text(
        json.dumps(qa,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"READ_ME_RU.txt").write_text(
        "V6: ИСПЫТАТЕЛЬНЫЙ КРЕПЁЖ КРЫЛЬЕВ, НЕ ГОТОВАЯ ФИГУРКА.\n"
        "Два асимметричных штифта на крыло исключают вращение; "
        "отступ от спины 4 мм. Повторный импорт STEP пройден.\n"
        "Подбирать зазор на образцах 0,15/0,20/0,25 мм. "
        "Монтаж к реальному туловищу возможен только после приёмки "
        "внешности новой мастер-модели V6.\n",encoding="utf-8")
    return qa


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    export_fixture(args.output)


if __name__=="__main__":
    main()
