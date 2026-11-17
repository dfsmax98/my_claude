# -*- coding: utf-8 -*-
"""
Created on Mon Feb 26 23:06:53 2024

@author: z00119a
"""
import pandas as pd
import numpy as np
from optbinning.binning.metrics import jeffrey
from optbinning.binning.auto_monotonic import type_of_monotonic_trend
from optbinning import BinningProcess
from joblib import Parallel, delayed, effective_n_jobs

# 新增
from joblib import Parallel, delayed, effective_n_jobs
from joblib.externals.loky import set_loky_pickler
set_loky_pickler('cloudpickle')   # 新增


from sklearn.preprocessing import KBinsDiscretizer
from sklearn.utils import shuffle
import re
import itertools

from os.path import dirname,join

import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import font_manager as fm
from  matplotlib import cm, ticker
from matplotlib.pyplot import style
# 兼容新旧 matplotlib: 3.6+ 把 seaborn 样式重命名为 seaborn-v0_8-*; 失效不影响 Excel 报告功能
for _sty in ('seaborn-white', 'seaborn-v0_8-white'):
    try:
        style.use(_sty)
        break
    except (OSError, ValueError):
        continue
from statsmodels.graphics.mosaicplot import mosaic
import pylab
pylab.rcParams['font.sans-serif'] = ['SimHei']  # 指定默认字体
pylab.rcParams['axes.unicode_minus'] = False  # 解决保存图像是负号'-'显示为方块的问题

import os
import xlwings as xw

import excel2img
from IPython.display import display

# impala 仅用于可选遥测(get_log), 缺失不影响报告功能
try:
    from impala.dbapi import connect
except ImportError:
    connect = None
import getpass
import traceback

import time
from datetime import datetime
import json
import types
# graphviz 仅用于决策树可视化(plt_rule_to_tree), 缺失不影响报告功能
try:
    import graphviz
except ImportError:
    graphviz = None
from sklearn import tree
from sklearn.tree import  DecisionTreeClassifier
# from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

#%% 通用函数
def print_g(s,m='1;36;40m'):
        print(f"\033[{m}{s}\033[0m")
     
     
def get_log(name):
    try:
        if connect is None:
            return  # impala 未安装, 跳过可选遥测
        # 凭证从环境变量读取, 不硬编码; 缺失则跳过遥测
        _h = os.getenv('SM_HIVE_HOST'); _u = os.getenv('SM_MODEL_PY_USER'); _p = os.getenv('SM_MODEL_PY_PASSWORD')
        if not (_h and _u and _p):
            return
        conn = connect(host=_h, port=int(os.getenv('SM_HIVE_PORT', '10009')),
                       database='default', auth_mechanism='PLAIN',
                       user=_u, password=_p)
        cur = conn.cursor()
        
        log_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user= getpass.getuser()
        
        s = f"{log_time}. {user} start invoke {name} !!"
        
        cur.execute(f'insert into table d_mx.fix_zyt_log select "{s}"')
        
    except:
        pass


   
def timer(func):
    
    def wrapper(*arg,**kwargs):
        start_time = time.time()
        result = func(*arg,**kwargs)
        end_time = time.time()
        run_time = end_time-start_time
        hour,rem = divmod(run_time,3600)
        minutes,seconds = divmod(rem,60)
        
        print(f"Cost Time: {int(hour):02d}:{int(minutes):02d}:{int(seconds):02d}")
        return result
    return wrapper


def load_data_path(data_file_name):
    module_path = os.path.dirname(__file__)
    file_path = os.path.join(module_path, data_file_name)
    return file_path

def load_data(data_file_name):
    file_path = load_data_path(data_file_name)
    data = pd.read_csv(file_path)
    return data  
        

def monotonic_trend(x):
    if len(set(x.values))<=1:
        return 'no_Mono'
    else:
        corr = np.corrcoef(x,[i+1 for i in range(len(x))]).min()
        # print(corr)
        if corr <= -0.6:
            return 'descending'
        elif corr >= 0.6:
            return "ascending"
        else:
            return "no_Mono"
        

def get_group_perf(df_t,x='dup6_pct',y='fpd30',amt=None,by_cust=None,add_totals=True):
    
    df_t[x] = df_t[x].replace('Special','Missing')
    
    if y=='fake_y':
        y=None
        
    if y:
        df_t = df_t.copy()#[df_t[y]>=0]
        
        
    if len(df_t)==0:
        a = pd.DataFrame()
    else:
        a = df_t.groupby([x]).apply(lambda k4: pd.Series(
            {'total': k4.shape[0],
             'good': k4[k4[y]==0][y].count() if y and len(k4[k4[y]>=0])>0 else np.nan,
             'bad': k4[k4[y]>=0][y].sum() if y and len(k4[k4[y]>=0])>0 else np.nan,
             'risk': k4[k4[y]>=0][y].mean() if y else np.nan,
              'tot_amt': k4[k4[amt]>=0].shape[0] if amt and df_t[amt].max()==1 else k4[amt].sum() if amt else np.nan,
              'good_amt': k4[k4[amt]==0][amt].count() if y and amt and df_t[amt].max()==1 else k4[(k4[amt]>=0)&(k4[y]==0)][amt].sum() if y and amt else np.nan,
              'bad_amt': k4[k4[amt]>=0][amt].sum() if y and amt and df_t[amt].max()==1 else k4[(k4[amt]>=0)&(k4[y]==1)][amt].sum() if y and amt else np.nan
                })
            ).assign(
                pct = lambda k5: k5.total/df_t.shape[0],
                avg_amt =  lambda k5: k5.tot_amt/k5.total if amt else np.nan,
                risk_amt = lambda k5: k5.bad_amt/(k5.good_amt+k5.bad_amt) if y and amt else np.nan,
                lift = lambda k5: k5.risk/df_t[df_t[y]>=0][y].mean() if y else np.nan,
                lift_amt = lambda k5: k5.risk_amt/(df_t[df_t[amt]>=0][amt].sum()/df_t[df_t[amt]>=0].shape[0]) if y and amt and df_t[amt].max()==1 else k5.risk_amt/((df_t[df_t[amt]>=0][amt]*df_t[df_t[y]>=0][y]).sum()/df_t[df_t[amt]>=0][amt].sum()) if y and amt else np.nan,
                ).assign(
                    amt_xiaolv = lambda k5: k5.risk_amt/k5.risk if y and amt else np.nan
                    )
        
        #归户
        if by_cust:
            a1 = df_t.groupby([x]).apply(lambda k4: pd.Series(
                {'total_cust': k4[by_cust].nunique(),
                 'bad_cust': k4[k4[y]==1][by_cust].nunique() if y and len(k4[k4[y]>=0])>0 else np.nan,
                 'risk_cust': k4[k4[y]==1][by_cust].nunique()/k4[k4[y]>=0][by_cust].nunique() if y and len(k4[k4[y]>=0])>0 else np.nan,
                  'tot_amt': k4[k4[amt]>=0].shape[0] if amt and df_t[amt].max()==1 else k4[amt].sum() if amt else np.nan
                  })
                ).assign(
                    avg_amt_cust =  lambda k5: k5.tot_amt/k5.total_cust if amt else np.nan,
                    lift_cust = lambda k5: k5.risk_cust/(df_t[df_t[y]>=1][by_cust].nunique()/df_t[df_t[y]>=0][by_cust].nunique()) if y  and len(df_t[df_t[y]>=1])>0 else np.nan,
                    )
                    
            a1 = a1[['total_cust','bad_cust','risk_cust','avg_amt_cust','lift_cust']]
            
        else:
            a1 = pd.DataFrame(columns=['total_cust','bad_cust','risk_cust','avg_amt_cust','lift_cust'])
        
        
        a = pd.concat([a,a1],axis=1)
        n_nonevent = a.good.values
        n_event = a.bad.values
    
        n_records = n_event + n_nonevent
        t_n_nonevent = n_nonevent.sum()
        t_n_event = n_event.sum()
        # t_n_records = t_n_nonevent + t_n_event
        # t_event_rate = t_n_event / t_n_records
    
        # p_records = (n_records / t_n_records ) if y else a.total/a.total.sum()
        p_event = n_event / t_n_event
        p_nonevent = n_nonevent / t_n_nonevent
    
        mask = (n_event > 0) & (n_nonevent > 0)
        # event_rate = np.zeros(len(n_records))
        woe = np.zeros(len(n_records))
        iv = np.zeros(len(n_records))
        ks = np.abs(p_event.cumsum() - p_nonevent.cumsum()) # 新增
    
        # Compute weight of evidence and event rate
        # event_rate[mask] = n_event[mask] / n_records[mask]
        # constant = np.log(t_n_event / t_n_nonevent)
        # woe[mask] = np.log(1 / event_rate[mask] - 1) + constant
        # Compute Gini
        # tgini = gini(n_event, n_nonevent)
    
        # Compute divergence measures
        p_ev = p_event[mask]
        p_nev = p_nonevent[mask]
        
        woe[mask] = np.log(p_ev/p_nev)
        iv[mask] = (p_ev - p_nev)*woe[mask]
        
        
        if y and len(df_t[y])>0 and len(mask)>0:
            try:
                iv[mask] = (p_ev - p_nev)*woe[mask]
                # iv[mask] = jeffrey(p_ev, p_nev, return_sum=False)
            except:
                pass
            
        t_iv = iv.sum()
        t_ks = ks.max()
    
        Mono = type_of_monotonic_trend(a.risk.values[:-1])
            
            # Mono= a[a.index!='Missing'][['risk']].apply(monotonic_trend).values[0]
            
        # a['pct'] = p_records
        a['IV'] = iv
        a['KS'] = ks
        a['WoE'] = woe
        a['Mono'] = Mono
        
        a.index.name='group'
        a['x'] = x
        
        if y:
            a['y'] = y
        else:
            a['y'] = 'No_y'
            
       
        del a['good_amt']
        
        
        if add_totals:
            df_t['t'] = 'total'  
                 
            b = df_t.groupby('t').apply(lambda k4: pd.Series(
                {'total': k4.shape[0],
                 'good': k4[k4[y]==0][y].count() if y and len(k4[k4[y]>=0])>0 else np.nan,
                 'bad': k4[k4[y]>=0][y].sum() if y and len(k4[k4[y]>=0])>0 else np.nan,
                 'risk': k4[k4[y]>=0][y].mean() if y else np.nan,
                  'tot_amt': k4[k4[amt]>=0].shape[0] if amt and df_t[amt].max()==1 else k4[amt].sum() if amt else np.nan,
                  'bad_amt': k4[k4[amt]>=0][amt].sum() if y and amt and df_t[amt].max()==1 else (k4[k4[amt]>=0][amt]*k4[k4[y]>=0][y]).sum() if y and amt else np.nan,
                    })
                ).assign(
                    pct = lambda k5: k5.total/df_t.shape[0],
                    avg_amt =  lambda k5: k5.tot_amt/k5.total if amt else np.nan,
                    risk_amt = lambda k5: k5.bad_amt/k5.tot_amt if y and amt else np.nan,
                    lift = lambda k5: k5.risk/df_t[df_t[y]>=0][y].mean() if y else np.nan,
                    lift_amt = lambda k5: k5.risk_amt/(df_t[df_t[amt]>=0][amt].sum()/df_t[df_t[amt]>=0].shape[0]) if y and amt and df_t[amt].max()==1 else k5.risk_amt/((df_t[df_t[amt]>=0][amt]*df_t[df_t[y]>=0][y]).sum()/df_t[df_t[amt]>=0][amt].sum()) if y and amt else np.nan,
                    ).assign(
                        amt_xiaolv = lambda k5: k5.risk_amt/k5.risk if y and amt else np.nan
                        )
                        
            #归户
            if by_cust:
                b1 = df_t.groupby(['t']).apply(lambda k4: pd.Series(
                    {'total_cust':k4[k4[y]>=0][by_cust].nunique(),
                     'bad_cust': k4[k4[y]==1][by_cust].nunique() if y and len(k4[k4[y]>=0])>0 else np.nan,
                     'risk_cust': k4[k4[y]==1][by_cust].nunique()/k4[k4[y]>=0][by_cust].nunique() if y and len(k4[k4[y]>=0])>0 else np.nan,
                      'tot_amt': k4[k4[amt]>=0].shape[0] if amt and df_t[amt].max()==1 else k4[amt].sum() if amt else np.nan
                      })
                    ).assign(
                        avg_amt_cust =  lambda k5: k5.tot_amt/k5.total_cust if amt else np.nan,
                        lift_cust = lambda k5: k5.risk_cust/(df_t[df_t[y]>=1][by_cust].nunique()/df_t[df_t[y]>=0][by_cust].nunique()) if y and len(df_t[df_t[y]>=1])>0 else np.nan,
                        )
                        
                b1 = b1[['total_cust','bad_cust','risk_cust','avg_amt_cust','lift_cust']]
            else:
                b1 = pd.DataFrame(columns=['total_cust','bad_cust','risk_cust','avg_amt_cust','lift_cust'])
                
            b = pd.concat([b,b1],axis=1)
                
            if y:
                totals = list(b.loc['total'].values)+[t_iv, t_ks,"",Mono,x,y]
            else:
                totals = list(b.loc['total'].values)+[t_iv, t_ks,"",Mono,x,'No_y']
            

            a.loc["Total"] = totals
            
        # df['lift'] = df['Event rate']/df['Event rate'].iloc[-1]
        # df['x'] = self.name
        a.index = a.index.astype(str)
    
        a = a[['total', 'good','bad', 'pct','risk','lift', 'tot_amt', 'bad_amt', 'avg_amt',
           'risk_amt', 'lift_amt', 'amt_xiaolv', 'total_cust', 'bad_cust', 'avg_amt_cust',
           'risk_cust', 'lift_cust', 'IV', 'KS', 'WoE', 'Mono',
           'x', 'y']]
    
    return a    

def get_groups_perf(df_t,x_list,y_list=['fpd30','mob3_k30'],amt=None,by_cust=None,add_totals=True):
    result = []
    
    for x in x_list:
        if by_cust:
            df_t1 = df_t[[by_cust]]
        else:
            df_t1 = pd.DataFrame(index=df_t.index)
        if len(re.findall(r'[><=]=?',x))>0:
            r = replace_digitbeginx(x)
            try:
                df_t1[x] = np.where(df_t.index.isin(df_t.query(r).index),1,0)
            except:
                df_t1[x] = df_t[x]
        else:
            df_t1[x] = df_t[x]
        
        if amt:
            df_t1 = pd.concat([df_t1,df_t[amt]],axis=1)
            
        if y_list:
            df_t1 = pd.concat([df_t1,df_t[y_list]],axis=1)
            for y in y_list:
                a = get_group_perf(df_t1,x=x,y=y,amt=amt,by_cust=by_cust,add_totals=add_totals)
                result.append(a)
                
        else:
            a = get_group_perf(df_t1,x=x,y=None,amt=amt,by_cust=by_cust,add_totals=add_totals)
            result.append(a)
            
    R = pd.concat(result)
    
    return R
 


# def get_groups_perf(df_t,x_list,y_list=['fpd30','mob3_k30'],amt=None,add_totals=True):
#     result = []
    
#     if y_list:
#         for x in x_list:
#             df_t1 = df_t[y_list]
#             if amt:
#                 df_t1 = pd.concat([df_t1,df_t[amt]],axis=1)
#             if len(re.findall(r'[><=]=?',x))>0:
#                 r = replace_digitbeginx(x)
#                 df_t1[x] = np.where(df_t.index.isin(df_t.query(r).index),1,0)
#             else:
#                 df_t1[x] = df_t[x]
                
#             for y in y_list:
#                 a = get_group_perf(df_t1[df_t1[y]>=0],x=x,y=y,amt=amt,add_totals=add_totals)
            
#                 result.append(a)
#     else:
#         for x in x_list:
#             df_t1 = pd.DataFrame(index=df_t.index)
#             if amt:
#                 df_t1 = pd.concat([df_t1,df_t[amt]],axis=1)
#             if len(re.findall(r'[><=]=?',x))>0:
#                 r = replace_digitbeginx(x)
#                 df_t1[x] = np.where(df_t.index.isin(df_t.query(r).index),1,0)
#             else:
#                 df_t1[x] = df_t[x]
                
#             a = get_group_perf(df_t1,x=x,y=None,amt=amt,add_totals=add_totals)
#             result.append(a)
        
#     R = pd.concat(result)
#     return R

            
def get_multi_groups_perf(df_t,inputx,y_list=['fpd30','mob3_k30'],amt=None,by_cust=None,add_totals=True,n_jobs=10):
    inputx = sorted(set(inputx),key=inputx.index)
    
    if n_jobs==1 or len(inputx)==1 or len(inputx)<n_jobs:
        result = get_groups_perf(df_t,x_list=inputx,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=add_totals)
    else:
        ids = np.arange(len(inputx))
        id_blocks = np.array_split(ids, n_jobs)
        names = np.asarray(inputx)
        blocks = Parallel(n_jobs=n_jobs,backend='threading')( # 修改 0609 新增 ,backend='threading'
            delayed(get_groups_perf)(
                df_t, x_list=names[id_block],y_list=y_list,amt=amt,by_cust=by_cust,add_totals=add_totals)
            for id_block in id_blocks)
        
        result = pd.concat(blocks)
    
    return result

def get_psi(a,inputx):
    the_P = pd.DataFrame()
    for x in inputx:
        for y1 in a.y.unique():
            the_p = pd.DataFrame()
            b = a[(a['x']==x)&(a['y']==y1)]['pct']
            pct = b.unstack(0).fillna(0)
            pct = pct[pct.index!='Missing'].iloc[:-1]
            P = pd.concat([(pct.iloc[:,i]-pct.iloc[:,0])*np.log(pct.iloc[:,i]/pct.iloc[:,0]) for i in range(pct.shape[1])],axis=1)
            P.columns = pct.columns
            P.loc['Total'] =P.sum().replace(np.inf,1)
            the_p['psi'] = P.unstack()
            the_p['x'] = x
            the_p['y'] = y1
            the_P = pd.concat([the_P,the_p])
    the_P = the_P.reset_index()
    return the_P

def get_multi_psi(a,inputx,n_jobs=10):
    
    rows = pd.Series(range(0,len(inputx)),index=inputx)
    
    n_jobs = min(n_jobs,len(rows.index))
    row_cut = pd.qcut(rows,n_jobs,labels=range(0,n_jobs))
    corssx_list=[]
    for i in range(0,n_jobs):
        corssx_list.append(list(row_cut[row_cut==i].index))
        
    # parallel_obj = Parallel(n_jobs=n_jobs,verbose=0,max_nbytes=None) 修改0609
    parallel_obj = Parallel(n_jobs=n_jobs, verbose=0, max_nbytes=None, backend='threading')

	
    jobs = []
    for i in range(0,n_jobs):
        jobs.append(delayed(get_psi)(a,corssx_list[i]))
    
    multiprocess_out = parallel_obj(jobs)
                
    
    # if n_jobs==1 or len(inputx)==1 or len(inputx)<n_jobs:
    #     result = get_psi(a,inputx)
    # else:
    #     ids = np.arange(len(inputx))
    #     id_blocks1 = np.array_split(ids, n_jobs)
    #     names = np.asarray(inputx)
    #     blocksx = Parallel(n_jobs=n_jobs)(
    #         delayed(get_psi)(a,inputx=names[id_blockx])
    #         for id_blockx in id_blocks1)
        
    result = pd.concat(multiprocess_out)
    
    return result


def get_df_dt(tmpdf,dt,dt_cut):
    '''
    
    Parameters
    ----------
    df : dataframe
        包含时间列的df.
    dt : string, optional
        时间字段. The default is 'shouxin_date'.
    dt_cut : string\list\int, optional
        The default is 'month'.
        样本拆分月自定义切点，list自定义 如:[-np.inf,20190101,20190601,20190901,np.inf]
        或者指定某一列 如'shouxin_month','month1' 
        或者是整数，2,3 表示将样本等分切成2份，三份

    Returns
    -------
    df with dt.

    '''
    if dt:
        dfc = tmpdf[[dt]]
        
        # 判断跨时字段
        if dt_cut==None:
            dfc['dt_cut'] = 'All'
            
        if dt_cut in tmpdf.columns:
            dfc['dt_cut'] = tmpdf[dt_cut].astype('str')
          
        if dt_cut=='month':
            dfc['dt_cut'] = dfc[dt].astype('str').str.replace('-','').str[0:6]
            
        if isinstance(dt_cut,int):
            if dt_cut==1:
                dfc['dt_cut'] = 'All'
            else:
                if dfc[dt].dtypes=='O':
                    dfc[dt] = dfc[dt].astype('str').str[0:10].str.replace('-','').astype(int)
                est = KBinsDiscretizer(n_bins=dt_cut,strategy='quantile')
                est.fit(dfc[[dt]])
                dt_cut= np.concatenate([[-np.inf], est.bin_edges_[0][1:-1], [np.inf]])
                dt_cut1= est.bin_edges_[0]
                
        if isinstance(dt_cut,list) or isinstance(dt_cut,np.ndarray):
            if dfc[dt].dtypes=='O':
                dfc[dt] = dfc[dt].astype('str').str[0:10].str.replace('-','').astype(int)
            
            bins_str = ["{0}_[{1:.{3}f}, {2:.{3}f})".format('0'+str(i) if i<10 else str(i),dt_cut1[i], dt_cut1[i+1], 0) for i in range(len(dt_cut1)-1)]

            dfc['dt_cut'] = pd.cut(dfc[dt],dt_cut,precision=0,labels=bins_str)
            
    else:
        dfc = pd.DataFrame(index=tmpdf.index)
        if isinstance(dt_cut, int):
            if dt_cut==1:
                dfc['dt_cut'] = 'All'
            else:
                dfc['dt_cut'] = pd.qcut(shuffle(dfc).index,dt_cut,duplicates='drop',labels=False).astype('str')
        elif dt_cut==None:
            dfc['dt_cut'] = 'All'
            
        elif isinstance(dt_cut, str):
            dfc['dt_cut'] = tmpdf[dt_cut].astype('str')
        else:
            dt_cut=None
            dfc['dt_cut'] = 'All'
        
    return dfc


def full_describe(df,miss_values=[-99,np.nan,-9999]):
    
    # get_log("DDViz full_describe")
    
    df1 = df.replace(miss_values,np.nan)
   
    top = pd.DataFrame({x: pd.Series([str(k)+': '+str('{:.2%}'.format(v)) for k,v in df1[x].value_counts(normalize=True).head(7).to_dict().items()]) for x in df.columns}).T
    top.columns = ['value'+str(i+1) for i in top.columns]
    
    desc = df1.describe(percentiles=[],include='all').T
    
    if 'unique' in list(desc):
        desc['unique'].update(df1.apply(lambda x: x.nunique()))
    else:
        desc['unique'] = df1.apply(lambda x: x.nunique())
        
    if 'min' not in list(desc):
        desc['min'] = desc['max'] = desc['mean'] = np.nan
    desc = desc[['count','unique','min','mean','max']]
    
    desc['type'] = df1.dtypes
    desc['miss%'] = df1.apply(lambda x: '{:.2%}'.format(x.isnull().sum()/x.shape[0]))
    
    desc['count'] = desc['count'].astype(int)
    desc['type'] = desc['type'].astype(str)
    
    cat_desc = pd.concat([desc[df1.dtypes=='O'],top[df1.dtypes=='O']],axis=1)
    cat_desc = cat_desc.drop(['min','mean','max'],axis=1)
    
    num_desc = pd.concat([desc[df1.dtypes!='O'],top[df1.dtypes!='O']],axis=1)
        
    return cat_desc,num_desc

   

def replace_digitbeginx(r):
    a = re.findall(r'\s*(\w+)\s*([><=]=?)\s*(-?[0-9.]+)',r)
    rmap = dict(zip([ xi[0] for xi in a] ,['`'+xi[0]+'`' if xi[0][0].isdigit() else xi[0] for xi in a]))
    for k,v in rmap.items():
        r = r.replace(k,v)
    return r

def split_rule(s):
    if '(' in s:
        thes = re.findall(r'\((.*?)\)',s)
        for i in thes:
            s = s.replace(i,'')
        others = s   
        others = others.replace(' and ',' & ').replace(' or ',' | ').replace(' ','')
        others = re.split(r'[&|]',others.replace(' ','').replace('(', '').replace(')', ''))
        others = [i for i in others if len(i)>1]
        
        thes = [i.replace('(', '').replace(')', '') for i in thes]
        single_rule = thes+others

    else:
        rule = s.replace(' and ',' & ').replace(' or ',' | ').replace(' ','')
        single_rule = re.split(r'[&|]',rule.replace(' ','').replace('(', '').replace(')', '')) 

    return single_rule


def get_out_excel(name = 'out_all_in_one_template.xlsx'):
    """修改获取路径方式，使用io打开"""
    module_path = os.path.dirname(__file__)
    file_path = os.path.join(module_path, name)
    # f = pd.read_excel(file_path)
    return file_path


def get_data_dt_detect(df,miss_values,dt,sort_columns_by=None,output_path=None,if_rplc_miss=1):
    
    '''
    Parameters
    ----------
    df : pd.dataframe
        输入dataframe,需包含,dt.
    dt : string
        默认='dt'
    miss_values: list
        缺失值列表，缺失值单独一箱,默认 = [-99]
    
    sort_columns_by : string or None
        missing matrix图的排序，可用 ['有效起始日', '缺失率', None] 三个值做排序，默认不排序，按照df送进的列顺序。
    
    output_path : string or None
        文件存储地址，注意文件为xlsm格式的，例如可写 = '数据集缺失检测.xlsm'， 默认为None，不保存文件                                            
    

    Returns
    -------
    inputx对应的有效起始日期，有效起始日期后的数据量
    
        
    Examples:
        .. code-block:: python

            from DDViz import DDViz
            # import data
            df = DDViz.load_data('dq_ts_inputx.csv')
            miss_values=[-99,-1,np.nan,"-99",-9999]
            
            #保存文件
            dt_map = DDViz.get_data_dt_detect(df,dt='shouxin_date',miss_values=miss_values,sort_columns_by='有效起始日', output_path='数据集缺失检测.xlsm')
            
            #不保存
            dt_map = DDViz.get_data_dt_detect(df,dt='shouxin_date',miss_values=miss_values,sort_columns_by=None, output_path=None)

    
    '''    
    if if_rplc_miss==0:
        df1 = df.sort_values(by=dt).reset_index(drop=True)
    else:
        df1 = df.replace(miss_values,np.nan).sort_values(by=dt).reset_index(drop=True)
    
    first_valid_index = df1.apply(pd.Series.first_valid_index).fillna(df1.shape[0]).astype(int)
    first_valid_dt = first_valid_index.apply(lambda xi: df1.loc[xi-1,dt] if xi==len(df1) else df1.loc[xi,dt])
    valid_len = df1.shape[0]-first_valid_index
    nunique = df1.apply(lambda x:x.nunique(dropna=False))
    unique_ratio = df1.apply(lambda x: x.value_counts(normalize=True,dropna=False).iloc[0])
    top_value = unique_ratio#df1.apply(lambda x: x.value_counts(dropna=False).idxmax())
    missing_rate = df1.isnull().sum()/df1.shape[0]
    
    inputx_out =  pd.concat([first_valid_dt,valid_len,nunique,unique_ratio,top_value,missing_rate],axis=1)
    inputx_out.columns=['有效起始日','有效数据量','unique数','top值率','top值','缺失率']
    inputx_out['有效数据占比'] = inputx_out['有效数据量']/df1.shape[0]
    
    if output_path:
        
        if sort_columns_by:
            xlist = list(inputx_out.reset_index().sort_values([sort_columns_by,'index'])['index'])
        else:
            xlist = list(inputx_out.index)

        out_null_df = df1.groupby(dt).apply(lambda x: (x.isnull().sum()/x.shape[0]))[xlist]
        
        print('生成数据有效性检测报告....')
        import xlwings as xw
        app = xw.App(visible=False, add_book=False)
        app.display_alerts=False
        app.screen_updating=True
        # file_path = 'D:/ProgramData/Anaconda3/envs/report/Lib/site-packages/DDViz/dataset_missing_dt_check_template.xlsm'
        file_path = get_out_excel(name='dataset_missing_dt_check_template.xlsm')
        wb = app.books.open(file_path)
        wb.sheets('数据集有效日期').range('a2').options(index=True,header=False).value = inputx_out
        wb.sheets('数据集缺失率图').range('a2').options(index=True,header=True).value = out_null_df
        
        wb.macro('format_missing')()
    
        # wb.api.RefreshAll()
        print('报告已生成！！') 
        if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        wb.save(os.path.join(os.path.dirname(output_path), '数据有效性检测报告.xlsm'))
        wb.close()
        app.kill()
        
        return inputx_out

    else:
    
        return inputx_out
 


def out_all_in_one(df,inputx,is_rule=0,is_cross=0,
               y_list=['fpd30','mob3_k30'],amt=None,by_cust=None,
               dt='close_date',dt_cut=2,
               miss_values=[-99],
               bin_method={
                    'Notbin':False,
                    'enumeration_n':None,
                    'fix_bin':None , 
                    'cart':{'min_samples_leaf':[0.0001],'max_leaf_nodes':[20]}, # 叶子节点最小样本数占比，最大的叶子节点数
                    'uniform':[20],
                    'quantile':[20]
                    },
               combine_method={
                    'Notcombine':False,
                    'mono':'auto_asc_desc',
                    'min_bin_bad':3 
                    },
               output_path='./output_report/out_all_in_one_report.xlsx',
               verbose=1,
               n_jobs=0):
    
    '''数据诊断一键输出函数。DDViz 1.1.9版本，Copyright zhangyuting
    
    Parameters
    ----------
    :df : 包含x,y的数据集
    
    :inputx : 参与挖掘的特征
    
    :is_rule : 规则开启参数，如果inputx是一个规则或一组规则时使用。如inputx='a>=1&b<2' 或['a>=1&b<2','c>=4']
    
    :is_cross: 是否查看特征交叉，输出交叉表，如分组后，x1&x2的交叉情况。默认是0，不看
    
    :y_list : 数据集中好坏样本标签列名称，支持一次性传入多个y标签计算，如y_list=['fpd4','mob3_k10','fpd30'], 多个y标签时，分组以第一个y的分组统一
    
    :amt: 金额风险指标，默认None,也可以是第二个风险标签，如同时看'fpd1'和'fpd4', 则可以amt='fpd1'
    
    :dt : string
        dt = 'shouxin_date' 按shouxin_date列
        dt = None 样本中没有时间列
        样本拆分的日期，一般我们建模中常用的，建案时间，交易时间等等。格式为 20190101、2019-01-01均可.默认'create_date'.
    
    :dt_cut : 跨时切分方式，默认 'month'.不管样本中是否包含month列，都可以直接按月拆分..
        list,int,string optional
        =list 时 如：[-np.inf,20190101,20190601,20190901,np.inf]
        ='month' 或者指定df中的某一列 如'shouxin_month','month1'
        =1,2,3 样本等分成3份。。 
        =None, 不切分
    
    :miss_values : 缺失值列表，缺失值单独一箱，默认 [-99].
    
    :bin_method : dict, 分箱方式，包含5中方式，
                bin_method={
                 'Notbin':False, # 不分箱，优先级最高，若选择不分箱，则其他key不生效，对全局生效
                 'enumeration_n':None, # 枚举值阈值，可写 None 或者整数值， None代表不考虑枚举值个数，全都自动分箱； 如填5，代表枚举值个数<=5的不分箱不合并。对全局生效
                 'fix_bin':None, # 固定分箱，针对某一个或多个特征，固定分箱切点。如设置为 fix_bin：{'score1':[277,500]}，若想对某个变量单独设置不分箱，其他变量根据枚举值判断自动分箱，则可设置为{'score1':'Notbin'}
                 'cart':{'min_samples_leaf':[0.0001],'max_leaf_nodes':[20]}, # 决策树分箱，叶子节点最小样本数占比，最大的叶子节点数
                 'uniform':[20], # 等宽分箱 列表中支持多个可选参数
                 'quantile':[20] # 等频分箱列表中支持多个可选参数
                 }
                
    :combine_method : dict, 合并方式，分箱后的合并，包含3中方式。
                combine_method={
                 'Notcombine':False, # 不合并，优先级最高，若选择不合并，则其他key不生效
                 'mono':'auto_asc_desc', #自动递增递减分箱合并，不确定变量单调趋势时推荐使用，默认= 'auto_asc_desc'.
                 'min_bin_bad':3 # 分箱最小坏样本个数， 若不想限制，设置为None 
                 }
    :output_path : 存储地址，保存组合一键数据诊断分析报告，默认值"out_all_in_one_report.xlsx". 会自动创建相应的文件夹
    
    :verbose : 0或者1，默认=1，打印过程
    
    :n_jobs : int, 开启多进程，数值越大，进程越多。如=10，开启10个进程； =0 不开启进程
    
    Returns
    -------
    A : dataframe, 所有inputx计算结果。包含分箱，分组风险，单调性，iv，ks，psi等指标。
    
    df_t : dataframe, df经分箱转换后的数据集
    
    inputx_splits : dict, 所有inputx 的分箱切点
        
    '''
    cross_x=[]
    if isinstance(inputx,tuple):
        is_cross=1
        
        cross_x = [(x1,x2) for x1 in inputx[0] for x2 in inputx[1]]
        print(f"定点交叉开启，共生成 {len(cross_x)} 个交叉变量")
        inputx = inputx[0]+inputx[1]
        
        
    if isinstance(inputx,list):
        if dt and dt in inputx:
            inputx.remove(dt)
        if y_list:
            inputx = [x for x in inputx if x not in y_list]
        if dt_cut and isinstance(dt_cut, str) and dt_cut in inputx:
            inputx.remove(dt_cut)
        
    try:
        if y_list:
            y = y_list[0]
        else:
            df['fake_y'] = np.random.choice([0,1],size=len(df))
            y='fake_y'
            y_list = [y]
            bin_method['Notbin'] = False
            bin_method['cart'] = None
            bin_method['uniform'] = None
            combine_method['Notcombine'] = True
            if bin_method['quantile']:
                pass
            else:
                bin_method['quantile'] = [10]
            if verbose:
                print('无 Y变量计算')
        
        dt_df = get_df_dt(df,dt,dt_cut)
        # print(dt_df)
        
        inputx_splits={}
        A = pd.DataFrame() 
                
        if is_rule==1: 
            if isinstance(inputx,str): # 若inputx是单条规则，则拆开看具体单条规则中每一条子规则的组成
                rule = inputx
                rl = split_rule(rule)
                inputx = [rule]+rl
                inputx = sorted(set(inputx),key=inputx.index)
                
            bin_method['Notbin'] = True
            inputx1=[]
            
        if is_rule==0:
            cat = list(df[inputx].select_dtypes(include='O'))
            nu = df[inputx].apply(lambda x1: x1.nunique())
            if bin_method['enumeration_n']:
                inputx = list(nu[nu>bin_method['enumeration_n']].index)
                inputx1 = list(nu[nu<=bin_method['enumeration_n']].index)
            else:
                inputx = list(nu[nu>1].index)
                inputx1 = list(nu[nu<=1].index)
        
            if isinstance(bin_method['fix_bin'], dict):
                fix_bin = bin_method['fix_bin']
                notbx = [k for k,v in fix_bin.items() if v=='Notbin']
                inputx1 = list(set(inputx1+notbx))
                inputx = list(set(inputx)-set(notbx))
                
        if combine_method['Notcombine']:
            if_optimize=False
            mono = 'auto_heuristic'
            min_bin_n_event = None
        else:
            if_optimize = True
            mono = combine_method['mono']
            min_bin_n_event = combine_method['min_bin_bad']
            
    
        if n_jobs==0:
            n_jobs=1
        n_jobs = effective_n_jobs(n_jobs)
        
        df_t = pd.DataFrame(index=df.index)
        if bin_method['Notbin']:
            if y_list:
                df_t = pd.concat([dt_df,df[y_list]],axis=1)
            if amt:
                df_t = pd.concat([df[amt],df_t],axis=1)
            if by_cust:
                df_t = pd.concat([df[[by_cust]],df_t],axis=1)
                
            
        
            if is_rule==0:
                df_t = pd.concat([df_t,df[inputx+inputx1].replace(miss_values,'Missing')],axis=1)
            if is_rule==1:
                df_t = pd.concat([df_t,df[inputx+inputx1].replace(miss_values,-99)],axis=1)
            
            str_cross_x = []
            if is_cross==1:
                if len(cross_x)==0:
                    cross_x = list(itertools.combinations(inputx+inputx1, 2))
                    print(f"两两交叉开启，共生成 {len(cross_x)} 个两两交叉变量")
                str_cross_x = [str(i) for i in cross_x]
                for i in cross_x:
                    if is_rule==1:
                        df_t[str(i)] = np.where(df_t.index.isin(df_t.query(i[0]+'&' +i[1]).index),1,0)
                    else:
                        df_t[str(i)] = df_t[i[0]].astype(str)+'&'+df_t[i[1]].astype(str)
                
            a = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx+inputx1+str_cross_x,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
            
            if a.index.get_level_values(0).nunique()>1:
                df_t['dt_cut'] ='All'
                a1 = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx+inputx1+str_cross_x,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                a = pd.concat([a.reset_index(),a1.reset_index()]).set_index(['dt_cut','group'])

            the_P = get_psi(a,inputx+inputx1+str_cross_x)
            
            a = a.reset_index()
            a = pd.merge(a,the_P,how='left',on=['dt_cut','group','x','y'])
            a['bin_method'] = np.where(a['x'].isin(str_cross_x),'cross','Notbin')
            A = pd.concat([A,a])
            
        else:
        
            if len(inputx)>0:
                user_splits = bin_method['fix_bin']
                if isinstance(user_splits, dict):
                    binning_fit_params = {k:{'user_splits':v} for k,v in user_splits.items() if isinstance(v,list) }    
                    if len(binning_fit_params)==0:
                       binning_fit_params = None
                else:
                    binning_fit_params = None
                
                bin_m = [k for k,v in bin_method.items() if v]
                for m in bin_m:
                    if m in ['Notbin','fix_bin','enumeration_n']:
                        pass
                    else:
                        if bin_method['cart'] and m =='cart':
                            max_n_prebins = bin_method['cart']['max_leaf_nodes'] # 老板本默认=50
                            min_prebin_size = bin_method['cart']['min_samples_leaf'] # 老版本的score_cut
                            if verbose:
                                print(f'决策树分箱，参数：叶子节点最小样本数占比 {min_prebin_size}，最大的叶子节点数 {max_n_prebins}')
                        if bin_method['uniform'] and m =='uniform':
                            max_n_prebins = bin_method['uniform']
                            min_prebin_size = [0.0001]
                            if verbose:
                                print(f'等宽分箱，参数：{max_n_prebins}')
                        if bin_method['quantile'] and m =='quantile':
                            max_n_prebins = bin_method['quantile']
                            min_prebin_size = [0.0001]
                            if verbose:
                                print(f'等频分箱，参数：{max_n_prebins}')
                                
                        param_g = list(itertools.product(max_n_prebins,min_prebin_size))
                        
                        for p in param_g:
                            bp = BinningProcess(variable_names=inputx,prebinning_method=m,
                                                max_n_prebins=p[0], min_prebin_size=p[1],
                                                min_bin_n_event=min_bin_n_event,
                                                monotonic_trend=mono,
                                                min_n_bins=None, max_n_bins=None, min_bin_size=None,
                                                max_bin_size=None, max_pvalue=None,
                                                max_pvalue_policy="consecutive", 
                                                selection_criteria=None,#{'iv':{'min':0.001}},
                                                categorical_variables=cat, 
                                                special_codes=miss_values,
                                                split_digits=3, binning_fit_params= binning_fit_params,#{'fqz_score_app_cost0':{'user_splits':[277,300]}},
                                                binning_transform_params=None, if_optimize=if_optimize, n_jobs=n_jobs, verbose=False)
                            
                            
                            bp.fit(df[df[y]>=0][inputx],df[df[y]>=0][y])
                            
                            a = bp._binned_variables
                            if m=='cart':
                                k = str(p)
                            else:
                                k = str(p[0])
                            inputx_splits[m+'_'+k] = {k:a[k].splits for k in a.keys()}
                        
                            df_t = bp.transform(df[inputx],metric='bins',show_digits=3)
                            df_t.index = df.index
                        
                            if amt:
                                df_t = pd.concat([dt_df,df[amt],df[y_list],df_t],axis=1)
                            else:
                                df_t = pd.concat([dt_df,df[y_list],df_t],axis=1)
                                
                            if by_cust:
                                df_t = pd.concat([df_t,df[[by_cust]]],axis=1)
                                
                            df_t = df_t.replace('Special','Missing')
                            
                            a = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                            
                        
                            if a.index.get_level_values(0).nunique()>1:
                                df_t['dt_cut'] ='All'
                                a1 = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                                a = pd.concat([a.reset_index(),a1.reset_index()]).set_index(['dt_cut','group'])
                            
                            
                            # the_P = get_multi_psi(a,inputx,n_jobs=50)
                            the_P = get_psi(a,inputx)
                            
                            a = a.reset_index()
                            a = pd.merge(a,the_P,how='left',on=['dt_cut','group','x','y'])
                            
                            a['bin_method'] = m+'_'+k
                
                            A = pd.concat([A,a])
                if verbose:
                    aa = '合并' if if_optimize else '不合并'
                    print(f'是否分箱合并：{aa}')
                    
            if len(inputx1)>0:
                
                print(f'{len(inputx1)} 个变量不分箱，不合并 ')
                    
                if len(df_t)==0:
                    if amt:
                        df_t = pd.concat([dt_df,df[amt],df[y_list],df_t],axis=1)
                    else:
                        df_t = pd.concat([dt_df,df[y_list],df_t],axis=1)
                    if by_cust:
                        df_t = pd.concat([df_t,df[[by_cust]]],axis=1)
                        
                df_t['dt_cut'] = dt_df['dt_cut'] 
                df_t = pd.concat([df_t,df[inputx1].replace(miss_values,'Missing')],axis=1)
                a = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx1,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                
                if a.index.get_level_values(0).nunique()>1:
                    df_t['dt_cut'] ='All'
                    a1 = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,inputx1,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                    a = pd.concat([a.reset_index(),a1.reset_index()]).set_index(['dt_cut','group'])
                    
                the_P = get_psi(a,inputx1)
                
                a = a.reset_index()
                a = pd.merge(a,the_P,how='left',on=['dt_cut','group','x','y'])
                a['bin_method'] = 'Notbin'
                A = pd.concat([A,a])
              
            str_cross_x = []
            if is_cross==1:
                if len(cross_x)==0:
                    cross_x = list(itertools.combinations(inputx+inputx1, 2))
                    print(f"两两交叉开启，共生成 {len(cross_x)} 个两两交叉变量")
                    
                str_cross_x = [str(i) for i in cross_x]
                for i in cross_x:
                    if is_rule==1:
                        df_t[str(i)] = np.where(df_t.index.isin(df_t.query(i[0]+'&' +i[1]).index),1,0)
                    else:
                        df_t[str(i)] = df_t[i[0]].astype(str)+'&'+df_t[i[1]].astype(str)
                
                df_t['dt_cut'] = dt_df['dt_cut'] 
                a = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,str_cross_x,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                
                if a.index.get_level_values(0).nunique()>1:
                    df_t['dt_cut'] ='All'
                    a1 = df_t.groupby('dt_cut').apply(lambda k: get_multi_groups_perf(k,str_cross_x,y_list=y_list,amt=amt,by_cust=by_cust,add_totals=True,n_jobs=n_jobs))
                    a = pd.concat([a.reset_index(),a1.reset_index()]).set_index(['dt_cut','group'])
    
                the_P = get_psi(a,str_cross_x)
                
                a = a.reset_index()
                a = pd.merge(a,the_P,how='left',on=['dt_cut','group','x','y'])
                a['bin_method'] = 'cross'
                A = pd.concat([A,a])
                
            
            # df_t['dt_cut'] = dt_df['dt_cut'] 
            df_t = df_t.replace('Special','Missing')
        
        
        if output_path==None:
            return A,df_t,inputx_splits
        
        else:
            # 结果写入excel
            if verbose:
                print('生成out_all_in_one报告....')
            
            try:
                cat_desc,num_desc = full_describe(df[inputx],miss_values=miss_values)
            except:
                cat_desc,num_desc = pd.DataFrame(),pd.DataFrame()
            
            app = xw.App(visible=False, add_book=False)
            app.display_alerts=False
            app.screen_updating=True
            
            try:
                file_path = get_out_excel(name='out_all_in_one_template.xlsx')
                # file_path = join('C:\\Users\\z00119a\\Desktop\\z00119a-张玉婷\\zhangyuting\\DDViz\\DDViz_1.1.9\\remote-win\\DDViz', 'out_all_in_one_template.xlsx')
                wb = app.books.open(file_path)
                if len(cat_desc)>0:
                    wb.sheets('字符型变量描述').range('a2').options(index=True,header=False).value = cat_desc
                if len(num_desc)>0:
                    wb.sheets('数值型变量描述').range('a2').options(index=True,header=False).value = num_desc
                wb.sheets('分组明细').range('a2').options(index=False,header=False).value = A
                # if is_cross==0:
                #    wb.sheets['交叉表'].delete()
                
                wb.api.RefreshAll()
                print('报告已生成！！')   
                if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
                    os.makedirs(os.path.dirname(output_path))
                wb.save(output_path)
                wb.close()
                app.kill()
            except:
                print('报告保存失败，请手动保存！！') 
                app.kill()
            
        # get_log("DDViz 1.1.18 out_all_in_one success")
        
        return A,df_t,inputx_splits
        
    except Exception as e:
        print (e)
        print(traceback.format_exc())
        # get_log("DDViz 1.1.18 out_all_in_one fail")
        
       


def update_report(a,update_a,output_path = None):
    a['flag'] = a['x']+a['y']+a['bin_method']
    update_a['flag'] = update_a['x']+update_a['y']+update_a['bin_method']
    
    final_a = pd.concat([a[~a.flag.isin(update_a.flag)],update_a])
    
    final_a.drop(columns=['flag'],inplace=True)
    
    if output_path==None:
        return final_a
    
    else:
        # 结果写入excel
        print('更新out_all_in_one报告....')
        
        app = xw.App(visible=False, add_book=False)
        app.display_alerts=False
        app.screen_updating=True
        
        file_path = get_out_excel(name='out_all_in_one_template.xlsx')
        wb = app.books.open(file_path)
        wb.sheets('分组明细').range('a2').options(index=False,header=False).value = final_a
    
        wb.api.RefreshAll()
        print('报告已生成！！')   
        if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        wb.save(output_path)
        wb.close()
        app.kill()
        
        return final_a
    

def plt_multi_mosaic(df,inputx,
               y='fpd30',amt=None,
               dt='close_date',dt_cut=2,
               miss_values=[-99],
               bin_method={
                    'Notbin':False,
                    'fix_bin':None , 
                    'cart':{'min_samples_leaf':[0.0001],'max_leaf_nodes':[20]}, # 叶子节点最小样本数占比，最大的叶子节点数
                    'uniform':[20],
                    'quantile':[20]
                    },
               combine_method={
                    'Notcombine':False,
                    'mono':'auto_asc_desc',
                    'min_bin_bad':3 
                    },
               bs=3,
               if_plot=True,
               output_path=None,
               verbose=1,
               n_jobs=0):
    
    '''
    马赛克图画图工具
    ----------
    其余参数同DDViz.out_all_in_one
    :param bs : int           放大倍数，画马赛克图有时因y占比太少，导致画图不清，这里放大橙色部分方便看图 默认=3
    :param if_plot : bool     默认True, 默认直接画图 
    :param output_path : 存储地址，保存马赛克图，默认值None. 会自动创建相应的文件夹
    '''

    # get_log("DDViz 1.1.18 plt_multi_mosaic")
     
    
    A,df_t,bins = out_all_in_one(df,inputx,is_rule=0,
                   y_list=[y],amt=amt,
                   dt=dt,dt_cut=dt_cut,
                   miss_values=miss_values,
                   bin_method=bin_method,
                   combine_method=combine_method,
                   output_path=None,
                   verbose=0,
                   n_jobs=n_jobs)
    
    if dt:
        dt_range = str(df[dt].min())+'~'+str(df[dt].max())
    else:
        dt_range = 'All'

    if if_plot:
        for x in A.x.unique():
            
            a = A[(A['x']==x)&(A['y']==y)&(A['bin_method']==A['bin_method'].unique()[0])].set_index('x')
            
            # a = pd.concat([a[a['group']=='Missing'],a[a['group']!='Missing']])
            cross_bindf = a[a['group']!='Total']
            cross_vardf = a[a['group']=='Total']
            
            tot_size = a.query('dt_cut=="All" and group=="Total"').loc[x,'total']
            tot_iv = a.query('dt_cut=="All" and group=="Total"').loc[x,'IV']
            tot_ks = a.query('dt_cut=="All" and group=="Total"').loc[x,'KS']
            tot_missing = a.query('dt_cut=="All" and group=="Missing"').loc[x,'pct'] if 'Missing' in a['group'] else 0
            tot_mono = a.query('dt_cut=="All" and group=="Total"').loc[x,'Mono']


            if isinstance(cross_vardf.loc[x],pd.DataFrame):
                the_vdf = cross_vardf.loc[x].reset_index().set_index('dt_cut')
            else:
                the_vdf = cross_vardf.loc[x].to_frame().T.reset_index().set_index('dt_cut')
                
            if isinstance(cross_bindf.loc[x],pd.DataFrame):
                the_bdf = cross_bindf.loc[x].reset_index().set_index(['group','dt_cut']).unstack(1).fillna(0)
            else:
                the_bdf = cross_bindf.loc[x].to_frame().T.reset_index().set_index(['group','dt_cut']).unstack(1).fillna(0)
                
            the_bdf = pd.concat([the_bdf[the_bdf.index=='Missing'],the_bdf[the_bdf.index!='Missing']])
                   
            
            cross_len = the_vdf['total']
            cross_sum = the_vdf['bad']
            cross_mean = the_vdf['risk']
            
            exmiss = the_bdf[the_bdf.index!='Missing']
            if len(exmiss)==0:
                max_bs = min_bs = pd.Series(index=the_vdf.index).fillna(1)
                max_pct = min_pct = pd.Series(index=the_vdf.index).fillna(1)
                max_badn = min_badn = pd.Series(index=the_vdf.index).fillna(0)
                tot_missing = 1
            else:
                max_bs = the_bdf[the_bdf.index!='Missing']['lift'].iloc[-1] # 最后一箱的风险
                max_pct = the_bdf[the_bdf.index!='Missing']['pct'].iloc[-1]# 最后一箱的占比
                max_badn = the_bdf[the_bdf.index!='Missing']['bad'].iloc[-1]# 最后一箱的坏客户数
                
                min_bs = the_bdf[the_bdf.index!='Missing']['lift'].iloc[0]
                min_pct = the_bdf[the_bdf.index!='Missing']['pct'].iloc[0]
                min_badn = the_bdf[the_bdf.index!='Missing']['bad'].iloc[0]
            
            missing_pct = the_bdf.loc['Missing','pct'] if 'Missing' in a['group'].unique() else pd.Series(index=the_vdf.index).fillna(0)
            
            
            #画分时段马赛克图        
            l = sorted(list(the_vdf.index))
    
            fig = plt.figure(figsize=(5*len(l),4))
            fig.suptitle('{},{}, 总样本量：{}, 时间跨度:{}\n\n总IV:{:.2f}, 总KS:{:.2f}, 总空值率:{:.2%}, 总趋势:{}'.format(x,y,tot_size,dt_range,tot_iv,tot_ks,tot_missing,tot_mono), 
                         x = 0.1, y = 1.2, ha='left',size=15,bbox = dict(facecolor = 'grey',alpha=0.1))
    
            for k in l:  
                i = l.index(k)
                the_max_bs = max_bs[k] # 最后一箱的风险
                the_max_pct = max_pct[k]# 最后一箱的占比
                the_max_badn = max_badn[k]# 最后一箱的坏客户数
                
                the_min_bs = min_bs[k]
                the_min_pct = min_pct[k]
                the_min_badn = min_badn[k]
                    
                bad_rate = [1 if ic*bs>1 else ic*bs for ic in the_bdf['risk'][k]]
                the_lift = the_bdf['lift'][k]
                the_pct = the_bdf['pct'][k]
                x_pos =[0]+ list(np.cumsum(the_pct))[:-1]
                x_label_pos = []
                for j in range(len(list(the_pct))):
                    if j ==0:
                        x_label_pos.append(round(list(the_pct)[j]/2,4))
                    else:
                        x_label_pos.append(round((sum(list(the_pct)[:j])+list(the_pct)[j]/2),4))
                ax = plt.subplot(1,len(l),i+1)
                ax.text(0.01, 0.88, "首:{:.1f}倍,{:.0f}个,占{:.1%};  \n尾:{:.1f}倍,{:.0f} 个,占{:.1%}".format(the_min_bs,the_min_badn,the_min_pct,the_max_bs,the_max_badn,the_max_pct), fontdict={'size': '11', 'color': 'b'}) # 写平均风险值
                ax.set_title(' {}, 样本：{:.0f}/{:.0f}({:.2%}), \n IV:{:.2f}, KS:{:.2f}, PSI:{:.2f}, miss:{:.0%}'.format(str(k),cross_sum[k],cross_len[k],cross_mean[k],
                                                                                                 the_vdf['IV'][k],the_vdf['KS'][k],
                                                                                                 the_vdf['psi'][k],missing_pct[k]),size = 12) #表标题
    
                ax.bar(x_pos,[1]*len(bad_rate), width=the_pct, align='edge',ec='w',lw=1,label='N',color='silver',alpha=0.8)
                ax.bar(x_pos,bad_rate,width=the_pct,align='edge',ec='w',lw=1,label='Y',color='coral',alpha=0.8)
                ax.axhline(y =cross_mean[k]*bs,color='r',label='warning line1',linestyle='--',linewidth=1)
                ax.text(0.95,cross_mean[k]*bs+0.05,'avg:'+str(round(cross_mean[k]*100,1)),ha='center',fontsize=9,color='r')
                ax.set_xticks(x_label_pos)
                # ax.set_yticks(y_label_pos)
                ax.set_xticklabels([str(xj) for xj in list(the_bdf.index)],rotation=90,fontsize=10)
                # ax.set_yticklabels(['Y','N'])    
                for n1,n2,n3 in zip(x_label_pos,bad_rate,the_lift):
                    ax.text(n1,n2/2,str(round(n3,1)),ha='center',fontsize=9)
        
                    # 存图
            if output_path==None:
    
                plt.show()
    
            else:   
                if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
                    os.makedirs(os.path.dirname(output_path))
                fig.savefig('{}/{}_{:.3f}_{}.png'.format(os.path.dirname(output_path),
                                                            tot_mono,
                                                            tot_iv, 
                                                            re.sub(r"[\/\\\:\*\?\"\<\>\|]", '',x)), 
                                pad_inches=0.3, dpi=100, papertype='a4',bbox_inches='tight')
                plt.close()   
                
        
                
    return A,df_t,bins
            



def create_rsk_fig(a,dt_range,x,y,amt=None,bin_method='cart'):
    # cross_vardf['dt_cut'] = cross_vardf['dt_cut'].astype('str')
    # cross_bindf['dt_cut'] = cross_bindf['dt_cut'].astype('str')
    if y:
        a = a[(a['x']==x)&(a['y']==y)&(a['bin_method']==bin_method)].set_index('x')
    else:
        a = a[(a['x']==x)&(a['y']=='No_y')&(a['bin_method']==bin_method)].set_index('x')
    
    # a = pd.concat([a[a['group']=='Missing'],a[a['group']!='Missing']])
    cross_bindf = a[a['group']!='Total']
    cross_vardf = a[a['group']=='Total']
    
    tot_size = a.query('dt_cut=="All" and group=="Total"').loc[x,'total']
    tot_iv = a.query('dt_cut=="All" and group=="Total"').loc[x,'IV']
    tot_ks = a.query('dt_cut=="All" and group=="Total"').loc[x,'KS']
    tot_missing = a.query('dt_cut=="All" and group=="Missing"').loc[x,'pct'] if 'Missing' in a['group'] else 0
    tot_mono = a.query('dt_cut=="All" and group=="Total"').loc[x,'Mono']
    
    if isinstance(cross_vardf.loc[x],pd.DataFrame):
        the_vdf = cross_vardf.loc[x].reset_index().set_index('dt_cut')
    else:
        the_vdf = cross_vardf.loc[x].to_frame().T.reset_index().set_index('dt_cut')
        
    if isinstance(cross_bindf.loc[x],pd.DataFrame):
        the_bdf = cross_bindf.loc[x].reset_index().set_index(['group','dt_cut']).unstack(1).fillna(0)
    else:
        the_bdf = cross_bindf.loc[x].to_frame().T.reset_index().set_index(['group','dt_cut']).unstack(1).fillna(0)
        
    the_bdf = pd.concat([the_bdf[the_bdf.index=='Missing'],the_bdf[the_bdf.index!='Missing']])
    
    cross_len = the_vdf['total']
    cross_sum = the_vdf['bad']
    cross_mean = the_vdf['risk']
    
    exmiss = the_bdf[the_bdf.index!='Missing']
    if len(exmiss)==0:
        max_bs = min_bs = pd.Series(index=the_vdf.index).fillna(1)
        max_pct = min_pct = pd.Series(index=the_vdf.index).fillna(1)
        max_badn = min_badn = pd.Series(index=the_vdf.index).fillna(0)
        tot_missing = 1
    else:
        max_bs = the_bdf[the_bdf.index!='Missing']['lift'].iloc[-1] # 最后一箱的风险
        max_pct = the_bdf[the_bdf.index!='Missing']['pct'].iloc[-1]# 最后一箱的占比
        max_badn = the_bdf[the_bdf.index!='Missing']['bad'].iloc[-1]# 最后一箱的坏客户数
        
        min_bs = the_bdf[the_bdf.index!='Missing']['lift'].iloc[0]
        min_pct = the_bdf[the_bdf.index!='Missing']['pct'].iloc[0]
        min_badn = the_bdf[the_bdf.index!='Missing']['bad'].iloc[0]
    
    missing_pct = the_bdf.loc['Missing','pct'] if 'Missing' in a['group'].unique() else pd.Series(index=the_vdf.index).fillna(0)
    
    #画分时段马赛克图     
    l = sorted(list(the_vdf.index))

    fig = plt.figure(figsize=(5*len(l),4))
    fig.suptitle('{},{}, 总样本量：{:.0f}, 时间跨度:{}\n\n总IV:{:.2f}, 总KS:{:.2f}, 总空值率:{:.2%}, 总趋势:{}'.format(x,y,tot_size,dt_range,tot_iv,tot_ks,tot_missing,tot_mono), 
                 x = 0.1, y = 1.2, ha='left',size=15,bbox = dict(facecolor = 'grey',alpha=0.1))

    for k in l:  
        i = l.index(k)
        the_max_bs = max_bs[k] # 最后一箱的风险
        the_max_pct = max_pct[k]# 最后一箱的占比
        the_max_badn = max_badn[k]# 最后一箱的坏客户数
        
        the_min_bs = min_bs[k]
        the_min_pct = min_pct[k]
        the_min_badn = min_badn[k]
    
        # 柱状图
        the_pct = the_bdf['pct'][k]
        
        color = 'k'
        xlabel = [str(xx) for xx in the_bdf.index]
        ax1 = plt.subplot(1,len(l),i+1)
        ax1.set_xticklabels(xlabel,rotation=90,fontsize=10)
        ax1.bar(xlabel, the_pct,alpha=0.2,color = color,label='样本占比')
        
        ax1.text(0.01, 0.88, "首:{:.1f}倍,{:.0f}个,占{:.1%};  \n尾:{:.1f}倍,{:.0f} 个,占{:.1%}".format(the_min_bs,the_min_badn,the_min_pct,the_max_bs,the_max_badn,the_max_pct), transform=ax1.transAxes, fontdict={'size': '11', 'color': 'b'}) # 写平均风险值
        ax1.set_title(' {}, 样本：{:.0f}/{:.0f}({:.2%}), \n IV:{:.2f}, KS:{:.2f}, PSI:{:.2f}, miss:{:.0%}'.format(str(k),cross_sum[k],cross_len[k],cross_mean[k],
                                                                                         the_vdf['IV'][k],the_vdf['KS'][k],
                                                                                         the_vdf['psi'][k],missing_pct[k]),size = 12) #表标题
        ax1.set_ylim([0,the_bdf['pct'].max().max()*1.1])
        ax1.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1,decimals=0))
        ax1.axes.set_ylabel('')
        ax1.tick_params(axis='y', labelcolor='#696969')
        if i == len(l)-1:
            ax1.legend(loc='upper right')
        
        if y:
            # badrate 曲线
            bad_rate = the_bdf['risk'][k]
            the_lift = the_bdf['lift'][k]
            frsk = bad_rate.copy()
            flift = the_lift.copy()
            if missing_pct.max()>0:
                frsk.iloc[0] = np.nan
                flift.iloc[0] = np.nan
            ax2 = ax1.twinx()
            if cross_bindf[cross_bindf.group!='Missing'].shape[0]>0:
                ylim_max = cross_bindf[cross_bindf.group!='Missing'].loc[x][['risk','risk_amt']].max().max()
            else:
                ylim_max = cross_bindf.loc[x][['risk','risk_amt']].max().max()
                
            ax2.plot(xlabel,frsk,'o-',color='red',markersize=4,label=y)
            for a,b,c in zip([i for i in range(len(xlabel))], frsk, flift):
                ax2.annotate("{:.1f}".format(c), xy=(a,b), xytext=(-4, 5), textcoords='offset points', weight='heavy')
            ax2.axhline(y=cross_mean[k], color='grey', label='avg_risk', linestyle='--', linewidth=1) # 平均风险线
            ax2.set_ylim([0,ylim_max*1.2])
            ax2.yaxis.set_major_formatter(ticker.PercentFormatter(xmax=1,decimals=0))
            ax2.axes.set_ylabel('')
            ax2.tick_params(axis='y', labelcolor='#A52A2A')
            
            
             # 空箱badrate 打点
            if missing_pct[k]>0:
                ax3 = ax1.twinx()
                sns.pointplot(xlabel, [ylim_max*1 if bad_rate.iloc[0]>=ylim_max else bad_rate.iloc[0]]+[np.nan]*(len(xlabel)-1), ax=ax3, alpha=0.2,color='blue',scale=0.6)  # 画在ax3画布上
                for idx,(a,b,c) in enumerate(zip([i for i in range(len(xlabel))], bad_rate,the_lift)):
                    if idx==0:
                        if bad_rate.iloc[0]>=ylim_max:
                            ax3.annotate("{:.1f}".format(c), xy=(a,ylim_max), xytext=(-8, 5), textcoords='offset points', weight='heavy',color='blue')
                        else:
                            ax3.annotate("{:.1f}".format(c), xy=(a,b), xytext=(-8, 5), textcoords='offset points', weight='heavy',color='blue')
                
                ax3.set_ylim([0,ylim_max*1.2])
                ax3.yaxis.set_ticklabels([]) 
                ax3.axes.set_ylabel('')
                
        if amt and y:
            # 金额badrate曲线
            # ax4 = ax2.twinx()
            bad_rate1 = the_bdf['risk_amt'][k]
            frsk1 = bad_rate1.copy()
            if missing_pct.max()>0:
                frsk1.iloc[0] = np.nan
            ax2.plot(xlabel,frsk1,'o-',color='y',markersize=4,label=amt)
            for a,b in zip([i for i in range(len(xlabel))], frsk1):
                ax2.annotate("{:.1%}".format(b), xy=(a,b), xytext=(-12, 5), textcoords='offset points', weight='heavy')
            ax2.axhline(y=the_vdf['risk_amt'][k], color='y', label='avg_risk', linestyle='--', linewidth=1)
            ax2.set_ylim([0,ylim_max*1.2])
            ax2.axes.set_ylabel('')
            
            # 空箱badrate 打点
            if missing_pct[k]>0:
                sns.pointplot(xlabel, [ylim_max*1 if bad_rate1.iloc[0]>=ylim_max else bad_rate1.iloc[0]]+[np.nan]*(len(xlabel)-1), ax=ax3, alpha=0.2,color='y',scale=0.6)  # 画在ax3画布上
                for idx,(a,b) in enumerate(zip([i for i in range(len(xlabel))], bad_rate1)):
                    if idx==0:
                        if bad_rate1.iloc[0]>=ylim_max:
                            ax3.annotate("{:.1%}".format(b), xy=(a,ylim_max), xytext=(-8, 5), textcoords='offset points', weight='heavy',color='y')
                        else:
                            ax3.annotate("{:.1%}".format(b), xy=(a,b), xytext=(-8, 5), textcoords='offset points', weight='heavy',color='y')
                
                ax3.yaxis.set_ticklabels([]) 
                ax3.axes.set_ylabel('')
    plt.close()
                
    return fig,tot_mono,tot_iv

    

def plt_multi_rsk_trend(df,inputx,is_rule=0,
               y='fpd30',amt=None,
               dt='close_date',dt_cut=2,
               miss_values=[-99],
               bin_method={
                    'Notbin':False,
                    'fix_bin':None , 
                    'cart':{'min_samples_leaf':[0.0001],'max_leaf_nodes':[20]}, # 叶子节点最小样本数占比，最大的叶子节点数
                    'uniform':[20],
                    'quantile':[20]
                    },
               combine_method={
                    'Notcombine':False,
                    'mono':'auto_asc_desc',
                    'min_bin_bad':3 
                    },
               if_plot=True,
               output_path=None,
               verbose=1,
               n_jobs=0):

    
        
    '''
    分组风险趋势图函数
    ----------
    其余参数同DDViz.out_all_in_one
    :param if_plot : bool     默认True, 默认直接画图 
    :param output_path : 存储地址，保存马赛克图，默认值None. 会自动创建相应的文件夹
    '''
    # get_log("DDViz 1.1.18 plt_multi_rsk_trend")
    if y:
        y_list = [y]
    else:
        y_list=None
    cross_vardf,df_t,bins = out_all_in_one(df,inputx,is_rule=is_rule,
                   y_list=y_list,amt=amt,
                   dt=dt,dt_cut=dt_cut,
                   miss_values=miss_values,
                   bin_method=bin_method,
                   combine_method=combine_method,
                   output_path=None,
                   verbose=0,
                   n_jobs=n_jobs)
    
    if dt:
        dt_range = (str(df[dt].min())+'~'+str(df[dt].max())).replace('.0','')
    else:
        dt_range = 'All'
        
    x_list = list(cross_vardf.x.unique())

    if if_plot:
        if is_rule==1 and isinstance(inputx,str):
            F = []
            for x in x_list:
                f,tot_mono,tot_iv = create_rsk_fig(cross_vardf,dt_range=dt_range,x=x,y=y,amt=amt,bin_method='Notbin')
                F.append(f)
        
            fig = excel2img.merge_img1(img=F,scale=1)
            
            if output_path==None:
                display(fig)
            else:   
                if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
                    os.makedirs(os.path.dirname(output_path))
                fig.save('{}/{}_{:.3f}_{}.png'.format(os.path.dirname(output_path),
                                                            tot_mono,
                                                            tot_iv, 
                                                            re.sub(r"[\/\\\:\*\?\"\<\>\|]", '',inputx)))
            
        else:
            for x in x_list:
                fig,tot_mono,tot_iv = create_rsk_fig(cross_vardf,dt_range=dt_range,x=x,y=y,amt=amt,bin_method=cross_vardf.bin_method.unique()[0])

                if output_path==None:
                    display(fig)
                else:   
                    if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
                        os.makedirs(os.path.dirname(output_path))
                    fig.savefig('{}/{}_{:.3f}_{}.png'.format(os.path.dirname(output_path),
                                                                    tot_mono,
                                                                    tot_iv, 
                                                                    re.sub(r"[\/\\\:\*\?\"\<\>\|]", '',x)), 
                                        pad_inches=0.3, dpi=100, papertype='a4',bbox_inches='tight')

               
    return cross_vardf,df_t,bins


#%%
def create_heatmap(b,the_vdf,x,y,tot_size,dt_range,tot_iv,tot_ks,tot_mono,by='lift',color='YlOrRd',xticklabels=True,title=True,xlabel=True):

    if by=='lift':
        b['showp'] = b.apply(lambda x: f"{x['lift']:.1f}\n( {x['bad']:.0f} )",axis=1)
        vmin=0
        vmax=3
    else:
        b['showp'] = b.apply(lambda x: f"{x['pct']*100:.2f}%\n( {x['total']:.0f} )",axis=1)
        vmin=vmax=None
        

    # a = pd.concat([a[a['group']=='Missing'],a[a['group']!='Missing']])
        
    
    b = b.unstack()
    l = sorted(b.index.get_level_values('dt_cut').unique())
    
    fig = plt.figure(figsize=(7*len(l),3.5))
    if title:
        fig.suptitle('{},{}, 总样本量：{:.0f}, 时间跨度:{}\n\n总IV:{:.2f}, 总KS:{:.2f}, 总趋势:{}'.format(x,y,tot_size,dt_range,tot_iv,tot_ks,tot_mono), 
                      x = 0.12, y = 1.3, ha='left',size=15,bbox = dict(facecolor = 'grey',alpha=0.1))

    for k in l:  
        i = l.index(k)
        b1 = b[b.index.get_level_values('dt_cut')==k][by].droplevel('dt_cut')
        b2 = b[b.index.get_level_values('dt_cut')==k]['showp'].droplevel('dt_cut')
        if b1.shape[0]>4 or b1.shape[1]>4:
            size=8
        else:
            size=12
        ax1 = fig.add_subplot(1,len(l),i+1)
        
        
        sns.heatmap(b1,cmap=color,annot=b2,fmt="", ax = ax1,vmin=vmin,vmax=vmax, linewidths=0.5,annot_kws={"size":size},xticklabels =xticklabels)
        if title:
            ax1.set_title(' {}, 样本：{:.0f}/{:.0f}({:.2%}), \n IV:{:.2f}, KS:{:.2f}, PSI:{:.2f}'.format(str(k),the_vdf['total'][k],the_vdf['bad'][k],the_vdf['risk'][k],
                                                                                             the_vdf['IV'][k],the_vdf['KS'][k],
                                                                                             the_vdf['psi'][k]),size = 12) #表标题
        if not xlabel:
            ax1.set(xlabel="")
    plt.close()
    return fig

def show_cross_x(a,x,y,show=['total','pct']):
    """

    Parameters
    ----------
    a : dataframe out_all_in_one，开启is_cross后计算出来的第一个参数.
        
    x : string 要查看的交叉表 x="('dt_bqs_id_daily_multi_count_1h', 'opec_dhb_operator')".
    y : string 指定查看y. y='fpd4'
    show : list or string, optional
        展示的内容，可选项['total', 'bad', 'pct','risk', 'tot_amt', 'bad_amt','avg_amt', 'risk_amt', 'lift', 'lift_amt']. The default is ['total','pct'].

    Returns
    -------
    b : dataframe   交叉表.

    """
    si = eval(x)
    a[si[0]] =  a['group'].str.split('&').str[0]
    a[si[1]] =  a['group'].str.split('&').str[1]
    bb = a[(a['y']==y)&(a.group!='Total')].groupby(['dt_cut',si[0],si[1]])[['total', 'bad', 'pct','risk', 'tot_amt', 'bad_amt','avg_amt', 'risk_amt', 'lift', 'lift_amt']].sum()
    b = bb.unstack()[show]
    display(b)
    return b

def plt_multi_cross_x(df,inputx,is_rule=0,is_cross=1,
               y='fpd30',amt=None,
               dt='close_date',dt_cut=2,
               miss_values=[-99],
               bin_method={
                    'Notbin':False,
                    'fix_bin':None , 
                    'cart':{'min_samples_leaf':[0.0001],'max_leaf_nodes':[20]}, # 叶子节点最小样本数占比，最大的叶子节点数
                    'uniform':None,
                    'quantile':None,
                    },
               combine_method={
                    'Notcombine':False,
                    'mono':'auto_asc_desc',
                    'min_bin_bad':3 
                    },
               if_plot=True,
               output_path=None,
               verbose=0,
               n_jobs=0):
    
    a1,b1,bins = out_all_in_one(df,inputx,is_rule=is_rule,is_cross=1,
                   y_list=[y],amt=amt,
                   dt=dt,dt_cut=dt_cut,
                   miss_values=miss_values,
                   bin_method=bin_method,
                   combine_method=combine_method,
                   output_path=None,
                   verbose=0,
                   n_jobs=n_jobs)
    
    aa = a1[a1['x'].str.contains(', ')]
    
    if dt:
        dt_range = (str(df[dt].min())+'~'+str(df[dt].max())).replace('.0','')
    else:
        dt_range = 'All'
        
    if if_plot:
        for i in aa.x.unique():
            tot_size = aa.query('dt_cut=="All" and group=="Total"')['total'].values[0]
            tot_iv = aa.query('dt_cut=="All" and group=="Total"')['IV'].values[0]
            tot_ks = aa.query('dt_cut=="All" and group=="Total"')['KS'].values[0]
            tot_mono = aa.query('dt_cut=="All" and group=="Total"')['Mono'].values[0]
            
            the_vdf = aa.query("group=='Total'")[['dt_cut','total','bad','risk','IV','KS','psi']].set_index('dt_cut')
            
            
            si = eval(i)
            aa[si[0]] =  aa['group'].str.split('&').str[0]
            aa[si[1]] =  aa['group'].str.split('&').str[1]
            bb = aa[(aa['y']==y)&(aa.group!='Total')].groupby(['dt_cut',si[0],si[1]])[['total', 'bad', 'pct','risk', 'tot_amt', 'bad_amt','avg_amt', 'risk_amt', 'lift', 'lift_amt']].sum()

            f1 = create_heatmap(bb,the_vdf,i,y,tot_size,dt_range,tot_iv,tot_ks,tot_mono,by='lift',color='YlOrRd',xticklabels=False,title=True,xlabel=False)
            f2 = create_heatmap(bb,the_vdf,i,y,tot_size,dt_range,tot_iv,tot_ks,tot_mono,by='pct',color='Blues',xticklabels=True,title=False,xlabel=True)
            fig = excel2img.merge_img1(img=[f1,f2],scale=1)
             
            if output_path==None:
                display(fig)
                return a1,b1,bins
            else:  
                if os.path.dirname(output_path) and not os.path.exists(os.path.dirname(output_path)):
                     os.makedirs(os.path.dirname(output_path))
                fig.save('{}/{}_{}.png'.format(os.path.dirname(output_path),
                                                             si[0],
                                                             si[1]))
                return a1,b1,bins
    else:
        return a1,b1,bins

#%%

def tranpose_conditions(x):
    if x=='<=':
        x1 = '>'
    elif x=='>':
        x1='<='
    elif x=='<':
        x1='>='
    elif x=='>=':
        x1='<'
    elif x=='==':
        x1='<>'
    else:
        x1=x
    return x1



def plt_rule_to_tree(df,y='fpd30',r='lbs_latitude <= 45.8089 & dz_model_combo_score > 632.500 & hx_rs02_score <= 0.1817'):
    rlist = r.split(' & ' )
    s = len(df[df[y]>=0])
    bad = len(df[df[y]==1])
    risk = bad/s
    
    N = {}
    tmp = df[df[y]>=0].copy()
    for n,r1 in enumerate(rlist):
        tmp = tmp.reset_index(drop=True)
        # print(r1)
        tmp['is_hit'] = np.where(tmp.index.isin(tmp.query(r1).index),1,0)
        a = tmp.groupby(['is_hit']).apply(lambda k4: pd.Series(
            {'total': k4.shape[0],
             'good': k4.shape[0]-k4[k4[y]>=0][y].sum() if y and len(k4[k4[y]>=0])>0 else np.nan,
             'bad': k4[k4[y]>=0][y].sum() if y and len(k4[k4[y]>=0])>0 else np.nan,
             'risk': k4[k4[y]>=0][y].mean() if y else np.nan
                })
            ).assign(
                pct = lambda k5: k5.total/s,
                lift = lambda k5: k5.risk/risk if y else np.nan)
        a = a.to_json(orient='index')
        N['node'+str(n)] = {r1:a}
        tmp = tmp.query(r1)
            
        
    n_node_samples = []
    C = []
    value = []
    lift = []
    bad = []
    pct = []
    for k in N:
        # print(k)
        v = json.loads(list(N[k].values())[0])
        r = list(N[k].keys())[0]
        conditions = re.findall(r'\s*(\w+)\s*([><=]=?)\s*(-?[0-9.]+)',r)
        if '0' in v.keys():
            v1_total = v["1"]['total']
            v1_good = v["1"]['good']
            v1_bad = v["1"]['bad']
            v1_lift = v['1']['lift']
            v1_pct = v['1']['pct']
        else:
            v1_total = v1_good = v1_bad = v1_lift = v1_pct = 0
            
        if '1' in v.keys():
            v0_total = v["0"]['total']
            v0_good = v["0"]['good']
            v0_bad = v["0"]['bad']
            v0_lift = v['0']['lift']
            v0_pct = v['0']['pct']
        else:
            v0_total = v0_good = v0_bad = v0_lift = v0_pct = 0
            
        s1 = [v1_total,v0_total]
        value1 = [[[v1_good,v1_bad]],[[v0_good,v0_bad]]]
        lift1 = [v1_lift,v0_lift]
        bad1 = [v1_bad,v0_bad]
        pct1 = [v1_pct,v0_pct]
        
        if k=='node0':
            s1 = [sum(s1),v1_total,v0_total]
            value1 = [[[v1_good+v0_good,v1_bad+v0_bad]],[[v1_good,v1_bad]],[[v0_good,v0_bad]]]
            lift1 = [1, v1_lift,v0_lift]
            bad1 = [sum(bad1),v1_bad,v0_bad]
            pct1 = [sum(pct1),v1_pct,v0_pct]
            
        n_node_samples = n_node_samples+s1
        C = C+conditions
        value = value+value1
        lift = lift+lift1
        bad = bad+bad1
        pct = pct+pct1
        
    f = [i[0] for i in C]
    new=[]
    for i in C[1:]:
        new.extend([i,-2])
    f_n = [C[0]]+new+[-2,-2]
    
    # f_n = [C[i] if i<=1 else C[i-1] if i%2==1 and i<=len(C) else -2 for i in range(len(n_node_samples))]
    f_n_right = [-2 if i==-2 else (i[0],tranpose_conditions(i[1]),i[2]) for i in f_n]
    feature = [-2 if i==-2 else f.index(i[0]) for i in f_n]
    threshold = [-2 if i==-2 else float(i[2]) for i in f_n]
    children_left = [-1 if i==-2 else f_n.index(i)+1 if f_n.index(i)==0 else f_n.index(i)+2 for i in f_n]
    
    children_right = [-1 if i==-2 else f_n.index(i)+2 if f_n.index(i)==0 else f_n.index(i)+3 for i in f_n]
    n_node_samples = [int(i) for i in n_node_samples]
    bad = [int(i) for i in bad]
    
    
    clf = DecisionTreeClassifier()
    clf.classes_ = np.array([0,1])
    clf.n_features_ = len(f)
    clf.tree_ = types.SimpleNamespace()
    clf.tree_.children_left =  np.array(children_left)
    clf.tree_.children_right =  np.array(children_right)
    clf.tree_.feature =  np.array(feature)
    clf.tree_.threshold =  np.array(threshold)
    clf.tree_.value =  np.array(value)
    clf.tree_.n_node_samples =  np.array(n_node_samples)
    clf.tree_.weighted_n_node_samples =  np.array(n_node_samples)
    clf.tree_.f_n =  np.array(f_n)
    clf.tree_.f_n_right =  np.array(f_n_right)
    clf.tree_.n_features =  len(f)
    clf.tree_.n_outputs =  1
    clf.tree_.n_classes =  np.array([2])
    clf.tree_.lift = np.array(lift)
    clf.tree_.pct = np.array(pct)
    clf.tree_.type_name ='rule'
    clf.tree_.bad = np.array(bad)
    
    dot_data = tree.export_graphviz(clf,feature_names = f,impurity=False, filled=True, rounded=True,out_file=None)
    
    dot_data = dot_data.replace('helvetica','Consolas')
    dot_data_list = dot_data.split(';')
    
    dot_data_list_new = []
    for item in dot_data_list:
        lift = re.findall(r'lift = ([^ ]+)\\',item)
        if len(lift)>0:
            
            if float(lift[0])>=2.5:
                c = '#fdce7b'
            elif float(lift[0])>=1.5:
                c = '#FFFACD'
            else:
                c = '#ffffff'
            item1 = re.sub(r'fillcolor="(.*?)"',f'fillcolor="{c}"',item)
            
            dot_data_list_new.append(item1)
        else:
            dot_data_list_new.append(item)
    
    dot_data_new = ';'.join(dot_data_list_new)
    graph = graphviz.Source(dot_data_new)
    
    return graph