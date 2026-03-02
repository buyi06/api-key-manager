# OpenClaw API Key管理器集成指南

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
