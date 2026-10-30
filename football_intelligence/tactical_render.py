"""RGB pitch, radar, and occupancy images; no matplotlib or model dependency."""
import math


COLORS = {"A": (250, 95, 105), "B": (235, 235, 245),
          "goalkeeper": (255, 210, 60), "official": (40, 220, 220)}


def pitch_image(pitch, *, title, subtitle, scale=10, rotate=False, heat=None, cell_m=1):
    import cv2
    import numpy as np
    length, width = pitch["length_m"], pitch["width_m"]
    w, h, left, top = round(length*scale), round(width*scale), 40, 90
    image = np.full((h+150, w+80, 3), (15, 24, 38), dtype=np.uint8)
    for x in range(w):
        image[top:top+h+1, left+x] = (29, 79, 59) if int(x/max(1,w/10)) % 2 else (33, 86, 64)
    if heat is not None and np.max(heat) > 0:
        # Grid values are probability mass per cell. Scaling is per image, labeled below.
        normalized = np.uint8(np.clip(heat/np.max(heat)*255, 0, 255))
        heat_rgb = cv2.cvtColor(cv2.applyColorMap(normalized, cv2.COLORMAP_JET), cv2.COLOR_BGR2RGB)
        size = (max(w, round(heat.shape[1]*cell_m*scale)), max(h, round(heat.shape[0]*cell_m*scale)))
        overlay = cv2.resize(heat_rgb, size, interpolation=cv2.INTER_LINEAR)[:h, :w]
        alpha = cv2.resize((normalized > 0).astype(float), size, interpolation=cv2.INTER_LINEAR)[:h, :w, None]*.7
        if rotate:
            overlay, alpha = overlay[::-1, ::-1], alpha[::-1, ::-1]
        base = image[top:top+h, left:left+w]
        base[:] = (base*(1-alpha)+overlay*alpha).astype(np.uint8)
    white = (205, 221, 213)
    def pt(x, y):
        return round(left+x*scale), round(top+y*scale)
    def rectangle(x1, y1, x2, y2):
        cv2.rectangle(image, pt(x1,y1), pt(x2,y2), white, 2, cv2.LINE_AA)
    rectangle(0,0,length,width)
    cv2.line(image, pt(length/2,0), pt(length/2,width), white, 2, cv2.LINE_AA)
    cv2.circle(image, pt(length/2,width/2), round(9.15*scale), white, 2, cv2.LINE_AA)
    cv2.circle(image, pt(length/2,width/2), 3, white, -1)
    for right in (False, True):
        edge = length if right else 0
        sign = -1 if right else 1
        rectangle(edge,width/2-20.16,edge+sign*16.5,width/2+20.16)
        rectangle(edge,width/2-9.16,edge+sign*5.5,width/2+9.16)
        rectangle(edge-sign*2,width/2-3.66,edge,width/2+3.66)
        cv2.circle(image,pt(edge+sign*11,width/2),3,white,-1)
        # Only the part of the penalty arc outside the penalty box is painted.
        angle = math.degrees(math.acos(5.5/9.15))
        start, end = (180-angle,180+angle) if right else (-angle,angle)
        cv2.ellipse(image, pt(edge+sign*11,width/2), (round(9.15*scale),)*2, 0,
                    start,end,white,2,cv2.LINE_AA)
    cv2.putText(image,title,(40,32),cv2.FONT_HERSHEY_SIMPLEX,.65,(242,245,248),2,cv2.LINE_AA)
    cv2.putText(image,subtitle,(40,59),cv2.FONT_HERSHEY_SIMPLEX,.43,(185,203,218),1,cv2.LINE_AA)
    cv2.putText(image,"Display rotated 180 degrees" if rotate else "Canonical orientation | attacking direction unknown",
                (40,h+127),cv2.FONT_HERSHEY_SIMPLEX,.44,(185,203,218),1,cv2.LINE_AA)
    return image


def radar_image(frame, pitch, *, scale=6, rotate=False):
    import cv2
    image = pitch_image(pitch, title=f"RADAR | {frame['quality']} | {frame['timestamp_s']:.2f}s",
                        subtitle=f"{frame['match_id'][:55]} | eligible positions only", scale=scale, rotate=rotate)
    for point in frame["positions"]:
        x, y = point["x_m"], point["y_m"]
        if rotate:
            x, y = pitch["length_m"]-x, pitch["width_m"]-y
        center = round(40+x*scale), round(90+y*scale)
        color = COLORS.get(point["role"], COLORS.get(point["team"], (160,160,160)))
        cv2.circle(image,center,6,(12,20,32),-1,cv2.LINE_AA)
        cv2.circle(image,center,4,color,-1,cv2.LINE_AA)
        cv2.putText(image,str(point["track_id"]),(center[0]+7,center[1]-5),
                    cv2.FONT_HERSHEY_SIMPLEX,.35,color,1,cv2.LINE_AA)
    if not frame["positions"]:
        cv2.putText(image,"POSITIONS UNAVAILABLE",(55,120),cv2.FONT_HERSHEY_SIMPLEX,.6,(255,210,100),2)
    return image


def export_heatmaps(summary, output, *, rotate=False):
    import cv2
    import numpy as np
    files = []
    for group in summary["groups"]:
        identity = group["identity"]
        label = (f"Team {identity['team']}" if identity["type"] == "team"
                 else f"Track {identity['track_id']} | {identity['role']} | team {identity['team']}")
        image = pitch_image(summary["pitch"], title=f"{label} | {summary['quality']}",
            subtitle=f"{identity['match_id'][:40]} | {group['observed_person_seconds']:.2f} person-s | NOT pitch control | shot {identity['shot_id']}",
            heat=np.array(group["probability_mass"]), cell_m=summary["cell_m"], rotate=rotate)
        # Explicit legend prevents comparing colors between separately normalized maps.
        bar = np.arange(256, dtype=np.uint8)[None, :]
        legend = cv2.cvtColor(cv2.applyColorMap(bar, cv2.COLORMAP_JET),cv2.COLOR_BGR2RGB)
        image[-34:-20, -310:-54] = np.repeat(legend,14,axis=0)
        cv2.putText(image,"0         relative to this map's peak",(image.shape[1]-310,image.shape[0]-5),
                    cv2.FONT_HERSHEY_SIMPLEX,.34,(220,230,240),1)
        name = f"heatmap-{group['id']}.png"
        if not cv2.imwrite(str(output/name),cv2.cvtColor(image,cv2.COLOR_RGB2BGR)):
            raise OSError("Failed to write heatmap")
        files.append(name)
    if not files:
        image = pitch_image(summary["pitch"],title="OCCUPANCY UNAVAILABLE",
            subtitle=f"{summary['quality']} | no eligible continuous positions | no inferred activity",rotate=rotate)
        name = "heatmap-unavailable.png"
        if not cv2.imwrite(str(output/name),cv2.cvtColor(image,cv2.COLOR_RGB2BGR)):
            raise OSError("Failed to write unavailable map")
        files.append(name)
    return files
