import pandas as pd, numpy as np, os
pd.set_option('display.width',250); pd.set_option('display.max_columns',60)
def sp(a,b):
    m=a.notna()&b.notna(); return np.corrcoef(a[m].rank(),b[m].rank())[0,1]
runs=pd.read_pickle(os.path.expanduser("~/scratch/runs.pkl"))
runs['zeta']=runs.p_damping/(2*np.sqrt(runs.p_stiffness))
print("zeta vs inband(spearman):",round(sp(runs.zeta,runs.inband_ratio_contact),3),
      " zeta vs mae:",round(sp(runs.zeta,runs.force_err_mae),3),
      " zeta vs overpress:",round(sp(runs.zeta,runs.overpress_ratio),3))
runs['zbin']=pd.cut(runs.zeta,[0,0.6,0.9,1.2,1.6,3])
print("\n=== zeta 구간별 ===")
print(runs.groupby('zbin',observed=True).agg(n=('zeta','size'),inband=('inband_ratio_contact','mean'),mae=('force_err_mae','mean'),over=('overpress_ratio','mean'),fstd=('force_std_contact','mean')).round(3).to_string())
runs['sbin']=pd.cut(runs.p_speed_scale,[0.5,1.5,2.5,3.5,4.5])
print("\n=== speed_scale 구간별 ===")
print(runs.groupby('sbin',observed=True).agg(n=('p_speed_scale','size'),inband=('inband_ratio_contact','mean'),contact=('contact_ratio','mean'),mae=('force_err_mae','mean'),steps=('steps','mean')).round(3).to_string())
runs['kbin']=pd.cut(runs.p_stiffness,[200,350,500,650,800])
print("\n=== stiffness 구간별 ===")
print(runs.groupby('kbin',observed=True).agg(n=('p_stiffness','size'),inband=('inband_ratio_contact','mean'),over=('overpress_ratio','mean'),fstd=('force_std_contact','mean')).round(3).to_string())

# waypoint 단위
df=pd.read_pickle(os.path.expanduser("~/scratch/all.pkl"))
df['seg']=df['run_id'].str.split('_').str[0]
wp=df.groupby(['run_id','seg','polish_pass','waypoint_idx']).agg(
    steps=('step','size'),contact=('contacting','mean'),inband=('in_band','mean'),
    f=('filtered_force_n','mean'),tgt=('target_force_n','first'),
    kmax=('wp_kappa_max','first'),kmin=('wp_kappa_min','first'),tilt=('wp_tilt_deg','first'),
    rho=('wp_rho_edge','first'),dth=('wp_dtheta_n','first'),
    k=('p_stiffness','first'),c=('p_damping','first'),spd=('p_speed_scale','first')).reset_index()
wp['err']=(wp.f-wp.tgt).abs()
print("\n=== waypoint 단위 샘플 수:",len(wp))
feat=['kmax','kmin','tilt','rho','dth','k','c','spd','tgt']
print("\n=== waypoint 특징 ↔ inband/contact 상관(spearman) ===")
for f_ in feat:
    print(f"{f_:6s} inband={sp(wp[f_],wp.inband): .3f}  contact={sp(wp[f_],wp.contact): .3f}  err={sp(wp[f_],wp.err): .3f}")
print("\n=== tilt 구간별 (수직도) ===")
wp['tb']=pd.cut(wp.tilt,[0,15,30,50,70,90])
print(wp.groupby('tb',observed=True).agg(n=('tilt','size'),contact=('contact','mean'),inband=('inband','mean'),err=('err','mean')).round(3).to_string())
print("\n=== rho_edge 구간별 (가장자리 근접) ===")
wp['rb']=pd.cut(wp.rho,[0.28,0.6,0.8,1.0,1.2,1.8])
print(wp.groupby('rb',observed=True).agg(n=('rho','size'),contact=('contact','mean'),inband=('inband','mean'),err=('err','mean')).round(3).to_string())
wp.to_pickle(os.path.expanduser("~/scratch/wp.pkl"))
