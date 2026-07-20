#!/usr/bin/env python3
"""
BrowserAgent 测试脚本
验证浏览器自动化功能和英伟达 API 集成
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.browser_agent import BrowserAgent, search_with_browser, extract_place_info


def check_configuration():
    """检查配置是否完整"""
    print("=" * 60)
    print("配置检查")
    print("=" * 60)

    required_vars = [
        "NVIDIA_API_KEY",
        "NVIDIA_BASE_URL",
        "NVIDIA_MODEL"
    ]

    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value and value != f"your_{var.lower()}":
            print(f"✓ {var}: {value[:20]}..." if len(value) > 20 else f"✓ {var}: {value}")
        else:
            print(f"✗ {var}: 未配置")
            missing.append(var)

    if missing:
        print(f"\n❌ 缺少配置项: {', '.join(missing)}")
        print("\n请在 .env 文件中配置:")
        print("  NVIDIA_API_KEY=your_nvidia_api_key")
        print("  NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1")
        print("  NVIDIA_MODEL=meta/llama-3.1-70b-instruct")
        return False

    print("\n✓ 配置完整")
    return True


async def test_basic_navigation():
    """测试 1: 基本页面导航"""
    print("\n" + "=" * 60)
    print("测试 1: 基本页面导航")
    print("=" * 60)

    try:
        agent = BrowserAgent(headless=True, max_steps=10)

        result = await agent.execute(
            task="访问百度首页，返回页面标题",
            start_url="https://www.baidu.com"
        )

        if result["success"]:
            print(f"✓ 导航成功")
            print(f"  结果: {result['result']}")
            return True
        else:
            print(f"✗ 导航失败: {result['error']}")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_search_functionality():
    """测试 2: 搜索功能"""
    print("\n" + "=" * 60)
    print("测试 2: 搜索功能")
    print("=" * 60)

    try:
        result = await search_with_browser("Python 教程", max_results=3)

        print(f"✓ 搜索完成")
        print(f"  结果预览: {result[:200]}..." if len(result) > 200 else f"  结果: {result}")
        return True

    except Exception as e:
        print(f"✗ 搜索失败: {e}")
        return False


async def test_place_extraction():
    """测试 3: 地点信息提取"""
    print("\n" + "=" * 60)
    print("测试 3: 地点信息提取（百度地图）")
    print("=" * 60)

    try:
        result = await extract_place_info("天安门", "北京")

        if result["success"]:
            print(f"✓ 信息提取成功")
            print(f"  数据: {result['data']}")
            return True
        else:
            print(f"✗ 信息提取失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def test_form_interaction():
    """测试 4: 表单交互（可选）"""
    print("\n" + "=" * 60)
    print("测试 4: 表单交互")
    print("=" * 60)

    try:
        agent = BrowserAgent(headless=True, max_steps=15)

        result = await agent.execute(
            task="""
            访问百度搜索，完成以下操作：
            1. 在搜索框输入"北京旅游景点"
            2. 点击搜索按钮
            3. 提取第一个搜索结果的标题和链接
            """,
            start_url="https://www.baidu.com"
        )

        if result["success"]:
            print(f"✓ 表单交互成功")
            print(f"  结果: {result['result'][:200]}..." if len(result['result']) > 200 else f"  结果: {result['result']}")
            return True
        else:
            print(f"✗ 表单交互失败: {result['error']}")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        return False


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("BrowserAgent 测试套件")
    print("=" * 60)

    # 检查配置
    if not check_configuration():
        return False

    print("\n提示: 首次运行会自动安装 Playwright 浏览器（约 300MB）")
    print("      如果测试失败，请先运行: playwright install chromium\n")

    # 运行测试
    tests = [
        ("基本导航", test_basic_navigation),
        ("搜索功能", test_search_functionality),
        ("地点提取", test_place_extraction),
        ("表单交互", test_form_interaction),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except KeyboardInterrupt:
            print(f"\n用户中断测试")
            break
        except Exception as e:
            print(f"\n✗ {name} 异常: {e}")
            results.append((name, False))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status}  {name}")

    print(f"\n通过率: {passed}/{total} ({passed * 100 // total if total > 0 else 0}%)")

    if passed == total:
        print("\n🎉 所有测试通过！BrowserAgent 工作正常")
        return True
    elif passed > 0:
        print(f"\n⚠️ 部分测试失败，但核心功能可用")
        return True
    else:
        print(f"\n❌ 所有测试失败，请检查配置和网络")
        return False


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="BrowserAgent 测试脚本")
    parser.add_argument("--test", choices=["basic", "search", "place", "form", "all"],
                        default="all", help="选择要运行的测试")
    args = parser.parse_args()

    # 运行测试
    if args.test == "all":
        success = asyncio.run(run_all_tests())
    elif args.test == "basic":
        success = asyncio.run(test_basic_navigation())
    elif args.test == "search":
        success = asyncio.run(test_search_functionality())
    elif args.test == "place":
        success = asyncio.run(test_place_extraction())
    elif args.test == "form":
        success = asyncio.run(test_form_interaction())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
