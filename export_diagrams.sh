#!/bin/bash
# Mermaid 图表批量导出脚本
# 需要先安装 mermaid-cli: npm install -g @mermaid-js/mermaid-cli

echo "开始导出 Mermaid 图表为 PNG..."

# 创建输出目录
mkdir -p diagrams

# 提取所有 Mermaid 代码块
awk '/```mermaid/,/```/' 系统流程图.md > temp_diagrams.txt

# 计数器
counter=1

# 分割并导出每个图表
while IFS= read -r line; do
    if [[ $line == '```mermaid' ]]; then
        # 开始新的图表
        current_file="diagrams/diagram_${counter}.mmd"
        echo "" > "$current_file"
        in_block=1
    elif [[ $line == '```' ]] && [[ $in_block == 1 ]]; then
        # 结束当前图表，导出为 PNG
        mmdc -i "$current_file" -o "diagrams/diagram_${counter}.png" -w 2000 -H 1500
        echo "✓ 导出: diagrams/diagram_${counter}.png"
        ((counter++))
        in_block=0
    elif [[ $in_block == 1 ]]; then
        # 添加内容到当前图表
        echo "$line" >> "$current_file"
    fi
done < temp_diagrams.txt

# 清理临时文件
rm temp_diagrams.txt

echo ""
echo "导出完成！共生成 $((counter-1)) 张图表"
echo "图表保存在 diagrams/ 目录下"
echo ""
echo "如果你没有安装 mermaid-cli，请运行："
echo "  npm install -g @mermaid-js/mermaid-cli"
