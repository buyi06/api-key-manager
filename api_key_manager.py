#!/usr/bin/env python3
"""
API Key 轮询管理器
支持多个 API key 的负载均衡和故障转移

特性:
- 并发限制: 每个key同时只能1个请求
- QPS限制: 每个key限制10 QPS
- 有效期: 每个key 7天有效期，过期自动标记
- 智能故障转移: 429错误自动冷却
"""

import json
import time
import threading
from typing import List, Dict, Optional, Tuple
from collections import deque
from datetime import datetime, timedelta
from dataclasses import dataclass, field


@dataclass
class KeyStats:
    """单个Key的统计信息"""
    requests: int = 0
    errors: int = 0
    last_used: float = 0.0
    healthy: bool = True
    request_times: deque = field(default_factory=lambda: deque(maxlen=100))
    active_requests: int = 0  # 当前活跃请求数
    created_at: float = field(default_factory=time.time)  # key添加时间
    is_fallback: bool = False
    cooldown_until: float = 0.0  # 冷却结束时间
    
    def is_expired(self, max_age_days: float = 7.0) -> bool:
        """检查key是否过期"""
        return time.time() - self.created_at > max_age_days * 24 * 3600
    
    def is_in_cooldown(self) -> bool:
        """检查是否在冷却期"""
        return time.time() < self.cooldown_until
    
    def get_remaining_time(self, max_age_days: float = 7.0) -> float:
        """获取剩余有效时间（秒）"""
        remaining = max_age_days * 24 * 3600 - (time.time() - self.created_at)
        return max(0, remaining)


class APIKeyManager:
    # 默认配置
    DEFAULT_QPS_LIMIT = 10
    DEFAULT_CONCURRENCY_LIMIT = 1
    DEFAULT_MAX_AGE_DAYS = 7.0
    DEFAULT_COOLDOWN_SECONDS = 30.0
    
    def __init__(self, config_path: str = "/root/.nanobot/config.json"):
        import os
        
        # 优先使用本地配置文件
        local_config_path = config_path.replace(".json", ".local.json")
        if os.path.exists(local_config_path):
            self.config_path = local_config_path
        else:
            self.config_path = config_path
        
        # Key池
        self.api_keys: List[str] = []
        self.current_index: int = 0
        
        # 限制配置
        self.qps_limit = self.DEFAULT_QPS_LIMIT
        self.concurrency_limit = self.DEFAULT_CONCURRENCY_LIMIT
        self.max_age_days = self.DEFAULT_MAX_AGE_DAYS
        self.cooldown_seconds = self.DEFAULT_COOLDOWN_SECONDS
        self.qps_window = 1.0  # QPS时间窗口
        
        # 统计信息
        self.key_stats: Dict[str, KeyStats] = {}
        
        # 线程安全
        self.lock = threading.RLock()
        
        # 负载均衡策略
        self.strategy = "round-robin"
        
        # 备用key
        self.fallback_key: Optional[str] = None
        self.fallback_config: Optional[Dict] = None
        
        # 加载配置
        self.load_config()
        
        # 启动后台清理线程
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动后台线程定期清理过期key"""
        def cleanup_loop():
            while True:
                time.sleep(3600)  # 每小时检查一次
                self._cleanup_expired_keys()
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
    
    def _cleanup_expired_keys(self):
        """清理过期的key"""
        with self.lock:
            expired_keys = [
                k for k in self.api_keys 
                if self.key_stats.get(k) and self.key_stats[k].is_expired(self.max_age_days)
            ]
            for key in expired_keys:
                if key != self.fallback_key:  # 保留备用key
                    print(f"⚠️ Key已过期（{self.max_age_days}天）: {self._mask_key(key)}")
                    # 标记为不健康而不是直接移除，让用户决定
                    self.key_stats[key].healthy = False
    
    def load_config(self):
        """加载配置文件"""
        import os
        
        if not os.path.exists(self.config_path):
            print(f"⚠️ 配置文件不存在: {self.config_path}")
            return
        
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)
            
            providers = config.get("providers", {})
            custom = providers.get("custom", {})
            
            # 加载key池
            self.api_keys = custom.get("apiKeys", [])
            
            # 加载限制配置
            limits = custom.get("limits", {})
            self.qps_limit = limits.get("qps", self.DEFAULT_QPS_LIMIT)
            self.concurrency_limit = limits.get("concurrency", self.DEFAULT_CONCURRENCY_LIMIT)
            self.max_age_days = limits.get("maxAgeDays", self.DEFAULT_MAX_AGE_DAYS)
            self.cooldown_seconds = limits.get("cooldownSeconds", self.DEFAULT_COOLDOWN_SECONDS)
            
            # 加载负载均衡策略
            lb = custom.get("loadBalancing", {})
            self.strategy = lb.get("strategy", "round-robin")
            
            # 加载备用key
            fallback = custom.get("fallback", {})
            if fallback.get("enabled", False):
                self.fallback_key = fallback.get("apiKey")
                self.fallback_config = fallback
                if self.fallback_key and self.fallback_key not in self.api_keys:
                    self.api_keys.append(self.fallback_key)
            
            # 初始化统计
            # 先加载keyMetadata（包含创建时间）
            key_metadata = custom.get("keyMetadata", {})
            for key in self.api_keys:
                metadata = key_metadata.get(key, {})
                created_at = metadata.get("created_at", time.time())
                if key not in self.key_stats:
                    self.key_stats[key] = KeyStats(
                        created_at=created_at,
                        is_fallback=(key == self.fallback_key)
                    )
                else:
                    # 更新已存在的key的创建时间
                    self.key_stats[key].created_at = created_at
            
            print(f"✅ 已加载 {len(self.api_keys)} 个API keys")
            print(f"   QPS限制: {self.qps_limit}/s, 并发限制: {self.concurrency_limit}, 有效期: {self.max_age_days}天")
            
        except Exception as e:
            print(f"❌ 加载配置失败: {e}")
    
    def _is_key_rate_limited(self, api_key: str) -> bool:
        """检查key是否超过QPS限制"""
        stats = self.key_stats.get(api_key)
        if not stats:
            return False
        
        current_time = time.time()
        request_times = stats.request_times
        
        # 清理过期的时间戳
        while request_times and current_time - request_times[0] > self.qps_window:
            request_times.popleft()
        
        return len(request_times) >= self.qps_limit
    
    def _is_key_at_concurrency_limit(self, api_key: str) -> bool:
        """检查key是否达到并发限制"""
        stats = self.key_stats.get(api_key)
        if not stats:
            return False
        return stats.active_requests >= self.concurrency_limit
    
    def _is_key_available(self, api_key: str, include_fallback: bool = False) -> bool:
        """检查key是否可用（健康、未过期、未限流、未达并发限制）
        
        Args:
            api_key: 要检查的key
            include_fallback: 是否包含备用key（默认不包含）
        """
        stats = self.key_stats.get(api_key)
        if not stats:
            return False
        
        # 备用key需要特殊处理
        if stats.is_fallback and not include_fallback:
            return False
        
        # 检查健康状态
        if not stats.healthy:
            return False
        
        # 备用key永不过期，普通key检查过期
        if not stats.is_fallback and stats.is_expired(self.max_age_days):
            return False
        
        # 检查是否在冷却期
        if stats.is_in_cooldown():
            return False
        
        # 检查QPS限制
        if self._is_key_rate_limited(api_key):
            return False
        
        # 检查并发限制
        if self._is_key_at_concurrency_limit(api_key):
            return False
        
        return True
    
    def get_next_key(self) -> Optional[str]:
        """获取下一个可用的API key
        
        优先使用普通key，当所有普通key都不可用时才使用备用key
        """
        with self.lock:
            if not self.api_keys:
                return None
            
            # 先尝试普通key（不包含fallback）
            if self.strategy == "least-used":
                key = self._least_used(include_fallback=False)
            else:
                key = self._round_robin(include_fallback=False)
            
            # 如果没有可用的普通key，尝试备用key
            if key is None and self.fallback_key:
                key = self._get_fallback_key()
                if key:
                    print(f"🔄 所有主key不可用，使用备用key")
            
            return key
    
    def _get_fallback_key(self) -> Optional[str]:
        """获取备用key（如果可用）"""
        if not self.fallback_key:
            return None
        
        stats = self.key_stats.get(self.fallback_key)
        if not stats:
            return None
        
        # 备用key检查：健康、不在冷却、未达限流
        if not stats.healthy or stats.is_in_cooldown():
            return None
        if self._is_key_rate_limited(self.fallback_key):
            return None
        if self._is_key_at_concurrency_limit(self.fallback_key):
            return None
        
        self._record_request_start(self.fallback_key)
        return self.fallback_key
    
    def _round_robin(self, include_fallback: bool = False) -> Optional[str]:
        """轮询策略"""
        n = len(self.api_keys)
        if n == 0:
            return None
        
        attempts = 0
        while attempts < n:
            key = self.api_keys[self.current_index]
            self.current_index = (self.current_index + 1) % n
            
            if self._is_key_available(key, include_fallback=include_fallback):
                # 记录请求
                self._record_request_start(key)
                return key
            
            attempts += 1
        
        # 没有可用的key
        return None
    
    def _least_used(self, include_fallback: bool = False) -> Optional[str]:
        """最少使用策略"""
        available_keys = [k for k in self.api_keys if self._is_key_available(k, include_fallback=include_fallback)]
        if not available_keys:
            return None
        
        best_key = min(available_keys, key=lambda k: self.key_stats[k].requests)
        self._record_request_start(best_key)
        return best_key
    
    def _record_request_start(self, api_key: str):
        """记录请求开始"""
        stats = self.key_stats[api_key]
        current_time = time.time()
        stats.requests += 1
        stats.last_used = current_time
        stats.request_times.append(current_time)
        stats.active_requests += 1
    
    def release_key(self, api_key: str):
        """释放key（请求完成后调用）"""
        with self.lock:
            stats = self.key_stats.get(api_key)
            if stats:
                stats.active_requests = max(0, stats.active_requests - 1)
    
    def mark_error(self, api_key: str, error_type: str = "429", retry_after: Optional[int] = None):
        """
        标记key出错
        
        Args:
            api_key: 出错的key
            error_type: 错误类型 (429, 401, 403等)
            retry_after: 服务器建议的重试等待时间（秒）
        """
        with self.lock:
            stats = self.key_stats.get(api_key)
            if not stats:
                return
            
            stats.errors += 1
            
            if error_type == "429":
                # 限流错误：进入冷却
                cooldown = retry_after if retry_after else int(self.cooldown_seconds)
                stats.cooldown_until = time.time() + cooldown
                stats.healthy = False
                print(f"⚠️ Key {self._mask_key(api_key)} 触发429，冷却{cooldown}秒")
                
                # 冷却结束后恢复
                threading.Timer(cooldown, self._recover_key, args=[api_key]).start()
                
            elif error_type in ("401", "403", "unauthorized"):
                # 认证错误：永久标记为不健康
                stats.healthy = False
                print(f"❌ Key {self._mask_key(api_key)} 认证失败({error_type})，已标记为不健康")
    
    def _recover_key(self, api_key: str):
        """冷却结束后恢复key"""
        with self.lock:
            stats = self.key_stats.get(api_key)
            if stats:
                stats.healthy = True
                stats.cooldown_until = 0.0
                print(f"✅ Key {self._mask_key(api_key)} 已从冷却中恢复")
    
    def add_key(self, api_key: str, created_at: Optional[float] = None) -> bool:
        """
        添加新的API key
        
        Args:
            api_key: 要添加的key
            created_at: key的创建时间（用于恢复已知的key）
        
        Returns:
            是否添加成功
        """
        with self.lock:
            if api_key in self.api_keys:
                print(f"⚠️ Key已存在: {self._mask_key(api_key)}")
                return False
            
            self.api_keys.append(api_key)
            self.key_stats[api_key] = KeyStats(
                created_at=created_at if created_at else time.time(),
                is_fallback=False
            )
            self._save_config()
            print(f"✅ 已添加Key: {self._mask_key(api_key)}")
            return True
    
    def remove_key(self, api_key: str) -> bool:
        """移除API key"""
        with self.lock:
            if api_key not in self.api_keys:
                return False
            
            self.api_keys.remove(api_key)
            self.key_stats.pop(api_key, None)
            self._save_config()
            print(f"✅ 已移除Key: {self._mask_key(api_key)}")
            return True
    
    def replace_key(self, old_key: str, new_key: str) -> bool:
        """替换key（用于过期更换）"""
        with self.lock:
            if old_key in self.api_keys:
                idx = self.api_keys.index(old_key)
                self.api_keys[idx] = new_key
                self.key_stats.pop(old_key, None)
                self.key_stats[new_key] = KeyStats(created_at=time.time())
                self._save_config()
                print(f"✅ 已替换Key: {self._mask_key(old_key)} -> {self._mask_key(new_key)}")
                return True
            return False
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            import os
            
            # 读取现有配置
            if os.path.exists(self.config_path):
                with open(self.config_path, "r") as f:
                    config = json.load(f)
            else:
                config = {}
            
            providers = config.setdefault("providers", {})
            custom = providers.setdefault("custom", {})
            
            # 保存keys时排除备用key（备用key单独保存）
            regular_keys = [k for k in self.api_keys if k != self.fallback_key]
            custom["apiKeys"] = regular_keys
            
            # 保存key的创建时间（用于恢复）
            key_metadata = {}
            for key in self.api_keys:
                stats = self.key_stats.get(key)
                if stats:
                    key_metadata[key] = {
                        "created_at": stats.created_at
                    }
            custom["keyMetadata"] = key_metadata
            
            # 保存备用key配置
            if self.fallback_key:
                custom["fallback"] = {
                    "enabled": True,
                    "apiKey": self.fallback_key,
                    "baseURL": self.fallback_config.get("baseURL") if self.fallback_config else None
                }
            else:
                custom["fallback"] = {"enabled": False}
            
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.lock:
            now = time.time()
            key_details = {}
            
            for key in self.api_keys:
                stats = self.key_stats.get(key)
                if not stats:
                    continue
                
                remaining = stats.get_remaining_time(self.max_age_days)
                key_details[key] = {
                    "masked": self._mask_key(key),
                    "requests": stats.requests,
                    "errors": stats.errors,
                    "healthy": stats.healthy,
                    "active_requests": stats.active_requests,
                    "created_at": stats.created_at,
                    "remaining_seconds": remaining,
                    "remaining_hours": remaining / 3600,
                    "remaining_days": remaining / 86400,
                    "is_expired": stats.is_expired(self.max_age_days),
                    "is_fallback": stats.is_fallback,
                    "in_cooldown": stats.is_in_cooldown(),
                }
            
            return {
                "total_keys": len(self.api_keys),
                "healthy_keys": sum(1 for k in self.api_keys if self._is_key_available(k)),
                "expired_keys": sum(1 for k in self.api_keys 
                                   if self.key_stats.get(k) and self.key_stats[k].is_expired(self.max_age_days)),
                "total_requests": sum(self.key_stats[k].requests for k in self.api_keys if self.key_stats.get(k)),
                "total_errors": sum(self.key_stats[k].errors for k in self.api_keys if self.key_stats.get(k)),
                "config": {
                    "qps_limit": self.qps_limit,
                    "concurrency_limit": self.concurrency_limit,
                    "max_age_days": self.max_age_days,
                    "cooldown_seconds": self.cooldown_seconds,
                    "strategy": self.strategy,
                },
                "key_details": key_details,
            }
    
    def _mask_key(self, key: str) -> str:
        """遮蔽key中间部分"""
        if len(key) <= 12:
            return key[:4] + "*" * (len(key) - 4)
        return key[:8] + "*" * (len(key) - 12) + key[-4:]
    
    def get_expired_keys(self) -> List[Tuple[str, float]]:
        """获取所有过期的key及其过期时间"""
        with self.lock:
            expired = []
            for key in self.api_keys:
                stats = self.key_stats.get(key)
                if stats and stats.is_expired(self.max_age_days) and not stats.is_fallback:
                    expired_at = stats.created_at + self.max_age_days * 86400
                    expired.append((key, expired_at))
            return expired
    
    def get_expiring_keys(self, within_hours: float = 24) -> List[Tuple[str, float]]:
        """获取即将过期的key（默认24小时内）"""
        with self.lock:
            expiring = []
            for key in self.api_keys:
                stats = self.key_stats.get(key)
                if stats and not stats.is_fallback:
                    remaining = stats.get_remaining_time(self.max_age_days)
                    if 0 < remaining < within_hours * 3600:
                        expired_at = stats.created_at + self.max_age_days * 86400
                        expiring.append((key, expired_at, remaining))
            return expiring
    
    def set_fallback_key(self, api_key: str, base_url: Optional[str] = None) -> bool:
        """
        设置备用key
        
        Args:
            api_key: 备用key
            base_url: 可选的API基础URL
        
        Returns:
            是否设置成功
        """
        with self.lock:
            # 如果之前有备用key，先取消其标记
            if self.fallback_key and self.fallback_key in self.key_stats:
                self.key_stats[self.fallback_key].is_fallback = False
            
            self.fallback_key = api_key
            self.fallback_config = {
                "enabled": True,
                "apiKey": api_key,
                "baseURL": base_url
            }
            
            # 如果key不在池中，添加进去
            if api_key not in self.api_keys:
                self.api_keys.append(api_key)
            
            # 初始化或更新统计信息
            if api_key not in self.key_stats:
                self.key_stats[api_key] = KeyStats(
                    created_at=time.time(),
                    is_fallback=True
                )
            else:
                self.key_stats[api_key].is_fallback = True
            
            self._save_config()
            print(f"✅ 已设置备用key: {self._mask_key(api_key)}")
            return True
    
    def clear_fallback_key(self) -> bool:
        """清除备用key"""
        with self.lock:
            if not self.fallback_key:
                print("⚠️ 没有设置备用key")
                return False
            
            old_key = self.fallback_key
            if old_key in self.key_stats:
                self.key_stats[old_key].is_fallback = False
            
            self.fallback_key = None
            self.fallback_config = None
            self._save_config()
            print(f"✅ 已清除备用key: {self._mask_key(old_key)}")
            return True
    
    def get_fallback_status(self) -> Optional[Dict]:
        """获取备用key状态"""
        with self.lock:
            if not self.fallback_key:
                return None
            
            stats = self.key_stats.get(self.fallback_key)
            if not stats:
                return None
            
            return {
                "key": self.fallback_key,
                "masked": self._mask_key(self.fallback_key),
                "healthy": stats.healthy,
                "requests": stats.requests,
                "errors": stats.errors,
                "active_requests": stats.active_requests,
                "in_cooldown": stats.is_in_cooldown(),
                "base_url": self.fallback_config.get("baseURL") if self.fallback_config else None,
            }
    
    def get_all_regular_keys_expired(self) -> bool:
        """检查是否所有普通key都已过期"""
        with self.lock:
            for key in self.api_keys:
                stats = self.key_stats.get(key)
                if stats and not stats.is_fallback:
                    if not stats.is_expired(self.max_age_days) and stats.healthy:
                        return False
            return True


# 全局实例
key_manager = APIKeyManager()


if __name__ == "__main__":
    import sys
    
    print("🔑 API Key 管理器")
    print("=" * 50)
    
    stats = key_manager.get_stats()
    print(f"\n📊 总览:")
    print(f"   总keys: {stats['total_keys']}")
    print(f"   可用: {stats['healthy_keys']}")
    print(f"   过期: {stats['expired_keys']}")
    print(f"   总请求: {stats['total_requests']}")
    print(f"   总错误: {stats['total_errors']}")
    
    print(f"\n⚙️ 配置:")
    for k, v in stats['config'].items():
        print(f"   {k}: {v}")
    
    print(f"\n📋 Key详情:")
    for key, details in stats['key_details'].items():
        status = "✅" if details['healthy'] and not details['is_expired'] else "❌"
        if details['in_cooldown']:
            status = "⏳"
        print(f"   {status} {details['masked']}")
        print(f"      请求: {details['requests']}, 错误: {details['errors']}, 活跃: {details['active_requests']}")
        print(f"      剩余: {details['remaining_hours']:.1f}小时 ({details['remaining_days']:.2f}天)")
        if details['is_expired']:
            print(f"      ⚠️ 已过期!")
        elif details['remaining_hours'] < 24:
            print(f"      ⚠️ 即将过期!")
    
    # 检查过期和即将过期的key
    expired = key_manager.get_expired_keys()
    if expired:
        print(f"\n🚨 已过期的keys:")
        for key, expired_at in expired:
            print(f"   {key_manager._mask_key(key)} - 过期于 {datetime.fromtimestamp(expired_at)}")
    
    expiring = key_manager.get_expiring_keys(within_hours=24)
    if expiring:
        print(f"\n⚠️ 24小时内将过期的keys:")
        for key, expired_at, remaining in expiring:
            print(f"   {key_manager._mask_key(key)} - 剩余 {remaining/3600:.1f}小时")