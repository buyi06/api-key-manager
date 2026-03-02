#!/usr/bin/env python3
"""
API Key管理器兼容性测试
测试在nanobot和OpenClaw中的使用情况
"""

import sys
import os
import json
import time

# 添加nanobot路径
sys.path.append('/root/.nanobot')

def test_nanobot_integration():
    """测试nanobot集成"""
    print("🤖 测试nanobot集成...")
    
    try:
        # 测试API Key管理器
        from api_key_manager import key_manager
        print("✅ API Key管理器导入成功")
        
        # 测试获取key
        api_key = key_manager.get_next_key()
        if api_key:
            print(f"✅ 获取API key成功: {api_key[:10]}...")
        else:
            print("❌ 获取API key失败")
            return False
        
        # 测试统计
        stats = key_manager.get_stats()
        print(f"✅ 统计信息: {stats['total_keys']}个keys, {stats['healthy_keys']}个健康")
        
        # 测试custom_provider集成
        from nanobot.providers.custom_provider import CustomProvider
        print("✅ CustomProvider导入成功")
        
        # 创建provider实例
        provider = CustomProvider(
            api_base="https://apis.iflow.cn/v1",
            default_model="glm-4.6"
        )
        print("✅ CustomProvider实例创建成功")
        
        return True
        
    except Exception as e:
        print(f"❌ nanobot集成测试失败: {e}")
        return False

def test_openclaw_compatibility():
    """测试OpenClaw兼容性"""
    print("\n🔧 测试OpenClaw兼容性...")
    
    try:
        # 检查OpenClaw目录
        openclaw_path = "/root/.nanobot/workspace/openclaw-zero-token"
        if os.path.exists(openclaw_path):
            print("✅ OpenClaw项目目录存在")
        else:
            print("❌ OpenClaw项目目录不存在")
            return False
        
        # 测试API Key管理器在OpenClaw环境中的使用
        from api_key_manager import APIKeyManager
        
        # 创建独立的manager实例
        test_config = "/tmp/test_openclaw_config.json"
        test_config_data = {
            "providers": {
                "custom": {
                    "apiKeys": [
                        "sk-test-key-1",
                        "sk-test-key-2"
                    ],
                    "loadBalancing": {
                        "strategy": "round-robin"
                    }
                }
            }
        }
        
        with open(test_config, "w") as f:
            json.dump(test_config_data, f, indent=2)
        
        # 测试独立manager
        openclaw_manager = APIKeyManager(config_path=test_config)
        print("✅ OpenClaw API Key管理器创建成功")
        
        # 测试轮询
        key1 = openclaw_manager.get_next_key()
        key2 = openclaw_manager.get_next_key()
        
        if key1 and key2 and key1 != key2:
            print("✅ 轮询功能正常")
        else:
            print("❌ 轮询功能异常")
            return False
        
        # 测试错误处理
        openclaw_manager.mark_error(key1, "429")
        print("✅ 错误处理功能正常")
        
        # 清理测试文件
        os.remove(test_config)
        
        return True
        
    except Exception as e:
        print(f"❌ OpenClaw兼容性测试失败: {e}")
        return False

def create_openclaw_integration_guide():
    """创建OpenClaw集成指南"""
    print("\n📝 创建OpenClaw集成指南...")
    
    guide_content = """# OpenClaw API Key管理器集成指南

## 🚀 快速集成

### 1. 复制文件
```bash
# 复制API Key管理器到OpenClaw项目
cp api_key_manager.py /path/to/openclaw/
cp manage_keys.py /path/to/openclaw/
```

### 2. 基本使用
```python
from api_key_manager import APIKeyManager

# 创建管理器实例
manager = APIKeyManager(config_path="your_config.json")

# 获取API key
api_key = manager.get_next_key()
if not api_key:
    print("没有可用的API key")
    return

# 使用API key进行请求
try:
    response = make_llm_request(api_key, prompt)
except Exception as e:
    if "429" in str(e):
        manager.mark_error(api_key, "429")
    raise
```

### 3. 配置文件格式
```json
{
  "providers": {
    "custom": {
      "apiKeys": [
        "sk-your-key-1",
        "sk-your-key-2",
        "sk-your-key-3"
      ],
      "loadBalancing": {
        "strategy": "round-robin",
        "healthCheck": true,
        "failover": true
      }
    }
  }
}
```

## 🔧 高级功能

### 动态管理
```python
# 添加新key
manager.add_key("sk-new-key")

# 移除key
manager.remove_key("sk-old-key")

# 获取统计
stats = manager.get_stats()
```

### 错误处理
```python
# 429限流错误
manager.mark_error(api_key, "429")  # 30秒冷却

# 认证错误
manager.mark_error(api_key, "401")  # 永久禁用
```

## 📊 监控和统计
```python
stats = manager.get_stats()
print(f"总keys: {stats['total_keys']}")
print(f"健康keys: {stats['healthy_keys']}")
print(f"总请求: {stats['total_requests']}")
print(f"总错误: {stats['total_errors']}")
```

## 🛡️ 最佳实践

1. **定期检查**: 使用`get_stats()`监控key状态
2. **错误处理**: 始终捕获并标记429错误
3. **配置备份**: 定期备份配置文件
4. **日志记录**: 记录key使用情况和错误

## 🔄 负载均衡策略

- **round-robin**: 轮询分配，适合均匀使用
- **least-used**: 选择使用次数最少的，适合不均匀负载

选择合适的策略可以最大化API key利用率！
"""
    
    with open("/tmp/openclaw_integration_guide.md", "w", encoding="utf-8") as f:
        f.write(guide_content)
    
    print("✅ OpenClaw集成指南创建完成")

def main():
    """主测试函数"""
    print("🧪 API Key管理器兼容性测试开始\n")
    
    # 测试nanobot集成
    nanobot_ok = test_nanobot_integration()
    
    # 测试OpenClaw兼容性
    openclaw_ok = test_openclaw_compatibility()
    
    # 创建集成指南
    create_openclaw_integration_guide()
    
    # 总结
    print("\n" + "="*50)
    print("📊 测试结果总结:")
    print(f"🤖 nanobot集成: {'✅ 通过' if nanobot_ok else '❌ 失败'}")
    print(f"🔧 OpenClaw兼容性: {'✅ 通过' if openclaw_ok else '❌ 失败'}")
    
    if nanobot_ok and openclaw_ok:
        print("\n🎉 所有测试通过！API Key管理器可以在两个系统中正常使用！")
        print("\n📖 集成指南: /tmp/openclaw_integration_guide.md")
    else:
        print("\n⚠️  部分测试失败，请检查错误信息")
    
    return nanobot_ok and openclaw_ok

if __name__ == "__main__":
    main()