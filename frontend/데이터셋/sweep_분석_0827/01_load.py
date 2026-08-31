import pandas as pd, numpy as np, glob, os, json
d="/sessions/rcw-01wech2x8rpdcfqbps4g1htr/mnt/해커톤/데이터셋/sweep_traj_csv/sweep_traj_csv"
files=sorted(glob.glob(os.path.join(d,"*.csv")))
frames=[]
for f in files:
    df=pd.read_csv(f)
    df['file']=os.path.basename(f)
    frames.append(df)
    print(os.path.basename(f), df.shape, df['run_id'].nunique())
all_=pd.concat(frames,ignore_index=True)
all_.to_pickle(os.path.expanduser("~/scratch/all.pkl"))
print("TOTAL", all_.shape, "runs:", all_['run_id'].nunique())
