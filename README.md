# API Key 轮询管理器

一个支持多个 API key 的负载均衡和简单故障转移的 Python 管理系统。

## ✨ 特性

- 🔄 **多策略轮询**: 支持 round-robin 和 least-used 两种负载均衡策略
- 🛡️ **故障转移**: 自动检测 429 错误并临时禁用限流的 API key
- 🔧 **动态管理**: 支持运行时添加和移除 API key
- 📊 **统计监控**: 实时统计每个 key 的使用情况和健康状态
- 💾 **配置持久化**: 自动保存配置到 JSON 文件
- 🎯 **线程安全**: 使用锁机制确保并发安全

## 📁 文件结构

```
api-key-manager/
├── api_key_manager.py    # 核心管理器类
├── manage_keys.py        # 命令行管理工具
└── README.md            # 项目说明
```

## 🚀 快速开始

### 1. 基本使用

```python
from api_key_manager import key_manager

# 获取下一个可用的 API key
api_key = key_manager.get_next_key()

# 标记错误
key_manager.mark_error(api_key, "429")

# 获取统计信息
stats = key_manager.get_stats()
```

### 2. 命令行工具

```bash
# 添加新的 API key
python manage_keys.py add sk-your-new-api-key

# 移除 API key
python manage_keys.py remove sk-old-api-key

# 列出所有 keys
python manage_keys.py list

# 查看统计信息
python manage_keys.py stats

# 测试轮询功能
python manage_keys.py test
```

### 3. 配置文件格式

```json
{
  "providers": {
    "custom": {
      "apiKeys": [
        "sk-第一个key",
        "sk-第二个key",
        "sk-第三个key"
      ],
      "loadBalancing": {
        "strategy": "round-robin",
        "healthCheck": true,
        "failover": true,
        "healthCheckInterval": 30
      }
    }
  }
}
```

## 📋 API 参考

### APIKeyManager 类

#### 主要方法

- `get_next_key()` - 获取下一个可用的 API key
- `add_key(api_key)` - 添加新的 API key
- `remove_key(api_key)` - 移除 API key
- `mark_error(api_key, error_type)` - 标记 key 出错
- `get_stats()` - 获取统计信息
- `load_config()` - 加载配置文件

#### 负载均衡策略

1. **round-robin**: 轮询分配，跳过不健康的 key
2. **least-used**: 选择使用次数最少的健康 key

#### 错误处理

- **429**: 临时限流，30秒冷却后自动恢复
- **401**: 认证错误，标记为永久不健康

## 🔧 系统要求

- Python 3.7+
- threading (标准库)
- json (标准库)
- time (标准库)

## 📊 统计信息示例

```json
{
  "total_keys": 3,
  "healthy_keys": 3,
  "total_requests": 100,
  "total_errors": 2,
  "key_details": {
    "sk-key1": {
      "requests": 35,
      "errors": 1,
      "last_used": 1677648900.0,
      "healthy": true
    }
  }
}
```

## 🛠️ 集成示例

### 集成到 nanobot

```python
# 在 API 调用中使用
api_key = key_manager.get_next_key()
if not api_key:
    raise Exception("No healthy API keys available")

try:
    response = make_api_call(api_key, request_data)
except Exception as e:
    if "429" in str(e):
        key_manager.mark_error(api_key, "429")
    raise
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📞 联系

如有问题，请通过 GitHub Issues 联系。