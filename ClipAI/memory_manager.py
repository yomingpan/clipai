
"""
Memory Manager for ClipAI
Handles dual-track context memory (Auto/Manual) and persistent logging.
"""
import json
import os
import time
import warnings
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import deque
import threading
from clipai.core.cancellation import get_cancellation_controller

# Directory for persistent logs
MEMORY_LOG_DIR = "logs"
MEMORY_LOG_FILE = os.path.join(MEMORY_LOG_DIR, "memory_archive.jsonl")


def _ensure_log_dir():
    """Ensure the log directory exists."""
    os.makedirs(MEMORY_LOG_DIR, exist_ok=True)


class MemoryManager:
    def __init__(self, max_auto=3):
        self._lock = threading.Lock()
        self._auto_buffer: deque = deque(maxlen=max_auto)
        self._manual_buffer: List[Dict[str, Any]] = []
        self._last_active_time: float = time.time()
        self._auto_memory_ttl: int = 0
        self._session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._debug_enabled: bool = False

    def _check_ttl(self):
        """Check if auto memory has expired and clear it if necessary."""
        # If TTL is 0, auto memory is effectively disabled (cleared immediately)
        if self._auto_memory_ttl == 0:
            if len(self._auto_buffer) > 0:
                self._auto_buffer.clear()
            return

        current_time = time.time()
        if current_time - self._last_active_time > self._auto_memory_ttl:
            if len(self._auto_buffer) > 0:
                print(f"[clipai] Auto memory expired and cleared ({len(self._auto_buffer)} items).")
                self._auto_buffer.clear()

    def set_auto_memory_ttl(self, minutes: int):
        """Set the TTL for auto memory in minutes."""
        with self._lock:
            self._auto_memory_ttl = minutes * 60
            print(f"[clipai] Auto memory TTL set to {minutes} minutes.")
            # If set to 0, clear immediately
            if self._auto_memory_ttl == 0:
                self._auto_buffer.clear()

    def get_auto_memory_ttl(self) -> int:
        """Get the current auto memory TTL in minutes."""
        with self._lock:
            return self._auto_memory_ttl // 60

    def update_activity(self):
        """Update the last active timestamp to prevent TTL expiration."""
        with self._lock:
            self._last_active_time = time.time()

    def memorize(
        self,
        content: str,
        content_type: str = "ai_response",
        comment: Optional[str] = None,
        action_id: Optional[str] = None,
        original_input: Optional[str] = None,
        is_manual: bool = False
    ) -> Dict[str, Any]:
        """Store content in memory."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self._session_id,
            "content_type": content_type,
            "content": content,
            "comment": comment,
            "action_id": action_id,
            "original_input": original_input,
            "is_manual": is_manual
        }
        
        should_emit = False
        with self._lock:
            if is_manual:
                self._manual_buffer.append(entry)
                print(f"[clipai] Manual memory pinned: {content[:30]}...")
                should_emit = True
            else:
                if self._auto_memory_ttl == 0:
                    return entry
                self._auto_buffer.append(entry)
                print(f"[clipai] Auto memory updated: {content[:30]}...")
                should_emit = True
            
            self._last_active_time = time.time()
            
            _ensure_log_dir()
            try:
                with open(MEMORY_LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[clipai] Failed to persist memory: {e}")
        
        # Emit OUTSIDE the lock to prevent deadlock when subscribers
        # (e.g., TrayIcon._on_memory_changed) call back into MemoryManager.
        # See doc/lesson_learnt_ui_deadlock.md.
        if should_emit:
            from clipai.core.event_bus import get_event_bus, Events
            get_event_bus().emit(Events.MEMORY_CHANGED)
        
        return entry

    def get_context_for_prompt(self) -> Dict[str, str]:
        """Get formatted context for both tracks."""
        with self._lock:
            self._check_ttl()
            
            manual_parts = []
            for i, mem in enumerate(self._manual_buffer, 1):
                text = f"[Pinned {i}]"
                if mem.get("comment"):
                    text += f" (Note: {mem['comment']})"
                text += f"\n{mem['content']}"
                manual_parts.append(text)
            
            auto_parts = []
            for i, mem in enumerate(self._auto_buffer, 1):
                text = f"[Recent {i}]"
                if mem.get("original_input"):
                    text += f"\nUser: {mem['original_input']}"
                text += f"\nAI: {mem['content']}"
                auto_parts.append(text)
                
            return {
                "manual": "\n\n---\n\n".join(manual_parts),
                "auto": "\n\n---\n\n".join(auto_parts)
            }

    def clear_context(self) -> int:
        """Clear all short-term context (Auto and Manual)."""
        with self._lock:
            count = len(self._auto_buffer) + len(self._manual_buffer)
            self._auto_buffer.clear()
            self._manual_buffer.clear()
            self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Emit OUTSIDE the lock — see doc/lesson_learnt_ui_deadlock.md
        from clipai.core.event_bus import get_event_bus, Events
        get_event_bus().emit(Events.MEMORY_CHANGED)
        
        print(f"[clipai] All context cleared: {count} entries removed.")
        return count

    def get_memory_count(self) -> int:
        """Get total number of items in memory (Auto + Manual)."""
        with self._lock:
            self._check_ttl()
            return len(self._auto_buffer) + len(self._manual_buffer)

    def get_manual_count(self) -> int:
        """Get number of pinned items."""
        with self._lock:
            return len(self._manual_buffer)

    def get_auto_count(self) -> int:
        """Get number of recent items (after TTL check)."""
        with self._lock:
            self._check_ttl()
            return len(self._auto_buffer)

    def get_all_memories(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all memory entries as raw lists for UI display."""
        with self._lock:
            self._check_ttl()
            return {
                "manual": list(self._manual_buffer),
                "auto": list(self._auto_buffer),
            }

    def remove_last_manual_memory(self) -> bool:
        """Remove the most recently added manual (pinned) memory entry."""
        removed = None
        with self._lock:
            if self._manual_buffer:
                removed = self._manual_buffer.pop()
                print(f"[clipai] Undo: removed manual memory '{removed['content'][:30]}...'")
        
        # Emit OUTSIDE the lock — see doc/lesson_learnt_ui_deadlock.md
        if removed is not None:
            from clipai.core.event_bus import get_event_bus, Events
            get_event_bus().emit(Events.MEMORY_CHANGED)
            return True
        return False

    def remove_manual_memory_by_index(self, index: int) -> bool:
        """Remove a manual memory entry by its index."""
        removed = None
        with self._lock:
            if 0 <= index < len(self._manual_buffer):
                removed = self._manual_buffer.pop(index)
                print(f"[clipai] Removed manual memory [{index}]: '{removed['content'][:30]}...'")
        
        # Emit OUTSIDE the lock — see doc/lesson_learnt_ui_deadlock.md
        if removed is not None:
            from clipai.core.event_bus import get_event_bus, Events
            get_event_bus().emit(Events.MEMORY_CHANGED)
            return True
        return False

    def set_debug_mode(self, enabled: bool):
        """Set the global debug mode."""
        with self._lock:
            self._debug_enabled = enabled

    def is_debug_enabled(self) -> bool:
        """Check if debug mode is enabled."""
        with self._lock:
            return self._debug_enabled


# --- Singleton Management ---
_manager: Optional[MemoryManager] = None
_mgr_lock = threading.Lock()

def get_memory_manager() -> MemoryManager:
    """Get the global MemoryManager singleton."""
    global _manager
    with _mgr_lock:
        if _manager is None:
            _manager = MemoryManager()
        return _manager


# --- Backward-Compatible Module-Level API ---

def memorize(content, content_type="ai_response", comment=None, action_id=None, original_input=None, is_manual=False):
    return get_memory_manager().memorize(content, content_type, comment, action_id, original_input, is_manual)

def get_context_for_prompt() -> Dict[str, str]:
    return get_memory_manager().get_context_for_prompt()

def clear_context() -> int:
    return get_memory_manager().clear_context()

def get_memory_count() -> int:
    return get_memory_manager().get_memory_count()

def get_manual_count() -> int:
    return get_memory_manager().get_manual_count()

def get_auto_count() -> int:
    return get_memory_manager().get_auto_count()

def get_all_memories() -> Dict:
    return get_memory_manager().get_all_memories()

def remove_last_manual_memory() -> bool:
    return get_memory_manager().remove_last_manual_memory()

def remove_manual_memory_by_index(index) -> bool:
    return get_memory_manager().remove_manual_memory_by_index(index)

def set_auto_memory_ttl(minutes):
    get_memory_manager().set_auto_memory_ttl(minutes)

def get_auto_memory_ttl() -> int:
    return get_memory_manager().get_auto_memory_ttl()

def update_activity():
    get_memory_manager().update_activity()

def set_debug_mode(enabled):
    get_memory_manager().set_debug_mode(enabled)

def is_debug_enabled() -> bool:
    return get_memory_manager().is_debug_enabled()


# --- Cancellation API (Delegated to CancellationController) ---
# DEPRECATED: Import directly from clipai.core.cancellation instead.

def set_cancel_event():
    """Deprecated: Use ``get_cancellation_controller().set_cancel_event()`` directly."""
    warnings.warn(
        "memory_manager.set_cancel_event() is deprecated. "
        "Use clipai.core.cancellation.get_cancellation_controller().set_cancel_event() instead.",
        DeprecationWarning, stacklevel=2,
    )
    get_cancellation_controller().set_cancel_event()

def clear_cancel_event():
    """Deprecated: Use ``get_cancellation_controller().clear_cancel_event()`` directly."""
    warnings.warn(
        "memory_manager.clear_cancel_event() is deprecated. "
        "Use clipai.core.cancellation.get_cancellation_controller().clear_cancel_event() instead.",
        DeprecationWarning, stacklevel=2,
    )
    get_cancellation_controller().clear_cancel_event()

def is_cancelled() -> bool:
    """Deprecated: Use ``get_cancellation_controller().is_cancelled()`` directly."""
    warnings.warn(
        "memory_manager.is_cancelled() is deprecated. "
        "Use clipai.core.cancellation.get_cancellation_controller().is_cancelled() instead.",
        DeprecationWarning, stacklevel=2,
    )
    return get_cancellation_controller().is_cancelled()

def register_interruptible(obj):
    """Deprecated: Use ``get_cancellation_controller().register_interruptible()`` directly."""
    warnings.warn(
        "memory_manager.register_interruptible() is deprecated. "
        "Use clipai.core.cancellation.get_cancellation_controller().register_interruptible() instead.",
        DeprecationWarning, stacklevel=2,
    )
    get_cancellation_controller().register_interruptible(obj)

def interrupt_active_action():
    """Deprecated: Use ``get_cancellation_controller().interrupt_active_action()`` directly."""
    warnings.warn(
        "memory_manager.interrupt_active_action() is deprecated. "
        "Use clipai.core.cancellation.get_cancellation_controller().interrupt_active_action() instead.",
        DeprecationWarning, stacklevel=2,
    )
    get_cancellation_controller().interrupt_active_action()



