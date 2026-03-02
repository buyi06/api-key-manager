#!/usr/bin/env python3
"""
API Key管理CLI工具
"""

import sys
import json
from api_key_manager import key_manager

def show_help():
    """显示帮助信息"""
    print("""
🔑 API Key管理工具

用法:
  python manage_keys.py <命令> [参数]

命令:
  add <key>        添加新的API key
  remove <key>     移除API key
  list             列出所有API keys
  stats            显示统计信息
  test             测试轮询功能
  help             显示此帮助信息

示例:
  python manage_keys.py add sk-xxxxxxxxxxxxx
  python manage_keys.py list
  python manage_keys.py stats
""")

def list_keys():
    """列出所有API keys"""
    keys = key_manager.api_keys
    if not keys:
        print("❌ 没有配置任何API keys")
        return
    
    print("🔑 当前配置的API keys:")
    for i, key in enumerate(keys, 1):
        stats = key_manager.key_stats.get(key, {})
        status = "✅ 健康" if stats.get('healthy', True) else "❌ 不健康"
        masked_key = key[:8] + "*" * (len(key) - 12) + key[-4:] if len(key) > 12 else key
        print(f"  {i}. {masked_key} - {status}")
        print(f"     请求: {stats.get('requests', 0)}, 错误: {stats.get('errors', 0)}")

def show_stats():
    """显示统计信息"""
    stats = key_manager.get_stats()
    print("📊 API Key统计信息:")
    print(f"  总keys数: {stats['total_keys']}")
    print(f"  健康keys: {stats['healthy_keys']}")
    print(f"  总请求数: {stats['total_requests']}")
    print(f"  总错误数: {stats['total_errors']}")
    
    if stats['total_requests'] > 0:
        success_rate = ((stats['total_requests'] - stats['total_errors']) / stats['total_requests']) * 100
        print(f"  成功率: {success_rate:.1f}%")

def add_key(api_key):
    """添加API key"""
    if not api_key.startswith('sk-'):
        print("❌ API key格式不正确，应该以'sk-'开头")
        return
    
    key_manager.add_key(api_key)
    print(f"✅ 已添加API key: {api_key[:8]}...{api_key[-4:]}")
    print(f"📈 现在共有 {len(key_manager.api_keys)} 个API keys")

def remove_key(api_key):
    """移除API key"""
    if api_key in key_manager.api_keys:
        key_manager.remove_key(api_key)
        print(f"✅ 已移除API key: {api_key[:8]}...{api_key[-4:]}")
        print(f"📉 剩余 {len(key_manager.api_keys)} 个API keys")
    else:
        print("❌ 未找到指定的API key")

def test_round_robin():
    """测试轮询功能"""
    print("🧪 测试轮询功能 (获取10个keys):")
    selected_keys = []
    for i in range(10):
        key = key_manager.get_next_key()
        if key:
            masked = key[:8] + "*" * (len(key) - 12) + key[-4:] if len(key) > 12 else key
            selected_keys.append(masked)
            print(f"  {i+1}. {masked}")
        else:
            print(f"  {i+1}. ❌ 无可用key")
    
    # 统计分布
    from collections import Counter
    distribution = Counter(selected_keys)
    print("\n📈 分布统计:")
    for key, count in distribution.items():
        print(f"  {key}: {count} 次")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "help" or command == "-h" or command == "--help":
        show_help()
    elif command == "list":
        list_keys()
    elif command == "stats":
        show_stats()
    elif command == "add":
        if len(sys.argv) < 3:
            print("❌ 请提供要添加的API key")
            return
        add_key(sys.argv[2])
    elif command == "remove":
        if len(sys.argv) < 3:
            print("❌ 请提供要移除的API key")
            return
        remove_key(sys.argv[2])
    elif command == "test":
        test_round_robin()
    else:
        print(f"❌ 未知命令: {command}")
        show_help()

if __name__ == "__main__":
    main()