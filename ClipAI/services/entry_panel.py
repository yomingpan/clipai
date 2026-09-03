from __future__ import annotations

from dataclasses import dataclass, replace

from ClipAI.core.models import EntryActionRef, EntryInputSourcePreview, EntryPanelDecision, EntryPanelDensity, EntryPanelOption, EntryPanelSnapshot
from ClipAI.services.action_catalog import ActionCatalog


@dataclass(frozen=True)
class EntryPanelCandidate:
    action: EntryActionRef
    label: str
    description: str


@dataclass(frozen=True)
class EntryPanelCategory:
    category_id: str
    slot: int
    label: str
    description: str
    flagship: tuple[EntryPanelCandidate, ...]
    advanced: tuple[EntryPanelCandidate, ...]


class EntryPanelCatalog:
    """Validated presentation metadata and lookup indexes for the Entry Panel."""

    def __init__(
        self,
        categories: tuple[EntryPanelCategory, ...],
        *,
        actions: ActionCatalog,
    ) -> None:
        category_ids: set[str] = set()
        category_slots: set[int] = set()
        candidates: dict[EntryActionRef, EntryPanelCandidate] = {}
        categories_by_id: dict[str, EntryPanelCategory] = {}
        categories_by_slot: dict[int, EntryPanelCategory] = {}
        for category in categories:
            if category.slot not in {3, 4, 5, 6}:
                raise ValueError("entry panel category slot must be one of: 3, 4, 5, 6")
            if category.slot in category_slots:
                raise ValueError(f"duplicate category slot: {category.slot}")
            if category.category_id in category_ids:
                raise ValueError(f"duplicate category id: {category.category_id}")
            if len(category.flagship) > 4:
                raise ValueError("entry panel flagship must contain at most 4 candidates")
            category_slots.add(category.slot)
            category_ids.add(category.category_id)
            categories_by_slot[category.slot] = category
            categories_by_id[category.category_id] = category
            for candidate in (*category.flagship, *category.advanced):
                if candidate.action.press_type not in {"short", "long"}:
                    raise ValueError(
                        f"unknown entry action press type: {candidate.action.press_type}"
                    )
                if not actions.contains(candidate.action.action_id):
                    raise ValueError(
                        "unknown entry action: "
                        f"{candidate.action.action_id}/{candidate.action.press_type}"
                    )
                if candidate.action in candidates:
                    raise ValueError(
                        "duplicate entry action: "
                        f"{candidate.action.action_id}/{candidate.action.press_type}"
                    )
                candidates[candidate.action] = candidate
        self._categories = categories
        self._categories_by_id = categories_by_id
        self._categories_by_slot = categories_by_slot
        self._candidates = candidates
        self._actions = actions

    @property
    def categories(self) -> tuple[EntryPanelCategory, ...]:
        return self._categories

    def category_for_slot(self, slot: int) -> EntryPanelCategory:
        try:
            return self._categories_by_slot[slot]
        except KeyError as exc:
            raise ValueError(f"unknown entry panel category slot: {slot}") from exc

    def candidate_for_action(self, action: EntryActionRef) -> EntryPanelCandidate:
        try:
            return self._candidates[action]
        except KeyError as exc:
            raise ValueError(
                f"unknown entry panel action: {action.action_id}/{action.press_type}"
            ) from exc

    def recent_candidate_for_action(
        self,
        action: EntryActionRef,
    ) -> EntryPanelCandidate | None:
        """Resolve localized replay copy without changing browse topology."""
        configured = self._candidates.get(action)
        if configured is not None:
            return configured
        if action.press_type not in {"short", "long"}:
            return None
        try:
            resolved = self._actions.resolve(action.action_id, action.press_type)
        except ValueError:
            return None
        description = (
            resolved.feedback_contract.ai_help_label
            if resolved.feedback_contract is not None
            else resolved.name
        )
        return EntryPanelCandidate(action, resolved.name, description)

    def category(self, category_id: str) -> EntryPanelCategory:
        try:
            return self._categories_by_id[category_id]
        except KeyError as exc:
            raise ValueError(f"unknown entry panel category: {category_id}") from exc


class EntryPanelCoordinator:
    def __init__(
        self,
        catalog: EntryPanelCatalog,
        *,
        density: EntryPanelDensity = "detailed",
    ) -> None:
        self._catalog = catalog
        self._density = density
        self._snapshot: EntryPanelSnapshot | None = None
        self._recent: tuple[EntryActionRef, ...] = ()
        self._disabled: dict[EntryActionRef, str] = {}
        self._pending = False

    @property
    def snapshot(self) -> EntryPanelSnapshot | None:
        return self._snapshot

    @property
    def actions(self) -> tuple[EntryActionRef, ...]:
        return tuple(
            candidate.action
            for category in self._catalog.categories
            for candidate in (*category.flagship, *category.advanced)
        )

    def open(
        self,
        panel_id: str,
        *,
        recent: tuple[EntryActionRef, ...] = (),
        disabled: dict[EntryActionRef, str] | None = None,
        preparing: bool = False,
        source_preview: EntryInputSourcePreview | None = None,
    ) -> EntryPanelSnapshot:
        recent_candidates = tuple(
            candidate
            for action in recent[:3]
            if (candidate := self._catalog.recent_candidate_for_action(action))
            is not None
        )
        self._recent = tuple(candidate.action for candidate in recent_candidates)
        self._disabled = dict(disabled or {})
        self._pending = preparing
        recent_options = tuple(
            self._action_option(index, candidate)
            for index, candidate in enumerate(recent_candidates)
        )
        self._snapshot = EntryPanelSnapshot(
            panel_id,
            "root",
            density=self._density,
            options=recent_options + tuple(
                EntryPanelOption(
                    category.slot,
                    category.label,
                    category.description,
                    category_id=category.category_id,
                )
                for category in self._catalog.categories
            ),
            status="preparing" if preparing else "idle",
            message="正在讀取來源內容…" if preparing else "",
            source_preview=source_preview,
        )
        return self._snapshot

    def open_more(self) -> EntryPanelSnapshot:
        if self._snapshot is None or self._snapshot.page != "scene":
            raise RuntimeError("entry panel scene is not open")
        category = self._catalog.category(self._snapshot.category_id)
        self._snapshot = replace(
            self._snapshot,
            page="more",
            category_id=category.category_id,
            options=tuple(
                self._action_option(None, item)
                for item in category.advanced
            ),
            search_text="",
        )
        return self._snapshot

    def set_search(self, text: str) -> EntryPanelSnapshot:
        if self._snapshot is None or self._snapshot.page != "more":
            raise RuntimeError("entry panel more page is not open")
        category = self._catalog.category(self._snapshot.category_id)
        query = text.strip().casefold()
        candidates = tuple(
            item
            for item in category.advanced
            if not query
            or query in item.label.casefold()
            or query in item.description.casefold()
            or query in item.action.action_id.casefold()
        )
        self._snapshot = replace(
            self._snapshot,
            page="more",
            category_id=category.category_id,
            options=tuple(
                self._action_option(None, item)
                for item in candidates
            ),
            search_text=text,
        )
        return self._snapshot

    def toggle_density(self) -> EntryPanelSnapshot:
        if self._snapshot is None:
            raise RuntimeError("entry panel is not open")
        density = "compact" if self._snapshot.density == "detailed" else "detailed"
        self._density = density
        self._snapshot = replace(self._snapshot, density=density)
        return self._snapshot

    def begin_input_preparation(self) -> EntryPanelSnapshot:
        if self._snapshot is None:
            raise RuntimeError("entry panel is not open")
        self._pending = True
        self._snapshot = replace(
            self._snapshot,
            status="preparing",
            message="正在讀取來源內容…",
            source_preview=EntryInputSourcePreview("preparing"),
            options=self._project_option_lifecycle(self._snapshot.options),
        )
        return self._snapshot

    def complete_input_preparation(
        self,
        source_preview: EntryInputSourcePreview,
    ) -> EntryPanelSnapshot:
        if self._snapshot is None:
            raise RuntimeError("entry panel is not open")
        self._pending = False
        self._snapshot = replace(
            self._snapshot,
            status="idle",
            message="",
            source_preview=source_preview,
            options=self._project_option_lifecycle(self._snapshot.options),
        )
        return self._snapshot

    def close(self) -> None:
        self._pending = False
        self._snapshot = None

    def show_error(
        self,
        message: str,
        *,
        source_preview: EntryInputSourcePreview | None = None,
    ) -> EntryPanelSnapshot:
        if self._snapshot is None:
            raise RuntimeError("entry panel is not open")
        self._pending = False
        self._snapshot = replace(
            self._snapshot,
            status="error",
            message=message,
            source_preview=source_preview or self._snapshot.source_preview,
            options=self._project_option_lifecycle(self._snapshot.options),
        )
        return self._snapshot

    def set_disabled(
        self,
        disabled: dict[EntryActionRef, str],
    ) -> EntryPanelSnapshot | None:
        self._disabled = dict(disabled)
        if self._snapshot is None:
            return None
        self._snapshot = replace(
            self._snapshot,
            options=self._project_option_lifecycle(self._snapshot.options),
        )
        return self._snapshot

    def back(self) -> EntryPanelSnapshot | None:
        if self._snapshot is None:
            return None
        if self._snapshot.page == "more":
            category = self._catalog.category(self._snapshot.category_id)
            self._snapshot = replace(
                self._snapshot,
                page="scene",
                category_id=category.category_id,
                options=tuple(
                    self._action_option(index, item)
                    for index, item in enumerate(category.flagship, start=1)
                ),
                search_text="",
            )
            return self._snapshot
        if self._snapshot.page == "scene":
            previous = self._snapshot
            root = self.open(
                previous.panel_id,
                recent=self._recent,
                disabled=self._disabled,
                preparing=self._pending,
                source_preview=previous.source_preview,
            )
            self._snapshot = replace(
                root,
                density=previous.density,
                status=previous.status,
                message=previous.message,
                source_preview=previous.source_preview,
            )
            return self._snapshot
        return self._snapshot

    def select_digit(self, digit: str) -> EntryPanelDecision:
        if self._snapshot is None:
            raise RuntimeError("entry panel is not open")
        if not digit.isdigit():
            return EntryPanelDecision(self._snapshot)
        slot = int(digit)
        option = next((item for item in self._snapshot.options if item.slot == slot), None)
        if (
            option is not None
            and option.action is not None
            and option.enabled
            and not option.pending
        ):
            return EntryPanelDecision(self._snapshot, option.action)
        if self._snapshot.page == "root" and option is not None and option.category_id:
            category = self._catalog.category_for_slot(slot)
            self._snapshot = replace(
                self._snapshot,
                page="scene",
                category_id=category.category_id,
                options=tuple(
                    self._action_option(index, item)
                    for index, item in enumerate(category.flagship, start=1)
                ),
                search_text="",
            )
        return EntryPanelDecision(self._snapshot)

    def _action_option(
        self,
        slot: int | None,
        candidate: EntryPanelCandidate,
    ) -> EntryPanelOption:
        reason = self._disabled.get(candidate.action, "")
        return EntryPanelOption(
            slot,
            candidate.label,
            candidate.description,
            candidate.action,
            enabled=not reason,
            pending=self._pending and not reason,
            disabled_reason=reason,
        )

    def _project_option_lifecycle(
        self,
        options: tuple[EntryPanelOption, ...],
    ) -> tuple[EntryPanelOption, ...]:
        return tuple(
            replace(
                option,
                enabled=not (reason := self._disabled.get(option.action, "")),
                pending=self._pending and not reason,
                disabled_reason=reason,
            )
            if option.action is not None
            else option
            for option in options
        )
