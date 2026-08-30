from ClipAI.app.recent_action_persistence import RecentActionPersistence
from ClipAI.core.models import EntryActionRef


class Supervisor:
    def __init__(self) -> None:
        self.tasks = {}
        self.classes = {}

    def submit(self, task_id, work, on_unhandled_error, *, task_class="interactive", cancellation_hook=None):
        del on_unhandled_error, cancellation_hook
        self.tasks[task_id] = work
        self.classes[task_id] = task_class


class Store:
    def __init__(self) -> None:
        self.saved = []

    def save(self, refs) -> None:
        self.saved.append(refs)


def test_persistence_coalesces_latest_refs_on_maintenance_lane() -> None:
    supervisor = Supervisor()
    store = Store()
    persistence = RecentActionPersistence(store, supervisor)
    first = (EntryActionRef("a", "short"),)
    latest = (EntryActionRef("b", "long"), EntryActionRef("a", "short"))

    persistence.schedule(first)
    persistence.schedule(latest)
    supervisor.tasks["recent-actions:persist"]()

    assert supervisor.classes["recent-actions:persist"] == "maintenance"
    assert store.saved == [latest]
