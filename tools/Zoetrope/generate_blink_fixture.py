#!/usr/bin/env python3
"""Synthetic blink-portrait test fixture. Not a real singer's likeness."""
import argparse
import pathlib
import struct
import zlib

WIDTH,HEIGHT=300,450
BLINK=(1.0,.96,.80,.54,.22,.03,.03,.22,.54,.80,.96,1.0)

def ellipse(x,y,cx,cy,rx,ry):
    return ((x-cx)/rx)**2+((y-cy)/ry)**2<=1

def pixel(x,y,openness,style="classic"):
    v=244
    if ellipse(x,y,150,480,178,133): v=52
    if ellipse(x,y,150,366,35,88): v=154
    if ellipse(x,y,50,217,17,30) or ellipse(x,y,250,217,17,30): v=140
    if ellipse(x,y,150,178,118,144): v=45
    if ellipse(x,y,150,215,102,156):
        v=int(max(100,min(219,184+.17*(x-150)-.09*abs(y-195))))
    if ellipse(x,y,150,166,117,139) and (
        y<126+.28*abs(x-150) or (abs(x-150)>91 and y<275)
        or (y<172 and abs(x-150)>62)):
        v=39
    for ex in (108,192):
        dx=x-ex
        if abs(dx)<34 and abs(y-(174-4*(1-(dx/34)**2)))<=2.2:
            v=37
    if 147<=x<=151 and 222<=y<=256: v=140
    if ellipse(x,y,143,259,5,2.4) or ellipse(x,y,160,259,5,2.4): v=75
    if abs(x-150)<23 and abs(y-(299+.010*(x-150)**2))<1.5: v=70
    if abs(x-150)<18 and abs(y-(309-.007*(x-150)**2))<1.3: v=142
    # Only the eyes change between frames; face, background and cheeks are fixed.
    # The bold style is a deliberately graphic stress-test target, NOT a
    # claim that real face photos can preserve this exaggerated open/closed gap.
    for ex in (108,192):
        dx=x-ex
        if abs(dx)>31 or not (183<=y<=220): continue
        if style=="bold":
            # High-contrast eyes designed to tolerate the disc's small wedge.
            # Static black outline, changing high-area iris/eyelid fill.
            q=(dx/29)**2 + ((y-200)/16)**2
            if q<=1:
                v=round(25+230*openness)
                if q>.82: v=20
                if openness>.5 and ellipse(x,y,ex,200,4.8,6): v=18
            continue
        arc=max(0.,1.-(dx/31)**2)**.5
        height=11.6*openness*arc
        dy=y-200
        if abs(dy)<=height: v=247
        if openness>.25 and ellipse(x,y,ex,200,8.7,10):
            if abs(dy)<=height+.7:
                v=52
                if ellipse(x,y,ex,200,3.6,4.5): v=16
        if abs(dy+height)<=1.5 or abs(dy-height)<=1.15: v=27
    return v

def write_png(path,pixels):
    def chunk(tag,body):
        return struct.pack(">I",len(body))+tag+body+struct.pack(">I",zlib.crc32(tag+body)&0xffffffff)
    scan=b"".join(b"\x00"+pixels[y*WIDTH:(y+1)*WIDTH] for y in range(HEIGHT))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+
        chunk(b"IHDR",struct.pack(">IIBBBBB",WIDTH,HEIGHT,8,0,0,0,0))+
        chunk(b"IDAT",zlib.compress(scan,7))+chunk(b"IEND",b""))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=pathlib.Path,required=True)
    p.add_argument("--style",choices=("classic","bold"),default="classic")
    args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if any(args.out.iterdir()): raise ValueError("Output directory must be empty")
    for frame,openness in enumerate(BLINK):
        pix=bytes(pixel(x,y,openness,args.style) for y in range(HEIGHT) for x in range(WIDTH))
        write_png(args.out/f"{frame:02}.png",pix)
    print(f"blink-fixture: PASS (style={args.style}, 12 synthetic 300x450 portraits, eye-only motion)")

if __name__=="__main__": main()
