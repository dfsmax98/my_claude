# -*- coding: utf-8 -*-
"""
实时核验: 新录音进来 -> 提客户声纹 -> ①1:1 判本人 ②1:N 查黑产。

设计成 VoiceprintVerifier 类(模型 + 库预加载), 供常驻服务复用, 规避每次
重载模型(~60s)。命令行入口用于单次测试/回归。

决策三段(不靠单一硬阈值):
  >= THR_STRICT(0.751)     判同/命中
  [THR_EER(0.634), 0.751)  存疑(需文本/业务证据)
  < THR_EER                判异/未命中
下界用同人5分位 0.634(标定得出), 上界用异人95分位/保守阈值 0.751。

用法(单次测试):
  MODELSCOPE_CACHE=./ms_cache PYTHONIOENCODING=utf-8 \
    python pipelines/verify_realtime.py <录音> [--cust-no 13x] \
      [--customer-db data/customer_db.pkl] [--black-db data/black_db.pkl]
"""
import os, sys, argparse, io, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import numpy as np
from common import vpdb, embedding
from common.extract import extract_customer_embedding, NotDualTrackError

THR_STRICT = 0.751   # 保守判同/命中(异人95分位)
THR_EER = 0.634      # 存疑下界(同人5分位)


def _band(score):
    if score >= THR_STRICT:
        return "命中"
    if score >= THR_EER:
        return "存疑"
    return "未命中"


class VoiceprintVerifier:
    """常驻核验器: 预加载模型 + 声纹库。"""

    def __init__(self, customer_db, black_db):
        self.cust_db = vpdb.load_db(customer_db)
        self.black_db = vpdb.load_db(black_db)
        embedding.get_model()   # 预热, 避免首次请求 60s

    def _customer_primary_embs(self, cust_no):
        """取某客户号 primary_cluster 的模板 embedding 列表。"""
        ident = self.cust_db.get("identities", {}).get(cust_no)
        if not ident or ident.get("primary_cluster") in (None, "undecided"):
            return None
        pids = set(ident["primary_cluster"])
        return [r["emb"] for r in self.cust_db["records"] if r["id"] in pids]

    def verify(self, audio_path, cust_no=None):
        """核验一通录音。返回结果 dict。"""
        try:
            q, meta = extract_customer_embedding(audio_path, return_meta=True)
        except NotDualTrackError as e:
            return {"error": "非双轨", "detail": str(e)}
        if q is None:
            return {"error": "提取失败/质检reject", "meta": meta}

        out = {"meta": meta, "cust_no": cust_no}

        # 线1: 1:1 本人核验
        if cust_no:
            primary = self._customer_primary_embs(cust_no)
            if primary is None:
                out["self_check"] = {"status": "证据不足",
                                     "reason": "该客户号无主簇(单通/undecided)"}
            else:
                s1 = max(float(np.dot(q, e)) for e in primary)
                band = _band(s1)
                out["self_check"] = {
                    "status": {"命中": "本人", "存疑": "存疑", "未命中": "非本人告警"}[band],
                    "score": round(s1, 3), "band": band}
                # 命中 aux 而非 primary -> 疑似代接
                ident = self.cust_db["identities"][cust_no]
                aux_ids = {i for grp in ident.get("aux_clusters", []) for i in grp}
                if aux_ids:
                    aux_embs = [r["emb"] for r in self.cust_db["records"] if r["id"] in aux_ids]
                    s_aux = max((float(np.dot(q, e)) for e in aux_embs), default=0.0)
                    if s_aux >= THR_STRICT and s_aux > s1:
                        out["self_check"]["note"] = f"疑似代接(命中aux {s_aux:.3f}>主簇)"

        # 线2: 1:N 黑产检索
        hits = vpdb.search_by_identity(q, self.black_db, id_key="actor_id", topk=5)
        black = [{"actor": a, "score": round(s, 3), "band": _band(s), "rec": rid}
                 for a, s, rid in hits]
        out["black_search"] = {
            "hit": bool(black and black[0]["band"] == "命中"),
            "topk": black}
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--cust-no", default=None)
    ap.add_argument(
        "--customer-db",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed", "customer_db.pkl"
        ),
    )
    ap.add_argument(
        "--black-db",
        default=os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "processed", "black_db.pkl"
        ),
    )
    args = ap.parse_args()

    v = VoiceprintVerifier(args.customer_db, args.black_db)
    res = v.verify(args.audio, args.cust_no)
    print(json.dumps(res, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
