#!/usr/bin/env python3
"""
百度地图 API 测试脚本
"""
import os
import requests
import json

def test_baidu_maps():
    """测试百度地图 API"""
    api_key = os.getenv("BAIDU_MAPS_API_KEY", "")

    print("=" * 60)
    print("百度地图 API 测试")
    print("=" * 60)

    if not api_key:
        print("\n❌ 错误: 未设置 BAIDU_MAPS_API_KEY 环境变量")
        return False

    print(f"\n✓ API Key 已配置: {api_key[:10]}...")

    # 测试 1: 地点搜索
    print("\n测试 1: 地点搜索（北京烤鸭）")
    print("-" * 60)

    url = "https://api.map.baidu.com/place/v2/search"
    params = {
        "query": "烤鸭",
        "region": "北京",
        "output": "json",
        "ak": api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == 0:
            results = data.get("results", [])
            print(f"✓ 找到 {len(results)} 个结果")

            # 显示前3个结果
            for i, place in enumerate(results[:3], 1):
                print(f"\n  [{i}] {place.get('name')}")
                print(f"      地址: {place.get('address')}")
                location = place.get('location', {})
                print(f"      坐标: ({location.get('lat')}, {location.get('lng')})")
        else:
            print(f"❌ API 错误: {data.get('message')}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

    # 测试 2: 地理编码
    print("\n\n测试 2: 地理编码（地址转坐标）")
    print("-" * 60)

    url = "https://api.map.baidu.com/geocoding/v3/"
    params = {
        "address": "北京市海淀区上地十街10号",
        "city": "北京市",
        "output": "json",
        "ak": api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == 0:
            location = data.get("result", {}).get("location", {})
            print(f"✓ 地址: 北京市海淀区上地十街10号")
            print(f"✓ 坐标: ({location.get('lat')}, {location.get('lng')})")
            print(f"✓ 精度: {data.get('result', {}).get('precise', 0)}")
            print(f"✓ 置信度: {data.get('result', {}).get('confidence', 0)}")
        else:
            print(f"❌ API 错误: {data.get('message')}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

    # 测试 3: 路线规划
    print("\n\n测试 3: 路线规划（天安门到颐和园）")
    print("-" * 60)

    url = "https://api.map.baidu.com/directionlite/v1/driving"
    params = {
        "origin": "39.915,116.404",  # 天安门
        "destination": "40.0,116.275",  # 颐和园
        "ak": api_key
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("status") == 0:
            result = data.get("result", {})
            routes = result.get("routes", [])

            if routes:
                route = routes[0]
                print(f"✓ 距离: {route.get('distance')} 米")
                print(f"✓ 预计时间: {route.get('duration')} 秒")

                steps = route.get("steps", [])
                print(f"✓ 路线步骤: {len(steps)} 步")

                # 显示前3个步骤
                for i, step in enumerate(steps[:3], 1):
                    print(f"\n  [{i}] {step.get('instruction')}")
                    print(f"      距离: {step.get('distance')} 米")
        else:
            print(f"❌ API 错误: {data.get('message')}")
            return False

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

    print("\n" + "=" * 60)
    print("✓ 所有测试通过！百度地图 API 工作正常")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = test_baidu_maps()
    sys.exit(0 if success else 1)
