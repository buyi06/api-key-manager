# API Key 轮询管理器

一个支持多个 API key 的负载均衡和故障转移的 Python 管理系统，专为高并发场景设计。

## ✨ 特性

- 🔄 **多策略轮询**: 支持 round-robin 和 least-used 两种负载均衡策略
- 🛡️ **QPS限制**: 每个key独立QPS限制（默认10/s），防止触发API限流
- 🔒 **并发限制**: 每个key独立并发限制（默认1），防止并发冲突
- ⏰ **有效期管理**: 每个key 7天有效期，过期自动标记，支持过期提醒
- 🚨 **智能故障转移**: 自动检测 429 错误并临时禁用限流的 API key
- 🔧 **备用key支持**: 主key全部不可用时自动切换到备用key
- 🔧 **动态管理**: 支持运行时添加、移除、替换 API key
- 📊 **统计监控**: 实时统计每个 key 的使用情况、健康状态、剩余有效期
- 💾 **配置持久化**: 自动保存配置到 JSON 文件
- 🎯 **线程安全**: 使用锁机制确保并发安全
- 📁 **本地配置优先**: 优先使用 config.local.json 存储敏感信息

## 📁 文件结构

```
api-key-manager/
├── api_key_manager.py    # 核心管理器类
├── manage_keys.py        # 命令行管理工具
├── compatibility_test.py # 兼容性测试套件
├── openclaw_integration_guide.md # OpenClaw集成指南
└── README.md            # 项目说明
```

## 🚀 快速开始

### 1. 基本使用

```python
from api_key_manager import key_manager

# 获取下一个可用的 API key
api_key = key_manager.get_next_key()
if not api_key:
    print("没有可用的 API key")
    return

# 标记错误
key_manager.mark_error(api_key, "429")

# 获取统计信息
stats = key_manager.get_stats()
print(f"健康key数量: {stats['healthy_keys']}/{stats['total_keys']}")
```

### 2. 配置文件格式

```json
{
  "providers": {
    "custom": {
      "apiKeys": [
        "sk-第一个key",
        "sk-第二个key", 
        "sk-第三个key"
      ],
      "limits": {
        "qps": 10,
        "concurrency": 1,
        "maxAgeDays": 7,
        "cooldownSeconds": 30
      },
      "loadBalancing": {
        "strategy": "round-robin"
      },
      "fallback": {
        "enabled": true,
        "apiKey": "ak_备用key",
        "name": "备用Key"
      },
      "keyMetadata": {
        "sk-第一个key": {
          "created_at": 1709510400
        }
      }
    }
  }
}
```

**配置说明:**
- `limits.qps`: 每个key的QPS限制（默认10）
- `limits.concurrency`: 每个key的并发限制（默认1）
- `limits.maxAgeDays`: key的有效期天数（默认7）
- `limits.cooldownSeconds`: 429错误冷却时间（默认30）
- `keyMetadata`: 保存key的创建时间，用于有效期计算
```

### 3. 命令行工具

```bash
# 添加新的 API key
python3 manage_keys.py add sk-your-new-api-key

# 移除 API key
python3 manage_keys.py remove sk-old-api-key

# 替换 API key（用于过期更换）
python3 manage_keys.py replace sk-old-key sk-new-key

# 列出所有 keys 及状态
python3 manage_keys.py list

# 查看统计信息
python3 manage_keys.py stats

# 查看已过期的keys
python3 manage_keys.py expired

# 查看即将过期的keys（默认24小时）
python3 manage_keys.py expiring

# 查看即将过期的keys（48小时内）
python3 manage_keys.py expiring 48

# 测试轮询功能
python3 manage_keys.py test

# 设置key的创建时间（用于恢复已知key）
python3 manage_keys.py set sk-xxx "2026-03-01T00:00:00"
```

## 📋 API 参考

### APIKeyManager 类

#### 主要方法

- `get_next_key()` - 获取下一个可用的 API key（自动跳过不健康、过期、限流、并发满的key）
- `release_key(api_key)` - 释放key（请求完成后必须调用，减少并发计数）
- `add_key(api_key, created_at=None)` - 添加新的 API key
- `remove_key(api_key)` - 移除 API key
- `replace_key(old_key, new_key)` - 替换 API key（用于过期更换）
- `mark_error(api_key, error_type, retry_after=None)` - 标记 key 出错
- `get_stats()` - 获取统计信息
- `get_expired_keys()` - 获取所有过期的key
- `get_expiring_keys(within_hours=24)` - 获取即将过期的key
- `load_config()` - 加载配置文件

#### 负载均衡策略

1. **round-robin**: 轮询分配，跳过不健康和QPS限制的key
2. **least-used**: 选择使用次数最少的健康key

#### QPS限制

- **默认限制**: 每个key最多10次/秒
- **时间窗口**: 1秒
- **自动清理**: 超过时间窗口的请求自动清理
- **智能跳过**: 达到限制的key自动跳过

#### 并发限制

- **默认限制**: 每个key同时最多1个请求
- **自动跟踪**: 实时跟踪每个key的活跃请求数
- **必须释放**: 请求完成后必须调用 `release_key()` 释放

#### 有效期管理

- **默认有效期**: 7天
- **自动过期**: 过期后自动标记为不可用
- **备用key例外**: 备用key永不过期
- **后台清理**: 每小时自动检查过期key
- **过期提醒**: 支持查询即将过期的key

#### 错误处理

- **429**: 临时限流，30秒冷却后自动恢复
- **401**: 认证错误，标记为永久不健康
- **其他错误**: 记录统计但不影响key状态

#### 备用key机制

- **自动添加**: 备用key自动加入key池
- **优先级**: 主key优先，备用key作为最后选择
- **独立统计**: 备用key有独立的使用统计

## 🔧 系统要求

- Python 3.7+
- threading (标准库)
- json (标准库)
- time (标准库)
- collections (标准库)

## 📊 统计信息示例

```json
{
  "total_keys": 4,
  "healthy_keys": 4,
  "total_requests": 100,
  "total_errors": 2,
  "key_details": {
    "sk-key1": {
      "requests": 35,
      "errors": 1,
      "last_used": 1677648900.0,
      "healthy": true,
      "request_times": [1677648895.0, 1677648896.0, ...],
      "is_fallback": false
    },
    "ak_fallback": {
      "requests": 5,
      "errors": 0,
      "last_used": 1677648950.0,
      "healthy": true,
      "request_times": [1677648948.0, 1677648949.0, ...],
      "is_fallback": true
    }
  }
}
```

## 🛠️ 集成示例

### ✅ 已验证兼容的系统

#### 1. nanobot 集成 (完全兼容)
```python
# nanobot 自动集成，无需额外配置
# CustomProvider 已内置 API Key 轮询功能
from nanobot.providers.custom_provider import CustomProvider

provider = CustomProvider(
    api_base="https://apis.iflow.cn/v1",
    default_model="glm-4.6"
)
# 自动轮询多个 API keys，429 错误自动处理，QPS限制保护
```

#### 2. OpenClaw 集成 (完全兼容)
```python
from api_key_manager import APIKeyManager

# 创建管理器实例
manager = APIKeyManager(config_path="openclaw_config.json")

# 获取 API key
api_key = manager.get_next_key()
if not api_key:
    print("没有可用的 API key")
    return

# 使用 API key 进行请求
try:
    response = make_llm_request(api_key, prompt)
except Exception as e:
    if "429" in str(e):
        manager.mark_error(api_key, "429")
    raise
```

### 通用集成模式
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

## 🎯 性能特性

### QPS管理
- **独立限制**: 每个key独立的QPS限制
- **智能分配**: 自动跳过达到限制的key
- **实时监控**: 实时跟踪每个key的请求频率
- **自动恢复**: 限制解除后自动恢复使用

### 故障转移
- **快速检测**: 429错误立即检测和处理
- **智能冷却**: 30秒冷却期，避免频繁切换
- **自动恢复**: 冷却结束后自动恢复健康状态
- **备用保障**: 主key全部失效时自动使用备用key

### 负载均衡
- **轮询策略**: 平均分配请求负载
- **最少使用**: 优先使用使用次数少的key
- **健康检查**: 自动跳过不健康的key
- **统计驱动**: 基于实时统计进行智能分配

## 🧪 兼容性测试

项目包含完整的兼容性测试套件：

```bash
# 运行兼容性测试
python3 compatibility_test.py
```

### 测试覆盖范围
- ✅ nanobot 集成测试
- ✅ OpenClaw 兼容性测试  
- ✅ 轮询功能测试
- ✅ QPS限制测试
- ✅ 错误处理测试
- ✅ 备用key测试
- ✅ 配置管理测试

### 测试结果
```
🧪 API Key管理器兼容性测试开始

🤖 测试nanobot集成...
✅ API Key管理器导入成功
✅ 获取API key成功
✅ 统计信息: 4个keys, 4个健康
✅ CustomProvider导入成功
✅ CustomProvider实例创建成功

🔧 测试OpenClaw兼容性...
✅ OpenClaw项目目录存在
✅ OpenClaw API Key管理器创建成功
✅ 轮询功能正常
✅ 错误处理功能正常

🎯 测试QPS限制...
✅ QPS限制功能正常
✅ 请求时间戳队列工作正常

🛡️ 测试备用key...
✅ 备用key配置正常
✅ 故障转移功能正常

🎉 所有测试通过！API Key管理器可以在两个系统中正常使用！
```

## 📚 详细文档

- [OpenClaw 集成指南](openclaw_integration_guide.md) - 详细的 OpenClaw 集成步骤
- [兼容性测试代码](compatibility_test.py) - 完整的测试套件

## 🔄 版本历史

### v3.0.0 (最新)
- ✨ 新增 并发限制功能（每个key同时只能1个请求）
- ✨ 新增 有效期管理（7天过期自动标记）
- ✨ 新增 `release_key()` 方法（请求完成必须调用）
- ✨ 新增 `replace_key()` 方法（方便过期更换）
- ✨ 新增 `get_expired_keys()` / `get_expiring_keys()` 方法
- ✨ 新增 后台清理线程（每小时检查过期key）
- 🔧 优化 CLI工具支持过期管理命令
- 🔧 优化 统计信息包含剩余有效期

### v2.0.0
- ✨ 新增 QPS限制功能
- ✨ 新增 备用key支持
- ✨ 新增 请求时间戳队列
- ✨ 新增 本地配置文件优先
- 🔧 优化 轮询算法
- 🔧 优化 错误处理机制

### v1.0.0
- 🎉 初始版本发布
- ✨ 基础轮询功能
- ✨ 故障转移机制
- ✨ 统计监控

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发指南
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

MIT License

## 📞 联系

如有问题，请通过 GitHub Issues 联系。

---

**⭐ 如果这个项目对你有帮助，请给个星标支持！**