#!/usr/bin/env python3
"""
API Key 轮询管理器
支持多个 API key 的负载均衡和简单故障转移
"""

import json
import time
import threading
from typing import List, Dict, Optional
from collections import deque


class APIKeyManager:
    def __init__(self, config_path: str = "/root/.nanobot/config.json"):
        # 优先使用本地配置文件（包含真实key），如果不存在则使用公共配置文件
        local_config_path = "/root/.nanobot/config.local.json"
        import os
        if os.path.exists(local_config_path):
            self.config_path = local_config_path
        else:
            self.config_path = config_path
        self.api_keys: List[str] = []
        self.current_index: int = 0
        # QPS限制配置
        self.qps_limit_per_key = 10  # 每个key限制10 QPS
        self.qps_window = 1.0  # 时间窗口1秒
        # key_stats 结构:
        # {
        #   key: {
        #       'requests': int,
        #       'errors': int,
        #       'last_used': float(timestamp),
        #       'healthy': bool,
        #       'request_times': deque([timestamp1, timestamp2, ...])  # 请求时间戳队列
        #   }
        # }
        self.key_stats: Dict[str, Dict] = {}
        self.lock = threading.Lock()
        self.strategy = "round-robin"
        self.load_config()

    def _is_key_rate_limited(self, api_key: str) -> bool:
        """检查key是否超过QPS限制"""
        stats = self.key_stats.get(api_key)
        if not stats:
            return False
        
        current_time = time.time()
        request_times = stats["request_times"]
        
        # 清理过期的请求时间戳（超过时间窗口的）
        while request_times and current_time - request_times[0] > self.qps_window:
            request_times.popleft()
        
        # 检查当前窗口内的请求数是否超过限制
        return len(request_times) >= self.qps_limit_per_key

    def load_config(self):
        """加载配置文件中的 key 列表"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)

            providers = config.get("providers", {})
            custom = providers.get("custom", {})

            # 你自己维护的 key 池
            self.api_keys = custom.get("apiKeys", [])
            
            # 添加备用key到key池
            fallback = custom.get("fallback", {})
            if fallback.get("enabled", False):
                fallback_key = fallback.get("apiKey")
                if fallback_key:
                    self.fallback_key = fallback_key
                    self.fallback_config = fallback
                    # 如果备用key不在主key池中，添加它
                    if fallback_key not in self.api_keys:
                        self.api_keys.append(fallback_key)
                        print(f"✅ 备用key已添加: {fallback.get('name', 'Unknown')}")
                    else:
                        print(f"✅ 备用key已配置: {fallback.get('name', 'Unknown')}")
                else:
                    self.fallback_key = None
                    self.fallback_config = None
            else:
                self.fallback_key = None
                self.fallback_config = None

            # 负载策略
            lb = custom.get("loadBalancing", {})
            self.strategy = lb.get("strategy", "round-robin")

            # 初始化统计
            for key in self.api_keys:
                if key not in self.key_stats:
                    self.key_stats[key] = {
                        "requests": 0,
                        "errors": 0,
                        "last_used": 0.0,
                        "healthy": True,
                        "request_times": deque(maxlen=self.qps_limit_per_key * 2),  # 保存最近2倍限制的请求
                        "is_fallback": key == self.fallback_key if hasattr(self, 'fallback_key') else False
                    }
        except Exception as e:
            print(f"加载配置失败: {e}")

    def get_next_key(self) -> Optional[str]:
        """获取下一个可用的 API key。若全部不健康，返回 None"""
        with self.lock:
            if not self.api_keys:
                return None

            if self.strategy == "least-used":
                return self._least_used()
            else:
                return self._round_robin()

    def _round_robin(self) -> Optional[str]:
        """轮询策略: 跳过不健康 key 和 QPS限制 key，全不健康/全限制则返回 None"""
        n = len(self.api_keys)
        if n == 0:
            return None

        attempts = 0
        while attempts < n:
            key = self.api_keys[self.current_index]
            self.current_index = (self.current_index + 1) % n

            stats = self.key_stats.get(key)
            if stats and stats.get("healthy", True) and not self._is_key_rate_limited(key):
                # 记录请求
                current_time = time.time()
                stats["requests"] += 1
                stats["last_used"] = current_time
                stats["request_times"].append(current_time)
                return key

            attempts += 1

        # 全部不健康或全部达到QPS限制
        return None

    def _least_used(self) -> Optional[str]:
        """最少使用策略: 在健康且未达QPS限制的 key 中选 requests 最少的"""
        available_keys = [
            k for k in self.api_keys
            if (self.key_stats.get(k, {}).get("healthy", True) and 
                not self._is_key_rate_limited(k))
        ]
        if not available_keys:
            return None

        best_key = min(available_keys, key=lambda k: self.key_stats[k]["requests"])
        current_time = time.time()
        self.key_stats[best_key]["requests"] += 1
        self.key_stats[best_key]["last_used"] = current_time
        self.key_stats[best_key]["request_times"].append(current_time)
        return best_key

    def mark_error(self, api_key: str, error_type: str = "429"):
        """
        标记某个 key 出错。
        - 429: 视为临时性限流 -> 30 秒冷却，期间不参与分配
        - 401 等致命错误: 你可以选择直接移除 / 标记为永久不健康
        """
        with self.lock:
            stats = self.key_stats.get(api_key)
            if not stats:
                return

            stats["errors"] += 1

            if error_type == "429":
                # 临时限流: 进入冷却
                stats["healthy"] = False
                # 30 秒后尝试恢复为健康状态
                threading.Timer(30.0, self._recover_key, args=[api_key]).start()
            elif error_type in ("401", "unauthorized"):
                # 认证错误: 可以选择直接标记为长期不健康
                stats["healthy"] = False
                # 你也可以在这里选择调用 remove_key(api_key)

    def _recover_key(self, api_key: str):
        """冷却结束后尝试恢复 key 的健康状态。真正的"测试"由下一次实际请求来完成。"""
        with self.lock:
            stats = self.key_stats.get(api_key)
            if stats:
                stats["healthy"] = True

    def add_key(self, api_key: str):
        """添加新的 API key"""
        with self.lock:
            if api_key not in self.api_keys:
                self.api_keys.append(api_key)
                self.key_stats[api_key] = {
                    "requests": 0,
                    "errors": 0,
                    "last_used": 0.0,
                    "healthy": True,
                    "request_times": deque(maxlen=self.qps_limit_per_key * 2),
                }
                self._save_config()

    def remove_key(self, api_key: str):
        """移除 API key"""
        with self.lock:
            if api_key in self.api_keys:
                self.api_keys.remove(api_key)
                self.key_stats.pop(api_key, None)
                self._save_config()

    def _save_config(self):
        """把 apiKeys 写回配置文件（只改自己这部分）"""
        try:
            with open(self.config_path, "r") as f:
                config = json.load(f)

            providers = config.setdefault("providers", {})
            custom = providers.setdefault("custom", {})
            custom["apiKeys"] = self.api_keys

            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def get_stats(self) -> Dict:
        """获取简单统计信息"""
        with self.lock:
            return {
                "total_keys": len(self.api_keys),
                "healthy_keys": sum(
                    1
                    for k in self.api_keys
                    if self.key_stats.get(k, {}).get("healthy", True)
                ),
                "total_requests": sum(
                    self.key_stats[k]["requests"] for k in self.api_keys
                ),
                "total_errors": sum(
                    self.key_stats[k]["errors"] for k in self.api_keys
                ),
                "key_details": self.key_stats.copy(),
            }


# 全局实例
key_manager = APIKeyManager()


if __name__ == "__main__":
    print("API Key 管理器测试:")
    print(f"当前 keys: {key_manager.api_keys}")
    print(f"统计: {json.dumps(key_manager.get_stats(), indent=2, ensure_ascii=False)}")