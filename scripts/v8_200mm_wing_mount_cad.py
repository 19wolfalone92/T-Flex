#!/usr/bin/env python3
"""Independent V8 200 mm wing-fastener CAD prototype; NOT attached to the sculpt."""
import json,sys
from pathlib import Path
import cadquery as cq
import trimesh
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader

P={'width':42.,'height':17.,'plate_thickness':4.5,'wing_centres':12.5,
   'gap':5.,'peg_spacing':7.5,'peg_diameter':3.2,'peg_length':10.7,
   'radial_clearance':.2,'hub_width':16.8,'hub_height':13.8,
   'hub_depth':10.,'bore_depth':7.,'handed_vertical_offset':2.9}
def cyl(r,length,x,y,z):
    return cq.Solid.makeCylinder(r,length,cq.Vector(x,y,z),cq.Vector(0,1,0))
def make():
    p=P;assert p['peg_length']-p['gap']>4.5
    assert p['bore_depth']+1.5<p['hub_depth']
    assert p['hub_width']>p['peg_spacing']+p['peg_diameter']+2*p['radial_clearance']+2
    bridge=cq.Workplane('XY').box(p['width'],p['plate_thickness'],p['height']).val()
    face=p['plate_thickness']/2
    parts={}
    for s,label in [(-1,'LEFT'),(1,'RIGHT')]:
        xc=s*p['wing_centres'];centres=[(xc-p['peg_spacing']/2,0.),
                                  (xc+p['peg_spacing']/2,s*p['handed_vertical_offset'])]
        for x,z in centres:bridge=bridge.fuse(cyl(p['peg_diameter']/2,p['peg_length'],x,face,z))
        front=face+p['gap']
        hub=(cq.Workplane('XY').box(p['hub_width'],p['hub_depth'],p['hub_height'])
             .translate((xc,front+p['hub_depth']/2,0)).val())
        for x,z in centres:
            hub=hub.cut(cyl(p['peg_diameter']/2+p['radial_clearance'],p['bore_depth'],x,front,z))
        parts[f'WING_{label}_TEST_HUB']=hub
    bridge=bridge.clean();parts['BACK_HIDDEN_TEST_BRIDGE']=bridge
    assert all(part.isValid() and len(part.Solids())==1 for part in parts.values())
    for n,part in parts.items():
        if n!='BACK_HIDDEN_TEST_BRIDGE':assert part.intersect(bridge).Volume()<.005
    return parts
def main(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    parts=make()
    for d in ['STEP','STL','CALIBRATION']:(out/d).mkdir(exist_ok=True)
    qa={}
    for name,part in parts.items():
        cq.exporters.export(part,str(out/'STEP'/f'{name}.step'),exportType='STEP')
        path=out/'STL'/f'{name}.stl'
        cq.exporters.export(part,str(path),exportType='STL',tolerance=.035)
        mesh=trimesh.load_mesh(path,force='mesh')
        assert mesh.is_volume and mesh.is_watertight and mesh.volume>0
        qa[name]=round(float(mesh.volume),2)
    compound=out/'V8_200MM_WING_MOUNT_PROTOTYPE.step'
    cq.exporters.export(cq.Compound.makeCompound(list(parts.values())),str(compound),exportType='STEP')
    r=STEPControl_Reader();assert r.ReadFile(str(compound))==IFSelect_RetDone
    assert r.TransferRoots()>0 and BRepCheck_Analyzer(r.OneShape()).IsValid()
    for radial in (.15,.20,.25):
        dia=P['peg_diameter']+2*radial
        part=(cq.Workplane('XY').box(12,12,9,centered=(True,True,False))
              .cut(cq.Workplane('XY').circle(dia/2).extrude(9)).val())
        path=out/'CALIBRATION'/f'BORE_{dia:.2f}mm_RADIAL_{radial:.2f}.stl'
        cq.exporters.export(part,str(path),exportType='STL')
        assert trimesh.load_mesh(path).is_volume
    pin=cq.Solid.makeCylinder(P['peg_diameter']/2,9,cq.Vector(0,0,0))
    cq.exporters.export(pin,str(out/'CALIBRATION'/'PEG_3.20mm.stl'),exportType='STL')
    info={'prototype_for_figure_mm':200,'params':P,'parts_volume_mm3':qa,
          'step_valid':True,'original_character_wings_attached':False,
          'printer_fit_tested':False,'load_tested':False,
          'print_ready_certified':False}
    (out/'HARDWARE_QA.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(info,indent=2))
if __name__=='__main__':main(sys.argv[1])
