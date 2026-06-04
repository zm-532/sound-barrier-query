# 声屏障标准查询系统

本项目基于 `docs/国内声屏障标准汇总表.xlsx` 构建本地声屏障标准查询系统，支持：

- 按标准名称或标准号查询技术内容
- 按产品或材料名称查看多标准横向对比
- 按技术关键词检索相关标准内容
- 使用检索增强的机器人助手生成带来源的总结

## 运行

```powershell
uv run python -m sound_barrier_query.web --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

## 测试

```powershell
uv run python -m unittest tests.test_query_engine -v
```
