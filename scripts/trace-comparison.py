"""Compare walking paths at metre scale without merging nearby alternatives."""
import math

SCALE_X=6371000*math.pi/180*math.cos(math.radians(49))
SCALE_Y=6371000*math.pi/180
CELL=30


def describe(segments):
    lines=[[(p[0]*SCALE_X,p[1]*SCALE_Y) for p in s] for s in segments]
    points=[p for s in lines for p in s]
    bounds=(min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points))
    length=sum(math.dist(a,b) for s in lines for a,b in zip(s,s[1:]))
    return {'lines':lines,'bounds':bounds,'length':length,'grid':None}


def index(shape):
    if shape['grid'] is not None:return shape['grid']
    grid={};long=[]
    for line in shape['lines']:
        for a,b in zip(line,line[1:]):
            x0,x1=math.floor((min(a[0],b[0])-2)/CELL),math.floor((max(a[0],b[0])+2)/CELL)
            y0,y1=math.floor((min(a[1],b[1])-2)/CELL),math.floor((max(a[1],b[1])+2)/CELL)
            segment=(a,b)
            if (x1-x0+1)*(y1-y0+1)>4096:
                long.append(segment);continue
            for x in range(x0,x1+1):
                for y in range(y0,y1+1):grid.setdefault((x,y),[]).append(segment)
    shape['grid']=(grid,long)
    return grid,long


def squared_distance(point,segment):
    a,b=segment;dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0,min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    return (point[0]-a[0]-t*dx)**2+(point[1]-a[1]-t*dy)**2


def directed_match(first,second):
    grid,long=index(second)
    for line in first['lines']:
        for a,b in zip(line,line[1:]):
            count=max(1,math.ceil(math.dist(a,b)/4))
            for i in range(count+1):
                t=i/count;point=(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]))
                nearby=grid.get((math.floor(point[0]/CELL),math.floor(point[1]/CELL)),[])
                if not any(squared_distance(point,s)<=4 for s in nearby+long):return False
    return True


def equivalent(first,second):
    # This is deliberately tighter than GPS accuracy: a 10 m alternative stays
    # distinct. Compare both directions to detect missing branches or shortcuts.
    if len(first['lines'])!=len(second['lines']):return False
    if abs(first['length']-second['length'])>max(2,min(first['length'],second['length'])*.01):return False
    if any(abs(a-b)>2 for a,b in zip(first['bounds'],second['bounds'])):return False
    return directed_match(first,second) and directed_match(second,first)
