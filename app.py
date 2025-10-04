import io
import os
import zipfile
from datetime import datetime
import datetime as dt
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st

st.set_page_config(page_title="WEEE 申报（德国）小工具", page_icon="♻️", layout="wide")

st.title("♻️ 德国 WEEE 报表生成器（基于 Amazon EPR Category Report）")

with st.expander("使用说明（简要）", expanded=False):
    st.markdown(
        """
        1) 上传一个或多个 **Amazon EPR Category Report**（CSV 或 Excel）。  
        2) 在侧边栏确认列映射：  
           - **F列** → 国家（应选择 **DE**）  
           - **K列** → 范围/类型（需为 **EEE**）  
           - **M列** → 产品类型（映射到德国 WEEE 六大类别之一）  
           - **W列** → 重量（将进行求和）  
           - **月份列** → 用于按 **YYYY-MM** 生成每月申报文件名  
        3) 如产品类型→WEEE 类别的映射未知，请在“产品类型映射”中上传/编辑。  
        4) 点击 **生成报表**，即可下载分月汇总的 CSV（文件名形如 `WEEE_DE_YYYY-MM.csv`）。
        """
    )

# --------------------------
# Sidebar – Column mapping
# --------------------------
st.sidebar.header("列映射设置")

st.sidebar.markdown(
    """
    默认按 **Excel 列位置**（F=第6列，K=第11列，M=第13列，W=第23列）读取：  
    - 若文件包含表头但列名与报告模板不同，**依然会按列顺序**读取。  
    - 如需手动指定，请在下方切换到“按列名映射”。
    """
)

map_mode = st.sidebar.radio(
    "映射模式",
    ["按列序号（F/K/M/W）", "按列名"],
    index=0
)

default_indices = {"country": 5, "scope": 10, "ptype": 12, "weight": 22}
month_hint_names = ["month", "reporting month", "reporting_month", "month_of_report", "date", "order date", "period"]

# --------------------------
# Product type → WEEE category mapping
# --------------------------
st.sidebar.
