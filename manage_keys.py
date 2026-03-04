#!/usr/bin/env python3
"""
API Key管理CLI工具

功能:
- 添加/移除/替换keys
- 查看keys状态和有效期
- 检查过期/即将过期的keys
- 测试轮询功能
"""

import sys
import json
from datetime import datetime, timedelta
from api_key_manager import key_manager


def show_help():
    """显示帮助信息"""
    print("""
🔑 API Key管理工具

用法:
  python manage_keys.py <命令> [参数]

命令:
  add <key>              添加新的API key
  remove <key>           移除API key
  replace <old> <new>    替换API key（用于过期更换）
  list                   列出所有API keys及状态
  stats                  显示统计信息
  expired                显示已过期的keys
  expiring [hours]       显示即将过期的keys（默认24小时）
  test [count]           测试轮询功能
  set <key> <created>    设置key的创建时间（ISO格式）
  
  备用key管理:
  fallback set <key> [base_url]  设置备用key（永不过期）
  fallback show                  显示备用key状态
  fallback clear                 清除备用key

示例:
  python manage_keys.py add sk-xxxxxxxxxxxxx
  python manage_keys.py replace sk-old sk-new
  python manage_keys.py expiring 48
  python manage_keys.py fallback set sk-backup-key https://api.example.com
  python manage_keys.py fallback show
""")


def list_keys():
    """列出所有API keys"""
    keys = key_manager.api_keys
    if not keys:
        print("❌ 没有配置任何API keys")
        return
    
    stats = key_manager.get_stats()
    print(f"🔑 当前配置的API keys ({len(keys)}个):")
    print("-" * 60)
    
    for key, details in stats['key_details'].items():
        # 状态图标
        if details['is_expired']:
            status = "🚫 已过期"
        elif details['in_cooldown']:
            status = "⏳ 冷却中"
        elif not details['healthy']:
            status = "❌ 不健康"
        elif details['active_requests'] > 0:
            status = "🔄 使用中"
        else:
            status = "✅ 可用"
        
        print(f"\n{details['masked']}")
        print(f"  状态: {status}")
        print(f"  请求: {details['requests']} | 错误: {details['errors']} | 活跃: {details['active_requests']}")
        
        # 有效期信息
        if details['is_fallback']:
            print(f"  有效期: ∞ (备用key)")
        else:
            remaining = details['remaining_seconds']
            if remaining <= 0:
                print(f"  有效期: ❌ 已过期")
            else:
                days = int(remaining // 86400)
                hours = int((remaining % 86400) // 3600)
                mins = int((remaining % 3600) // 60)
                if days > 0:
                    print(f"  有效期: {days}天{hours}小时")
                elif hours > 0:
                    print(f"  有效期: {hours}小时{mins}分钟 ⚠️")
                else:
                    print(f"  有效期: {mins}分钟 🚨")
        
        # 创建时间
        created = datetime.fromtimestamp(details['created_at'])
        print(f"  创建于: {created.strftime('%Y-%m-%d %H:%M')}")


def show_stats():
    """显示统计信息"""
    stats = key_manager.get_stats()
    
    print("📊 API Key统计信息")
    print("=" * 50)
    print(f"\n📈 总览:")
    print(f"   总keys数: {stats['total_keys']}")
    print(f"   可用keys: {stats['healthy_keys']}")
    print(f"   过期keys: {stats['expired_keys']}")
    print(f"   总请求数: {stats['total_requests']}")
    print(f"   总错误数: {stats['total_errors']}")
    
    if stats['total_requests'] > 0:
        success_rate = ((stats['total_requests'] - stats['total_errors']) / stats['total_requests']) * 100
        print(f"   成功率: {success_rate:.1f}%")
    
    print(f"\n⚙️ 配置:")
    cfg = stats['config']
    print(f"   QPS限制: {cfg['qps_limit']}/s")
    print(f"   并发限制: {cfg['concurrency_limit']}")
    print(f"   有效期: {cfg['max_age_days']}天")
    print(f"   冷却时间: {cfg['cooldown_seconds']}秒")
    print(f"   策略: {cfg['strategy']}")


def add_key(api_key):
    """添加API key"""
    if not api_key.startswith('sk-'):
        print("⚠️ API key通常以'sk-'开头，确定要添加吗？")
    
    success = key_manager.add_key(api_key)
    if success:
        print(f"✅ 已添加API key: {key_manager._mask_key(api_key)}")
        print(f"📈 现在共有 {len(key_manager.api_keys)} 个API keys")
    else:
        print(f"❌ 添加失败")


def remove_key(api_key):
    """移除API key"""
    success = key_manager.remove_key(api_key)
    if success:
        print(f"✅ 已移除API key: {key_manager._mask_key(api_key)}")
        print(f"📉 剩余 {len(key_manager.api_keys)} 个API keys")
    else:
        print("❌ 未找到指定的API key")


def replace_key(old_key, new_key):
    """替换API key"""
    success = key_manager.replace_key(old_key, new_key)
    if success:
        print(f"✅ 已替换Key:")
        print(f"   旧: {key_manager._mask_key(old_key)}")
        print(f"   新: {key_manager._mask_key(new_key)}")
    else:
        print(f"❌ 未找到旧key: {key_manager._mask_key(old_key)}")


def show_expired():
    """显示已过期的keys"""
    expired = key_manager.get_expired_keys()
    if not expired:
        print("✅ 没有过期的keys")
        return
    
    print(f"🚨 已过期的keys ({len(expired)}个):")
    print("-" * 50)
    for key, expired_at in expired:
        expired_time = datetime.fromtimestamp(expired_at)
        print(f"  {key_manager._mask_key(key)}")
        print(f"    过期于: {expired_time.strftime('%Y-%m-%d %H:%M')}")


def show_expiring(hours=24):
    """显示即将过期的keys"""
    expiring = key_manager.get_expiring_keys(within_hours=hours)
    if not expiring:
        print(f"✅ 没有{hours}小时内将过期的keys")
        return
    
    print(f"⚠️ {hours}小时内将过期的keys ({len(expiring)}个):")
    print("-" * 50)
    for key, expired_at, remaining in expiring:
        expired_time = datetime.fromtimestamp(expired_at)
        remaining_hours = remaining / 3600
        print(f"  {key_manager._mask_key(key)}")
        print(f"    剩余: {remaining_hours:.1f}小时")
        print(f"    过期于: {expired_time.strftime('%Y-%m-%d %H:%M')}")


def test_round_robin(count=10):
    """测试轮询功能"""
    print(f"🧪 测试轮询功能 (获取{count}个keys):")
    print("-" * 50)
    
    selected_keys = []
    for i in range(count):
        key = key_manager.get_next_key()
        if key:
            masked = key_manager._mask_key(key)
            selected_keys.append(masked)
            print(f"  {i+1}. {masked}")
            # 模拟请求完成后释放
            key_manager.release_key(key)
        else:
            print(f"  {i+1}. ❌ 无可用key")
    
    # 统计分布
    if selected_keys:
        from collections import Counter
        distribution = Counter(selected_keys)
        print(f"\n📈 分布统计:")
        for key, cnt in distribution.items():
            bar = "█" * cnt
            print(f"  {key}: {bar} ({cnt}次)")


def set_created_time(api_key, created_str):
    """设置key的创建时间"""
    try:
        # 解析ISO格式时间
        created_at = datetime.fromisoformat(created_str).timestamp()
    except ValueError:
        print(f"❌ 时间格式错误，请使用ISO格式，如: 2026-03-01T00:00:00")
        return
    
    stats = key_manager.key_stats.get(api_key)
    if not stats:
        print(f"❌ 未找到key: {key_manager._mask_key(api_key)}")
        return
    
    old_created = datetime.fromtimestamp(stats.created_at)
    new_created = datetime.fromtimestamp(created_at)
    
    stats.created_at = created_at
    # 保存到配置文件
    key_manager._save_config()
    
    print(f"✅ 已更新key创建时间:")
    print(f"   {key_manager._mask_key(api_key)}")
    print(f"   旧: {old_created.strftime('%Y-%m-%d %H:%M')}")
    print(f"   新: {new_created.strftime('%Y-%m-%d %H:%M')}")
    
    # 显示新的有效期
    remaining = stats.get_remaining_time(key_manager.max_age_days)
    if remaining <= 0:
        print(f"   状态: 🚫 已过期")
    else:
        print(f"   剩余: {remaining/3600:.1f}小时")


def set_fallback_key(api_key, base_url=None):
    """设置备用key"""
    success = key_manager.set_fallback_key(api_key, base_url)
    if success:
        print(f"\n📌 备用key特性:")
        print(f"   • 永不过期")
        print(f"   • 不参与正常轮询")
        print(f"   • 当所有主key都不可用时自动启用")
        print(f"   • 用于协助更新主key")


def show_fallback():
    """显示备用key状态"""
    status = key_manager.get_fallback_status()
    if not status:
        print("⚠️ 没有设置备用key")
        print("\n使用以下命令设置备用key:")
        print("  python manage_keys.py fallback set <key> [base_url]")
        return
    
    print("📌 备用Key状态")
    print("-" * 50)
    print(f"   Key: {status['masked']}")
    print(f"   状态: {'✅ 可用' if status['healthy'] and not status['in_cooldown'] else '❌ 不可用'}")
    print(f"   请求: {status['requests']} | 错误: {status['errors']} | 活跃: {status['active_requests']}")
    print(f"   有效期: ∞ (永不过期)")
    if status['base_url']:
        print(f"   Base URL: {status['base_url']}")
    
    # 检查主key状态
    all_expired = key_manager.get_all_regular_keys_expired()
    if all_expired:
        print(f"\n⚠️ 所有主key已过期，备用key将自动启用！")


def clear_fallback():
    """清除备用key"""
    key_manager.clear_fallback_key()


def main():
    """主函数"""
    if len(sys.argv) < 2:
        show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command in ("help", "-h", "--help"):
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
    elif command == "replace":
        if len(sys.argv) < 4:
            print("❌ 请提供旧key和新key")
            return
        replace_key(sys.argv[2], sys.argv[3])
    elif command == "expired":
        show_expired()
    elif command == "expiring":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 24
        show_expiring(hours)
    elif command == "test":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        test_round_robin(count)
    elif command == "set":
        if len(sys.argv) < 4:
            print("❌ 请提供key和创建时间")
            return
        set_created_time(sys.argv[2], sys.argv[3])
    elif command == "fallback":
        if len(sys.argv) < 3:
            print("❌ 请提供fallback子命令: set, show, clear")
            return
        sub_cmd = sys.argv[2].lower()
        if sub_cmd == "set":
            if len(sys.argv) < 4:
                print("❌ 请提供备用key")
                return
            api_key = sys.argv[3]
            base_url = sys.argv[4] if len(sys.argv) > 4 else None
            set_fallback_key(api_key, base_url)
        elif sub_cmd == "show":
            show_fallback()
        elif sub_cmd == "clear":
            clear_fallback()
        else:
            print(f"❌ 未知的fallback子命令: {sub_cmd}")
            print("   可用: set, show, clear")
    else:
        print(f"❌ 未知命令: {command}")
        show_help()


if __name__ == "__main__":
    main()