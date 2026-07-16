# 设计稿工作台

本项目用于整理各产品线的 PDF 设计稿，生成：

- `rename_preview.csv`：重命名预览清单
- `design_index.csv` / `design_index.json`：设计稿工作台台账
- `index.html`：本地网页工作台
- `pdf/`：规范命名后的 PDF 副本
- `thumbnails/`：PDF 首页缩略图

## 功能

- 扫描原始设计稿目录并提取基础元数据
- 自动给出规范化命名建议
- 自动识别产品分类，默认支持 `涂附 / 砂轮 / 钢丝刷 / 金刚石工具 / 其他`
- 当前默认配置会先把未命中的文件归入 `涂附`
- 基于 SHA256 标记重复文件
- 从确认后的 CSV 批量复制、重命名并生成缩略图
- 输出可搜索、可筛选的本地网页图库
- 通过简表字段新增单个设计稿并更新资料库

## 目录结构

运行后会生成如下目录：

```text
设计稿工作台/
├── data/
│   ├── design_index.csv
│   ├── design_index.json
│   └── rename_preview.csv
├── pdf/
│   ├── DONE/
│   ├── 历史/
│   └── 进行中/
├── thumbnails/
└── index.html
```

## 使用方式

### 1. 生成预览清单

```bash
python3 design_library.py scan \
  --source "/Users/zhanghan/Desktop/涂覆包装-设计稿" \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台"
```

执行后请先检查：

- `设计稿工作台/data/rename_preview.csv`
- 自动识别出的 `产品分类`、`产品系列`、`产品编码`、`核心规格`、`包装类型`
- 是否需要补充 `设计图号`、`客户`、`备注`

### 2. 根据确认后的 CSV 正式建库

```bash
python3 design_library.py build \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台"
```

`build` 会读取 `rename_preview.csv`，复制 PDF 到 `pdf/`，并生成：

- `design_index.csv`
- `design_index.json`
- `index.html`
- `thumbnails/`

### 3. 新增单个设计稿

```bash
python3 design_library.py add \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台" \
  --file "/absolute/path/to/file.pdf" \
  --product-category "涂附" \
  --product-series "B65" \
  --product-code "B65" \
  --spec "150-49H" \
  --package-type "彩盒" \
  --date "20250827" \
  --version "V1" \
  --channel "独立站" \
  --status "DONE"
```

### 4. 仅重建网页

```bash
python3 design_library.py site \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台"
```

### 5. 应用网页导出的改名清单

先在 `index.html` 里整理每个设计稿的“计划名称”，再点击网页上的“导出改名清单 CSV”。

之后执行：

```bash
python3 design_library.py apply-renames \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台" \
  --rename-csv "/absolute/path/to/rename_drafts_xxxxx.csv"
```

这个命令会：

- 先备份当前 `rename_preview.csv`
- 将导出的 `planned_new_name` 写回预览清单
- 自动重建 `pdf/`、`thumbnails/`、`design_index.csv`、`design_index.json`、`index.html`
- 让网页展示名称和工作台本地 PDF 文件名保持同步

### 6. 应用网页导出的删除清单

先在网页里用筛选 + 多选圈出要删除的设计稿，再点击“导出删除清单 CSV”。

之后执行：

```bash
python3 design_library.py apply-delete-list \
  --output "/Users/zhanghan/Documents/涂覆包装设计稿整理归类/设计稿工作台" \
  --delete-csv "/absolute/path/to/delete_list_xxxxx.csv"
```

这个命令会：

- 先备份当前 `rename_preview.csv`
- 删除删除清单中对应的原始 PDF
- 从 `rename_preview.csv` 中移除这些记录
- 自动重建 `pdf/`、`thumbnails/`、`design_index.csv`、`design_index.json`、`index.html`
- 额外输出一份删除执行记录 `deleted_from_selection.csv`

## 命名规则

统一命名模板：

```text
产品编码-核心规格-包装类型-YYYYMMDD-V版本.pdf
```

示例：

- `B65-150-49H-彩盒-20250827-V1.pdf`
- `BT77-70X198_70X420-彩盒-20250715-V2.pdf`
- `BD8-32-规格标签-20250818-V1.pdf`

## 支持的包装类型

- `彩盒`
- `标签`
- `规格标签`
- `刀模图`
- `吊卡盒`
- `吸塑彩贴`
- `外箱`
- `说明卡`
- `信封包装`

## 默认产品分类

- `涂附`
- `砂轮`
- `钢丝刷`
- `金刚石工具`
- `其他`

## 产品分类配置

分类规则已外置到：

```text
product_categories.json
```

系列规则已外置到：

```text
product_series_rules.json
```

当前默认策略：

- 当前这批设计稿通过 `force_all_category` 统一归到 `涂附`
- 所有未命中的文件默认归为 `涂附`
- 以后如果你新增 `砂轮 / 钢丝刷 / 金刚石工具` 的设计稿，只需要改这个 JSON，不需要改主脚本

## 当前工作台优化

- 当前这批设计稿全部归在 `涂附`
- 工作台已新增 `产品系列` 维度，便于按 `B15 / B25 / B65 / BT77 / BDL9 / V字卷` 等系列查看历史稿
- 首页提供系列概览按钮，可一键筛选某个系列
- 产品系列规则也已外置，后续可以持续把 `待补充` 压缩成更贴近业务的系列
- 当前系列识别采用“编码系列优先”，尽量优先显示 `B15 / B25 / B65 / BT77 / BDL9` 这类稳定系列
- 系列识别会同时参考“文件名 + 所在文件夹路径”，因此像 `快换碟套装`、`拉绒片` 这类目录信息也能参与识别
- `build` 会优先保留 `rename_preview.csv` 中你已经人工确认过的 `new_name`
- `build` 重新执行时会先清理旧的 `pdf/` 和 `thumbnails/` 产物，避免历史重建残留越积越多
- 缩略图生成已增加超时兜底，个别异常 PDF 不会再拖住整个工作台建库
- 网页已支持“计划名称草稿”，草稿会保存在当前浏览器，可导出成 CSV，再通过 `apply-renames` 批量同步回工作台
- 网页已支持“一行一条”的列表整理模式，可按筛选结果批量多选，并导出所选清单或删除清单

## 备注

- `scan` 只生成预览，不会改动原始文件
- `build` 采用复制方式建库，不会修改原始设计稿目录
- 缩略图依赖系统中的 `pdftoppm`
