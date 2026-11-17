# -*- coding: utf-8 -*-
"""
对 cache 中 app_l1=未知 / risk_type=未知 的 app 重新打标。
策略变更:
- 禁止返回"未知"，必须给出最可能的判断
- emoji+乱码名+随机包名 强制 → 伪冒仿冒/山寨低质
- 简短中文名结合行业惯用词 → 低 confidence 推断
- 同时重打 reason='LLM调用失败' 的残留
"""
import os, re, sys, json, time, sqlite3, logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic, pandas as pd

BASE = Path(r"d:\my_claude\反欺诈")
BATCH_DIR = BASE / "tagging_tmp"
CACHE_DB  = BASE / "applist_label_cache_applist_tag_0522_v2.sqlite"
INPUT_CSV = BASE / "applist_tag_0522.csv"

MODEL = "claude-opus-4-6"
BATCH_SIZE = 25
MAX_WORKERS = 5
MAX_RETRIES = 3
OUTPUT_PREFIX = "relabel_unknown"

APP_L1 = [
    "系统应用","办公软件","借贷软件","金融理财","银行","政务",
    "社交通讯","电商购物","生活服务","出行交通","视频影音",
    "阅读资讯","游戏","教育学习","摄影美化","健康运动","旅游",
    "工具","区块链加密","色情成人","棋牌赌博","其他","未知",
]
L2_MAP = {
    "系统应用":["系统组件","桌面启动","厂商应用"],
    "办公软件":["文档处理","协作OA","邮箱","会议视频","翻译"],
    "借贷软件":["小额现金贷","银行信贷","消费分期","信用卡管理","助贷导流","贷款超市"],
    "金融理财":["基金股票","保险理财","记账","外汇","支付钱包"],
    "银行":["银行APP"],"政务":["政务服务"],
    "社交通讯":["即时通讯","陌生人社交","出海社交","匿名IM","社区论坛","婚恋"],
    "电商购物":["综合电商","垂直电商","二手电商","海淘特卖","拼团"],
    "生活服务":["外卖","本地生活","招聘","家政维修","投诉维权"],
    "出行交通":["网约车","公共交通","地图导航","火车机票"],
    "视频影音":["短视频","长视频","直播","影视点播","音乐音频"],
    "阅读资讯":["新闻","小说","漫画"],
    "游戏":["手游","模拟器"],
    "教育学习":["在线课程","K12","语言学习","题库"],
    "摄影美化":["拍照修图"],"健康运动":["运动健身","健康医疗"],"旅游":["旅游软件"],
    "工具":["系统工具","安全清理","文件管理","输入法","浏览器","网络工具","改机工具","多开分身","接码工具"],
    "区块链加密":["交易所","钱包","挖矿"],
    "色情成人":["色情视频","色情直播","约炮社交"],
    "棋牌赌博":["真钱棋牌","体育博彩","彩票"],
    "其他":["其他"],"未知":["未知"],
}
RISK_TYPES = [
    "无","小额现金贷","反催收","征信修复","投诉平台","赌博","区块链","色情",
    "翻墙VPN","山寨低质","伪冒仿冒","改机软件","黑灰产工具","网赚刷量",
    "隐私窃取","其他高风险","未知",
]
TAXONOMY = (
    "## 一级标签 app_l1:\n" + " / ".join(APP_L1) + "\n\n"
    + "## 二级标签 app_l2:\n"
    + "\n".join(f"- {l1}: {' / '.join(l2s)}" for l1, l2s in L2_MAP.items())
    + "\n\n## 风险类型 risk_type:\n" + " / ".join(RISK_TYPES)
)

SYSTEM_PROMPT = f"""你是反欺诈分析师，本次任务是对**之前被标记为"未知"的 app 进行二次激进打标**。

{TAXONOMY}

## 重要规则（本轮严格执行）
**禁止返回 app_l1="未知" 或 risk_type="未知"**，必须给出最可能的判断。

### 马甲包/伪冒识别（强制规则）
满足以下任一特征 → **app_l1=其他, app_l2=其他, risk_type=伪冒仿冒, confidence=0.6**:
- 名称含 emoji 表情符（🍉🌳❤️🥝 等）+ 乱码字符（Φ Ρ Ι ※ ∞ 等特殊符号）
- 名称为单/两字符 + 包名为长随机字母数字（如 `com.xxxxxx.yyyyyyy`）
- 名称含拼音乱混（如 "kaixin联_ing"）+ 包名随机

### 山寨低质识别
- 名称简短模糊（"蓝莓"/"福蓓"/"知意" 等无品牌信息）+ 包名 com.xxx.xxx 随机字符
  → **app_l1=其他, app_l2=其他, risk_type=山寨低质, confidence=0.5**
- uni.UNI* 包名（uni-app 套壳）+ 无明确语义中文名
  → **app_l1=其他, app_l2=其他, risk_type=山寨低质, confidence=0.5**

### 推理规则
- 中文名有词义就推断行业（"星空赚动"→网赚, "惠民花"→现金贷, "旋风加速器"→VPN）
- 包名词根有信号（vpn/loan/cash/game/news/shop/mall/sex/porn/coin/wallet 等）
- 英文短名（KEY, TT, Spv）+ 完全随机包名 → 大概率山寨低质，confidence=0.4

### 持牌借贷/正规品牌
- 中文名疑似已知品牌但拿不准 → app_l1=借贷软件/金融理财/etc, risk_type=无, confidence=0.4

## 输出
严格 JSON 数组，不要 markdown 包裹:
[{{"app_package":"原样回填","app_l1":"...","app_l2":"...","risk_type":"...","confidence":0.0-1.0,"reason":"20字内"}}]

**再次强调：本轮绝不允许返回"未知"，宁可低 confidence 也要给标签。**
"""

def extract_json_array(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if m: text = m.group(1)
    s, e = text.find("["), text.rfind("]")
    if s == -1 or e == -1: raise ValueError(text[:200])
    return json.loads(text[s:e+1])

def label_batch(client, apps, batch_idx):
    user_msg = (
        f"对以下 {len(apps)} 个**之前被判为未知**的 app 重新打标，本轮禁止返回未知。\n\n"
        + json.dumps(apps, ensure_ascii=False)
    )
    results = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=4096,
                system=[{"type":"text","text":SYSTEM_PROMPT,"cache_control":{"type":"ephemeral"}}],
                messages=[{"role":"user","content":user_msg}],
            )
            text = next(b.text for b in resp.content if b.type=="text")
            results = extract_json_array(text)
            returned = {r["app_package"] for r in results}
            for a in apps:
                if a["app_package"] not in returned:
                    results.append({"app_package":a["app_package"],
                        "app_l1":"其他","app_l2":"其他","risk_type":"山寨低质",
                        "confidence":0.3,"reason":"LLM未返回兜底"})
            break
        except Exception as e:
            logging.warning("attempt %d failed: %s", attempt+1, e)
            time.sleep(2**attempt)
    if results is None:
        results = [{"app_package":a["app_package"],"app_l1":"其他","app_l2":"其他",
            "risk_type":"山寨低质","confidence":0.2,"reason":"LLM调用失败兜底"} for a in apps]

    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    name_map = {a["app_package"]: a.get("app_name","") for a in apps}
    enriched = [{"app_name":name_map.get(r["app_package"],""), **r} for r in results]
    (BATCH_DIR / f"{OUTPUT_PREFIX}_{batch_idx:03d}.json").write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
    return results

def save_cache(conn, results):
    conn.executemany(
        """INSERT OR REPLACE INTO label_cache
           (app_package,app_l1,app_l2,risk_type,confidence,reason,updated_at)
           VALUES (?,?,?,?,?,?,datetime('now'))""",
        [(r["app_package"],r["app_l1"],r["app_l2"],r["risk_type"],
          r["confidence"],r["reason"]) for r in results])
    conn.commit()

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    conn = sqlite3.connect(str(CACHE_DB), check_same_thread=False)

    # 找出所有需要重打的 app_package
    targets = conn.execute(
        "SELECT app_package FROM label_cache "
        "WHERE app_l1='未知' OR risk_type='未知' OR reason IN ('LLM调用失败','LLM未返回')"
    ).fetchall()
    target_pkgs = {r[0] for r in targets}
    logging.info("cache 中标记为未知/失败的包: %d", len(target_pkgs))

    # 取原始 CSV 拿 app_name
    df = pd.read_csv(INPUT_CSV).drop_duplicates("app_package")
    apps = (df[df["app_package"].isin(target_pkgs)]
            [["app_name","app_package"]].fillna("").to_dict("records"))
    # 只保留有 app_name 的（空名实在没信息）
    apps = [a for a in apps if a["app_name"].strip()]
    logging.info("有 app_name 可重打: %d", len(apps))

    if not apps:
        logging.info("无可重打项")
        return

    client = anthropic.Anthropic()
    t0 = time.time()
    batches = [apps[i:i+BATCH_SIZE] for i in range(0, len(apps), BATCH_SIZE)]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(label_batch, client, b, i+1): i+1 for i, b in enumerate(batches)}
        done, total = 0, len(futures)
        for f in as_completed(futures):
            res = f.result()
            save_cache(conn, res)
            done += 1
            if done % 5 == 0 or done == total:
                elapsed = time.time()-t0
                eta = elapsed/done*(total-done)
                logging.info("进度 %d/%d (%.0f%%) 已用 %.0fs ETA %.0fs",
                    done, total, done/total*100, elapsed, eta)
    logging.info("完成，总耗时 %.0fs", time.time()-t0)
    conn.close()

if __name__ == "__main__":
    main()
