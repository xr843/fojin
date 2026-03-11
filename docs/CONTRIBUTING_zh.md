# 参与贡献 FoJin

感谢你对 FoJin 项目的关注！本项目致力于让全球佛学文献更易被研究者获取，每一份贡献都有意义。

## 贡献方式

- **添加数据源** — 发现我们遗漏的佛学文本数据库？提 issue 或提交导入脚本。
- **改进搜索** — 更好的分词、排序或多语言支持。
- **修复 Bug** — 查看 [Issues](https://github.com/xr843/fojin/issues) 页面。
- **翻译** — 帮助翻译 UI 或文档。
- **文档** — 完善指南、添加示例、修正错误。

## 快速开始

1. Fork 并克隆仓库
2. 按照 README.md 中的 [Development](#development) 部分进行本地配置
3. 创建功能分支：`git checkout -b feat/your-feature`
4. 进行修改
5. 运行测试：`cd backend && pytest tests/ -q`
6. 使用清晰的提交信息
7. Push 并创建 Pull Request

## 代码规范

- **Python**：遵循 PEP 8，使用类型提示，Schema 使用 Pydantic。
- **TypeScript**：遵循现有 ESLint 配置，使用函数组件 + Hooks。
- **提交信息**：使用约定式提交（`feat:`、`fix:`、`docs:`、`refactor:`）。

## 添加数据源

1. 创建 `backend/scripts/import_<source_name>.py`
2. 参考现有导入脚本（如 `import_suttacentral.py`）
3. 在 `backend/scripts/import_all.py` 中注册
4. 更新 README.md 中的数据源表

## 提交 Issue

- 使用 GitHub Issue 模板
- Bug 请附上复现步骤
- 功能建议请描述使用场景

## 许可证

参与贡献即表示你同意将贡献内容按 Apache License 2.0 许可。
