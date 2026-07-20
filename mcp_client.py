"""
MCP 客户端管理器
管理和调用 MCP (Model Context Protocol) Servers
"""
import json
import logging
import subprocess
import os
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MCPClient:
    """MCP 客户端"""

    def __init__(self, server_name: str, config: Dict[str, Any]):
        self.server_name = server_name
        self.config = config
        self.process = None

    def start(self):
        """启动 MCP Server"""
        try:
            command = self.config["command"]
            args = self.config.get("args", [])
            env = os.environ.copy()

            # 合并环境变量（替换 ${VAR} 格式）
            server_env = self.config.get("env", {})
            for key, value in server_env.items():
                if value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    env[key] = os.getenv(env_var, "")
                else:
                    env[key] = value

            # 启动进程
            full_command = [command] + args
            logger.info(f"启动 MCP Server: {self.server_name}")
            logger.debug(f"命令: {' '.join(full_command)}")

            self.process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )

            logger.info(f"MCP Server {self.server_name} 已启动 (PID: {self.process.pid})")

        except Exception as e:
            logger.error(f"启动 MCP Server 失败: {e}")
            raise

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP Server 的工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if not self.process:
            raise RuntimeError(f"MCP Server {self.server_name} 未启动")

        try:
            # 构造 JSON-RPC 请求
            request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }

            # 发送请求
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            # 读取响应
            response_line = self.process.stdout.readline()
            response = json.loads(response_line)

            if "error" in response:
                raise RuntimeError(f"MCP 调用错误: {response['error']}")

            return response.get("result", {})

        except Exception as e:
            logger.error(f"MCP 工具调用失败: {e}")
            raise

    def stop(self):
        """停止 MCP Server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
            logger.info(f"MCP Server {self.server_name} 已停止")


class MCPManager:
    """MCP 管理器"""

    def __init__(self, config_path: str = "mcp_config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.clients: Dict[str, MCPClient] = {}

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            logger.info(f"加载 MCP 配置: {self.config_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"MCP 配置文件不存在: {self.config_path}")
            return {"servers": {}, "client": {}}
        except Exception as e:
            logger.error(f"加载 MCP 配置失败: {e}")
            return {"servers": {}, "client": {}}

    def get_enabled_servers(self) -> List[str]:
        """获取已启用的 MCP Servers"""
        return [
            name for name, config in self.config.get("servers", {}).items()
            if config.get("enabled", False)
        ]

    def start_server(self, server_name: str):
        """启动指定的 MCP Server"""
        if server_name in self.clients:
            logger.info(f"MCP Server {server_name} 已在运行")
            return

        server_config = self.config.get("servers", {}).get(server_name)
        if not server_config:
            raise ValueError(f"MCP Server {server_name} 不存在")

        if not server_config.get("enabled", False):
            logger.warning(f"MCP Server {server_name} 未启用")
            return

        client = MCPClient(server_name, server_config)
        client.start()
        self.clients[server_name] = client

    def start_all_enabled(self):
        """启动所有已启用的 MCP Servers"""
        enabled_servers = self.get_enabled_servers()
        logger.info(f"启动 {len(enabled_servers)} 个 MCP Servers")

        for server_name in enabled_servers:
            try:
                self.start_server(server_name)
            except Exception as e:
                logger.error(f"启动 {server_name} 失败: {e}")

    def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        调用 MCP Server 的工具

        Args:
            server_name: Server 名称
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果
        """
        if server_name not in self.clients:
            self.start_server(server_name)

        client = self.clients[server_name]
        return client.call_tool(tool_name, arguments)

    def stop_all(self):
        """停止所有 MCP Servers"""
        for server_name, client in self.clients.items():
            try:
                client.stop()
            except Exception as e:
                logger.error(f"停止 {server_name} 失败: {e}")

        self.clients.clear()
        logger.info("所有 MCP Servers 已停止")

    def __enter__(self):
        """上下文管理器：进入"""
        self.start_all_enabled()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器：退出"""
        self.stop_all()


# ============ 辅助函数 ============

def get_mcp_manager() -> MCPManager:
    """获取全局 MCP 管理器实例"""
    global _mcp_manager
    if "_mcp_manager" not in globals():
        _mcp_manager = MCPManager()
    return _mcp_manager


# ============ 使用示例 ============

if __name__ == "__main__":
    # 示例 1：使用上下文管理器
    print("\n" + "=" * 60)
    print("示例 1：使用上下文管理器")
    print("=" * 60)

    with MCPManager() as mcp:
        # 调用天气 MCP
        try:
            result = mcp.call_tool(
                "weather",
                "get_forecast",
                {"city": "Beijing", "days": 3}
            )
            print(f"天气查询结果: {result}")
        except Exception as e:
            print(f"天气查询失败: {e}")

        # 调用搜索 MCP
        try:
            result = mcp.call_tool(
                "brave_search",
                "search",
                {"query": "best travel destinations 2026"}
            )
            print(f"搜索结果: {result}")
        except Exception as e:
            print(f"搜索失败: {e}")

    # 示例 2：手动管理
    print("\n" + "=" * 60)
    print("示例 2：手动管理 MCP Servers")
    print("=" * 60)

    mcp = MCPManager()
    print(f"已启用的 Servers: {mcp.get_enabled_servers()}")

    try:
        mcp.start_server("weather")
        result = mcp.call_tool("weather", "get_current", {"city": "Shanghai"})
        print(f"上海天气: {result}")
    finally:
        mcp.stop_all()
