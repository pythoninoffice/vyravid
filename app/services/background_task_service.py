import asyncio
import uuid
import sqlite3
import json
from typing import Dict, Any, Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from enum import Enum
import logging
import os
from threading import Lock

logger = logging.getLogger(__name__)

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class BackgroundTaskService:
    """Service for managing background tasks with status tracking using SQLite"""

    def __init__(self, db_path: str = "data/background_tasks.db"):
        # SQLite database for persistent task storage (works across workers)
        self.db_path = db_path
        self._lock = Lock()
        self._running_tasks: Dict[str, Future] = {}
        # Thread pool for running background tasks independently of worker processes
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="bg_task_")

        # Ensure the data directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Initialize database
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with proper settings"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        """Initialize the SQLite database with the tasks table"""
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS background_tasks (
                        task_id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL,
                        message TEXT,
                        result TEXT,
                        error TEXT,
                        metadata TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                conn.commit()
                logger.info(f"Initialized background tasks database at {self.db_path}")
            finally:
                conn.close()

    def create_task(self, task_type: str, user_id: str, metadata: Optional[Dict] = None) -> str:
        """Create a new task and return its ID"""
        task_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO background_tasks
                    (task_id, task_type, user_id, status, progress, message, result, error, metadata, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id,
                    task_type,
                    user_id,
                    TaskStatus.PENDING,
                    0,
                    "Task created",
                    None,
                    None,
                    json.dumps(metadata or {}),
                    now,
                    now
                ))
                conn.commit()
                logger.info(f"Created task {task_id} of type {task_type} for user {user_id}")
            finally:
                conn.close()

        return task_id

    def update_task(
        self,
        task_id: str,
        status: Optional[TaskStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ):
        """Update task status and metadata"""
        with self._lock:
            conn = self._get_connection()
            try:
                # Build dynamic UPDATE query based on provided fields
                updates = []
                params = []

                if status is not None:
                    updates.append("status = ?")
                    params.append(status)
                if progress is not None:
                    updates.append("progress = ?")
                    params.append(progress)
                if message is not None:
                    updates.append("message = ?")
                    params.append(message)
                if result is not None:
                    updates.append("result = ?")
                    # Handle Pydantic models by converting to dict
                    if hasattr(result, 'model_dump'):
                        # Pydantic v2
                        result_data = result.model_dump()
                    elif hasattr(result, 'dict'):
                        # Pydantic v1
                        result_data = result.dict()
                    else:
                        # Regular dict or other JSON-serializable data
                        result_data = result
                    params.append(json.dumps(result_data))
                if error is not None:
                    updates.append("error = ?")
                    params.append(error)

                if not updates:
                    return

                # Always update the updated_at timestamp
                updates.append("updated_at = ?")
                params.append(datetime.utcnow().isoformat())

                # Add task_id for WHERE clause
                params.append(task_id)

                query = f"UPDATE background_tasks SET {', '.join(updates)} WHERE task_id = ?"
                conn.execute(query, params)
                conn.commit()

                logger.info(f"Updated task {task_id}: status={status}, progress={progress}, message={message}")
            finally:
                conn.close()

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status and data"""
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM background_tasks WHERE task_id = ?",
                    (task_id,)
                )
                row = cursor.fetchone()

                if not row:
                    return None

                # Convert row to dict
                task_data = dict(row)

                # Parse JSON fields
                if task_data.get("metadata"):
                    task_data["metadata"] = json.loads(task_data["metadata"])
                if task_data.get("result"):
                    task_data["result"] = json.loads(task_data["result"])

                return task_data
            finally:
                conn.close()

    async def run_task(
        self,
        task_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ):
        """Run a task in the background"""
        try:
            self.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                message="Processing started"
            )

            # Execute the task function
            result = await task_func(*args, **kwargs)

            self.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message="Task completed successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
            self.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message="Task failed",
                error=str(e)
            )
        finally:
            # Clean up the running task reference
            if task_id in self._running_tasks:
                del self._running_tasks[task_id]

    def _run_task_in_thread(
        self,
        task_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ):
        """
        Wrapper to run async task in a separate thread with its own event loop.
        This prevents the task from being killed when gunicorn worker times out.
        """
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Run the async task in this thread's event loop
            loop.run_until_complete(self.run_task(task_id, task_func, *args, **kwargs))
        finally:
            loop.close()

    def start_background_task(
        self,
        task_id: str,
        task_func: Callable,
        *args,
        **kwargs
    ) -> None:
        """Start a task in the background without blocking"""
        # Submit to thread pool instead of using asyncio.create_task
        # This ensures the task runs in a separate thread and won't be killed by worker timeout
        future = self._executor.submit(
            self._run_task_in_thread,
            task_id,
            task_func,
            *args,
            **kwargs
        )
        self._running_tasks[task_id] = future

        logger.info(f"Started background task {task_id} in thread pool")

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove tasks older than max_age_hours"""
        cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        cutoff_datetime = datetime.fromtimestamp(cutoff_time).isoformat()

        with self._lock:
            conn = self._get_connection()
            try:
                # Get task IDs to remove (for canceling running tasks)
                cursor = conn.execute(
                    "SELECT task_id FROM background_tasks WHERE created_at < ?",
                    (cutoff_datetime,)
                )
                tasks_to_remove = [row[0] for row in cursor.fetchall()]

                # Delete old tasks from database
                conn.execute(
                    "DELETE FROM background_tasks WHERE created_at < ?",
                    (cutoff_datetime,)
                )
                conn.commit()

                # Cancel any running tasks
                for task_id in tasks_to_remove:
                    if task_id in self._running_tasks:
                        future = self._running_tasks[task_id]
                        future.cancel()
                        del self._running_tasks[task_id]

                if tasks_to_remove:
                    logger.info(f"Cleaned up {len(tasks_to_remove)} old tasks")
            finally:
                conn.close()

    def shutdown(self):
        """Shutdown the thread pool executor gracefully"""
        logger.info("Shutting down background task service...")
        self._executor.shutdown(wait=True)
        logger.info("Background task service shutdown complete")

# Global instance
_background_task_service: Optional[BackgroundTaskService] = None

def get_background_task_service() -> BackgroundTaskService:
    """Get or create the background task service singleton"""
    global _background_task_service
    if _background_task_service is None:
        _background_task_service = BackgroundTaskService()
    return _background_task_service
