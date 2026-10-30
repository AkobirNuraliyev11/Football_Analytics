"""Generate a reproducible synthetic example. These are NOT match measurements."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from football_intelligence.telemetry_io import compute_telemetry


def demo(output, plot=False):
    output.mkdir(parents=True, exist_ok=False)
    source = output/"synthetic-tracks.jsonl"
    with source.open("x") as handle:
        for i in range(201):
            t = i/25
            people = []
            for track_id, speed, y in [(1,3,20), (2,6,30), (3,3,40), (4,3,50)]:
                if track_id == 3 and t > .4:
                    continue
                people.append({"track_id":track_id, "kind":"person", "role":"outfield", "team":"A",
                    "confirmed":True, "continuity_safe":True, "measurement_link_eligible":True,
                    "classification_conflict":False, "team_changed":False, "continuity_segment":0,
                    "calibration_id":"synthetic-exact-geometry", "coordinate_reference_id":"synthetic-pitch",
                    "ground_contact_reliable":track_id != 4, "projection_state":"validated_ground_position",
                    "pitch_position_candidate":{"x_m":10+speed*t, "y_m":y}})
            frame = {"match_id":"synthetic-demo-not-real-footage", "shot_id":0, "frame_index":i,
                "timestamp_s":t, "calibration_status":"validated", "detections":people}
            handle.write(json.dumps(frame)+"\n")
    compute_telemetry(source,output/"results")
    summary=json.loads((output/"results/telemetry-summary.json").read_text())
    rows={row["track_id"]:row for row in summary["fragments"]}
    assert set(rows)=={1,2}, rows
    for track, speed, distance, sprints in [(1,10.8,24,0),(2,21.6,48,1)]:
        row=rows[track]
        assert math.isclose(row["top_speed_kmh"],speed,abs_tol=1e-8)
        assert math.isclose(row["observed_distance_m"],distance,abs_tol=1e-8)
        assert row["sprint_count"]==sprints
    report = """# Step 6 — known-motion demonstration

**Synthetic inputs, not measurements from the football video.**

Two simulated players move for eight seconds on an exact virtual pitch. The first
moves three meters each second; the second moves six. The engine reproduces:

| Track | Speed | Observed distance | Sustained sprints |
|---|---|---|---|
| 1 | 10.8 km/h | 24 m | 0 |
| 2 | 21.6 km/h | 48 m | 1 |

The 0.4-second ghost track is excluded. A fourth track with unverified ground
contact is withheld. Measurements become visible after two seconds of continuous
eligible observations; the retained fragment includes its warmup distance.

The sprint is still in progress when the sample ends, so its end is marked truncated.
The real football clip has unvalidated geometry and ground contact, and must not
inherit these synthetic values. See its separately generated telemetry summary.
"""
    (output/"README.md").write_text(report)
    if plot:
        plot_demo(output)
    print(json.dumps({"status":"passed", "report":str(output/"README.md"),
                      "synthetic_results":summary["fragments"]},indent=2))


def plot_demo(output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    frames=[json.loads(line) for line in (output/"results/telemetry.jsonl").read_text().splitlines()]
    plt.style.use("dark_background")
    figure, axes=plt.subplots(1,2,figsize=(12,4.8))
    figure.patch.set_facecolor("#111b2a")
    for ax in axes:
        ax.set_facecolor("#111b2a")
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(alpha=.13)
        ax.set_xlabel("Time (seconds)")
        ax.axvspan(0,2,color="white",alpha=.06)
    for track,color in [(1,"#53cfc2"),(2,"#f7bb67")]:
        points=[(f["timestamp_s"],o) for f in frames for o in f["observations"]
                if o["track_id"]==track and o["speed_kmh"] is not None]
        for ax,field in zip(axes,["speed_kmh","observed_distance_m"]):
            ax.plot([t for t,_ in points],[o[field] for _,o in points],color=color,lw=2.5,label=f"Track {track}")
    axes[0].axhline(18,color="#aeb7c5",ls="--",lw=1,label="Sprint threshold")
    axes[0].set(ylabel="Speed (km/h)",ylim=(0,26),xlim=(0,8),title="Speed after the two-second warmup")
    axes[1].set(ylabel="Observed distance (meters)",ylim=(0,54),xlim=(0,8),title="Distance within each continuous fragment")
    axes[0].legend(frameon=False,loc="lower right")
    figure.suptitle("Step 6 · Known-motion checks",fontsize=19,x=.07,ha="left")
    figure.text(.07,.88,"SYNTHETIC DEMO — these values are not football-video measurements",color="#f7bb67")
    figure.text(.07,.035,"Track 1: 24 m, 0 sprints     |     Track 2: 48 m, 1 sprint     |     Ghost and ungrounded tracks excluded",fontsize=10)
    figure.subplots_adjust(top=.76,bottom=.19,wspace=.25,left=.07,right=.97)
    figure.savefig(output/"telemetry-demo.png",dpi=150,facecolor=figure.get_facecolor())
    plt.close(figure)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--plot",action="store_true",help="Also render a chart (requires matplotlib)")
    args=parser.parse_args()
    demo(args.output,args.plot)
