# -*- coding: utf-8 -*-
"""对疑似误标为高风险的 app 做保守 LLM 复审"""
import sys, re, json, time, sqlite3, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic, pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(r"d:\my_claude\反欺诈")
CACHE = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"
INPUT = BASE / "applist_tag_0522.csv"
BATCH_DIR = BASE / "tagging_tmp"
MODEL = "claude-opus-4-6"
BATCH_SIZE = 20
MAX_WORKERS = 4
PREFIX = "review_overlabeled"

REGULAR_KW = (
    "工商银行|建设银行|农业银行|中国银行|交通银行|招商银行|浦发银行|民生银行|"
    "兴业银行|光大银行|平安银行|中信银行|华夏银行|邮政储蓄|邮储|广发银行|"
    "北京银行|上海银行|南京银行|宁波银行|江苏银行|支付宝|微信|花呗|借呗|"
    "京东金条|美团金融|度小满|招联金融|马上消费|微粒贷|蚂蚁财富|陆金所|平安普惠|"
    "华为|小米|OPPO|vivo|荣耀|三星|苹果|Apple|百度|腾讯|阿里|京东|美团|滴滴|"
    "字节|抖音|快手|微博|新浪|搜狐|网易|知乎|B站|哔哩哔哩|政务|公安|税务|社保|"
    "公积金|12306|国家|政府|钉钉|飞书|企业微信|WPS|金山|Microsoft|Office|学习强国"
)
HIGH = ["小额现金贷","赌博","色情","翻墙VPN","山寨低质","伪冒仿冒","改机软件",
        "黑灰产工具","网赚刷量","隐私窃取","其他高风险","区块链","反催收","征信修复","投诉平台"]

SYSTEM_PROMPT = """你是反欺诈分析师，对一批"被标为高风险"的 app 做**保守**复审。

## 任务
判断这些高风险标签是否真的有误。**保守原则（极其重要）**:
- 默认信任原标签，只在**确凿误标**时才改回 risk_type=无
- 名称含正规品牌词不等于无风险：
  - 仿冒包（如"中国建设银行"包名 com.zgbz.jsyh）→ 仍是伪冒仿冒
  - 破解版/成人版（如"抖音破解版"/"成人快手"）→ 仍是山寨低质/色情
  - 多开分身（如包名 com.qihoo.magic.*）→ 仍是改机软件
- 山寨电商（"XX商城"+乱码包名）→ 仍是山寨低质
- 网赚游戏（"手游赚"/"0元游戏"）→ 仍是网赚刷量
- 虚拟定位工具（"GPS模拟器"/"位置模拟器"）→ 仍是改机软件

**只在以下情形改为 risk=无**:
- 包名是该品牌的**真实官方包名**（如 com.tencent.mm、com.eg.android.AlipayGphone）
- 名称是正规企业 VPN/政务 app（"哈工程VPN"/"国家政务"）

## 标签体系
app_l1: 系统应用/办公软件/借贷软件/金融理财/银行/政务/社交通讯/电商购物/生活服务/出行交通/视频影音/阅读资讯/游戏/教育学习/摄影美化/健康运动/旅游/工具/区块链加密/色情成人/棋牌赌博/其他
risk_type: 无/小额现金贷/反催收/征信修复/投诉平台/赌博/区块链/色情/翻墙VPN/山寨低质/伪冒仿冒/改机软件/黑灰产工具/网赚刷量/隐私窃取/其他高风险

## 输出
严格 JSON 数组:
[{"app_package":"原样回填","app_l1":"...","app_l2":"...","risk_type":"...","confidence":0.0-1.0,"reason":"20字内","verdict":"keep|change"}]
verdict=keep 表示原标签正确，change 表示确实误标已修正。
"""

def extract_json(t):
    t = t.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", t, re.DOTALL)
    if m: t = m.group(1)
    s, e = t.find("["), t.rfind("]")
    if s == -1 or e == -1: raise ValueError(t[:200])
    return json.loads(t[s:e+1])

def label_batch(client, apps, idx):
    msg = (f"对以下 {len(apps)} 个**被标为高风险**的 app 做保守复审。\n"
           f"`orig_*` 是当前标签。**只有确凿误标才改**，否则 verdict=keep 保留原标。\n\n"
           + json.dumps(apps, ensure_ascii=False))
    res = None
    for a in range(3):
        try:
            r = client.messages.create(
                model=MODEL, max_tokens=4096,
                system=[{"type":"text","text":SYSTEM_PROMPT,"cache_control":{"type":"ephemeral"}}],
                messages=[{"role":"user","content":msg}])
            res = extract_json(next(b.text for b in r.content if b.type=="text"))
            ret = {x["app_package"] for x in res}
            for x in apps:
                if x["app_package"] not in ret:
                    res.append({"app_package":x["app_package"],"app_l1":x["orig_l1"],
                        "app_l2":x["orig_l2"],"risk_type":x["orig_risk"],
                        "confidence":x.get("orig_conf",0.5),"reason":"LLM未返回保留",
                        "verdict":"keep"})
            break
        except Exception as e:
            logging.warning("attempt %d: %s", a+1, e)
            time.sleep(2**a)
    if res is None:
        res = [{"app_package":x["app_package"],"app_l1":x["orig_l1"],"app_l2":x["orig_l2"],
            "risk_type":x["orig_risk"],"confidence":x.get("orig_conf",0.5),
            "reason":"LLM失败保留","verdict":"keep"} for x in apps]
    BATCH_DIR.mkdir(exist_ok=True)
    nm = {a["app_package"]:a["app_name"] for a in apps}
    out = [{"app_name":nm.get(r["app_package"],""), **r} for r in res]
    (BATCH_DIR/f"{PREFIX}_{idx:03d}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = sqlite3.connect(str(CACHE), check_same_thread=False)
    df = pd.read_sql("SELECT * FROM label_cache", conn)
    src = pd.read_csv(INPUT).drop_duplicates("app_package")
    df = df.merge(src, on="app_package", how="left")
    df["app_name"] = df["app_name"].fillna("")

    high = df[df["risk_type"].isin(HIGH)]
    suspects_set = set()

    # 8 类规则
    rules = [
        ("正规品牌", high[high["app_name"].str.contains(REGULAR_KW, regex=True, na=False, case=False)]),
        ("低confidence", high[high["confidence"]<0.4]),
        ("山寨低质机构名", high[(high["risk_type"]=="山寨低质") &
            high["app_name"].str.contains("银行|商城|超市|医院|学校|学院|公司|集团|科技|股份", regex=True, na=False)]),
        ("改机软件像游戏", high[(high["risk_type"]=="改机软件") &
            high["app_name"].str.contains("模拟器|计算器|导航", regex=True, na=False)]),
        ("赌博像教学", high[(high["risk_type"]=="赌博") &
            high["app_name"].str.contains("教学|教程|学习|训练", regex=True, na=False)]),
        ("色情但常规社交", high[(high["risk_type"]=="色情") &
            high["app_name"].str.contains("陌陌|探探|Soul|Tinder|QQ|微信", regex=True, na=False)]),
        ("网赚是游戏", high[(high["risk_type"]=="网赚刷量") &
            high["app_name"].str.contains("游戏|手游", regex=True, na=False)]),
        ("VPN企业校园", high[(high["risk_type"]=="翻墙VPN") &
            high["app_name"].str.contains("企业|校园|高校|学校|政务|内部|公司|集团|令牌", regex=True, na=False)]),
    ]
    pkg_to_app = {}
    for _, sub in rules:
        for _, r in sub.iterrows():
            if r.app_package in suspects_set: continue
            suspects_set.add(r.app_package)
            pkg_to_app[r.app_package] = {
                "app_name": r.app_name, "app_package": r.app_package,
                "orig_l1": r.app_l1, "orig_l2": r.app_l2,
                "orig_risk": r.risk_type, "orig_conf": float(r.confidence) if pd.notna(r.confidence) else 0.5,
            }
    suspects = list(pkg_to_app.values())
    logging.info("待复审: %d 条", len(suspects))

    client = anthropic.Anthropic()
    t0 = time.time()
    batches = [suspects[i:i+BATCH_SIZE] for i in range(0, len(suspects), BATCH_SIZE)]
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(label_batch, client, b, i+1): i+1 for i, b in enumerate(batches)}
        done, total = 0, len(futs)
        for f in as_completed(futs):
            r = f.result()
            results.extend(r)
            done += 1
            if done % 2 == 0 or done == total:
                logging.info("进度 %d/%d 耗时 %.0fs", done, total, time.time()-t0)

    changed = [r for r in results if r.get("verdict")=="change" or r["risk_type"] != pkg_to_app[r["app_package"]]["orig_risk"]]
    kept = len(results) - len(changed)
    logging.info("复审完成: 改为无/其他风险 %d, 保留原标 %d", len(changed), kept)

    # 只写回有改动的
    conn.executemany(
        """INSERT OR REPLACE INTO label_cache
           (app_package,app_l1,app_l2,risk_type,confidence,reason,updated_at)
           VALUES (?,?,?,?,?,?,datetime('now'))""",
        [(r["app_package"],r["app_l1"],r["app_l2"],r["risk_type"],
          r["confidence"],r["reason"]+" [反向复审]") for r in changed])
    conn.commit()
    conn.close()

    if changed:
        print("\n改动样本:")
        for r in changed[:20]:
            orig = pkg_to_app[r["app_package"]]
            print(f"  {orig['app_name'][:25]:<25} {orig['orig_risk']} → {r['risk_type']} ({r.get('reason','')[:30]})")

if __name__ == "__main__":
    main()
