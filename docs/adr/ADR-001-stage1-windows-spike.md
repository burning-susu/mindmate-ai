# ADR-001：阶段 1 Windows 原生依赖 Spike

> 日期：2026-09-22
> 状态：验证完成，进入开发基线
> 范围：sqlite-vec、ONNX Runtime、Credential Manager、回环会话、Mock SSE、PyInstaller

## 结论

当前 Windows 11 x64 / Python 3.12.11 环境下，冻结的 sqlite-vec、ONNX Embedding、Windows Credential Manager、Mock SSE 和 PyInstaller one-folder 方案均可运行。PyInstaller 必须显式收集 `sqlite_vec/vec0.dll`；自动分析不会可靠带入该扩展。

## 证据

- `backend/spikes/sqlite_vec_spike.py`：512 维向量写入、`vector_meta` 范围过滤、Top-K 和删除通过。
- `backend/spikes/onnx_bge_spike.py`：使用 `onnx-community/bge-small-zh-v1.5-ONNX` 的 `base_model=BAAI/bge-small-zh-v1.5` 转换权重；CPUExecutionProvider 输出稳定 `(1, 512)`。
- `backend/spikes/credential_manager_spike.py`：Windows `WinVaultKeyring` 写入、读取和删除临时凭据通过。
- `backend/spikes/local_runtime_spike.py`：随机回环端口和本地会话 header 校验通过。
- `backend/spikes/mock_sse_spike.py`：`TEXT_DELTA` 与 `COMPLETED` SSE 事件通过。
- `backend/spikes/build_pyinstaller.ps1`：显式 `--add-binary ".venv/Lib/site-packages/sqlite_vec/vec0.dll;sqlite_vec"` 的 one-folder 构建通过。
- `backend/dist/mindmate-stage1/`（被 `.gitignore` 排除）：包含 `sqlite_vec/vec0.dll` 与 ONNX Runtime DLL；当前主机打包产物 health 请求返回 `status=ok`。
- 使用 `.\spikes\build_pyinstaller.ps1` 可重复生成上述 one-folder 包；当前 `backend/dist/` 和 `backend/build/` 均为忽略的临时产物。

## 模型来源与校验

| 文件 | SHA-256 |
| --- | --- |
| `onnx/model.onnx` | `69b353bb2aa2d09ab606ddbbc35437b03c843615a6bff28216a37fee7309c2aa` |
| `onnx/model.onnx_data` | `e72da961b03613124aa11317470c995ca197651a9d7f6be2b0e90aad92f71df0` |
| `tokenizer.json` | `3d09c84ebd10306706a79a8276b3ab736a40d8ec03251c7639f4e52c3a1a4f8e` |

模型下载只写入被忽略的 `backend/model-cache/`，没有把模型文件提交到 Git，也没有读取任何 API Key。

## 保留的验证缺口

- 尚未在独立干净 Windows 环境或 VM 执行安装包启动验证。
- 尚未执行 Inno Setup 安装/卸载流程。
- 阶段 1 只证明原生技术链路可行，不证明业务 RAG、质量阈值或发布完成。
