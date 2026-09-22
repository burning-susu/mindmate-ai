# 阶段 1 高风险技术 Spike 报告

> 日期：2026-09-22
> 状态：`PASSED_WITH_RELEASE_GAPS`

| Spike | 结果 | 证据 |
| --- | --- | --- |
| sqlite-vec 安装/加载 | PASS | `sqlite_vec 0.1.9`；CPU Windows/Python 3.12 |
| 512 维向量写入/过滤/Top-K/删除 | PASS | `backend/spikes/sqlite_vec_spike.py` |
| ONNX Runtime 加载 BGE | PASS | `onnxruntime 1.30.0`；CPUExecutionProvider；输出 `(1,512)` |
| Windows Credential Manager | PASS | `WinVaultKeyring` 临时凭据写/读/删 |
| 随机回环端口/本地会话 | PASS | `backend/spikes/local_runtime_spike.py` |
| Mock Provider SSE | PASS | `TEXT_DELTA`、`COMPLETED` |
| PyInstaller one-folder | PASS_WITH_RULE | 显式收集 `sqlite_vec/vec0.dll` 后构建和 health 启动通过 |
| 干净 Windows 环境启动 | NOT_RUN | 当前仅验证开发主机；需发布候选阶段执行 |

## 运行命令

```powershell
cd backend
uv run python spikes/sqlite_vec_spike.py
uv run python spikes/credential_manager_spike.py
uv run python spikes/local_runtime_spike.py
uv run python spikes/mock_sse_spike.py
uv run python spikes/onnx_bge_spike.py
.\spikes\build_pyinstaller.ps1
```

## 阶段结论

sqlite-vec、ONNX Runtime、Credential Manager、随机回环会话、Mock SSE 和 PyInstaller 当前均未证明冻结方案不可行，允许继续阶段 2；干净环境和正式安装包仍是后续发布门禁，不在本报告中宣称完成。
