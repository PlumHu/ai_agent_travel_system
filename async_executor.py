"""
异步并行执行器
==============
为 Agent Pipeline 提供并行执行能力。

核心价值：
  - 无依赖关系的工具调用并行执行（天气 + 攻略 + RAG 同时查询）
  - 信号量控制并发数，防止资源耗尽
  - 单任务超时和错误隔离（一个失败不影响其他）
  - 兼容同步调用（内部用 asyncio.run）

使用方式：
    executor = AsyncExecutor(max_concurrency=5)

    # 异步使用
    results = await executor.run_parallel([
        lambda: get_weather("大理"),
        lambda: search_guides("大理"),
        lambda: rag.retrieve("大理旅游"),
    ], timeout=15)

    # 同步使用（自动包装 asyncio.run）
    results = executor.run_parallel_sync([...])
"""
import asyncio
import functools
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TaskResult:
    """并行任务执行结果"""

    def __init__(
        self,
        index: int,
        success: bool,
        data: Any = None,
        error: str = None,
        duration_ms: float = 0,
        task_name: str = "",
    ):
        self.index = index
        self.success = success
        self.data = data
        self.error = error
        self.duration_ms = duration_ms
        self.task_name = task_name

    def __repr__(self):
        status = "✅" if self.success else "❌"
        return f"TaskResult({status} {self.task_name}, {self.duration_ms:.0f}ms)"


class AsyncExecutor:
    """
    异步并行执行器

    特性：
    - 信号量控制最大并发数（默认 5）
    - 单任务超时保护（默认 30s）
    - 错误隔离：一个任务失败不影响其他任务
    - 支持同步函数包装为异步执行（通过 ThreadPoolExecutor）
    - 返回所有结果（含成功和失败）
    """

    def __init__(
        self,
        max_concurrency: int = 5,
        default_timeout: float = 30.0,
        thread_pool_size: int = 10,
    ):
        """
        Args:
            max_concurrency: 最大并发任务数
            default_timeout: 单任务默认超时（秒）
            thread_pool_size: 线程池大小（用于同步函数异步化）
        """
        self.max_concurrency = max_concurrency
        self.default_timeout = default_timeout
        self._thread_pool = ThreadPoolExecutor(max_workers=thread_pool_size)

    async def run_parallel(
        self,
        tasks: List[Callable],
        timeout: float = None,
        task_names: List[str] = None,
    ) -> List[TaskResult]:
        """
        并行执行多个任务。

        Args:
            tasks: 可调用对象列表（同步或异步函数）
            timeout: 单任务超时（秒），None 时使用默认值
            task_names: 任务名称列表（用于日志）

        Returns:
            TaskResult 列表（与输入顺序对应）
        """
        timeout = timeout or self.default_timeout
        if task_names is None:
            task_names = [f"task_{i}" for i in range(len(tasks))]

        semaphore = asyncio.Semaphore(self.max_concurrency)

        logger.info(
            f"[AsyncExecutor] 开始并行执行 {len(tasks)} 个任务 "
            f"(max_concurrency={self.max_concurrency}, timeout={timeout}s)"
        )

        start_time = time.time()

        # 创建所有异步任务
        coroutines = [
            self._execute_with_semaphore(
                semaphore, task, i, task_names[i], timeout
            )
            for i, task in enumerate(tasks)
        ]

        # 并行执行
        results = await asyncio.gather(*coroutines, return_exceptions=False)

        total_duration = (time.time() - start_time) * 1000
        success_count = sum(1 for r in results if r.success)

        logger.info(
            f"[AsyncExecutor] 并行执行完成: {success_count}/{len(tasks)} 成功, "
            f"总耗时 {total_duration:.0f}ms"
        )

        return results

    async def _execute_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        task: Callable,
        index: int,
        task_name: str,
        timeout: float,
    ) -> TaskResult:
        """信号量控制的单任务执行"""
        async with semaphore:
            return await self._execute_single(task, index, task_name, timeout)

    async def _execute_single(
        self,
        task: Callable,
        index: int,
        task_name: str,
        timeout: float,
    ) -> TaskResult:
        """执行单个任务（含超时和错误处理）"""
        start = time.time()

        try:
            # 判断是否为异步函数
            if asyncio.iscoroutinefunction(task):
                result = await asyncio.wait_for(task(), timeout=timeout)
            else:
                # 同步函数放到线程池执行
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(self._thread_pool, task),
                    timeout=timeout,
                )

            duration = (time.time() - start) * 1000
            logger.debug(f"[AsyncExecutor] {task_name} 完成 ({duration:.0f}ms)")

            return TaskResult(
                index=index,
                success=True,
                data=result,
                duration_ms=duration,
                task_name=task_name,
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start) * 1000
            logger.warning(f"[AsyncExecutor] {task_name} 超时 ({timeout}s)")
            return TaskResult(
                index=index,
                success=False,
                error=f"超时 ({timeout}s)",
                duration_ms=duration,
                task_name=task_name,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.warning(f"[AsyncExecutor] {task_name} 失败: {e}")
            return TaskResult(
                index=index,
                success=False,
                error=str(e),
                duration_ms=duration,
                task_name=task_name,
            )

    def run_parallel_sync(
        self,
        tasks: List[Callable],
        timeout: float = None,
        task_names: List[str] = None,
    ) -> List[TaskResult]:
        """
        同步版并行执行（内部创建事件循环）。

        适用于没有运行中的 asyncio 事件循环的场景。
        """
        try:
            loop = asyncio.get_running_loop()
            # 已有事件循环，不能嵌套 asyncio.run
            # 使用线程池作为降级方案
            return self._run_in_threads(tasks, timeout, task_names)
        except RuntimeError:
            # 没有运行中的事件循环，正常使用 asyncio.run
            return asyncio.run(
                self.run_parallel(tasks, timeout, task_names)
            )

    def _run_in_threads(
        self,
        tasks: List[Callable],
        timeout: float = None,
        task_names: List[str] = None,
    ) -> List[TaskResult]:
        """线程池降级方案（当已在 async 上下文中时使用）"""
        timeout = timeout or self.default_timeout
        if task_names is None:
            task_names = [f"task_{i}" for i in range(len(tasks))]

        results = []
        futures = []

        for i, task in enumerate(tasks):
            future = self._thread_pool.submit(self._run_task_sync, task, i, task_names[i])
            futures.append(future)

        for future in futures:
            try:
                result = future.result(timeout=timeout)
                results.append(result)
            except Exception as e:
                results.append(TaskResult(
                    index=len(results), success=False, error=str(e), task_name=""
                ))

        return results

    @staticmethod
    def _run_task_sync(task: Callable, index: int, task_name: str) -> TaskResult:
        """在线程中执行同步任务"""
        start = time.time()
        try:
            result = task()
            duration = (time.time() - start) * 1000
            return TaskResult(index=index, success=True, data=result,
                            duration_ms=duration, task_name=task_name)
        except Exception as e:
            duration = (time.time() - start) * 1000
            return TaskResult(index=index, success=False, error=str(e),
                            duration_ms=duration, task_name=task_name)

    def shutdown(self):
        """关闭线程池"""
        self._thread_pool.shutdown(wait=False)


# ── 便捷函数 ─────────────────────────────────────────────────────

_default_executor: Optional[AsyncExecutor] = None


def get_executor() -> AsyncExecutor:
    """获取全局 AsyncExecutor 单例"""
    global _default_executor
    if _default_executor is None:
        _default_executor = AsyncExecutor()
    return _default_executor


def parallel_execute(
    tasks: List[Callable],
    timeout: float = 30.0,
    task_names: List[str] = None,
) -> List[TaskResult]:
    """
    便捷函数：并行执行多个任务（同步接口）。

    Args:
        tasks: 可调用对象列表
        timeout: 超时秒数
        task_names: 任务名称

    Returns:
        TaskResult 列表

    使用示例：
        from async_executor import parallel_execute

        results = parallel_execute([
            lambda: get_weather("大理"),
            lambda: search_guides("大理"),
            lambda: rag.retrieve("大理旅游"),
        ], task_names=["weather", "guides", "rag"])

        weather_data = results[0].data if results[0].success else None
    """
    executor = get_executor()
    return executor.run_parallel_sync(tasks, timeout, task_names)
