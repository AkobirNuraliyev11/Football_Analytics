"""Render saved diagnostic counts; does not run inference or imply global accuracy."""
import os
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

r=json.loads((ROOT/'evaluations/ball-aerial-baseline.json').read_text())
fig,axes=plt.subplots(2,1,figsize=(10,7.2))
fig.patch.set_facecolor('#f7f9fb')
for ax in axes:
    ax.set_facecolor('#f7f9fb')
    ax.spines[['top','right','left']].set_visible(False)
    ax.tick_params(axis='y',length=0,pad=12)
    ax.grid(axis='x',alpha=.18,zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(0,100)
    ax.set_xticks([0,25,50,75,100])
    ax.set_xlabel('Share of annotated observations or frames (%)')
values=[r['person_observation_funnel']['raw'],r['person_observation_funnel']['tracked']]
axes[0].barh([1,0],[v/682*100 for v in values],height=.46,color='#247c91',zorder=3)
axes[0].set_yticks([1,0],['Raw detector matches','After tracking'])
axes[0].set_title('PLAYERS  |  682 annotated observations',loc='left',pad=18,fontsize=13,fontweight='bold')
for y,v in zip([1,0],values):axes[0].text(v/682*100+2,y,f'{v}/682  ({v/682*100:.1f}%)',va='center',fontsize=11)
values=[31-r['ball_raw_missed_frames'],r['selection']['before']['correct']]
axes[1].barh([1,0],[v/31*100 for v in values],height=.46,color='#247c91',zorder=3)
axes[1].set_yticks([1,0],['Reference-near ball candidate','Correct selected match ball'])
axes[1].set_title('BALL  |  31 annotated frames',loc='left',pad=18,fontsize=13,fontweight='bold')
axes[1].text(91,1,'29/31 (93.5%)',ha='right',va='center',color='white',fontsize=11)
axes[1].text(2,0,'0/31 — all 31 unresolved',va='center',fontsize=11)
fig.suptitle('Where the current pipeline loses useful observations',x=.045,ha='left',fontsize=17,fontweight='bold')
fig.text(.045,.905,'One aerial development sequence · current default pipeline · not overall model accuracy',fontsize=11,color='#465467')
fig.text(.045,.035,'Players: symmetric 40 px / 10 px matching. Ball: candidate centre within 10 px of reference.\nCounts do not validate physical speed or prove performance on new matches.',fontsize=10,color='#465467')
fig.subplots_adjust(left=.32,right=.96,top=.80,bottom=.14,hspace=.75)
fig.savefig(ROOT/'docs/design/project-evidence.png',dpi=160,facecolor=fig.get_facecolor())
plt.close(fig)
