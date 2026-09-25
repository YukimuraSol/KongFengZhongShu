# 源码说明

`src/` 是控分中枢的可读源码（Python）。

- `backend/` —— 接口层（路由 / 服务 / 数据模型）
- `core/` —— 计算内核（圣遗物数值求解、参考库读取）
- `irminsul_scanner/` —— 扫描器对接与名称映射（扫描器本体未包含）
- `resources/reference/` —— 计算用参考库；`resources/` 根下为元数据与设置
- 根目录若干 `.py` —— 扫描结果转换、导入导出等脚本

## 未包含（体积或第三方许可原因，请自行获取）

- `python/` —— 打包用的 Python 运行时
- `resources/yas/yas_artifact_*.exe` —— 第三方扫描工具（约 51 MB × 2）
- `irminsul_scanner/resources/irminsul_kfzs.exe` —— 扫描器本体（约 18 MB）

安装包见 **Releases**。
