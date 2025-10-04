# ♻️ 德国 WEEE 报表生成器（Amazon EPR Category Report）

一个基于 **Streamlit** 的小工具：上传 Amazon 的 *EPR Category Reports*（CSV/Excel），
筛选 `F=DE`、`K=EEE`，将 `M` 列“产品类型”映射到德国 WEEE 六大类别，并按 `W` 列重量汇总，
自动生成按 **YYYY‑MM** 分月的申报 CSV 文件（`WEEE_DE_YYYY-MM.csv`）。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 使用步骤
1. 打开应用后，上传一个或多个 Amazon EPR Category Report（CSV 或 Excel）。
2. 在侧边栏选择 **映射模式**：
   - **按列序号（F/K/M/W）**：默认将 F/K/M/W 映射到第 6/11/13/23 列；
   - **按列名**：如你的报告有清晰的列名，直接填入对应列名，并指定“月份列名”。
3. 校对或上传 **产品类型映射**（`product_type` → `weee_category`，1–6）。
4. 点击 **生成报表**（应用在你上传后自动执行），页面提供 **逐月下载** 与 **整体 ZIP 下载**。

## GitHub & Streamlit Cloud 部署
1. 新建仓库并提交本项目文件：`app.py`、`requirements.txt`、`README.md`。
2. 登录 [streamlit.io](https://streamlit.io)，创建新应用，选择该仓库与分支，入口文件 `app.py`。
3. 部署完成后，即可在浏览器中使用该工具。

## WEEE 六大类别（德国，自 2018 年）
1. Heat exchange equipment  
2. Screens and monitors  
3. Lamps  
4. Large equipment  
5. Small equipment  
6. Small IT and telecommunication equipment

> 提示：你可以在应用侧边栏直接编辑“产品类型映射”表格，或上传一个 CSV（两列：`product_type`, `weee_category`）。