#!/usr/bin/env python3
"""Fail-closed cloud evidence aggregation. Hardware and Windows remain NOT_RUN."""
import argparse
import json
import subprocess
from pathlib import Path

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def main():
    p=argparse.ArgumentParser()
    for n in ("capacity","blink","stress","windows_script","report"):
        p.add_argument("--"+n.replace("_","-"),required=True)
    a=p.parse_args()
    c,b,s=read(a.capacity),read(a.blink),read(a.stress)
    assert c["gate"]=="PASS" and c["sectors"]==359849 and c["wav_bytes"]==846364892
    assert c["full_last_sector_present"] is True
    assert b["gate"]=="PASS" and b["sectors"]==359849
    assert b["readback_open_closed_difference"]>=0.55
    assert b["temporal_correlation_source_readback"]>=0.98
    assert s["gate"]=="PASS" and s["not_a_physical_pass"] is True
    assert s["total_tested_conditions"]==216 and len(s["scenarios"])==216
    assert s["surviving_conditions"]>=150
    assert s["model"]["assumed_survival_heuristic"]=={
        "minimum_absolute_open_minus_closed_gray":8.0,
        "minimum_temporal_correlation":0.85,
    }
    script=Path(a.windows_script).read_text(encoding="utf-8")
    assert all(x in script for x in ("359849","WINDOWS_ARTIFACT_PREP_PASS","NOT_RUN","Get-FileHash"))
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    result={
        "gate":"CLOUD_PRE_DEVICE_RC_PASS",
        "source_commit":sha,
        "source_branch":"feature/zoetrope-animation-v1",
        "tested":{"full_cd_sectors":c["sectors"],"full_cd_bytes":c["wav_bytes"],
                  "blink_gap":b["readback_open_closed_difference"],
                  "blink_temporal_r":b["temporal_correlation_source_readback"],
                  "stress_survived":s["surviving_conditions"],"stress_total":216},
        "windows_script":"PRESENT_STATIC_ONLY_NOT_RUN",
        "real_person_photo":"NOT_RUN",
        "physical_cd_r_burn":"NOT_RUN",
        "physical_optics":"NOT_RUN",
        "real_spindle_and_camera":"NOT_RUN",
        "warnings":["uncalibrated simulation is not optical evidence",
                    "encoded audio is an image carrier, not music"]
    }
    Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"CLOUD_PRE_DEVICE_RC_PASS | stress={s['surviving_conditions']}/216 | Windows=NOT_RUN | physical=NOT_RUN")

if __name__=="__main__":main()
