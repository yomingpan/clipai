from __future__ import annotations

EVENT_ACTION_START = "action_start"
EVENT_ACTION_COMPLETE = "action_complete"
EVENT_ACTION_ERROR = "action_error"
EVENT_PIPELINE_UPDATE = "pipeline_update"
EVENT_UI_STATUS = "ui_status"
EVENT_TTS_STATE = "tts_state"
EVENT_MEMORY_CHANGE = "memory_change"
EVENT_FOLLOW_UP_REQUEST = "follow_up_request"

ALL_EVENTS = {
    EVENT_ACTION_START,
    EVENT_ACTION_COMPLETE,
    EVENT_ACTION_ERROR,
    EVENT_PIPELINE_UPDATE,
    EVENT_UI_STATUS,
    EVENT_TTS_STATE,
    EVENT_MEMORY_CHANGE,
    EVENT_FOLLOW_UP_REQUEST,
}
