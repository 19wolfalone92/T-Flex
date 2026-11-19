#!/usr/bin/env python3
"""V8 200 mm master-sculpt DRAFT from the V7 intermediate. NOT print-ready.

This reproducible candidate applies true geometric relief to eyes-adjacent hair,
overlapping wing feathers, fabric and leather. A correct likeness still requires
human high-poly sculpture checked against the original private 18 game views.
"""
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import trimesh

def tube(pts,r,rgba):
    p=np.asarray(pts,float);n=14
    vv=[];ff=[]; tang=np.gradient(p,axis=0)
    tang/=np.maximum(np.linalg.norm(tang,axis=1,keepdims=True),1e-9)
    for center,t in zip(p,tang):
        a=np.cross(t,[0.,1.,0.])
        if np.linalg.norm(a)<.1:a=np.cross(t,[1.,0.,0.])
        a/=np.linalg.norm(a);b=np.cross(t,a)
        for j in range(n):vv.append(center+r*(a*np.cos(math.tau*j/n)+b*np.sin(math.tau*j/n)))
    for i in range(len(p)-1):
        for j in range(n):
            k=(j+1)%n;u=i*n+j;v=i*n+k;w=(i+1)*n+j;x=(i+1)*n+k
            ff.extend(((u,w,v),(v,w,x)))
    for j in range(1,n-1):
        ff.extend(((0,j+1,j),((len(p)-1)*n,(len(p)-1)*n+j,(len(p)-1)*n+j+1)))
    m=trimesh.Trimesh(vertices=vv,faces=ff,process=True)
    trimesh.repair.fix_normals(m)
    m.visual.vertex_colors=np.tile(np.array(rgba,dtype=np.uint8),(len(m.vertices),1))
    return m

def relief(name,m):
    kind=('feather' if 'WING_' in name and any(t in name for t in ('primary_','secondary_','covert_'))
        else 'hair' if any(t in name for t in ('_bob_','_lock_','forehead_swept_','hair_main_','hair_nape_'))
        else 'fabric' if any(t in name for t in ('_sleeve_','jacket_torso','boot_tall_shaft_','boot_ankle_'))
        else '')
    if not kind:return m,False
    color=m.visual.vertex_colors[0].copy()
    m=m.subdivide()
    m.visual.vertex_colors=np.tile(color,(len(m.vertices),1))
    v=m.vertices.copy();center=v.mean(axis=0);ev,axes=np.linalg.eigh(np.cov((v-center).T))
    p=(v-center)@axes[:,np.argmax(ev)];q=(v-center)@axes[:,np.argsort(ev)[-2]]
    p/=max(1,float(np.ptp(p)));q/=max(1,float(np.ptp(q)))
    if kind=='feather':
        h=.19*(np.sin(22.5*q)+.45*np.sin(46*q+2*p))*np.clip(1.2-2*abs(p),0,1)
    elif kind=='hair':
        h=.16*(np.sin(24*q+1.1*p)+.2*np.sin(44*q-3*p))*np.clip(1.3-1.8*abs(p),0,1)
    else:
        h=.28*(np.sin(9*q+2*p)+.2*np.sin(16*q-2*p))*np.clip(1.1-1.5*abs(p),0,1)
    m.vertices=v+m.vertex_normals*h[:,None]
    if m.volume<0:m.invert()
    return m,True

def add_details(scene,factor):
    colors={'black':(16,18,23,255),'metal':(176,183,191,255),'blue':(173,193,234,255)}
    items={}
    def add(name,pts,r,c):
        m=tube(np.array(pts)*factor,r*factor,colors[c])
        scene.add_geometry(m,geom_name=name,node_name=name);items[name]=m
    for s in (-1,1):
        add(f'SLEEVE_SEAM_{s}',[(s*23.8,-4.9,94),(s*25.5,-5.6,83),(s*28.7,-6.7,72),(s*31.2,-7.,64)],.35,'black')
        add(f'CUFF_DETAIL_{s}',[(s*25.8,-4.4,64.8),(s*29,-6.2,63.8),(s*32.5,-6.9,63.3),(s*35,-6.4,64.)],.42,'metal')
        add(f'BOOT_TOE_SEAM_{s}',[(s*4.5,-18.7,8.1),(s*7.6,-20.4,9.9),(s*12,-21,10.2),(s*15.2,-19.8,8.8)],.34,'black')
        add(f'BOOT_SHAFT_SEAM_{s}',[(s*6.,-11.5,43),(s*7.,-11.8,39),(s*7.2,-12.2,35),(s*7.5,-12.1,30)],.24,'metal')
        for j in range(2):
            t=np.linspace(0,1,11)
            points=np.stack([np.full_like(t,s*(1.6+j*.5))+s*2.3*np.sin(t*math.pi),
                             np.full_like(t,18.2),105-17*t],axis=1)
            add(f'BACK_RIBBON_FOLD_{s}_{j}',points,.18,'blue')
    add('FRONT_HEM_SEAM',[(-12,-10.7,80),(-7,-11,79.4),(0,-10.8,79),(7,-11,79.4),(12,-10.7,80)],.31,'black')
    add('FRONT_ZIP_SIDE_STITCH',[(12,-10.2,100),(13,-10.7,95),(13,-10.4,90),(13,-10.6,86)],.28,'metal')
    return len(items)

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-glb',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    base=trimesh.load(a.source_glb,force='scene')
    if not 100<=float(np.ptp(base.bounds[:,2]))<=250:raise ValueError('Bad source scale')
    factor=200.0/float(np.ptp(base.bounds[:,2]))
    scene=trimesh.Scene();changed=0
    for node in sorted(base.graph.nodes_geometry):
        transform, key=base.graph[node];mesh=base.geometry[key].copy()
        mesh.apply_transform(transform);mesh.apply_scale(factor)
        mesh,updated=relief(node,mesh);changed+=int(updated)
        scene.add_geometry(mesh,geom_name=node,node_name=node)
    count=add_details(scene,factor)
    zmin=float(scene.bounds[0,2])
    for g in scene.geometry.values():g.apply_translation((0,0,-zmin))
    final_factor=200.0/float(np.ptp(scene.bounds[:,2]))
    for g in scene.geometry.values():g.apply_scale(final_factor)
    glb=a.output_dir/'WINGED_CHARACTER_V8_200MM_HIGHPOLY_CANDIDATE.glb'
    scene.export(glb,file_type='glb')
    model=trimesh.load(glb,force='scene')
    bad=[name for name,m in model.geometry.items() if not(m.is_watertight and m.volume>0)]
    if bad:raise RuntimeError('Nonmanifold solids '+str(bad[:6]))
    height=float(np.ptp(model.bounds[:,2]))
    if abs(height-200)>.01:raise RuntimeError('Bad final height '+str(height))
    thin=sum(np.min(m.extents)<.8 for m in model.geometry.values())
    qa={'master_height_mm':round(height,4),'target_mm':200,
       'mesh_count':len(model.geometry),'face_count':sum(len(m.faces) for m in model.geometry.values()),
       'modified_sculpt_surfaces':changed,'real_detail_solids':count,
       'watertight_mesh_count':len(model.geometry),'thin_bbox_under_0_8mm':int(thin),
       'source_sha256':hashlib.sha256(a.source_glb.read_bytes()).hexdigest(),
       'output_sha256':hashlib.sha256(glb.read_bytes()).hexdigest(),
       'source_is_rejected_V7_draft':True,'full_likeness_approved':False,
       'physical_colour_parts_approved':False,'wing_hardware_integrated':False,
       'test_print_completed':False,'print_ready_certified':False}
    (a.output_dir/'V8_GEOMETRY_QA.json').write_text(json.dumps(qa,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(qa,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
