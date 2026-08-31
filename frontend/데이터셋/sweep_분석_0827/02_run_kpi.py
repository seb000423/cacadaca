import pandas as pd, numpy as np, os
pd.set_option('display.width',250); pd.set_option('display.max_columns',60); pd.set_option('display.max_rows',100)
df=pd.read_pickle(os.path.expanduser("~/scratch/all.pkl"))
df['seg']=df['run_id'].str.split('_').str[0]
df['kind']=np.where(df.run_id.str.contains('baseline'),'baseline','rand')
df['sample']=df['run_id'].str.extract(r'_(?:rand|baseline)_(\d+)_r').astype(int)

# 1) rand_N 파라미터가 파일 간 동일한가?
piv=df.groupby(['seg','sample'])[['p_target_force','p_stiffness','p_damping','p_speed_scale']].first().reset_index()
chk=piv[piv['sample']!=0].groupby('sample')[['p_target_force','p_stiffness','p_damping','p_speed_scale']].nunique()
print("=== rand 샘플별 세그먼트 간 파라미터 고유값(1이면 공유) ===")
print(chk.head(8).to_string()); print("... 전체 최대:", chk.max().to_dict())

# 2) 세그먼트별 run 수 / 샘플 인덱스 범위
print("\n=== 세그먼트별 ===")
g=df.groupby('seg').agg(runs=('run_id','nunique'), rows=('step','size'), wps=('waypoint_idx','max'), passes=('polish_pass','max'))
print(g.to_string())

# 3) run 단위 KPI
def rk(x):
    n=len(x); c=x['contacting']==1
    return pd.Series({
        'steps':n,
        'contact_ratio':c.mean(),
        'inband_ratio_all':(x['in_band']==1).mean(),
        'inband_ratio_contact':(x.loc[c,'in_band']==1).mean() if c.any() else np.nan,
        'overpress_ratio':(x['overpressure']==1).mean(),
        'force_mean_contact':x.loc[c,'filtered_force_n'].mean() if c.any() else np.nan,
        'force_std_contact':x.loc[c,'filtered_force_n'].std() if c.any() else np.nan,
        'force_err_mae':(x.loc[c,'filtered_force_n']-x.loc[c,'target_force_n']).abs().mean() if c.any() else np.nan,
        'force_max':x['filtered_force_n'].max(),
        'pause_steps':(x['high_force_pause_steps']>0).sum(),
        'wp_done':x['waypoint_idx'].max()+1,
        'p_target_force':x['p_target_force'].iloc[0],'p_stiffness':x['p_stiffness'].iloc[0],
        'p_damping':x['p_damping'].iloc[0],'p_speed_scale':x['p_speed_scale'].iloc[0],
        'seg':x['seg'].iloc[0],'kind':x['kind'].iloc[0],
    })
runs=df.groupby('run_id',group_keys=False).apply(rk)
runs.to_pickle(os.path.expanduser("~/scratch/runs.pkl"))
print("\n=== run 단위 KPI 요약 (595 runs) ===")
print(runs.drop(columns=['seg','kind']).describe().to_string())
print("\n=== baseline vs rand 평균 ===")
print(runs.groupby('kind')[['contact_ratio','inband_ratio_contact','overpress_ratio','force_err_mae','force_std_contact','steps']].mean().to_string())
