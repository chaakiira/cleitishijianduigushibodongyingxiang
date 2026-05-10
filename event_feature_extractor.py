"""
事件研究 - 数据增强与特征提取
输入: 事件整理总表（增强版）.xlsx
输出: 事件增强_含特征.xlsx
"""
import pandas as pd
import numpy as np
import re
from pathlib import Path

# ============================================================
# 1. 公司名 → A股代码映射表（基于你事件表中出现的公司手工整理）
# ============================================================
COMPANY_CODE_MAP = {
    # 固态/锂电
    "国轩高科": "002074", "海目星": "688559", "赣锋锂业": "002460",
    "孚能科技": "688567", "宁德时代": "300750", "比亚迪": "002594",
    "科达利": "002850", "天赐材料": "002709", "新宙邦": "300037",
    
    # 机器人/工业母机
    "绿的谐波": "688017", "双环传动": "002472", "埃斯顿": "002747",
    "敏芯股份": "688286", "汇川技术": "300124", "华中数控": "300161",
    "科德数控": "688305", "奥普特": "688686",
    
    # 军工/航天
    "通宇通讯": "002792", "天宜新材": "301036", "中天火箭": "003009",
    "电科蓝天": "002485", "航天发展": "000547", "航天动力": "600343",
    "航天长峰": "600855", "四川九洲": "000801", "中航高科": "600862",
    
    # 光模块/光通信
    "中际旭创": "300308", "新易盛": "300502", "中瓷电子": "003031",
    "华工科技": "000988", "天孚通信": "300394", "长飞光纤": "601869",
    "炬光科技": "688167", "三环集团": "300408", "亨通光电": "600487",
    "中天科技": "600522", "通鼎互联": "002491", "汇源通信": "000586",
    "通光线缆": "300265", "中兴通讯": "000063",
    
    # 船舶
    "中国船舶": "600150", "中船防务": "600685", "中船科技": "600072",
    
    # 钛白粉/化工材料
    "龙佰集团": "002601", "中核钛白": "002145", "金浦钛业": "000545",
    "中国巨石": "600176", "国际复材": "301526", "宏和科技": "603256",
    
    # 半导体
    "恒邦股份": "002237", "江丰电子": "300666", "阿石创": "300706",
    "海光信息": "688041", "寒武纪": "688256", "北方华创": "002371",
    "中芯国际": "688981", "华大九天": "301269",
    
    # 光伏
    "迈为股份": "300751", "捷佳伟创": "300724", "金辰股份": "603396",
    "帝科股份": "300842", "苏州固锝": "002079", "聚和股份": "688503",
    "隆基绿能": "601012",
    
    # LED/显示
    "三安光电": "600703", "兆驰股份": "002429", "瑞丰光电": "300241",
    "聚飞光电": "300303",
    
    # 第三代半导体
    "天岳先进": "688234", "东尼电子": "603595", "露笑科技": "002617",
    
    # 油服
    "中海油服": "601808", "石化油服": "600871", "杰瑞股份": "002353",
    "通源石油": "300164",
    
    # 跨境电商/物流
    "华贸物流": "603128", "中外运": "601598", "焦点科技": "002315",
    "吉宏股份": "002803",
    
    # 一体化压铸
    "文灿股份": "603348", "广东鸿图": "002101", "拓普集团": "601689",
    "旭升集团": "603305",
    
    # 稀土
    "中稀有色": "600259",  # 广晟有色曾用名相关
    "中国稀土": "000831", "盛和资源": "600392", "北方稀土": "600111",
    
    # 钠电
    "圣阳股份": "002580", "宗申动力": "001696", "华塑科技": "301157",
    
    # 低空经济
    "中无人机": "688297", "万丰奥威": "002085", "深城交": "301091",
    "莱斯信息": "688631",
    
    # AI/算力
    "浪潮信息": "000977", "中科曙光": "603019", "科大讯飞": "002230",
    "鸿合科技": "002955", "优博讯": "300531", "三六零": "601360",
    "昆仑万维": "300418", "拓尔思": "300229", "卫士通": "002268",
    "上海钢联": "300226",
    
    # 券商
    "中信证券": "600030", "东方财富": "300059", "华泰证券": "601688",
    
    # 基建环保
    "中国交建": "601800", "碧水源": "300070", "高能环境": "603588",
    "伟明环保": "603568",
    
    # 医药CXO
    "药明康德": "603259", "泰格医药": "300347",
    
    # 家电/消费电子
    "海尔智家": "600690", "立讯精密": "002475",
    
    # 互联网/传媒
    "人民网": "603000", "每日互动": "300766",
    
    # 农业
    "一拖股份": "601038", "隆平高科": "000998", "大北农": "002385",
    
    # 生物制造
    "凯赛生物": "688065",
    
    # 电力/能源
    "国能日新": "905678",  # 此为688900相关，需核实
    "远光软件": "002063", "三峡能源": "600905",
    
    # 理想汽车（港股，无A股代码，标记为港股）
    "理想汽车": "02015.HK",
}

# ============================================================
# 2. 行业关键词映射（申万一级近似）
# ============================================================
SECTOR_KEYWORDS = {
    "电子": ["芯片", "半导体", "面板", "LED", "存储", "晶圆", "光刻", "PCB", "碳化硅", "砷"],
    "计算机": ["AI", "人工智能", "大模型", "算力", "云计算", "软件", "数据中心", 
             "网络安全", "信创", "CPU", "智能体"],
    "通信": ["5G", "6G", "光纤", "基站", "卫星", "通信", "光模块", "光通信"],
    "汽车": ["新能源车", "电动车", "自动驾驶", "车企", "整车", "汽车"],
    "电气设备": ["光伏", "风电", "储能", "锂电", "电池", "充电桩", "新能源", "HJT", "钠电", "钠离子"],
    "医药生物": ["医药", "疫苗", "创新药", "医疗器械", "生物", "制药", "CXO", "细胞治疗"],
    "食品饮料": ["白酒", "乳制品", "食品", "饮料", "可可"],
    "银行": ["银行", "信贷", "LPR"],
    "非银金融": ["券商", "保险", "证券", "大金融"],
    "房地产": ["房地产", "地产", "楼市", "住房"],
    "有色金属": ["黄金", "铜", "铝", "锂", "稀土", "钴", "小金属", "镓锗", "锑", "钛白粉"],
    "化工": ["化工", "石化", "新材料"],
    "国防军工": ["军工", "国防", "航天", "导弹", "战斗机", "军舰", "高超音速"],
    "农林牧渔": ["农业", "养殖", "水产", "种业", "农机"],
    "公用事业": ["电力", "核电", "电网"],
    "交通运输": ["航运", "航空", "铁路", "物流", "港口", "跨境"],
    "传媒": ["游戏", "影视", "互联网平台"],
    "机械设备": ["机器人", "工程机械", "工业母机", "一体化压铸"],
    "采掘": ["煤炭", "石油", "天然气", "油气", "油服"],
    "建筑装饰": ["基建", "水利", "建筑"],
    "低空经济": ["低空", "飞行汽车", "无人机"],
}

# ============================================================
# 3. 核心处理类
# ============================================================
class EventEnhancer:
    def __init__(self, company_map, sector_keywords):
        self.company_map = company_map
        self.sector_keywords = sector_keywords
        # 按名称长度降序，优先匹配长名称
        self.sorted_names = sorted(company_map.keys(), key=len, reverse=True)
    
    def clean_date(self, date_val):
        """清洗日期字段，处理多种格式"""
        if pd.isna(date_val):
            return None
        
        s = str(date_val).strip()
        
        # 已是datetime
        if isinstance(date_val, pd.Timestamp):
            return date_val.normalize()
        
        # 处理 "2025 年 10 月 23 日" 这种格式
        match = re.search(r'(\d{4})\D+(\d{1,2})\D+(\d{1,2})', s)
        if match:
            y, m, d = match.groups()
            try:
                return pd.Timestamp(f"{y}-{int(m):02d}-{int(d):02d}")
            except:
                return None
        
        # 标准格式
        try:
            return pd.to_datetime(s).normalize()
        except:
            return None
    
    def match_tickers(self, text):
        """匹配股票代码"""
        if pd.isna(text):
            return []
        text = str(text)
        matched = []
        for name in self.sorted_names:
            if name in text:
                code = self.company_map[name]
                if code not in matched:
                    matched.append(code)
        return matched
    
    def match_company_names(self, text):
        """返回匹配到的公司名（用于验证）"""
        if pd.isna(text):
            return []
        text = str(text)
        matched = []
        for name in self.sorted_names:
            if name in text:
                if name not in matched:
                    matched.append(name)
        return matched
    
    def match_sectors(self, event_name, impact_target, description):
        """匹配行业"""
        text = " ".join([str(x) for x in [event_name, impact_target, description] if pd.notna(x)])
        matched = []
        for sector, keywords in self.sector_keywords.items():
            for kw in keywords:
                if kw in text:
                    if sector not in matched:
                        matched.append(sector)
                    break
        return matched
    
    def assess_date_precision(self, original_date):
        """评估日期精度"""
        if pd.isna(original_date):
            return "missing"
        try:
            d = pd.to_datetime(original_date)
            if d.day == 1:
                return "approximate"  # 月初近似
            return "precise"
        except:
            return "unknown"


# ============================================================
# 4. 特征工程
# ============================================================
def generate_features(df):
    """生成量化特征"""
    df = df.copy()
    
    # 类型编码
    type_map = {"宏观/地缘": 0, "行业/技术": 1, "政策": 2}
    df["type_code"] = df["类型"].map(type_map)
    
    # 强度编码
    intensity_map = {"高": 3, "中": 2, "低": 1}
    df["intensity_code"] = df["影响强度"].map(intensity_map).fillna(0).astype(int)
    
    # 方向编码
    direction_map = {"正面": 1, "负面": -1, "双向": 0}
    df["direction_code"] = df["影响方向"].map(direction_map).fillna(0).astype(int)
    
    # 窗口长度
    df["window_length"] = df["窗口结束(相对天数)"] - df["窗口开始(相对天数)"] + 1
    
    # 涉及标的数量
    df["target_count"] = df["matched_tickers"].apply(len)
    
    # 涉及行业数量
    df["sector_count"] = df["matched_sectors"].apply(len)
    
    # 是否首次出现同类同行业事件
    df_sorted = df.sort_values("event_date_clean").reset_index()
    seen = {}
    first_occur = []
    for _, row in df_sorted.iterrows():
        key = f"{row['类型']}|{','.join(sorted(row['matched_sectors']))}"
        if key not in seen:
            seen[key] = True
            first_occur.append(1)
        else:
            first_occur.append(0)
    df_sorted["is_first_occurrence"] = first_occur
    df = df_sorted.sort_values("index").drop(columns=["index"]).reset_index(drop=True)
    
    # 日期特征
    df["year"] = df["event_date_clean"].dt.year
    df["month"] = df["event_date_clean"].dt.month
    df["day_of_week"] = df["event_date_clean"].dt.dayofweek
    df["quarter"] = df["event_date_clean"].dt.quarter
    
    # 事件ID
    df["event_id"] = [f"EVT_{i:03d}" for i in range(len(df))]
    
    # 列表转字符串用于Excel存储
    df["matched_tickers_str"] = df["matched_tickers"].apply(lambda x: ";".join(x))
    df["matched_sectors_str"] = df["matched_sectors"].apply(lambda x: ";".join(x))
    df["matched_names_str"] = df["matched_names"].apply(lambda x: ";".join(x))
    
    return df


# ============================================================
# 5. 主流程
# ============================================================
def main():
    INPUT = "事件整理总表（增强版）.xlsx"
    OUTPUT = "事件增强_含特征.xlsx"
    
    # 读入
    df = pd.read_excel(INPUT, sheet_name="事件总表（增强版）")
    
    # 统一列名（处理换行符）
    df.columns = [c.replace("\n", "") for c in df.columns]
    print(f"读入 {len(df)} 条事件")
    print(f"列名: {list(df.columns)}")
    
    # 初始化增强器
    enhancer = EventEnhancer(COMPANY_CODE_MAP, SECTOR_KEYWORDS)
    
    # 日期清洗
    df["event_date_clean"] = df["发生日期"].apply(enhancer.clean_date)
    df["date_precision"] = df["发生日期"].apply(enhancer.assess_date_precision)
    
    # 公司/股票代码匹配
    df["matched_names"] = df["影响公司/行业"].apply(enhancer.match_company_names)
    df["matched_tickers"] = df["影响公司/行业"].apply(enhancer.match_tickers)
    
    # 行业匹配
    df["matched_sectors"] = df.apply(
        lambda row: enhancer.match_sectors(
            row["事件名称"], row["影响公司/行业"], row.get("影响描述", "")
        ), axis=1
    )
    
    # 特征工程
    df = generate_features(df)
    
    # 整理输出列顺序
    output_cols = [
        "event_id", "事件名称", "类型", "type_code",
        "发生日期", "event_date_clean", "date_precision",
        "窗口开始(相对天数)", "窗口结束(相对天数)", "window_length",
        "影响强度", "intensity_code",
        "影响方向", "direction_code",
        "影响公司/行业", "matched_names_str", "matched_tickers_str", "target_count",
        "matched_sectors_str", "sector_count",
        "is_first_occurrence",
        "year", "month", "quarter", "day_of_week",
        "影响描述", "AR/CAR量化提示", "数据来源"
    ]
    output_cols = [c for c in output_cols if c in df.columns]
    df_out = df[output_cols].copy()
    
    # 生成未匹配清单（需人工补充的）
    unmatched = df[df["target_count"] == 0][
        ["event_id", "事件名称", "影响公司/行业", "matched_sectors_str"]
    ].copy()
    
    # 输出统计摘要
    summary = pd.DataFrame({
        "指标": [
            "事件总数",
            "日期精确", "日期近似（月初）", "日期缺失",
            "已匹配股票代码", "未匹配股票代码",
            "宏观/地缘", "行业/技术", "政策",
            "高强度", "中强度", "低强度",
            "正面", "负面", "双向",
            "首次发生事件", "重复类型事件",
            "平均涉及标的数", "平均涉及行业数",
        ],
        "数值": [
            len(df),
            (df["date_precision"] == "precise").sum(),
            (df["date_precision"] == "approximate").sum(),
            (df["date_precision"] == "missing").sum(),
            (df["target_count"] > 0).sum(),
            (df["target_count"] == 0).sum(),
            (df["类型"] == "宏观/地缘").sum(),
            (df["类型"] == "行业/技术").sum(),
            (df["类型"] == "政策").sum(),
            (df["影响强度"] == "高").sum(),
            (df["影响强度"] == "中").sum(),
            (df["影响强度"] == "低").sum(),
            (df["影响方向"] == "正面").sum(),
            (df["影响方向"] == "负面").sum(),
            (df["影响方向"] == "双向").sum(),
            df["is_first_occurrence"].sum(),
            (df["is_first_occurrence"] == 0).sum(),
            round(df["target_count"].mean(), 2),
            round(df["sector_count"].mean(), 2),
        ]
    })
    
    # 写出Excel（多sheet）
    with pd.ExcelWriter(OUTPUT, engine="openpyxl") as writer:
        df_out.to_excel(writer, sheet_name="事件增强含特征", index=False)
        unmatched.to_excel(writer, sheet_name="待人工补充", index=False)
        summary.to_excel(writer, sheet_name="统计摘要", index=False)
    
    print(f"\n处理完成,已保存到 {OUTPUT}")
    print(f"\n=== 统计摘要 ===")
    print(summary.to_string(index=False))
    
    if len(unmatched) > 0:
        print(f"\n=== 未匹配的事件（共{len(unmatched)}条，需人工补充） ===")
        print(unmatched.to_string(index=False))
    
    return df_out, unmatched, summary


if __name__ == "__main__":
    main()