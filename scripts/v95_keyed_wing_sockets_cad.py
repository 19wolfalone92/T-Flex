"""V95: physical, twin-key anti-rotation female wing receivers.

Receivers are individual CAD STEP/STL prototypes; their union with the
character's REAL torso is still blocked pending an artist-approved 3D body.
"""
from pathlib import Path
import argparse,json,hashlib
import cadquery as cq
import trimesh

MALE_PIN_DIAMETER=3.10
FEMALE_HOLE_DIAMETER=3.50

def socket(side,center_x,out):
    body=cq.Workplane("XY").box(12,7,18).translate((center_x,7.9,115.0))
    for z in (111.,119.):
        bore=cq.Solid.makeCylinder(1.75,6.0,
            cq.Vector(center_x,12.0,z),cq.Vector(0,-1,0))
        body=body.cut(bore)
    mark=cq.Workplane("XY").box(4,.55,1).translate((center_x,11.,124.))
    body=body.cut(mark)
    if not body.val().isValid():raise ValueError("Invalid CAD receiver")
    name=f"V95_{side}_FEMALE_RECEIVER_NOT_IN_BODY"
    stl=out/(name+".stl");step=out/(name+".step")
    cq.exporters.export(body,str(stl),exportType="STL",tolerance=.055,angularTolerance=.1)
    cq.exporters.export(body,str(step),exportType="STEP")
    m=trimesh.load(stl)
    if not m.is_watertight or m.body_count!=1:
        raise AssertionError("Receiver STL not one closed volume")
    return {"side":side,"center_x_mm":center_x,"female_hole_diameter_mm":3.5,
        "wing_male_pin_diameter_mm":MALE_PIN_DIAMETER,"vertical_pitch_mm":8,
        "diametric_clearance_mm":.4,"analytic_cad_valid":True,
        "stl_watertight":True,"socket_volume_mm3":round(body.val().Volume(),2),
        "step_sha256":hashlib.sha256(step.read_bytes()).hexdigest(),
        "real_torso_union_completed":False}

def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    receivers=[socket("LEFT",-17.,out),socket("RIGHT",19.,out)]
    coupon=cq.Workplane("XY").box(24,8,8).translate((0,7,0))
    for x,diam in ((-7.5,3.3),(0.,3.5),(7.5,3.7)):
        coupon=coupon.cut(cq.Solid.makeCylinder(diam/2,8.6,
            cq.Vector(x,11.3,0),cq.Vector(0,-1,0)))
    cq.exporters.export(coupon,str(out/"V95_RESIN_BORE_FIT_3p3_3p5_3p7.stl"),
                        exportType="STL")
    report={"figure_target_height_mm":200,"receivers":receivers,
       "resin_test_bores_mm":[3.3,3.5,3.7],
       "physically_tested":False,"real_body_merged":False,
       "final_print_ready":False}
    (out/"V95_FEMALE_RECEIVER_QA.json").write_text(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--output",type=Path,required=True)
    print(json.dumps(build(p.parse_args().output),indent=2))
