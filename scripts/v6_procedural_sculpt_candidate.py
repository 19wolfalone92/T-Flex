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
 'skin':(0.99,0.78,0.78,1), 'white':(0.81,0.87,.97,1),
 'hair_shadow':(0.73,0.79,0.89,1),'hair_highlight':(0.91,0.94,1,1),
 'black':(0.07,0.08,0.11,1), 'coat':(0.12,0.14,0.18,1),
 'coat_high':(0.18,0.19,0.23,1), 'near_black':(0.045,0.051,0.065,1),
 'metal':(0.67,0.72,0.76,1),'dark_metal':(0.32,0.36,0.40,1),
 'scarlet':(0.94,0.34,0.24,1),'purple':(0.45,0.44,0.74,1),
 'rose_eye':(0.83,0.48,0.61,1), 'ivory':(0.96,0.96,0.99,1),
 'wing_l':(0.65,0.74,0.87,1), 'wing_l_light':(0.79,0.84,0.95,1),
 'wing_l_dark':(0.56,0.65,0.79,1), 'wing_r':(0.44,0.57,0.79,1),
 'wing_r_light':(0.56,0.68,0.86,1), 'wing_r_dark':(0.33,0.48,0.73,1),
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

def sculpted_lock(name, path, widths, depths, col, rings=10, sides=12, normal=(0,-1,0)):
    """Smooth separate feather/hair leaf as a truly watertight sculptural volume."""
    pts=np.array(path,dtype=float)
    def cr(p0,p1,p2,p3,t):
        return .5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)
    refined=[];wref=[];dref=[]
    for i in range(len(pts)-1):
        for k in range(rings):
            t=k/rings
            refined.append(cr(pts[max(0,i-1)],pts[i],pts[i+1],pts[min(len(pts)-1,i+2)],t))
            wref.append(float(widths[i]*(1-t)+widths[i+1]*t))
            dref.append(float(depths[i]*(1-t)+depths[i+1]*t))
    refined.append(pts[-1]);wref.append(max(float(widths[-1]),.10));dref.append(max(float(depths[-1]),.08))
    vv=[];faces=[]
    nrm=np.array(normal,dtype=float);nrm/=np.linalg.norm(nrm)
    for i,p in enumerate(refined):
        direction=np.array(refined[min(len(refined)-1,i+1)])-np.array(refined[max(0,i-1)])
        direction/=max(1.e-6,np.linalg.norm(direction))
        wdir=np.cross(nrm,direction)
        if np.linalg.norm(wdir)<.1:wdir=np.array([1.,0,0])
        wdir/=np.linalg.norm(wdir)
        for j in range(sides):
            a=math.tau*j/sides
            vv.append(np.array(p)+wdir*max(.12,wref[i])*math.cos(a)+nrm*max(.10,dref[i])*math.sin(a))
    for i in range(len(refined)-1):
        for j in range(sides):
            n=(j+1)%sides;u=i*sides+j;v=i*sides+n;a=(i+1)*sides+j;b=(i+1)*sides+n
            faces.extend([[u,a,v],[v,a,b]])
    for j in range(1,sides-1):
        faces.append([0,j+1,j]);faces.append([(len(refined)-1)*sides,(len(refined)-1)*sides+j,(len(refined)-1)*sides+j+1])
    mesh=trimesh.Trimesh(vertices=vv,faces=faces,process=True)
    trimesh.repair.fix_normals(mesh);add(name,mesh,col)

def fabric_mask(name):
    """Curved conformal black surgical mask with cheek-high rim and jaw protection."""
    n=40;m=20;vv=[];ff=[]
    def at(i,j,back=False):
        u=-1.+2.*i/n;t=j/m
        x=16.8*u*(1-.10*t-.12*t*t)
        top=122.4+4.2*(abs(u)**1.35)
        bottom=113.2+5.8*(abs(u)**1.7)
        z=top*(1-t)+bottom*t
        y=-11.2-6.45*(1-u*u)**.55*(0.52+0.48*math.sin(math.pi*t))
        if back:y+=1.8
        return [x,y,z]
    for back in [False,True]:
        for j in range(m+1):
            for i in range(n+1):vv.append(at(i,j,back))
    stride=n+1;offset=(n+1)*(m+1)
    for j in range(m):
        for i in range(n):
            a=j*stride+i;b=a+1;c=a+stride;d=c+1
            ff.extend([[a,b,c],[b,d,c],[a+offset,c+offset,b+offset],[b+offset,c+offset,d+offset]])
    for i in range(n):
        a=i;b=i+1;f=offset
        ff.extend([[a,a+f,b],[b,a+f,b+f]])
        a=m*stride+i;b=a+1;ff.extend([[a,b,a+f],[b,b+f,a+f]])
    for j in range(m):
        a=j*stride;b=(j+1)*stride;f=offset
        ff.extend([[a,b,a+f],[b,b+f,a+f]])
        a=j*stride+n;b=(j+1)*stride+n;ff.extend([[a,a+f,b],[b,a+f,b+f]])
    mesh=trimesh.Trimesh(vertices=vv,faces=ff,process=True)
    trimesh.repair.fix_normals(mesh);add(name,mesh,'black')
    path2('mask_upper_lip_seam',[at(i,0) for i in range(0,n+1,2)],.38,'coat_high')

def goggle_ring(name,center,radius=4.8,ring=.82,orient='front'):
    n=28;pts=[]
    for j in range(n+1):
        a=math.tau*j/n
        if orient=='front':pts.append((center[0]+radius*math.cos(a),center[1],center[2]+radius*math.sin(a)))
        else:pts.append((center[0],center[1]+radius*math.cos(a),center[2]+radius*math.sin(a)))
    for k in range(n):
        cyl(f'{name}_arc_{k:02d}',pts[k],pts[k+1],ring,'black' if k%5 else 'dark_metal',12)

def wing_feather(name,start,end,width,thickness,color,arch=1.6,layer_y=0.):
    """Curved separate, voluminous feather with soft distal profile."""
    a=np.array(start,dtype=float);b=np.array(end,dtype=float);dx=b-a
    perp=np.array([-dx[2],0,dx[0]]);perp/=max(np.linalg.norm(perp),1.e-7)
    vv=[];ff=[];sections=24;sides=12
    for i in range(sections):
        t=i/(sections-1)
        w=width*(.48+.49*math.sin(math.pi*t*.88)**.65)*(1-.88*max(0,(t-.91)/.09)**1.2)
        thick=thickness*(.52+.48*math.sin(math.pi*(.12+.82*t)))
        p=a+dx*t+np.array([0,layer_y+arch*math.sin(math.pi*t)-.28*t,.7*math.sin(math.pi*t)])
        for j in range(sides):
            q=math.tau*j/sides
            vv.append(p+perp*(w*math.cos(q))+np.array([0,.5*thick*math.sin(q),0]))
    for i in range(sections-1):
        for j in range(sides):
            k=(j+1)%sides;u=i*sides+j;v=i*sides+k;c=(i+1)*sides+j;d=(i+1)*sides+k
            ff.extend([[u,c,v],[v,c,d]])
    for j in range(1,sides-1):
        ff.append([0,j+1,j]);ff.append([(sections-1)*sides,(sections-1)*sides+j,(sections-1)*sides+j+1])
    mesh=trimesh.Trimesh(vertices=vv,faces=ff,process=True)
    trimesh.repair.fix_normals(mesh);add(name,mesh,color)

def inset_triangle(name,xy,front_y,thick,col):
    v0=[[x,front_y,z] for x,z in xy]
    v1=[[x,front_y+thick,z] for x,z in xy]
    verts=v0+v1;ff=[]
    for i in range(1,len(xy)-1):
        ff.extend([[0,i+1,i],[len(xy),len(xy)+i,len(xy)+i+1]])
    for i in range(len(xy)):
        j=(i+1)%len(xy)
        ff.extend([[i,j,i+len(xy)],[j,j+len(xy),i+len(xy)]])
    mesh=trimesh.Trimesh(vertices=verts,faces=ff,process=True)
    trimesh.repair.fix_normals(mesh);add(name,mesh,col)

def buckle(name,x,y,z,w,h,met='metal'):
 d=0.65
 for za in [z-h/2,z+h/2]:
  cyl(name+'_edgeH'+str(za),(x-w/2,y,za),(x+w/2,y,za),d,met,10)
 for xa in [x-w/2,x+w/2]:
  cyl(name+'_edgeV'+str(xa),(xa,y,z-h/2),(xa,y,z+h/2),d,met,10)
 cyl(name+'_clasp',(x-1,y-.7,z),(x+1,y-.7,z),.46,met)

# Refined V7 head: expressive two-colour eyes, shaped mask, flowing silver hair, sculpted beak.
ell('face_visible_sculpt',(0,-.5,127),(18.1,14.5,17.1),'skin',4)
for side in [-1,1]:
    ell(f'ear_{side}',(side*17.7,-.2,123.2),(3.35,2.65,4.8),'skin',3)
    x=side*8.35
    ell(f'sclera_{side}',(x,-14.0,129.0),(6.0,1.4,3.55),'ivory',3)
    iriscol='purple' if side==-1 else 'rose_eye'
    ell(f'iris_{side}',(x,-15.35,128.0),(3.6,.62,3.3),iriscol,3)
    ell(f'iris_lumen_{side}',(x,-15.99,127.5),(2.55,.29,2.8),'hair_shadow' if side==-1 else 'scarlet',3)
    ell(f'pupil_{side}',(x,-16.3,128.0),(1.25,.23,2.30),'black',3)
    ell(f'glint_{side}',(x-1.1,-16.7,129.8),(1.1,.28,.85),'ivory',2)
    ell(f'glint_lower_{side}',(x+.85,-16.6,126.4),(.60,.18,.45),'ivory',1)
    path2(f'thick_lash_{side}',[(x-6.0,-14.6,131.7),(x-4,-15.1,132.3),(x,-15.2,132.5),(x+6.0,-14.3,131.8)],.43,'near_black')
    for j in range(2):
        path2(f'lower_eye_line_{side}_{j}',[(x+(j*2-1)*3.7,-14.3,124.8),(x+(j*2-1)*5.0,-13.5,124.1)],.32,'near_black')
ell('nose_anime',(0,-15.0,123.8),(1.25,.85,.7),'skin',2)
fabric_mask('lower_face_mask_tailored')
for side in [-1,1]:
    tube(f'face_strap_{side}',[(side*15.6,-10,121.2),(side*18,-6.5,120),(side*19,0,120)],[.75,.75,.68],[.65,.60,.55],'near_black')
ell('hair_main_smooth_scalp',(0,3.3,139.9),(20.3,13.7,13.7),'white',4)
ell('hair_nape_underlayer',(0,10.5,128.4),(18.3,11.4,12.4),'hair_shadow',3)
for j in range(15):
    u=-1+2*j/14;x=18.7*u;z=148.7-4.2*abs(u)
    targetx=x+2.9*math.sin(j*.8)
    ztip=118.4+3.9*abs(u)+1.1*math.sin(j*1.2)
    sculpted_lock(f'rear_rounded_bob_{j:02d}',
        [(x*.92,10.5,z),(x,21.7,137.9),(targetx,22.8,126.2),(targetx+1.6*math.sin(j),20.8,ztip)],
        [3.4,4.2,4.2,1.1],[1.5,2.45,2.0,.5],
        'hair_highlight' if j%4==1 else 'white',normal=(0,1,0))
for side in [-1,1]:
    for j in range(3):
        x=side*(15.0+j*1.6)
        sculpted_lock(f'side_wispy_bob_{side}_{j}',
            [(x,6,147-j),(x+side*2,-2.2,136-j),(x+side*1.9,-6,127-j),(x+side*2.9,-3,120-j*1.2)],
            [3.1,4.0,3.2,.19],[2.2,2.5,1.7,.15],'white')
for j in range(10):
    x=-14.6+3.1*j;drop=max(0,j-2);endx=x+6.6+1.2*math.sin(.9*j)
    endz=136.7-(2.0*drop if j>=5 else .4*drop)-1.1*math.sin(.75*j)
    sculpted_lock(f'forehead_swept_white_lock_{j:02d}',
        [(x,-4.8,149.3),(x+1.4,-10.4,145.9),(x+4.1,-14.7,140.5),(endx,-18.25 if j>=5 else -15.7,endz)],
        [2.15,3.6,4.0,1.15],[1.9,2.4,1.4,.47], 'hair_highlight' if j in (4,8) else 'white')
ell('plague_mask_asymmetric_leather_dome',(-12.1,-4.2,142.1),(13.1,12.2,10.1),'black',4)
sculpted_lock('plague_beak_hooked_profile',
    [(-13.3,-13.5,143.3),(-17.2,-17.6,138.7),(-19.0,-19.6,129.3),(-18.8,-19.4,120.0)],
    [5.25,5.3,3.3,.24],[3.7,3.5,2.5,.23],'black',normal=(0,-1,0))
sculpted_lock('beak_highlight_right_lobe',
    [(-15,-16.6,140),(-18.4,-18.2,134.6),(-19.1,-18.9,125)],
    [1.55,1.25,.14],[.5,.4,.1],'coat_high')
ell('helmet_front_goggle_glass',(-13.5,-15.45,142.4),(3.8,1.55,3.9),'dark_metal',3)
ell('helmet_front_goggle_reflection',(-14.15,-17.00,143.1),(2.8,.22,2.5),'coat_high',3)
goggle_ring('helmet_front_goggle_metal_ring',(-13.5,-16.5,142.4),4.1,.68)
ell('helmet_side_goggle_glass',(-23.6,-3.6,143.9),(1.1,3.45,3.7),'dark_metal',3)
goggle_ring('helmet_side_goggle_ring',(-24.3,-3.6,143.9),3.8,.68,orient='side')
path2('plague_plate_seam',[(-20,-10.2,150),(-20,-11.5,145),(-20,-13.5,138),(-19.3,-16,132)],.32,'coat_high')
for i,p in enumerate([(-21,-14,134),(-22,-15.5,130),(-22.1,-17.2,125)]):
    ell(f'plague_helmet_rivet_{i}',p,(.91,.66,.91),'metal')
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

inset_triangle('real_skin_open_v_neckline',[(-5.7,108.3),(5.7,108.3),(0,97.8)],-13.0,1.15,'skin')
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

# Three feather tiers on anatomically arched floating wings.
for side in [-1,1]:
    wingstr='L' if side==-1 else 'R'
    primary='wing_l' if side==-1 else 'wing_r'
    light='wing_l_light' if side==-1 else 'wing_r_light'
    dark='wing_l_dark' if side==-1 else 'wing_r_dark'
    ell(f'WING_{wingstr}_strong_root',(side*18.8,22,105.4),(3.7,3.1,4.6),primary,3)
    tube(f'WING_{wingstr}_joint_arm',
        [(side*18.1,22.4,107.5),(side*27.5,21.8,107.0),(side*36,22,108.7),(side*44.2,21.1,112.0)],
        [3.7,4.25,3.35,1.8],[3.4,3.5,3.,1.4],primary,20)
    for i in range(15):
        t=i/14
        sx=31.1-5.2*t;sz=111.1-9.1*t
        ex=75.0-39.*(t**1.45)+1.2*math.sin(i*1.43)
        ez=120.0-36.4*t+1.6*math.sin(t*math.pi)
        wing_feather(f'WING_{wingstr}_primary_{i:02d}',(side*sx,20.3,sz),
           (side*ex,20.9,ez),4.05+.4*t,2.55,dark if side==1 else primary,arch=1.8)
    for i in range(16):
        t=i/15;sx=23.6+5.8*math.sin(math.pi*t);sz=107.2-8.0*t
        ex=63.2-31.0*t**1.5;ez=117.0-30.2*t
        wing_feather(f'WING_{wingstr}_secondary_{i:02d}',(side*sx,18.5,sz),
           (side*ex,16.8,ez),4.2,2.5,primary,arch=1.15)
    for i in range(15):
        t=i/14;x=21.+12*t;z=105.4-6.3*t
        wing_feather(f'WING_{wingstr}_covert_{i:02d}',(side*(x-5),15.0,z+1.8),
            (side*(x+9),15.5,z+1-5*t),3.85,2.1,light if i%3==0 else primary,.65)
    for i in range(12):
        t=i/11;sx=33-6*t;sz=110-8*t;ex=70-34*t**1.45;ez=119-34*t
        a=np.array([side*sx,17.75,sz]);b=np.array([side*ex,17.65,ez])
        cyl(f'WING_{wingstr}_embossed_shaft_{i:02d}',a*.75+b*.25,a*.10+b*.90,.20,light,8)
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
for name,color,mesh in PARTS:
 if name.startswith('WING_'):
  v=mesh.vertices.copy();ax=np.abs(v[:,0])
  v[:,0]=np.sign(v[:,0])*(np.minimum(ax,18.)+np.maximum(0.,ax-18.)*.68)
  mesh.vertices=v
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
'profile':'V7 3rd iteration - tighter mask, partial eye cover, rounded hair and hidden wing roots','target_height_mm':150,
'assembly_orientation':'Z-up front=-Y','art_approved':False,'print_ready_certified':False,
'final_colour_stl_released':False,'components':len(report),'material_bodies':dict(counts),
'watertight_components':sum(x['watertight'] for x in report),
'positive_volume_components':sum(x['positive_volume'] for x in report),
'candidate_bounds_mm':np.round(scene.bounds,2).tolist(),
'needs_work':['expert visual review of revised face, hair, wing silhouette','manual proof of eye, mask and helmet identity',
 'physical union by colour','wing bridge integration','printer tolerances','slicer acceptance']}
with open(os.path.join(OUT,'QA_CANDIDATE_NOT_RELEASED.json'),'w',encoding='utf-8') as f:json.dump(check,f,indent=2,ensure_ascii=False)
print(json.dumps(check,indent=2,ensure_ascii=False))