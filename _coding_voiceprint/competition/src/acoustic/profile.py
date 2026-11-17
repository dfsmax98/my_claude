# -*- coding: utf-8 -*-
"""
画像线(声学特征)接口预留 —— 本期不实现, 只定义接口与约束。

复用 extract 已提取的客户声道 wav/emb, 避免二次预处理。
性别/年龄/情绪作为叠加信号, 不单独定案(沿用"声学+文本+业务"三重验证)。

⚠ 接入时第一步: 验证模型调用不经过 modelscope.pipelines(Py3.14 段错误139)。
  - 情绪: emotion2vec 走 funasr 生态可行
  - 性别/年龄: 需找 funasr.AutoModel 或独立 pip 包路径, 否则不接
"""


def profile(customer_wav):
    """对客户声道 wav 提取画像属性。本期占位。

    返回(设计): {"gender": "male|female|unknown",
                "age_band": "青年|中年|老年|unknown",
                "emotion": "平静|激动|愤怒|..."}
    """
    raise NotImplementedError(
        "画像线本期未实现(见方案 §八)。接入前须先做 pipelines 段错误冒烟测试。")
