# Windows Packaging

V1 发布形态为 PyInstaller one-folder + Inno Setup 当前用户级安装。阶段 0 只建立目录；阶段 1 验证原生依赖，阶段 10 生成正式打包配置。

## LibreOffice PPTX 预览运行时

PPTX 原版式预览使用本地 LibreOffice headless 转 PDF，不调用云转换服务。开发机可通过 `MINDMATE_LIBREOFFICE_PATH` 指向 `soffice.com`/`soffice.exe`，或将完整 LibreOffice 安装目录放在 `runtime/libreoffice`。

正式打包前，从已核验来源取得完整 Windows LibreOffice 安装目录，并运行：

```powershell
.\scripts\stage-libreoffice.ps1 -SourceDirectory 'C:\path\to\LibreOffice'
```

也可通过 `.scriptsuild.ps1 -LibreOfficeHome 'C:\path\to\LibreOffice'` 在前端和后端构建前暂存运行时。脚本会校验转换程序和许可证文件，复制整个运行时到 `build/runtime/libreoffice`，记录版本、`soffice.exe` SHA-256 和随包许可证清单。正式 one-folder 包必须将该目录完整带入安装包；打包前还须固定来源版本、官方下载校验值和许可证审查证据。当前机器未提供 LibreOffice 安装目录时，构建脚本不会下载它，也不会伪装成预览成功。

当前仓库尚未进入阶段 10，正式 PyInstaller/Inno Setup 工程仍是发布缺口；运行时暂存不等于最终安装包已经包含 LibreOffice。
