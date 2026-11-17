# -*- coding: utf-8 -*-
"""
主流 app 标签字典 (手工维护, 与 LLM 打标互补).

背景:
  applist_tag_0522_v2.csv (内部 LLM 打标) + applist_tag_0605_2_clean.csv (外部清洗)
  这两份都聚焦于"长尾仿冒/壳包", 主流 app (微信/支付宝/淘宝/抖音/美团 ...)
  几乎都缺失. 用户 applist 表里 90% 命中是主流 app, 不补这块, 下游特征 left join
  会大面积 NULL.

  本文件手工维护 ~300 个最常装 app 的 (pkg, name, l1, l2, risk_type, quality_tag),
  作为 mainstream 标签源, 合并优先级最高 (mainstream > v2 > 0605).

字段约束:
  l1 取自 v3 APP_L1, l2 取自 v3 L2_MAP, risk_type 取自 v3 RISK_TYPES,
  quality_tag 取自 v3 QUALITY_TAGS. validate_label 会做强校验.

扩展原则:
  - 优先级: 装机量 > 名字模糊度 (越易混淆的越要进 mainstream, 锁定真实标签)
  - 借贷类 / 银行类 / 网约车类 / 投诉平台 这几个反欺诈关键品类要尽量穷举
  - 同一品类同一公司不同子产品也要列 (花呗 vs 借呗 vs 网商贷)
"""
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from run_label_v3 import validate_label

# 字段顺序: (pkg, name, l1, l2, risk_type, quality_tag)
MAINSTREAM = [
    # ============ 社交通讯 ============
    ("com.tencent.mm",                    "微信",          "社交通讯", "即时通讯",   "无", "无"),
    ("com.tencent.mobileqq",              "QQ",            "社交通讯", "即时通讯",   "无", "无"),
    ("com.tencent.wework",                "企业微信",      "办公软件", "邮箱",       "无", "企业员工"),
    ("com.alibaba.android.rimet",         "钉钉",          "办公软件", "邮箱",       "无", "企业员工"),
    ("com.ss.android.lark",               "飞书",          "办公软件", "邮箱",       "无", "企业员工"),
    ("com.sina.weibo",                    "微博",          "社交通讯", "社区论坛",   "无", "无"),
    ("com.zhihu.android",                 "知乎",          "阅读资讯", "新闻",       "无", "无"),
    ("com.douban.frodo",                  "豆瓣",          "社交通讯", "社区论坛",   "无", "无"),
    ("com.tencent.qqlite",                "QQ轻聊版",      "社交通讯", "即时通讯",   "无", "无"),
    ("com.immomo.momo",                   "陌陌",          "社交通讯", "陌生人社交", "无", "无"),
    ("com.p1.mobile.putong",              "探探",          "社交通讯", "陌生人社交", "无", "无"),
    ("com.tantanapp.android",             "探探",          "社交通讯", "陌生人社交", "无", "无"),
    ("com.tencent.tim",                   "TIM",           "办公软件", "邮箱",       "无", "企业员工"),
    ("com.tencent.wemeet.app",            "腾讯会议",      "办公软件", "邮箱",       "无", "企业员工"),
    ("us.zoom.videomeetings",             "Zoom",          "办公软件", "邮箱",       "无", "企业员工"),
    ("com.xingin.xhs",                    "小红书",        "社交通讯", "社区论坛",   "无", "无"),
    ("com.duowan.mobile",                 "YY",            "视频影音", "直播",       "无", "无"),

    # ============ 短视频 / 直播 / 长视频 ============
    ("com.ss.android.ugc.aweme",          "抖音",          "视频影音", "短视频",     "无", "无"),
    ("com.smile.gifmaker",                "快手",          "视频影音", "短视频",     "无", "无"),
    ("com.kuaishou.nebula",               "快手极速版",    "视频影音", "短视频",     "无", "无"),
    ("com.ss.android.ugc.aweme.lite",     "抖音极速版",    "视频影音", "短视频",     "无", "无"),
    ("tv.danmaku.bili",                   "哔哩哔哩",      "视频影音", "长视频",     "无", "无"),
    ("com.qiyi.video",                    "爱奇艺",        "视频影音", "影视点播",   "无", "无"),
    ("com.tencent.qqlive",                "腾讯视频",      "视频影音", "影视点播",   "无", "无"),
    ("com.youku.phone",                   "优酷",          "视频影音", "影视点播",   "无", "无"),
    ("com.hunantv.imgo.activity",         "芒果TV",        "视频影音", "影视点播",   "无", "无"),
    ("com.duowan.kiwi",                   "虎牙直播",      "视频影音", "直播",       "无", "无"),
    ("air.tv.douyu.android",              "斗鱼",          "视频影音", "直播",       "无", "无"),

    # ============ 音乐 ============
    ("com.netease.cloudmusic",            "网易云音乐",    "视频影音", "影视点播",   "无", "无"),
    ("com.tencent.qqmusic",               "QQ音乐",        "视频影音", "影视点播",   "无", "无"),
    ("com.kugou.android",                 "酷狗音乐",      "视频影音", "影视点播",   "无", "无"),
    ("cn.kuwo.player",                    "酷我音乐",      "视频影音", "影视点播",   "无", "无"),
    ("com.ximalaya.ting.android",         "喜马拉雅",      "视频影音", "影视点播",   "无", "无"),
    ("fm.qingting.qtradio",               "蜻蜓FM",        "视频影音", "影视点播",   "无", "无"),

    # ============ 电商购物 ============
    ("com.taobao.taobao",                 "淘宝",          "电商购物", "综合电商",   "无", "无"),
    ("com.tmall.wireless",                "天猫",          "电商购物", "综合电商",   "无", "无"),
    ("com.jingdong.app.mall",             "京东",          "电商购物", "综合电商",   "无", "无"),
    ("com.xunmeng.pinduoduo",             "拼多多",        "电商购物", "综合电商",   "无", "无"),
    ("com.suning.mobile.ebuy",            "苏宁易购",      "电商购物", "综合电商",   "无", "无"),
    ("com.taobao.idlefish",               "闲鱼",          "电商购物", "二手电商",   "无", "无"),
    ("com.wuba.zhuanzhuan",               "转转",          "电商购物", "二手电商",   "无", "无"),
    ("com.kaola",                         "考拉海购",      "电商购物", "海淘特卖",   "无", "无"),
    ("com.netease.kaola",                 "网易考拉",      "电商购物", "海淘特卖",   "无", "无"),
    ("com.dangdang.buy2",                 "当当",          "电商购物", "综合电商",   "无", "无"),
    ("com.vip.sdk.aliopen",               "唯品会",        "电商购物", "海淘特卖",   "无", "无"),
    ("com.achievo.vipshop",               "唯品会",        "电商购物", "海淘特卖",   "无", "无"),
    ("com.taobao.live",                   "淘宝直播",      "电商购物", "综合电商",   "无", "无"),
    ("com.taobao.taolive.uikit",          "淘宝直播",      "电商购物", "综合电商",   "无", "无"),
    ("com.taobao.litetao",                "淘宝特价版",    "电商购物", "综合电商",   "无", "无"),
    ("com.taobao.idlefishair",            "闲鱼",          "电商购物", "二手电商",   "无", "无"),
    ("com.youzan.mobile.zanim",           "有赞",          "电商购物", "综合电商",   "无", "个体工商户"),
    ("com.alibaba.wireless",              "1688",          "电商购物", "综合电商",   "无", "个体工商户"),
    ("com.taobao.qianniu",                "千牛",          "电商购物", "综合电商",   "无", "个体工商户"),
    ("com.jd.jr.cps.app",                 "京东橙分期",    "借贷软件", "消费分期",   "无", "无"),

    # ============ 生活服务 / 外卖 / 本地生活 ============
    ("com.sankuai.meituan",               "美团",          "生活服务", "本地生活",   "无", "无"),
    ("com.sankuai.meituan.takeoutnew",    "美团外卖",      "生活服务", "外卖",       "无", "无"),
    ("me.ele",                            "饿了么",        "生活服务", "外卖",       "无", "无"),
    ("com.baidu.lbs.waimai",              "百度外卖",      "生活服务", "外卖",       "无", "无"),
    ("com.dianping.v1",                   "大众点评",      "生活服务", "本地生活",   "无", "无"),
    ("com.lianjia.beike",                 "贝壳找房",      "生活服务", "本地生活",   "无", "无"),
    ("com.homelink.android",              "链家",          "生活服务", "本地生活",   "无", "无"),
    ("com.anjuke.android.app",            "安居客",        "生活服务", "本地生活",   "无", "无"),
    ("com.ke.app",                        "贝壳找房",      "生活服务", "本地生活",   "无", "无"),

    # ============ 出行交通 ============
    ("com.sdu.didi.psnger",               "滴滴出行",      "出行交通", "网约车",     "无", "无"),
    ("com.sdu.didi.gsui",                 "滴滴司机端",    "出行交通", "网约车",     "无", "网约车司机"),
    ("com.huaxiaozhu.rider",              "花小猪出行",    "出行交通", "网约车",     "无", "无"),
    ("com.cao.cao.passenger",             "曹操出行",      "出行交通", "网约车",     "无", "无"),
    ("cn.com.ttkk.mc.passenger.t3",       "T3出行",        "出行交通", "网约车",     "无", "无"),
    ("com.shouqiev",                      "首汽约车",      "出行交通", "网约车",     "无", "无"),
    ("com.didapinche.booking",            "嘀嗒出行",      "出行交通", "网约车",     "无", "无"),
    ("com.autonavi.minimap",              "高德地图",      "出行交通", "地图导航",   "无", "无"),
    ("com.baidu.BaiduMap",                "百度地图",      "出行交通", "地图导航",   "无", "无"),
    ("com.tencent.map",                   "腾讯地图",      "出行交通", "地图导航",   "无", "无"),
    ("com.MobileTicket",                  "铁路12306",     "出行交通", "火车机票",   "无", "无"),
    ("com.ctrip.train",                   "智行火车票",    "出行交通", "火车机票",   "无", "无"),
    ("ctrip.android.view",                "携程",          "出行交通", "旅游软件",   "无", "无"),
    ("com.taobao.trip",                   "飞猪",          "出行交通", "旅游软件",   "无", "无"),
    ("com.Qunar",                         "去哪儿",        "出行交通", "旅游软件",   "无", "无"),
    ("com.tongcheng.android",             "同程旅行",      "出行交通", "旅游软件",   "无", "无"),
    ("com.umetrip.android.umeairport",    "航旅纵横",      "出行交通", "火车机票",   "无", "优质客群"),
    ("com.amap.bus",                      "高德公交",      "出行交通", "公共交通",   "无", "无"),
    ("com.szzc",                          "神州租车",      "出行交通", "网约车",     "无", "无"),
    ("com.mobike.mobikeapp",              "摩拜单车",      "出行交通", "公共交通",   "无", "无"),
    ("com.hellobike.android",             "哈啰出行",      "出行交通", "网约车",     "无", "无"),
    ("com.lalamove.huolala.client",       "货拉拉",        "生活服务", "家政维修",   "无", "货车司机"),
    ("com.amh.lzd",                       "货拉拉司机",    "生活服务", "家政维修",   "无", "货车司机"),
    ("com.amh.mb.user",                   "货拉拉",        "生活服务", "家政维修",   "无", "货车司机"),
    ("com.amh.driver",                    "货拉拉司机",    "生活服务", "家政维修",   "无", "货车司机"),
    ("com.kuaigou.client",                "快狗打车",      "生活服务", "家政维修",   "无", "货车司机"),
    ("com.ymm.lib",                       "运满满",        "生活服务", "家政维修",   "无", "货车司机"),
    ("com.wlqq",                          "货车帮",        "生活服务", "家政维修",   "无", "货车司机"),

    # ============ 支付 / 银行 ============
    ("com.eg.android.AlipayGphone",       "支付宝",        "金融理财", "支付钱包",   "无", "无"),
    ("com.unionpay",                      "云闪付",        "金融理财", "支付钱包",   "无", "无"),
    ("com.icbc",                          "工商银行",      "银行",     "银行APP",    "无", "无"),
    ("com.icbc.MobileBank",               "中国工商银行",  "银行",     "银行APP",    "无", "无"),
    ("com.chinamworld.bocmbci",           "中国银行",      "银行",     "银行APP",    "无", "无"),
    ("com.chinamworld.main",              "建设银行",      "银行",     "银行APP",    "无", "无"),
    ("com.android.bankabc",               "农业银行",      "银行",     "银行APP",    "无", "无"),
    ("com.bankcomm.Bankcomm",             "交通银行",      "银行",     "银行APP",    "无", "无"),
    ("cmb.pb",                            "招商银行",      "银行",     "银行APP",    "无", "无"),
    ("com.cmbchina.ccd.pluto.cmbActivity","掌上生活",      "银行",     "银行APP",    "无", "无"),
    ("com.psbc.psbcmobilebank",           "邮储银行",      "银行",     "银行APP",    "无", "无"),
    ("com.cmschina",                      "招商证券",      "金融理财", "基金股票",   "无", "无"),
    ("com.cebbank.mobile.cemb",           "光大银行",      "银行",     "银行APP",    "无", "无"),
    ("com.citiccard.mobilebank",          "中信银行",      "银行",     "银行APP",    "无", "无"),
    ("com.pingan.paces.ccms",             "平安口袋银行",  "银行",     "银行APP",    "无", "无"),
    ("cn.com.spdb.mobilebank.per",        "浦发银行",      "银行",     "银行APP",    "无", "无"),
    ("com.cib.bankpadclient",             "兴业银行",      "银行",     "银行APP",    "无", "无"),
    ("cn.com.cmbc.newmbank",              "民生银行",      "银行",     "银行APP",    "无", "无"),
    ("com.huaxia.mb",                     "华夏银行",      "银行",     "银行APP",    "无", "无"),
    ("com.cgbchina.xpt",                  "广发银行",      "银行",     "银行APP",    "无", "无"),

    # ============ 借贷 / 消费金融 (反欺诈核心) ============
    ("com.antgroup.android.fl",           "花呗",          "借贷软件", "消费分期",   "无", "无"),
    ("com.antfortune.wealth",             "蚂蚁财富",      "金融理财", "基金股票",   "无", "无"),
    ("com.mybank.android.phone",          "网商银行",      "借贷软件", "网络小贷",   "无", "无"),
    ("com.jingdong.app.mall.jdfc",        "京东金融",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.jd.jrapp",                      "京东金融",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.qihoo.qiketong",                "360借条",       "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.qihoo360.contents",             "360借条",       "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.qihoo.creditease",              "360借条",       "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.fenqile.fenqile",               "分期乐",        "借贷软件", "消费分期",   "无", "无"),
    ("com.lakala.cardwatch",              "拉卡拉",        "金融理财", "支付钱包",   "无", "个体工商户"),
    ("com.baidu.duer.smartmate",          "度小满",        "借贷软件", "助贷导流",   "无", "无"),
    ("com.baidu.bobomoney",               "度小满金融",    "借贷软件", "助贷导流",   "无", "无"),
    ("cn.tongdun.android.shell",          "同盾科技",      "金融理财", "支付钱包",   "无", "无"),
    ("com.lufax.app",                     "陆金所",        "金融理财", "基金股票",   "无", "无"),
    ("com.jdjr.stock",                    "京东股票",      "金融理财", "基金股票",   "无", "无"),
    ("com.xiaomi.jr",                     "小米金融",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.huawei.wallet",                 "华为钱包",      "金融理财", "支付钱包",   "无", "无"),
    ("com.suning.mobile.epa",             "苏宁金融",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.maiyaole.ymq.app",              "买单侠",        "借贷软件", "消费分期",   "无", "无"),
    ("com.fenqi.shangcheng",              "趣店",          "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.qufenqi.android.app",           "趣分期",        "借贷软件", "消费分期",   "无", "无"),
    ("com.zhongan.papa",                  "众安保险",      "金融理财", "保险理财",   "无", "无"),
    ("com.huanbei.app",                   "还呗",          "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.youxinpai.app",                 "优信二手车",    "出行交通", "网约车",     "无", "无"),
    ("com.up360.parents.android",         "小赢卡贷",      "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.pingan.lendwithyou",            "平安普惠",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.pingan.lifeinsurance",          "平安人寿",      "金融理财", "保险理财",   "无", "无"),
    ("com.pingan.haofang",                "平安好房",      "生活服务", "本地生活",   "无", "无"),
    ("com.pingan.papd",                   "平安好医生",    "健康运动", "健康医疗",   "无", "无"),
    ("com.haier.cabin.duoduo",            "多多金融",      "借贷软件", "小额现金贷", "小额现金贷", "无"),
    ("com.mashang.app",                   "马上消费金融",  "借贷软件", "持牌消金",   "无", "无"),
    ("com.cfcfans.weifang.consumer",      "招联金融",      "借贷软件", "持牌消金",   "无", "无"),
    ("com.cmbc.consumer.app",             "中邮消费金融",  "借贷软件", "持牌消金",   "无", "无"),
    ("com.haier.cabin.haierxiaodai",      "海尔小贷",      "借贷软件", "网络小贷",   "无", "无"),
    ("com.zhongyuan.consumer",            "中原消费金融",  "借贷软件", "持牌消金",   "无", "无"),
    ("com.bjbst.zhongan",                 "中安心贷",      "借贷软件", "助贷导流",   "无", "无"),
    ("com.haodai.haodai",                 "好贷网",        "借贷软件", "贷款超市",   "无", "无"),
    ("com.rong360.app",                   "融360",         "借贷软件", "贷款超市",   "无", "无"),
    ("com.yiqi.lianlian",                 "翼支付",        "金融理财", "支付钱包",   "无", "无"),
    ("com.bestpay.app",                   "翼支付",        "金融理财", "支付钱包",   "无", "无"),

    # ============ 工具 / 系统 ============
    ("com.kingsoft.moffice_pro",          "WPS Office",    "办公软件", "文档处理",   "无", "无"),
    ("cn.wps.moffice_eng",                "WPS Office",    "办公软件", "文档处理",   "无", "无"),
    ("com.tencent.docs",                  "腾讯文档",      "办公软件", "文档处理",   "无", "无"),
    ("com.youdao.note",                   "有道云笔记",    "办公软件", "文档处理",   "无", "无"),
    ("com.evernote",                      "印象笔记",      "办公软件", "文档处理",   "无", "无"),
    ("com.baidu.netdisk",                 "百度网盘",      "工具",     "文件管理",   "无", "无"),
    ("com.quark.browser",                 "夸克",          "工具",     "浏览器",     "无", "无"),
    ("com.UCMobile",                      "UC浏览器",      "工具",     "浏览器",     "无", "无"),
    ("com.tencent.mtt",                   "QQ浏览器",      "工具",     "浏览器",     "无", "无"),
    ("com.android.chrome",                "Chrome",        "工具",     "浏览器",     "无", "无"),
    ("com.microsoft.emmx",                "Edge",          "工具",     "浏览器",     "无", "无"),
    ("com.baidu.searchbox",               "百度",          "工具",     "浏览器",     "无", "无"),
    ("com.tencent.android.qqdownloader",  "应用宝",        "工具",     "系统工具",   "无", "无"),
    ("com.cleanmaster.mguard_cn",         "猎豹清理大师",  "工具",     "安全清理",   "无", "无"),
    ("com.qihoo360.mobilesafe",           "360手机卫士",   "工具",     "安全清理",   "无", "无"),
    ("com.tencent.qqpimsecure",           "腾讯手机管家",  "工具",     "安全清理",   "无", "无"),
    ("com.sohu.inputmethod.sogou",        "搜狗输入法",    "工具",     "输入法",     "无", "无"),
    ("com.iflytek.inputmethod",           "讯飞输入法",    "工具",     "输入法",     "无", "无"),
    ("com.baidu.input",                   "百度输入法",    "工具",     "输入法",     "无", "无"),

    # ============ 阅读 / 资讯 ============
    ("com.tencent.weread",                "微信读书",      "阅读资讯", "小说",       "无", "无"),
    ("com.qidian.QDReader",               "起点读书",      "阅读资讯", "小说",       "无", "无"),
    ("com.dragon.read",                   "番茄小说",      "阅读资讯", "小说",       "无", "无"),
    ("com.kmxs.reader",                   "七猫免费小说",  "阅读资讯", "小说",       "无", "无"),
    ("com.qq.reader",                     "QQ阅读",        "阅读资讯", "小说",       "无", "无"),
    ("com.chaozh.iReaderFree",            "掌阅",          "阅读资讯", "小说",       "无", "无"),
    ("com.ss.android.article.news",       "今日头条",      "阅读资讯", "新闻",       "无", "无"),
    ("com.ss.android.article.lite",       "今日头条极速版","阅读资讯", "新闻",       "无", "无"),
    ("com.netease.newsreader.activity",   "网易新闻",      "阅读资讯", "新闻",       "无", "无"),
    ("com.sina.news",                     "新浪新闻",      "阅读资讯", "新闻",       "无", "无"),
    ("com.tencent.news",                  "腾讯新闻",      "阅读资讯", "新闻",       "无", "无"),
    ("com.kuaibao.kuaishou",              "快手极速版",    "视频影音", "短视频",     "无", "无"),
    ("com.MTReader",                      "免费小说",      "阅读资讯", "小说",       "无", "无"),

    # ============ 教育 ============
    ("com.zybang.parent",                 "作业帮",        "教育学习", "K12",        "无", "学生"),
    ("com.yuanfudao.tutor",               "猿辅导",        "教育学习", "K12",        "无", "学生"),
    ("com.fenbi.android.solar",           "小猿搜题",      "教育学习", "题库",       "无", "学生"),
    ("com.xueersi.lightclass",            "学而思",        "教育学习", "K12",        "无", "学生"),
    ("com.netease.edu.study",             "网易公开课",    "教育学习", "在线课程",   "无", "无"),
    ("com.tencent.edu",                   "腾讯课堂",      "教育学习", "在线课程",   "无", "无"),
    ("com.jiongji.andriod.card",          "百词斩",        "教育学习", "语言学习",   "无", "学生"),
    ("com.youdao.dict",                   "有道词典",      "教育学习", "语言学习",   "无", "无"),
    ("com.eusoft.eshater",                "扇贝单词",      "教育学习", "语言学习",   "无", "学生"),
    ("com.shanbay.words",                 "扇贝单词",      "教育学习", "语言学习",   "无", "学生"),
    ("com.duolingo",                      "多邻国",        "教育学习", "语言学习",   "无", "无"),
    ("com.ks.kaishustory",                "凯叔讲故事",    "教育学习", "K12",        "无", "无"),

    # ============ 招聘 ============
    ("com.hpbr.bosszhipin",               "BOSS直聘",      "生活服务", "本地生活",   "无", "无"),
    ("com.zhaopin.social",                "智联招聘",      "生活服务", "本地生活",   "无", "无"),
    ("com.job.android",                   "前程无忧",      "生活服务", "本地生活",   "无", "无"),
    ("com.liepin.activity",               "猎聘",          "生活服务", "本地生活",   "无", "无"),
    ("com.lagou.lgjobs",                  "拉勾招聘",      "生活服务", "本地生活",   "无", "无"),

    # ============ 政务 / 民生 ============
    ("com.hicorenational.antifraud",      "国家反诈中心",  "政务",     "政务服务",   "无", "无"),
    ("cn.xuexi.android",                  "学习强国",      "政务",     "政务服务",   "无", "公务员事业单位"),
    ("com.gridy.main",                    "个人所得税",    "政务",     "政务服务",   "无", "无"),
    ("com.csii.mobilebank",               "个人所得税",    "政务",     "政务服务",   "无", "无"),
    ("cn.gov.tax.its",                    "个人所得税",    "政务",     "政务服务",   "无", "无"),
    ("com.gov.medical.insurance",         "国家医保服务平台","政务",   "政务服务",   "无", "无"),
    ("com.eshore.ezone",                  "国家政务服务",  "政务",     "政务服务",   "无", "无"),
    ("cn.gov.pbc.dcep",                   "数字人民币",    "金融理财", "支付钱包",   "无", "无"),
    ("com.heytap.health",                 "OPPO运动健康",  "健康运动", "运动健身",   "无", "无"),

    # ============ 健康 / 运动 ============
    ("com.gotokeep.keep",                 "Keep",          "健康运动", "运动健身",   "无", "无"),
    ("com.codoon.gps",                    "咕咚",          "健康运动", "运动健身",   "无", "无"),
    ("com.yuedong.sport",                 "悦动圈",        "健康运动", "运动健身",   "无", "无"),
    ("com.huawei.health",                 "华为运动健康",  "健康运动", "运动健身",   "无", "无"),
    ("com.mi.health",                     "小米运动",      "健康运动", "运动健身",   "无", "无"),
    ("com.greenline.guahao",              "微医",          "健康运动", "健康医疗",   "无", "无"),
    ("com.lingan.seeyou",                 "美柚",          "健康运动", "健康医疗",   "无", "无"),
    ("com.dingxiang.doctor",              "丁香医生",      "健康运动", "健康医疗",   "无", "无"),

    # ============ 摄影 / 美化 ============
    ("com.mt.mtxx.mtxx",                  "美图秀秀",      "摄影美化", "未知",       "无", "无"),
    ("com.meitu.meiyancamera",            "美颜相机",      "摄影美化", "未知",       "无", "无"),
    ("com.commsource.beautyplus",         "BeautyPlus",    "摄影美化", "未知",       "无", "无"),
    ("com.lemon.faceu",                   "轻颜相机",      "摄影美化", "未知",       "无", "无"),

    # ============ 游戏 ============
    ("com.tencent.tmgp.sgame",            "王者荣耀",      "游戏",     "手游",       "无", "无"),
    ("com.tencent.tmgp.pubgmhd",          "和平精英",      "游戏",     "手游",       "无", "无"),
    ("com.miHoYo.GenshinImpact",          "原神",          "游戏",     "手游",       "无", "无"),
    ("com.tencent.tmgp.yqsy",             "光与夜之恋",    "游戏",     "手游",       "无", "无"),
    ("com.netease.onmyoji",               "阴阳师",        "游戏",     "手游",       "无", "无"),
    ("com.netease.mc",                    "我的世界",      "游戏",     "手游",       "无", "无"),
    ("com.tencent.tmgp.wepop",            "和平精英",      "游戏",     "手游",       "无", "无"),
    ("com.tencent.tmgp.cf",               "穿越火线",      "游戏",     "手游",       "无", "无"),
    ("com.qq.gp",                         "QQ游戏",        "游戏",     "手游",       "无", "无"),
    ("com.tencent.qqgame.boyaaddz",       "欢乐斗地主",    "游戏",     "手游",       "无", "无"),
    ("com.tencent.qqgame.hlmahjong",      "腾讯欢乐麻将",  "游戏",     "手游",       "无", "无"),

    # ============ 系统应用 (各厂商) ============
    ("com.android.email",                 "邮件",          "工具",     "邮箱",       "无", "无"),
    ("com.android.calendar",              "日历",          "办公软件", "文档处理",   "无", "无"),
    ("com.android.camera",                "相机",          "摄影美化", "未知",       "无", "无"),
    ("com.android.gallery3d",             "图库",          "摄影美化", "未知",       "无", "无"),
    ("com.android.contacts",              "联系人",        "社交通讯", "即时通讯",   "无", "无"),
    ("com.android.mms",                   "短信",          "社交通讯", "即时通讯",   "无", "无"),
    ("com.android.settings",              "设置",          "工具",     "系统工具",   "无", "无"),
    ("com.android.systemui",              "系统UI",        "工具",     "系统工具",   "无", "无"),
    ("com.android.providers.calendar",    "日历存储",      "工具",     "系统工具",   "无", "无"),
    ("com.android.vending",               "Google Play",   "工具",     "系统工具",   "无", "无"),
    ("com.google.android.gms",            "Google服务",    "工具",     "系统工具",   "无", "无"),
    # 华为
    ("com.huawei.appmarket",              "华为应用市场",  "工具",     "系统工具",   "无", "无"),
    ("com.huawei.hwid",                   "华为帐号",      "工具",     "系统工具",   "无", "无"),
    ("com.huawei.systemmanager",          "华为手机管家",  "工具",     "安全清理",   "无", "无"),
    ("com.huawei.android.launcher",       "华为桌面",      "工具",     "系统工具",   "无", "无"),
    ("com.huawei.browser",                "华为浏览器",    "工具",     "浏览器",     "无", "无"),
    # 小米
    ("com.miui.home",                     "小米桌面",      "工具",     "系统工具",   "无", "无"),
    ("com.xiaomi.market",                 "小米应用商店",  "工具",     "系统工具",   "无", "无"),
    ("com.miui.cleanmaster",              "小米手机管家",  "工具",     "安全清理",   "无", "无"),
    ("com.android.browser.xiaomi",        "小米浏览器",    "工具",     "浏览器",     "无", "无"),
    ("com.mipay.wallet",                  "小米钱包",      "金融理财", "支付钱包",   "无", "无"),
    # OPPO
    ("com.oppo.market",                   "OPPO软件商店",  "工具",     "系统工具",   "无", "无"),
    ("com.oppo.launcher",                 "OPPO桌面",      "工具",     "系统工具",   "无", "无"),
    ("com.coloros.safecenter",            "OPPO安全中心",  "工具",     "安全清理",   "无", "无"),
    ("com.heytap.market",                 "OPPO软件商店",  "工具",     "系统工具",   "无", "无"),
    # vivo
    ("com.bbk.appstore",                  "vivo应用商店",  "工具",     "系统工具",   "无", "无"),
    ("com.vivo.appstore",                 "vivo应用商店",  "工具",     "系统工具",   "无", "无"),
    ("com.bbk.launcher2",                 "vivo桌面",      "工具",     "系统工具",   "无", "无"),
    ("com.vivo.safecenter",               "vivo手机管家",  "工具",     "安全清理",   "无", "无"),
    ("com.vivo.browser",                  "vivo浏览器",    "工具",     "浏览器",     "无", "无"),
    ("com.vivo.wallet",                   "vivo钱包",      "金融理财", "支付钱包",   "无", "无"),
    # 三星
    ("com.samsung.android.app.notes",     "三星笔记",      "办公软件", "文档处理",   "无", "无"),
    ("com.sec.android.app.launcher",      "三星桌面",      "工具",     "系统工具",   "无", "无"),

    # ============ 邮箱 ============
    ("com.tencent.androidqqmail",         "QQ邮箱",        "办公软件", "邮箱",       "无", "无"),
    ("com.netease.mail",                  "网易邮箱大师",  "办公软件", "邮箱",       "无", "无"),
    ("com.microsoft.office.outlook",      "Outlook",       "办公软件", "邮箱",       "无", "企业员工"),

    # ============ 投诉 / 维权 ============
    ("com.heimao.tousu",                  "黑猫投诉",      "生活服务", "投诉维权",   "投诉平台", "无"),

    # ============ 基金 / 证券 (高活跃信号) ============
    ("com.eastmoney.android.berlin",      "东方财富",      "金融理财", "基金股票",   "无", "优质客群"),
    ("com.hexin.plat.android",            "同花顺",        "金融理财", "基金股票",   "无", "优质客群"),
    ("com.snowball.android",              "雪球",          "金融理财", "基金股票",   "无", "优质客群"),
    ("com.htsec.app",                     "海通证券",      "金融理财", "基金股票",   "无", "优质客群"),

    # ============ 高风险 - 区块链 / 虚拟币 ============
    ("com.okinc.okex.gp",                 "欧易OKX",       "区块链加密", "交易所",   "区块链", "无"),
    ("com.binance.dev",                   "币安",          "区块链加密", "交易所",   "区块链", "无"),
    ("com.huobiy.android",                "火币",          "区块链加密", "交易所",   "区块链", "无"),
    ("com.imtoken.app",                   "imToken",       "区块链加密", "交易所",   "区块链", "无"),
]


def build_df() -> pd.DataFrame:
    """转成与 v3 合并表同 schema 的 DataFrame, 并 validate."""
    records = []
    for pkg, name, l1, l2, risk, qual in MAINSTREAM:
        rec = {
            "app_package": pkg,
            "app_name":    name,
            "app_l1":      l1,
            "app_l2":      l2,
            "risk_type":   risk,
            "quality_tag": qual,
            "confidence":  0.99,           # 主流手工标定, 置信度最高
            "reason":      "mainstream手工标定",
            "source":      "mainstream",
        }
        validate_label(rec)
        records.append(rec)
    df = pd.DataFrame(records)
    # 同 pkg 多个 entry 时 keep first (人工排序代表了优先选择)
    df = df.drop_duplicates("app_package", keep="first")
    return df


if __name__ == "__main__":
    df = build_df()
    out = Path(__file__).parent / "applist_tag_mainstream.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[OUT] {out.name}: {len(df)} 主流 app")
    print("\nL1 分布:")
    print(df["app_l1"].value_counts().to_string())
    print("\n非'无' risk_type 分布:")
    print(df[df["risk_type"] != "无"]["risk_type"].value_counts().to_string())
    print("\n非'无' quality_tag 分布:")
    print(df[df["quality_tag"] != "无"]["quality_tag"].value_counts().to_string())
