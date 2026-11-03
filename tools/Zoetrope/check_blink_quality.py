#!/usr/bin/env python3
"""Check eye motion in generated CD readback; not real-disc optical acceptance."""
import argparse
import json
import math
from pathlib import Path
from compare_cd_readback import read_gray_png,correlation

WIDTH,HEIGHT=300,450
EYES=((79,137),(164,220))
OPEN=(0,1,10,11)
CLOSED=(5,6)

def white_fraction(pixels,width,points):
    values=[pixels[y*width+x] for x,y in points]
    return sum(value>=220 for value in values)/len(values)

def map_to_cd(frame,x,y):
    u=(x+.5)/WIDTH
    v=(y+.5)/HEIGHT
    radius=(1140-640*v)/3
    angle=(frame+.025+.95*u)*math.tau/12
    return (int(round(400+radius*math.sin(angle))),int(round(400-radius*math.cos(angle))))

def mean(values):
    return sum(values)/len(values)

def main():
    parser=argparse.ArgumentParser()
    for arg in ("frames","warp","readback","report"):
        parser.add_argument("--"+arg,required=True,type=Path)
    parser.add_argument("--sectors",type=int,default=45000)

    args=parser.parse_args()
    if args.sectors < 75:
        raise ValueError("Expected at least 75 sectors")
    frames=[]
    for i in range(12):
        w,h,image=read_gray_png(args.frames/f"{i:02}.png")
        if (w,h)!=(300,450): raise ValueError("Unexpected source frame dimensions")
        frames.append(image)
    changed=leaked=0
    for y in range(450):
        for x in range(300):
            index=y*300+x
            if any(image[index]!=frames[0][index] for image in frames[1:]):
                changed+=1
                if not (74<=x<=226 and 181<=y<=220): leaked+=1
    ww,wh,warp=read_gray_png(args.warp)
    rw,rh,readback=read_gray_png(args.readback)
    if (ww,wh,rw,rh)!=(800,800,800,800):
        raise ValueError("Unexpected CD preview dimensions")
    positions=[(x,y) for a,b in EYES for y in range(185,214) for x in range(a,b)]
    source,projection,recovered=[],[],[]
    for i in range(12):
        coords=[map_to_cd(i,x,y) for x,y in positions]
        if not all(0<=x<800 and 0<=y<800 for x,y in coords):
            raise ValueError("Eye ROI outside CD readback")
        source.append(white_fraction(frames[i],300,positions))
        projection.append(white_fraction(warp,800,coords))
        recovered.append(white_fraction(readback,800,coords))
    def gap(arr):
        return mean([arr[i] for i in OPEN])-mean([arr[i] for i in CLOSED])
    source_gap=gap(source)
    projection_gap=gap(projection)
    readback_gap=gap(recovered)
    timing_r=correlation(source,recovered)
    projection_r=correlation(projection,recovered)
    failures=[]
    if changed<=100 or leaked: failures.append("eye_only_frame_motion_invalid")
    if source_gap<.25: failures.append("source_eye_animation_not_visible")
    if readback_gap<.08: failures.append("readback_eye_open_closed_difference_below_0.08")
    if timing_r<.7: failures.append("readback_blink_temporal_correlation_below_0.7")
    if projection_r<.98: failures.append("readback_differs_from_projection")
    report={
        "gate":"PASS" if not failures else "FAIL",
        "scope":f"synthetic illustrated face, 12 frames, {args.sectors/75:.3f}-second CD-DA image test ({args.sectors} sectors)",
        "sectors":args.sectors,
        "changed_eye_pixels":changed,
        "changed_outside_eye_mask":leaked,
        "source_eye_white_fractions":[round(x,4) for x in source],
        "projection_eye_white_fractions":[round(x,4) for x in projection],
        "readback_eye_white_fractions":[round(x,4) for x in recovered],
        "source_open_closed_difference":round(source_gap,4),
        "projection_open_closed_difference":round(projection_gap,4),
        "readback_open_closed_difference":round(readback_gap,4),
        "temporal_correlation_source_readback":round(timing_r,4),
        "correlation_projection_readback":round(projection_r,4),
        "limitations":[
            "Synthetic illustrated face, not a real singer photograph.",
            "CD preview is a simulated digital readback, not physical CD-R.",
            "Unsampled pixels appear white in this renderer; perceptual legibility unverified.",
            "Full-capacity sector count alone does not establish actual burner, reflectivity, spindle or strobe behavior.",
            "The generated audio track contains encoded image pattern, not songs."
        ],
        "failures":failures
    }
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"blink-portrait-qc: {report['gate']} | source-gap={source_gap:.4f} | readback-gap={readback_gap:.4f} | temporal-r={timing_r:.4f}")
    if failures:
        print("blink-portrait failures: "+", ".join(failures))
        return 1
    return 0

if __name__=="__main__": raise SystemExit(main())
