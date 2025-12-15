#!/usr/bin/env python3
"""手动生成报告索引"""

import os
import glob
from datetime import datetime

# 读取所有报告文件
reports = glob.glob('pain_analysis_reports/*opportunity_analysis.md')
reports.sort()

index_content = f"""# 痛点机会分析报告索引

> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
> **分析数量**: {len(reports)}

---

## 📈 分析概览

本次共分析了 {len(reports)} 个高价值痛点聚类，每个聚类都包含详细的痛点分析、应用设计方案和可执行行动计划。

基于Reddit真实用户讨论，这些聚类代表了当前市场上的重要机会。

---

## 📋 报告列表

以下是按聚类名称排序的分析报告：

{chr(10).join([f"- [{os.path.basename(f)}]({f})" for f in reports])}

---

## 🎯 下一步行动建议

### 1. 优先级评估
根据机会评分和市场潜力，建议优先关注以下方向：
- 自动化工具（文件管理、任务整合）
- 工作流优化（会议、协作工具）
- 技术债务管理（文档、代码维护）

### 2. 用户验证
针对Top 3机会进行深度用户访谈：
- 找到10-20个目标用户
- 验证痛点真实存在且频繁发生
- 测试解决方案的接受度

### 3. MVP开发
选择最高价值的机会启动MVP开发：
- 专注解决1-2个核心痛点
- 快速原型和迭代
- 收集用户反馈并调整

### 4. 持续监控
定期更新Reddit数据，跟踪新的痛点趋势：
- 监控相关子版块的新帖子
- 识别新兴的工作流问题
- 及时调整产品方向

---

## 📊 统计信息

- 总报告数: {len(reports)}
- 数据来源: Reddit 痛点抓取系统
- 更新频率: 建议每月更新一次

---

*使用方法: 点击上方链接查看具体的机会分析报告*
"""

# 写入索引文件
with open('pain_analysis_reports/README.md', 'w', encoding='utf-8') as f:
    f.write(index_content)

print(f"✅ 索引文件已生成: pain_analysis_reports/README.md")
print(f"   • 包含 {len(reports)} 个报告链接")