# 内置规则引擎、Kronos 与 vn.py 量化增强

DSA在每只A股或ETF完成原分析后，默认调用仓库内置的量化增强流程：

- 内置规则引擎输出日线、周线规则信号、图形事件和逐项指标状态；
- Kronos输出未来价格路径的概率情景；
- vn.py Alpha可选评价当前规则信号在历史上的结果，不训练模型，也不输出另一项预测；
- DSA保存统一结果、展示报告并复用既有通知渠道。

三个结论保持分离。vn.py的“方向胜率”是相同规则信号在已完成历史窗口中的统计结果，不能解释为未来上涨概率。样本少于20次标记为低可信度，20至59次为中等，60次及以上为高。

## 默认部署

    QUANT_ENRICHMENT_ENABLED=true
    QUANT_VNPY_VALIDATION_ENABLED=false
    QUANT_ENRICHMENT_TIMEOUT_SECONDS=600

无需再部署ABU仓库。Kronos推理代码随DSA发布，首次分析时从Hugging Face下载约390 MB的Kronos-base和约15 MB的tokenizer到数据库同目录的 quant_engine/models，后续复用模型和预测缓存。Docker默认将它保存在 /app/data/quant_engine 持久化卷中。首次下载需要访问Hugging Face；离线部署可预先复制该缓存目录。

该能力默认开启；设为 QUANT_ENRICHMENT_ENABLED=false 可关闭。规则/Kronos失败、超时或模型暂时无法下载时，DSA保留原分析结果并在量化区显示降级状态。当前只支持六位A股和ETF代码。少量标的在单个DSA进程内串行执行Kronos，避免同时加载多个base模型。

## 兼容外部部署

旧部署仍可显式切回外部引擎：

    QUANT_ABU_ROOT=/absolute/path/to/abu
    QUANT_ABU_CONFIG=/absolute/path/to/abu/daily_signal.kronos.json
    QUANT_ABU_PYTHON=/absolute/path/to/abu/.venv/bin/python

vn.py仍是可选外部评价器：

    QUANT_VNPY_VALIDATION_ENABLED=true
    QUANT_VNPY_ROOT=/absolute/path/to/vnpy
    QUANT_VNPY_PYTHON=/absolute/path/to/vnpy/.venv/bin/python

标准JSON契约包含数据质量、拆分调整、技术指标、事件、Kronos结果和同口径历史行情。DSA持久化前会移除历史K线，只保存分析结果及vn.py评价。内置Kronos运行时代码沿用其MIT许可证，版权与来源版本记录保存在 src/quant_engine/kronos_runtime/LICENSE 和 NOTICE。
