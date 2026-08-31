# -*- coding: utf-8 -*-
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
import pandas as pd, numpy as np, os
A="/sessions/rcw-01wech2x8rpdcfqbps4g1htr/mnt/해커톤/07_에셋/"
OUT="/sessions/rcw-01wech2x8rpdcfqbps4g1htr/mnt/해커톤/데이터셋/sweep_분석_0827/"
for f in ["PRETENDARD-BOLD.OTF","PRETENDARD-MEDIUM.OTF","PRETENDARD-REGULAR.OTF"]: fm.fontManager.addfont(A+f)
BOLD=fm.FontProperties(fname=A+"PRETENDARD-BOLD.OTF"); MED=fm.FontProperties(fname=A+"PRETENDARD-MEDIUM.OTF"); REG=fm.FontProperties(fname=A+"PRETENDARD-REGULAR.OTF")
NAVY="#1B3A5C"; TEAL="#1A9080"; ORANGE="#E8552D"; GREY="#6B7684"; BORDER="#D4DBE2"
plt.rcParams['axes.unicode_minus']=False

runs=pd.read_pickle(os.path.expanduser("~/scratch/runs.pkl"))
runs['zeta']=runs.p_damping/(2*np.sqrt(runs.p_stiffness))
def style(ax):
    for s in ['top','right']: ax.spines[s].set_visible(False)
    for s in ['left','bottom']: ax.spines[s].set_color(BORDER)
    ax.tick_params(colors=GREY,labelsize=9)
    for t in ax.get_xticklabels()+ax.get_yticklabels(): t.set_fontproperties(REG)
    ax.grid(axis='y',color=BORDER,lw=.6,alpha=.7); ax.set_axisbelow(True)

# ---- FIG1: baseline vs 세그먼트별 최적
order=['C3','C4','C5','C13','C14','C15','C16','C17','SL1','SL2','SL3','SL4','SL9','SL10','SL11']
base={};best={};bp={}
for s in order:
    g=runs[runs.seg==s]
    base[s]=g[g.kind=='baseline'].inband_ratio_contact.iloc[0]
    gg=g[(g.kind=='rand')&(g.overpress_ratio==0)]
    if len(gg)==0: gg=g[g.kind=='rand']
    b=gg.sort_values('inband_ratio_contact',ascending=False).iloc[0]
    best[s]=b.inband_ratio_contact; bp[s]=(b.p_target_force,b.p_stiffness,b.p_damping,b.p_speed_scale)
fig,ax=plt.subplots(figsize=(11.7,4.6),dpi=200); style(ax)
x=np.arange(len(order)); w=.38
ax.bar(x-w/2,[base[s] for s in order],w,color=GREY,label="baseline 고정 게인 (5.0N / k350 / c35 / spd3.0)")
ax.bar(x+w/2,[best[s] for s in order],w,color=TEAL,label="세그먼트별 최적 파라미터 (39개 랜덤 중 최고)")
for i,s in enumerate(order):
    d=best[s]-base[s]
    ax.text(i+w/2,best[s]+.015,f"+{d*100:.0f}",ha='center',fontproperties=MED,fontsize=8,color=ORANGE)
ax.set_xticks(x); ax.set_xticklabels(order,fontproperties=MED,fontsize=9.5)
ax.set_ylim(0,1.13); ax.set_yticks([0,.25,.5,.75,1.0])
ax.set_ylabel("접촉 중 in-band 비율",fontproperties=MED,fontsize=10,color=NAVY)
ax.axvline(7.5,color=BORDER,lw=1.2,ls='--')
ax.text(3.5,1.08,"천장 로봇 C",ha='center',fontproperties=MED,fontsize=9.5,color=NAVY)
ax.text(11.5,1.08,"측면좌 로봇 SL",ha='center',fontproperties=MED,fontsize=9.5,color=NAVY)
ax.set_title("고정 게인은 형상에 따라 무너진다 — 세그먼트별 파라미터 적응 시 회복폭 (막대 위 숫자 = %p 개선)",
             fontproperties=BOLD,fontsize=13,color=NAVY,loc='left',pad=14)
lg=ax.legend(prop=MED,fontsize=9,frameon=False,loc='upper center',bbox_to_anchor=(0.5,-0.09),ncol=2)
fig.tight_layout(); fig.savefig(OUT+"fig1_baseline_vs_optimal.png",bbox_inches='tight',facecolor='white'); plt.close(fig)

# ---- FIG2: stiffness 스윗스팟
fig,ax=plt.subplots(figsize=(6.6,4.3),dpi=200); style(ax)
runs['kbin']=pd.cut(runs.p_stiffness,[200,350,500,650,800])
g=runs.groupby('kbin',observed=True).agg(inband=('inband_ratio_contact','mean'),over=('overpress_ratio','mean'),n=('p_stiffness','size'))
lbl=["200~350","350~500","500~650","650~800"]
ax.bar(lbl,g.inband,color=[GREY,TEAL,TEAL,GREY],width=.6)
for i,(v,n) in enumerate(zip(g.inband,g.n)): ax.text(i,v+.012,f"{v:.3f}",ha='center',fontproperties=MED,fontsize=9,color=NAVY)
ax.set_ylim(0,.92); ax.set_ylabel("in-band 비율",fontproperties=MED,fontsize=10,color=NAVY)
ax.set_xlabel("가상 스프링 강성 k",fontproperties=MED,fontsize=10,color=GREY)
ax2=ax.twinx(); ax2.plot(lbl,g.over*100,color=ORANGE,marker='o',lw=2,ms=5)
ax2.set_ylabel("과압(overpressure) 발생률 %",fontproperties=MED,fontsize=9.5,color=ORANGE)
ax2.tick_params(colors=ORANGE,labelsize=9); ax2.spines['top'].set_visible(False); ax2.set_ylim(0,10)
for t in ax2.get_yticklabels(): t.set_fontproperties(REG)
ax.set_title("강성 스윗스팟: 500~650\n너무 낮으면 추종 실패, 너무 높으면 과압",fontproperties=BOLD,fontsize=12,color=NAVY,loc='left',pad=12)
fig.tight_layout(); fig.savefig(OUT+"fig2_stiffness_sweetspot.png",bbox_inches='tight',facecolor='white'); plt.close(fig)

# ---- FIG3: 감쇠비
fig,ax=plt.subplots(figsize=(6.6,4.3),dpi=200); style(ax)
ax.scatter(runs.zeta,runs.inband_ratio_contact,s=13,color=TEAL,alpha=.35,edgecolors='none')
runs['zbin']=pd.cut(runs.zeta,[0,0.6,0.9,1.2,1.6,3])
gz=runs.groupby('zbin',observed=True).agg(m=('inband_ratio_contact','mean'))
cx=[0.3,0.75,1.05,1.4,2.3]
ax.plot(cx,gz.m,color=NAVY,marker='o',lw=2.2,ms=6,label="구간 평균")
ax.axvspan(1.2,1.6,color=ORANGE,alpha=.10)
ax.axvline(1.0,color=GREY,lw=1.1,ls='--')
ax.text(1.02,.04,"임계감쇠 ζ=1",fontproperties=REG,fontsize=8.5,color=GREY)
ax.text(1.4,1.02,"최적대 1.2~1.6",ha='center',fontproperties=MED,fontsize=9,color=ORANGE)
ax.set_xlim(0,2.9); ax.set_ylim(0,1.09)
ax.set_xlabel("감쇠비 ζ = c / (2√k)",fontproperties=MED,fontsize=10,color=GREY)
ax.set_ylabel("in-band 비율",fontproperties=MED,fontsize=10,color=NAVY)
ax.legend(prop=MED,fontsize=9,frameon=False,loc='lower right')
ax.set_title("임계감쇠보다 살짝 과감쇠가 낫다\n595개 run, 점 하나 = 한 파라미터 조합",fontproperties=BOLD,fontsize=12,color=NAVY,loc='left',pad=12)
fig.tight_layout(); fig.savefig(OUT+"fig3_damping_ratio.png",bbox_inches='tight',facecolor='white'); plt.close(fig)

# ---- FIG4: speed 트레이드오프
fig,ax=plt.subplots(figsize=(6.6,4.3),dpi=200); style(ax)
runs['sbin']=pd.cut(runs.p_speed_scale,[0.5,1.5,2.5,3.5,4.5])
gs=runs.groupby('sbin',observed=True).agg(inband=('inband_ratio_contact','mean'),steps=('steps','mean'))
lb=["0.5~1.5","1.5~2.5","2.5~3.5","3.5~4.5"]
ax.plot(lb,gs.inband,color=TEAL,marker='o',lw=2.4,ms=7,label="in-band 비율 (품질)")
ax.set_ylim(.6,.78); ax.set_ylabel("in-band 비율",fontproperties=MED,fontsize=10,color=TEAL)
ax.set_xlabel("속도 배율 speed_scale",fontproperties=MED,fontsize=10,color=GREY)
ax2=ax.twinx(); ax2.plot(lb,gs.steps,color=ORANGE,marker='s',lw=2.4,ms=6,ls='--',label="평균 스텝수 (사이클타임)")
ax2.set_ylabel("run 평균 스텝수",fontproperties=MED,fontsize=9.5,color=ORANGE)
ax2.tick_params(colors=ORANGE,labelsize=9); ax2.spines['top'].set_visible(False)
for t in ax2.get_yticklabels(): t.set_fontproperties(REG)
h1,l1=ax.get_legend_handles_labels(); h2,l2=ax2.get_legend_handles_labels()
ax.legend(h1+h2,l1+l2,prop=MED,fontsize=9,frameon=False,loc='upper center')
ax.set_title("품질 vs 사이클타임 트레이드오프\n느릴수록 정확하지만 1.5배 오래 걸린다",fontproperties=BOLD,fontsize=12,color=NAVY,loc='left',pad=12)
fig.tight_layout(); fig.savefig(OUT+"fig4_speed_tradeoff.png",bbox_inches='tight',facecolor='white'); plt.close(fig)

# ---- FIG5: 상관 히트맵
def sp(a,b):
    m=a.notna()&b.notna(); return np.corrcoef(a[m].rank(),b[m].rank())[0,1]
P=['p_target_force','p_stiffness','p_damping','p_speed_scale']
K=['inband_ratio_contact','force_err_mae','force_std_contact','overpress_ratio','contact_ratio','steps']
Pl=["목표힘","강성 k","감쇠 c","속도배율"]; Kl=["in-band\n비율","힘오차\nMAE","힘 표준\n편차","과압\n발생률","접촉\n비율","스텝수\n(시간)"]
M=np.array([[sp(runs[p],runs[k]) for k in K] for p in P])
fig,ax=plt.subplots(figsize=(7.6,3.5),dpi=200)
im=ax.imshow(M,cmap='RdBu_r',vmin=-.5,vmax=.5)
ax.set_xticks(range(len(K))); ax.set_yticks(range(len(P)))
ax.set_xticklabels(Kl,fontproperties=MED,fontsize=9); ax.set_yticklabels(Pl,fontproperties=MED,fontsize=10)
for i in range(len(P)):
    for j in range(len(K)):
        ax.text(j,i,f"{M[i,j]:+.2f}",ha='center',va='center',fontproperties=MED,fontsize=9.5,
                color='white' if abs(M[i,j])>.3 else '#222')
ax.tick_params(colors=NAVY,length=0); ax.spines[:].set_visible(False)
cb=fig.colorbar(im,shrink=.8); cb.ax.tick_params(labelsize=8,colors=GREY)
for t in cb.ax.get_yticklabels(): t.set_fontproperties(REG)
ax.set_title("파라미터 ↔ 성능 순위상관 (Spearman, n=595)",fontproperties=BOLD,fontsize=12,color=NAVY,loc='left',pad=12)
fig.tight_layout(); fig.savefig(OUT+"fig5_correlation.png",bbox_inches='tight',facecolor='white'); plt.close(fig)

# 최적 파라미터표 저장
rows=[[s,round(base[s],3),round(best[s],3),round(best[s]-base[s],3)]+[round(v,2) for v in bp[s]] for s in order]
tb=pd.DataFrame(rows,columns=['segment','baseline_inband','best_inband','delta','target_force_n','stiffness','damping','speed_scale'])
tb.to_csv(OUT+"세그먼트별_최적파라미터.csv",index=False,encoding='utf-8-sig')
print(tb.to_string(index=False))
print("\nfigures:",os.listdir(OUT))
