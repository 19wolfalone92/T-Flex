#!/usr/bin/env python3
"""New V6 reference-based procedural sculpt candidate, deliberately NOT V1-V5 or print approved.
Uses only the user's original screenshot proportions. mm, Z-up, -Y forwards.
No automated colours-to-STL release. All meshes explicit true volumes, individually named.
"""
import math, os, json, hashlib, csv
from collections import Counter
import numpy as np
import trimesh

OUT=os.environ.get('V6_OUT','/mnt/data/V6_PROCEDURAL_CANDIDATE')
os.makedirs(OUT,exist_ok=True)
PARTS=[]
C={
 'skin':(0.99,0.78,0.78,1), 'white':(0.86,0.91,1.,1),
 'hair_shadow':(0.68,0.76,0.89,1),'hair_highlight':(0.98,0.99,1,1),
 'black':(0.07,0.08,0.11,1), 'coat':(0.12,0.14,0.18,1),
 'coat_high':(0.18,0.19,0.23,1), 'near_black':(0.045,0.051,0.065,1),
 'metal':(0.67,0.72,0.76,1),'dark_metal':(0.32,0.36,0.40,1),
 'scarlet':(0.94,0.34,0.24,1),'purple':(0.45,0.44,0.74,1),
 'rose_eye':(0.83,0.48,0.61,1), 'ivory':(0.96,0.96,0.99,1),
 'wing_l':(0.74,0.83,0.96,1), 'wing_l_light':(0.88,0.92,0.99,1),
 'wing_l_dark':(0.60,0.70,0.85,1), 'wing_r':(0.49,0.63,0.86,1),
 'wing_r_light':(0.66,0.75,0.91,1), 'wing_r_dark':(0.40,0.53,0.76,1),
 'blue':(0.06,0.65,0.96,1)
}
def add(name, m, color):
 if m is None: return
 if isinstance(m,list):
  for i,q in enumerate(m):add(name+f'_{i:02d}',q,color)
  return
 m.apply_transform(np.eye(4));m.metadata['name']=name
 m.visual.vertex_colors=np.tile(np.array([int(round(v*255)) for v in C[color]],dtype=np.uint8), (len(m.vertices),1))
 PARTS.append((name,color,m))
def ell(name, pos, radius, col, subdiv=2):
 m=trimesh.creation.icosphere(subdivisions=subdiv,radius=1);m.apply_scale(radius);m.apply_translation(pos);add(name,m,col)
def tube(name, centers, rx, ry, col, sides=12):
 pts=np.array(centers,dtype=float);N=len(pts)
 if isinstance(rx,(int,float)):rx=[rx]*N
 if isinstance(ry,(int,float)):ry=[ry]*N
 vv=[]
 for i,p in enumerate(pts):
  tg=pts[min(N-1,i+1)]-pts[max(i-1,0)];tg/=max(np.linalg.norm(tg),1e-9)
  ax=np.array([0.,1.,0.]);
  if abs(np.dot(ax,tg))>0.89:ax=np.array([1.,0.,0.])
  u=np.cross(ax,tg);u/=np.linalg.norm(u);v=np.cross(tg,u)
  for j in range(sides):
   a=j*2*math.pi/sides;vv.append(p+math.cos(a)*rx[i]*u+math.sin(a)*ry[i]*v)
 ff=[]
 for i in range(N-1):
  for j in range(sides):
   k=(j+1)%sides;a=i*sides+j;b=i*sides+k;c=(i+1)*sides+j;d=(i+1)*sides+k
   ff.extend([[a,c,b],[b,c,d]])
 for j in range(1,sides-1):
  ff.append([0,j,j+1]);ff.append([(N-1)*sides,(N-1)*sides+j+1,(N-1)*sides+j])
 m=trimesh.Trimesh(vertices=vv,faces=ff,process=True);trimesh.repair.fix_normals(m);add(name,m,col)
def cyl(name,a,b,r,col,section=12):
 a=np.array(a);b=np.array(b);d=b-a;m=trimesh.creation.cylinder(radius=r,height=np.linalg.norm(d),sections=section)
 M=trimesh.geometry.align_vectors([0,0,1],d);m.apply_transform(M);m.apply_translation((a+b)/2);add(name,m,col)
def box(name,center,ext,col):
 m=trimesh.creation.box(extents=ext);m.apply_translation(center);add(name,m,col)
def path2(name,coords,r,col):
 for i in range(len(coords)-1):cyl(name+f'_{i}',coords[i],coords[i+1],r,col,8)
def star(name,ctr,R,r,thick,col):
 # planar star in XZ; thickness runs in Y
 verts=[]
 for y in [ctr[1]-thick/2,ctr[1]+thick/2]:
  for i in range(10):
   ang=math.pi/2+i*math.pi/5
   rr=R if i%2==0 else r
   verts.append([ctr[0]+rr*math.cos(ang),y,ctr[2]+rr*math.sin(ang)])
 ff=[]
 for i in range(1,9):ff.extend([[0,i,i+1],[10,10+i+1,10+i]])
 for i in range(10):a=i;b=(i+1)%10;ff.extend([[a,b,10+a],[b,10+b,10+a]])
 m=trimesh.Trimesh(vertices=verts,faces=ff,process=True);trimesh.repair.fix_normals(m);add(name,m,col)
def feather(name,start,end,width,thick,col,curve=0.):
 # A watertight double-curved, low-relief feather solid with soft scalloped edges.
 a=np.array(start,dtype=float);b=np.array(end,dtype=float);v=b-a
 perp=np.array([-v[2],0,v[0]],dtype=float);perp/=max(np.linalg.norm(perp),1e-9)
 n=20;sides=12;vv=[];ff=[]
 for i in range(n):
  t=i/(n-1)
  swell=(max(.008,math.sin(math.pi*(.035+.93*t))))**.7
  center=a+v*t+np.array([0,curve*math.sin(math.pi*t),0])
  for j in range(sides):
   q=2*math.pi*j/sides
   vv.append(center+perp*(width*swell*math.cos(q))+np.array([0,.5*thick*swell*math.sin(q),0]))
 for i in range(n-1):
  for j in range(sides):
   j2=(j+1)%sides;a0=i*sides+j;b0=i*sides+j2;c0=(i+1)*sides+j;d0=(i+1)*sides+j2
   ff.extend([[a0,c0,b0],[b0,c0,d0]])
 for j in range(1,sides-1):
  ff.append([0,j,j+1]);ff.append([(n-1)*sides,(n-1)*sides+j+1,(n-1)*sides+j])
 m=trimesh.Trimesh(vertices=vv,faces=ff,process=True)
 trimesh.repair.fix_normals(m);add(name,m,col)

def buckle(name,x,y,z,w,h,met='metal'):
 d=0.65
 for za in [z-h/2,z+h/2]:
  cyl(name+'_edgeH'+str(za),(x-w/2,y,za),(x+w/2,y,za),d,met,10)
 for xa in [x-w/2,x+w/2]:
  cyl(name+'_edgeV'+str(xa),(xa,y,z-h/2),(xa,y,z+h/2),d,met,10)
 cyl(name+'_clasp',(x-1,y-.7,z),(x+1,y-.7,z),.46,met)

# HEAD skin with ears, cheeks and heterochromia eyes. The eyes sit in front of face.
ell('face_visible_sculpt',(0,-0.5,127.0),(18.3,15.0,19.0),'skin',3)
for s in [-1,1]:
 ell(f'ear_{s}',(s*18.4,0,123.5),(3.3,2.8,5.0),'skin')
 # eyes upper sclera, iris, pupil, reflection layered outwards
 x=s*8.25
 ell(f'eye_white_{s}',(x,-14.4,128.2),(5.25,1.7,4.1),'ivory',3)
 color='purple' if s==-1 else 'rose_eye'
 ell(f'iris_{s}',(x+(-.45 if s==-1 else .3),-16.0,127.75),(3.1,.75,3.45),color,3)
 ell(f'pupil_{s}',(x,-16.6,127.3),(1.35,.48,2.55),'black',2)
 ell(f'eye_glint_{s}',(x-1.2,-17.2,129.0),(.85,.26,.92),'ivory',2)
 path2(f'upper_lash_{s}',[(x-5.8,-15.7,131.3),(x-3,-16,133.1),(x,-15.6,133.1),(x+5,-14.8,131.6)],.48,'black')
# Black face mask with fabric seams, directly BELOW iris and eye line
ell('lower_face_black_mask',(0,-11.8,117.0),(14.8,9.7,6.3),'black',3)
for s in [-1,1]:
 tube(f'mask_strap_{s}',[(s*14,-12.2,121.0),(s*18,-6,123),(s*18.7,.6,123)],.95,.67,'near_black')

# Fanned, asymmetrical white hair. Contour cap and numerous sculpted long locks.
ell('white_hair_back_mass',(0,4.2,136.4),(20.2,15.7,14.2),'white',3)
ell('white_hair_nape',(0,9.3,124.1),(19.0,10.0,13.0),'white',3)
for j in range(17):
 theta=math.pi*.16+j*(math.pi*.92/16)
 x=19*math.cos(theta);y=3+14*math.sin(theta)
 z=142.5 + (2.0 if j%4==0 else 0)
 p1=(x,y,z);p2=(x*1.04,19.7,130.0);p3=(x*.99,18.1,115.8+2.5*math.sin(j*2.1))
 tube(f'back_hair_lock_{j:02d}',[p1,p2,p3],[3.9,3.2,.38],[2.65,1.9,.30], 'hair_highlight' if j%3==0 else 'white',10)
# visible waves over forehead to right-side of face
for j in range(12):
 x=-17+j*3.05;z=148.2+.9*math.sin(j*1.9)
 targetx=(-16+j*3.15) + (6 if j>=5 else 1)
 tipz=134.5-5.1*math.sin(j*.30) + (1.8 if j<=2 else 0)
 tube(f'fringe_{j:02d}',[(x,-8.5,z),(x+2,-14.5,z-6),(targetx,-17.5,tipz)],[3.7,3.3,.25],[3.1,2.1,.24], 'hair_highlight' if j%4==1 else 'white',12)
# long separated hair tufts on left and right temple
for s in [-1,1]:
 for j in range(4):
  x=s*(17+j*.65)
  tube(f'temple_hair_{s}_{j}',[(x,-2+j,143-j*2),(x+s*2,-6-j*.5,130-j*1.1),(x+s*3,-3-j*.6,119-j*.75)], [3.5,2.6,.2],[2.3,1.9,.20],'white',10)

# upper plague doctor cap on model's upper left forehead (from reference, not eye-obscuring)
ell('plague_helmet_black_shell',(-12.0,-4.4,143),(13.6,12.3,9.4),'black',3)
ell('plague_helmet_highlight',(-18.3,-12.0,146.6),(4.9,1.2,5.0),'coat_high')
# beak curved down, hooked -Y toward face and -X
# avoids obscuring eye on opposite side
tube('plague_crow_beak',[(-17,-15.5,141),(-20,-19.2,135.4),(-21.5,-22,128.4),(-22,-19.9,123.1)],[5.7,5.4,3.9,.45],[4.4,3.8,2.7,.40],'black',14)
for s,x in enumerate([-22]):
 ell(f'goggle_rim_outer_{s}',(x,-15.8,140.4),(4.15,1.25,4.6),'metal',3)
 ell(f'goggle_lens_{s}',(x,-17,140.5),(3.15,.95,3.45),'dark_metal',3)
 ell(f'goggle_glass_{s}',(x-.55,-17.7,141.1),(1.65,.24,1.95),'coat_high')
for i in range(3):ell(f'helmet_rivet_{i}',(-23.4+i*2.6,-18.,134-i*4.1),(.8,.9,.8),'metal')

# NECK black choker, collar/ruff layered, asymmetrical goth fashion
ell('neck',(0,1,109),(6.8,7.0,6.2),'skin')
ell('neck_choker',(0,-0.0,113.6),(7.0,7.3,2.2),'near_black')
ell('collar_black',(0,2.2,105.1),(17.3,10.5,6.0),'black',2)
for s in [-1,1]:
 for j in range(4):feather(f'shoulder_collar_feather_{s}_{j}',(s*6,4,111),(s*(15+j*2),6.3,104-j*.7),2.4,2.7,'black',0.5)
# torso goth jacket main shell, v-collar/zipper and overlays
tube('black_jacket_torso',[(0,0,105),(0,0,99),(0,0,92),(0,0,79)],[16.,18.,17.5,15.2],[10.4,11.2,9.2,9.2],'coat',22)
for s in [-1,1]:
 tube(f'jacket_lapel_{s}',[(s*10,-10.1,106),(s*9,-12.8,98),(s*3.2,-11.5,92),(s*1.2,-9.8,84)],[3.3,3.4,2.1,.7],[1.0,1.0,.8,.5],'near_black',12)
 tube(f'jacket_lapel_edge_{s}',[(s*9,-13.1,103),(s*5,-13.9,97),(s*1,-10.4,87)],.53,.42,'metal',9)
tube('central_zip_silver',[(0,-11.5,87.0),(0,-10.3,78.8),(0,-10.3,73.2)],.54,.34,'metal')
ell('front_pendant_amber_star',(0,-13.8,102),(1.0,1.,1.),'scarlet')
star('jacket_heart_flower',(0,-14.7,101.9),3.8,1.7,1.3,'scarlet')
cyl('necklace_1',(-5,-11.8,108),(0,-13.1,102),.53,'metal');cyl('necklace_2',(5,-11.8,108),(0,-13.1,102),.53,'metal')

# arms with visible pale shoulders, full bell sleeves no slicing
for s in [-1,1]:
 ell(f'shoulder_skin_{s}',(s*20.4,-.1,100.5),(3.0,3.3,4.6),'skin')
 ell(f'shoulder_puff_{s}',(s*21.4,1.7,104.2),(4.5,5.7,3.2),'black')
 tube(f'arm_full_flared_sleeve_{s}',[(s*23.1,0.9,98.8),(s*24.8,.7,91),(s*28.6,.2,71.0),(s*31.5,-1.9,62.8)],[5.3,5.9,7.5,9.3],[4.3,4.4,5.0,5.7],'coat',18)
 tube(f'long_sleeve_open_cuff_{s}',[(s*30.3,-1.8,64.4),(s*31.5,-1.5,62.7)], [8.0,9.25],[5.5,5.8],'coat_high',18)
 for k in range(3):ell(f'sleeve_cuff_rivet_{s}_{k}',(s*(26.5+4*k),-5.7,63.6),(1.,.7,.9),'metal')
 tube(f'arm_black_strap_{s}',[(s*23,-5,97.5),(s*27.8,-5,96)],1.5,.85,'near_black')
 buckle(f'shoulder_buckle_{s}',s*25.2,-5.7,96.5,4.4,4.1)
 # exposed small hand below cuff
 ell(f'hand_{s}',(s*31.5,-1.8,60.3),(3.2,3.6,3.0),'skin')

# trousers black shorts, jacket waist, buttons and red stitching
tube('black_short_waist',[(0,0,80),(0,0,73),(0,0,67)],[15.7,15.8,16.2],[8.4,8.8,9.1],'near_black',20)
for s in [-1,1]:
 x=s*8.0
 tube(f'short_leg_{s}',[(x,0,71.5),(x,-.8,62)],[8.8,8.9],[7.9,8.0],'coat',16)
 tube(f'hemline_{s}',[(x,-.7,62),(x,-.7,61.8)],8.8,7.7,'near_black')
 ell(f'bare_thigh_{s}',(s*9.7,0,57.7),(6.0,5.7,8.3),'skin')
 tube(f'thigh_garter_{s}',[(s*9.7,0,60.),(s*9.7,0,57.5)],[6.1,6.1],[5.8,5.8],'near_black')
 buckle(f'garter_buckle_{s}',s*9.8,-5.85,59.2,4.7,4.3)
for k in range(7):ell(f'belt_silver_rivet_{k}',(-14+4.5*k,-9.65,76.3),(.92,.65,.9),'metal')
tube('belt_black',[(0,-.4,77.3),(0,-.4,74.3)],[16.,16.],[9.1,9.1],'black',20)
star('red_belt_pin',(0,-10.8,76.0),2.4,1.1,1.3,'scarlet')
for s in [-1,1]:
 for j in range(5):
  x=s*(4+j*1.55)
  cyl(f'short_red_stitch_{s}_{j}',(x,-8.3,64.1),(x+s*.6,-8.3,64.0),.20,'scarlet',6)

# Two separate tall heavy lace-up goth boots with massive toes; preserve legs gap
for s in [-1,1]:
 x=s*10.4
 tube(f'boot_tall_shaft_{s}',[(x,0,57.0),(x,.3,46.),(x,.6,34.),(x,-.3,19.),(x,-.7,8.)], [7.4,7.9,8.6,8.8,8.5],[6.7,7.4,8.7,9.4,9.0],'coat',20)
 ell(f'boot_toe_{s}',(x,-9.0,6.8),(10.4,13.7,6.3),'black',3)
 ell(f'boot_platform_{s}',(x,-5.0,2.45),(10.9,15.8,3.7),'near_black',3)
 tube(f'boot_ankle_slouch_{s}',[(x,-.8,20.),(x,-2.9,16.),(x,-1.2,10.)],[9.7,10.7,11.],[10.,10.0,10.7],'coat_high',15)
 tube(f'boot_calf_strap_{s}',[(x,.2,53.),(x,.2,49.7)],[7.9,8.2],[8.6,8.8],'near_black',16)
 buckle(f'boot_top_buckle_{s}',x,-8.95,52.0,5.5,5.7)
 buckle(f'boot_toe_plate_{s}',x,-21.6,4.5,3.4,3.9,'metal')
 # lacing zig-zag front, boot hardware eyelets
 for k in range(7):
  z=44-k*4.6
  for j in [-1,1]:ell(f'lacing_eyelet_{s}_{k}_{j}',(x+j*2.8,-8.4, z),(.67,.5,.63),'metal')
  z2=z-2.2
  cyl(f'boot_lace_cross_A_{s}_{k}',(x-2.7,-9.1,z),(x+2.7,-9.1,z2),.38,'near_black',8)
  cyl(f'boot_lace_cross_B_{s}_{k}',(x+2.7,-9.1,z),(x-2.7,-9.1,z2),.38,'near_black',8)

# elaborate blue wings, real sculpted feather geometry, separate side roots, 3 tiers
for s in [-1,1]:
 # hidden wing root pad sits behind shoulder (not the already-tested hardware)
 ell(f'WING_{"L" if s==-1 else "R"}_root',(s*17,12.8,110.2),(8.2,4.0,6.0),'wing_l' if s==-1 else 'wing_r',2)
 for layer in range(3):
  num=[13,13,13][layer]
  for i in range(num):
   u=i/(num-1);startx=18+layer*3.0+i*.9
   endx=29+u*(36-layer*4)+layer*2
   z0=115.7-layer*3.8 + 2.8*u
   # a high outer leading edge; outer feathers sweep and curve down toward tips
   z1=129.0+5.8*math.sin(math.pi*u*.89)-7.0*u-layer*6.4
   a=(s*startx,12+layer*.5,z0);b=(s*endx,13.5+layer*.6,z1)
   palette=(['wing_l_light','wing_l','wing_l_dark'] if s==-1 else ['wing_r_light','wing_r','wing_r_dark'])
   feather(f'WING_{"L" if s==-1 else "R"}_tier{layer}_primary{i:02}',a,b,3.0-0.35*layer,1.9,palette[layer],.9)
   # each primary shaft and sculpted barb veins as relief, may become post-paint at 150 mm
   p1=np.array(a)*.38+np.array(b)*.62;p2=np.array(a)*.13+np.array(b)*.87
   cyl(f'feather_vein_{s}_{layer}_{i}',p1+np.array([0,-1.3,0]),p2+np.array([0,-1.3,0]),.22,palette[(layer+1)%3],6)
 # fan over root, small overlapping coverts
 for i in range(16):
  xx=17+i*2.6; zz=115.5-4*(i/15)
  feather(f'wing_root_coverts_{s}_{i}',(s*xx,12,zz),(s*(xx+12),11.9,zz+4.8),2.85,2.8, 'wing_l' if s==-1 else 'wing_r',.3)

# Rear silver 5-point star and two vivid blue hanging ribbons
star('rear_SILVER_star',(0,16.1,108.5),4.3,1.9,1.8,'metal')
for s in [-1,1]:
 feather(f'back_blue_ribbon_{s}',(s*1.5,17,105.7),(s*5.6,18,81.0),1.30,1.55,'blue',1.3)
 # subtle tiny loop seam at top
 tube(f'ribbon_tie_{s}',[(s*1.,17.7,106),(s*4.3,18.0,103.0),(s*5.1,17.8,106.2)],[.85,.75,.8],[.7,.7,.7],'blue',9)

# candidate assembly metrics; notably not printable until tolerances and joins designed
# Correct the nominal master height while preserving proportions and z-up orientation.
raw_bounds=np.array([m.bounds for _,_,m in PARTS]); raw_min=float(raw_bounds[:,0,2].min());raw_max=float(raw_bounds[:,1,2].max())
scale=150.0/(raw_max-raw_min)
for _,_,mesh in PARTS:
 mesh.apply_translation([0,0,-raw_min]);mesh.apply_scale(scale)
 v=mesh.vertices.copy();v[:,2]=np.where(v[:,2]<=62.0,v[:,2]*(46.0/62.0),46.0+(v[:,2]-62.0)*(104.0/88.0));mesh.vertices=v
scene=trimesh.Scene()
counts=Counter()
report=[]
for name,color,m in PARTS:
 counts[color]+=1
 if m.volume<0: m.invert()
 scene.add_geometry(m,geom_name=name,node_name=name)
 report.append({'name':name,'material':color,'faces':len(m.faces),'vertices':len(m.vertices),
 'watertight':bool(m.is_watertight),'positive_volume':bool(m.volume>0),
 'bounds_mm':np.round(m.bounds,3).tolist()})
scene.export(os.path.join(OUT,'WINGED_CHARACTER_V6_NEW_SCULPT_CANDIDATE.glb'),file_type='glb')
# Export source manifest and explicit QA status; no final STL until human approves shape.
with open(os.path.join(OUT,'COMPONENTS.json'),'w',encoding='utf-8') as f:json.dump(report,f,indent=2,ensure_ascii=False)
check={'source':'original_user_18_views','geometry_is_new':True,'derivative_of_v5':False,
'profile':'reference-driven procedural first candidate','target_height_mm':150,
'assembly_orientation':'Z-up front=-Y','art_approved':False,'print_ready_certified':False,
'final_colour_stl_released':False,'components':len(report),'material_bodies':dict(counts),
'watertight_components':sum(x['watertight'] for x in report),
'positive_volume_components':sum(x['positive_volume'] for x in report),
'candidate_bounds_mm':np.round(scene.bounds,2).tolist(),
'needs_work':['independent frontal/back/sides silhouette matching','manual face and mask likeness review',
 'physical union by colour','wing bridge integration','printer tolerances','slicer acceptance']}
with open(os.path.join(OUT,'QA_CANDIDATE_NOT_RELEASED.json'),'w',encoding='utf-8') as f:json.dump(check,f,indent=2,ensure_ascii=False)
print(json.dumps(check,indent=2,ensure_ascii=False))