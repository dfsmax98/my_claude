# -*- coding: utf-8 -*-
"""对疑似漏标的 182 条走 LLM 复审"""
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
MAX_RETRIES = 3
PREFIX = "review_suspects"

# 同 audit_labels_v2.py
SUSPECT_RULES = [
    ("赌博", ["牛牛","炸金花","扎金花","德州","百家乐","老虎机","真金棋牌","真人棋牌",
              "棋牌室","棋牌大厅","真钱","彩票","竞彩","捕鱼","百人","龙虎斗","21点","21點"],
     ["计算器","教学","教程","学","新闻"]),
    ("色情", ["约炮","约会同城","撩妹","撩汉","裸聊","果聊","成人","深夜直播","小姐姐","御姐",
              "靓妹","骚","开车","荷尔蒙","暧昧","秒撩","美女直播","附近的女","附近秒聊"], []),
    ("翻墙VPN", ["翻墙","科学上网","Shadowsocks","SSR","V2Ray","机场加速","外网加速","翻墙加速"], []),
    ("网赚刷量", ["走路赚","看视频赚","试玩赚","刷视频赚","拉新赚","转发赚","阅读赚","签到赚",
                "悬赏任务","任务赚钱","赚钱app","抢红包","步步赚","看广告赚"], ["游戏"]),
    ("区块链", ["挖矿","加密货币","BTC","ETH","NFT","DeFi","Token","数字货币","区块链"], []),
    ("黑灰产工具", ["接码","虚拟号","按键精灵","抓包","逆向","群控","云控","自动脚本","脚本精灵"], []),
]

SYSTEM_PROMPT = """你是反欺诈分析师，对一批"先前被判定为 risk_type=无 但名字含可疑关键词"的 app 做复审。

## 任务
判断这些 app 的真实风险类型。**保守原则**：
- 如果名称只是巧合命中关键词（如"房贷计算器"含"贷"，"模拟器游戏"含"模拟器"），保留 risk_type=无
- 如果确实是该风险类（如"百家乐app"/"约炮神器"），按对应风险打标

## 标签体系
- app_l1: 系统应用/办公软件/借贷软件/金融理财/银行/政务/社交通讯/电商购物/生活服务/出行交通/视频影音/阅读资讯/游戏/教育学习/摄影美化/健康运动/旅游/工具/区块链加密/色情成人/棋牌赌博/其他
- 风险 risk_type: 无/小额现金贷/反催收/征信修复/投诉平台/赌博/区块链/色情/翻墙VPN/山寨低质/伪冒仿冒/改机软件/黑灰产工具/网赚刷量/隐私窃取/其他高风险

## 一致性规则（重要）
- risk=赌博 → app_l1=棋牌赌博
- risk=色情 → app_l1=色情成人
- risk=区块链 → app_l1=区块链加密
- risk=改机软件 → app_l1=工具, app_l2=改机工具

## 输出
严格 JSON 数组:
[{"app_package":"原样回填","app_l1":"...","app_l2":"...","risk_type":"...","confidence":0.0-1.0,"reason":"20字内"}]
"""

def extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if m: text = m.group(1)
    s, e = text.find("["), text.rfind("]")
    if s == -1 or e == -1: raise ValueError(text[:200])
    return json.loads(text[s:e+1])

def label_batch(client, apps, idx):
    msg = (f"对以下 {len(apps)} 个先前 risk=无 的 app 做复审，判断是否真的应改风险类型。\n"
           f"提示：每条 `_suspect` 字段是命中的疑似类别。\n\n"
           + json.dumps(apps, ensure_ascii=False))
    res = None
    for a in range(MAX_RETRIES):
        try:
            r = client.messages.create(
                model=MODEL, max_tokens=4096,
                system=[{"type":"text","text":SYSTEM_PROMPT,"cache_control":{"type":"ephemeral"}}],
                messages=[{"role":"user","content":msg}])
            res = extract_json(next(b.text for b in r.content if b.type=="text"))
            ret = {x["app_package"] for x in res}
            for a_ in apps:
                if a_["app_package"] not in ret:
                    res.append({"app_package":a_["app_package"],"app_l1":a_.get("orig_l1","未知"),
                        "app_l2":a_.get("orig_l2","未知"),"risk_type":"无","confidence":0.3,
                        "reason":"LLM未返回兜底保留原标"})
            break
        except Exception as e:
            logging.warning("attempt %d: %s", a+1, e)
            time.sleep(2**a)
    if res is None:
        res = [{"app_package":a["app_package"],"app_l1":a.get("orig_l1","未知"),
                "app_l2":a.get("orig_l2","未知"),"risk_type":"无","confidence":0.2,
                "reason":"LLM调用失败保留原标"} for a in apps]
    BATCH_DIR.mkdir(exist_ok=True)
    nm = {a["app_package"]:a["app_name"] for a in apps}
    out = [{"app_name":nm.get(r["app_package"],""), **r} for r in res]
    (BATCH_DIR/f"{PREFIX}_{idx:03d}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return res

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = sqlite3.connect(str(CACHE), check_same_thread=False)
    df = pd.read_sql("SELECT app_package,app_l1,app_l2,risk_type,confidence,reason FROM label_cache", conn)
    src = pd.read_csv(INPUT).drop_duplicates("app_package")
    df = df.merge(src, on="app_package", how="left")
    df["app_name"] = df["app_name"].fillna("")

    safe = df[df["risk_type"] == "无"]
    suspects = []
    seen = set()
    for label, kws, excludes in SUSPECT_RULES:
        if not kws: continue
        pat = "|".join(map(re.escape, kws))
        m = safe["app_name"].str.contains(pat, regex=True, na=False)
        if excludes:
            exp = "|".join(map(re.escape, excludes))
            m &= ~safe["app_name"].str.contains(exp, regex=True, na=False)
        for _, r in safe[m].iterrows():
            if r.app_package in seen: continue
            seen.add(r.app_package)
            suspects.append({
                "app_name": r.app_name, "app_package": r.app_package,
                "orig_l1": r.app_l1, "orig_l2": r.app_l2,
                "_suspect": label,
            })
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
                logging.info("进度 %d/%d  耗时 %.0fs", done, total, time.time()-t0)

    # 统计修改 / 保留
    changed = sum(1 for r in results if r["risk_type"] != "无")
    kept = len(results) - changed
    logging.info("复审完成: 改为高风险 %d, 保留无风险 %d", changed, kept)

    conn.executemany(
        """INSERT OR REPLACE INTO label_cache
           (app_package,app_l1,app_l2,risk_type,confidence,reason,updated_at)
           VALUES (?,?,?,?,?,?,datetime('now'))""",
        [(r["app_package"],r["app_l1"],r["app_l2"],r["risk_type"],
          r["confidence"],r["reason"]+" [复审]") for r in results])
    conn.commit()
    conn.close()
    logging.info("已写回 cache")

if __name__ == "__main__":
    main()
