import io
import os
import zipfile
from datetime import datetime
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
           - **月份列** → 用于按 **YYYY‑MM** 生成每月申报文件名  
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
st.sidebar.subheader("产品类型映射（M列 → WEEE 类别）")

with st.sidebar.expander("说明与模板", expanded=False):
    st.markdown(
        """
        - 德国 WEEE 六大类别：  
          1. Heat exchange equipment  
          2. Screens & monitors  
          3. Lamps  
          4. Large equipment  
          5. Small equipment  
          6. Small IT & telecom equipment  
        - 请将 **产品类型（M列取值）** 映射到 1–6。  
        - 可上传 CSV（两列：`product_type`, `weee_category`），或在下方编辑表格。
        """
    )

uploaded_map = st.sidebar.file_uploader("上传产品类型映射（CSV）", type=["csv"], key="map_upload", accept_multiple_files=False)

if "ptype_map_df" not in st.session_state:
    # provide a tiny starter mapping
    st.session_state.ptype_map_df = pd.DataFrame(
        {"product_type": ["example_heater", "example_pump"], "weee_category": [4, 5]}
    )

if uploaded_map is not None:
    try:
        df_map = pd.read_csv(uploaded_map)
        # normalize columns
        cols = [c.strip().lower() for c in df_map.columns]
        df_map.columns = cols
        if not {"product_type", "weee_category"}.issubset(set(df_map.columns)):
            st.sidebar.error("映射 CSV 需要包含列：product_type, weee_category")
        else:
            st.session_state.ptype_map_df = df_map[["product_type", "weee_category"]].copy()
            st.sidebar.success("已载入映射。")
    except Exception as e:
        st.sidebar.error(f"读取映射失败：{e}")

st.sidebar.markdown("（可直接在下表编辑，完成后点上方空白处以保存到会话）")
st.session_state.ptype_map_df = st.sidebar.data_editor(
    st.session_state.ptype_map_df, num_rows="dynamic", use_container_width=True
)

# --------------------------
# File upload
# --------------------------
files = st.file_uploader(
    "上传 Amazon EPR Category Report（CSV 或 Excel，可多选）",
    type=["csv", "xlsx", "xls"],
    accept_multiple_files=True
)

# Helper to read a single file as DataFrame
def _read_one(f) -> pd.DataFrame:
    name = f.name
    try:
        if name.lower().endswith(".csv"):
            df = pd.read_csv(f, dtype=str)
        else:
            df = pd.read_excel(f, dtype=str)
    except Exception:
        f.seek(0)
        if name.lower().endswith(".csv"):
            df = pd.read_csv(f, encoding="latin-1", dtype=str)
        else:
            df = pd.read_excel(f, dtype=str)
    # Preserve original order and also keep a duplicate with numeric columns
    return df

# Normalize: give access to both index-based and name-based selection
def _extract_columns(df: pd.DataFrame,
                     map_mode: str,
                     col_indices: Dict[str,int],
                     col_names: Dict[str, Optional[str]]) -> pd.DataFrame:
    dff = df.copy()

    # Try to coerce weight later to numeric
    def _get_by_index(d: pd.DataFrame, idx: int) -> pd.Series:
        if idx < 0 or idx >= d.shape[1]:
            raise IndexError(f"索引超出范围：{idx+1} 列（文件仅 {d.shape[1]} 列）")
        return d.iloc[:, idx]

    def _get_by_name(d: pd.DataFrame, name: str) -> pd.Series:
        # soft match: strip + casefold
        lc = {c.strip().casefold(): c for c in d.columns}
        key = name.strip().casefold()
        if key not in lc:
            raise KeyError(f"未找到列名：{name}")
        return d[lc[key]]

    # Country / Scope / Product type / Weight
    if map_mode == "按列序号（F/K/M/W）":
        country = _get_by_index(dff, col_indices["country"])
        scope = _get_by_index(dff, col_indices["scope"])
        ptype = _get_by_index(dff, col_indices["ptype"])
        weight = _get_by_index(dff, col_indices["weight"])
        # Try to propose a month column by heuristic on names and by position (A or B often date)
        month_series = None
        # Name-based hints first
        for c in dff.columns:
            if any(h in c.strip().lower() for h in { "month", "reporting", "period", "date"}):
                month_series = dff[c]
                break
        if month_series is None and dff.shape[1] > 0:
            month_series = dff.iloc[:, 0]
    else:
        # name-based
        country = _get_by_name(dff, col_names["country"])
        scope = _get_by_name(dff, col_names["scope"])
        ptype = _get_by_name(dff, col_names["ptype"])
        weight = _get_by_name(dff, col_names["weight"])
        month_name = col_names.get("month")
        month_series = _get_by_name(dff, month_name) if month_name else None
        if month_series is None:
            # fallback
            for c in dff.columns:
                if any(h in c.strip().lower() for h in { "month", "reporting", "period", "date"}):
                    month_series = dff[c]
                    break
            if month_series is None:
                month_series = dff.iloc[:, 0]

    out = pd.DataFrame({
        "country": country,
        "scope": scope,
        "product_type": ptype,
        "weight_raw": weight,
        "month_raw": month_series
    })
    # Clean weight
    out["weight_kg"] = (
        out["weight_raw"]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.extract(r"([-+]?\d*\.?\d+)")[0]
    )
    out["weight_kg"] = pd.to_numeric(out["weight_kg"], errors="coerce").fillna(0.0)

    # Normalize month to YYYY-MM
    def norm_month(x: str) -> Optional[str]:
        if x is None:
            return None
        s = str(x).strip()
        if not s:
            return None
        # Try common formats
        fmts = [
            "%Y-%m", "%Y/%m", "%Y.%m",
            "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
            "%d.%m.%Y", "%Y.%m.%d",
            "%b %Y", "%B %Y",
        ]
        for f in fmts:
            try:
                dt = datetime.strptime(s, f)
                return dt.strftime("%Y-%m")
            except Exception:
                pass
        # Try pandas to_datetime
        try:
            dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
            if pd.notna(dt):
                return dt.strftime("%Y-%m")
        except Exception:
            pass
        # Try to catch YYYYMM
        if s.isdigit() and len(s) == 6:
            return f"{s[0:4]}-{s[4:6]}"
        return None

    out["month"] = out["month_raw"].map(norm_month)
    return out

# Sidebar controls for mapping
if map_mode == "按列序号（F/K/M/W）":
    idx_country = st.sidebar.number_input("F列（国家）索引（从1开始）", min_value=1, value=6, step=1) - 1
    idx_scope   = st.sidebar.number_input("K列（范围/类型）索引（从1开始）", min_value=1, value=11, step=1) - 1
    idx_ptype   = st.sidebar.number_input("M列（产品类型）索引（从1开始）", min_value=1, value=13, step=1) - 1
    idx_weight  = st.sidebar.number_input("W列（重量）索引（从1开始）", min_value=1, value=23, step=1) - 1
    col_indices = {"country": idx_country, "scope": idx_scope, "ptype": idx_ptype, "weight": idx_weight}
    col_names = {}
else:
    name_country = st.sidebar.text_input("国家列名（对应F列）", value="Country")
    name_scope   = st.sidebar.text_input("范围/类型列名（对应K列）", value="Scope")
    name_ptype   = st.sidebar.text_input("产品类型列名（对应M列）", value="Product Type")
    name_weight  = st.sidebar.text_input("重量列名（对应W列）", value="Weight (kg)")
    name_month   = st.sidebar.text_input("月份列名（用于文件名）", value="Reporting Month")
    col_indices = {}
    col_names = {"country": name_country, "scope": name_scope, "ptype": name_ptype, "weight": name_weight, "month": name_month}

st.divider()

# --------------------------
# Main processing
# --------------------------
if files:
    dfs = []
    for f in files:
        df = _read_one(f)
        try:
            slim = _extract_columns(df, map_mode, col_indices, col_names)
            slim["source_file"] = f.name
            dfs.append(slim)
        except Exception as e:
            st.error(f"文件 `{f.name}` 解析失败：{e}")
    if dfs:
        data = pd.concat(dfs, ignore_index=True)
        st.success(f"已载入 {len(files)} 个文件，共 {len(data)} 条记录。")
        with st.expander("查看提取后的预览", expanded=False):
            st.dataframe(data.head(50), use_container_width=True)
    else:
        data = None
else:
    data = None

# --------------------------
# Build WEEE report
# --------------------------
def build_report(df: pd.DataFrame, ptype_map_df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    # Filter DE + EEE
    d = d[(d["country"].astype(str).str.strip().str.upper() == "DE") &
          (d["scope"].astype(str).str.strip().str.upper() == "EEE")]
    if d.empty:
        return d

    # Map product_type -> weee_category
    map_dict = dict(
        (str(r["product_type"]).strip(), int(r["weee_category"]))
        for _, r in ptype_map_df.iterrows()
        if pd.notna(r["product_type"]) and pd.notna(r["weee_category"])
    )
    d["weee_category"] = d["product_type"].map(lambda x: map_dict.get(str(x).strip(), None))

    # Warn for unmapped
    unmapped = sorted(set(d.loc[d["weee_category"].isna(), "product_type"].dropna().astype(str)))
    if unmapped:
        st.warning(f"存在未映射的产品类型（将被忽略汇总）：{', '.join(unmapped[:30])}" + (" ..." if len(unmapped) > 30 else ""))

    d = d[pd.notna(d["weee_category"])]
    d["weee_category"] = d["weee_category"].astype(int)

    # Month fallback: if missing, fill with one global month chosen by user
    if "month" not in d.columns or d["month"].isna().all():
        st.info("未成功解析月份。请在侧边栏改用‘按列名’映射指定月份列；或在下方选择一个统一月份。")
        month_pick = st.selectbox("统一申报月份（YYYY‑MM）", options=[datetime.now().strftime("%Y-%m")])
        d["month"] = month_pick

    # Group and sum weight
    grp = (
        d.groupby(["month", "weee_category"], as_index=False)["weight_kg"]
        .sum()
        .rename(columns={"weight_kg": "total_weight_kg"})
    )
    # Sort for readability
    grp = grp.sort_values(["month", "weee_category"]).reset_index(drop=True)
    return grp

if data is not None and not data.empty:
    result = build_report(data, st.session_state.ptype_map_df)
    if result is not None and not result.empty:
        st.subheader("汇总结果")
        st.dataframe(result, use_container_width=True)

        # Split by month & offer downloads
        months = result["month"].unique().tolist()
        months.sort()
        out_zip = io.BytesIO()
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for m in months:
                df_m = result[result["month"] == m].copy()
                fname = f"WEEE_DE_{m}.csv"
                csv_bytes = df_m.to_csv(index=False).encode("utf-8-sig")
                zf.writestr(fname, csv_bytes)

        st.download_button(
            "📦 下载所有月份 CSV（ZIP）",
            data=out_zip.getvalue(),
            file_name="WEEE_DE_reports.zip",
            mime="application/zip",
        )

        with st.expander("逐月下载", expanded=False):
            for m in months:
                df_m = result[result["month"] == m].copy()
                st.markdown(f"**{m}**")
                st.dataframe(df_m, use_container_width=True)
                st.download_button(
                    f"⬇️ 下载 {m}",
                    data=df_m.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"WEEE_DE_{m}.csv",
                    mime="text/csv",
                    key=f"dl_{m}"
                )
    else:
        st.info("没有可汇总的数据（可能是没有 DE + EEE 记录，或所有产品类型都未映射）。")

st.divider()
st.caption("提示：如需长期使用，请将本项目推送到 GitHub 并在 Streamlit Cloud 部署。")