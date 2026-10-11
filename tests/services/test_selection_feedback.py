import pytest
from ClipAI.services.selection_feedback import selection_failure_guidance


@pytest.mark.parametrize('reason,detail', [
    ('uia_text_failed', '選取讀取逾時或失敗。請再試一次；若持續發生，建議重新開啟 ClipAI。'),
    ('uia_provider_failed', '選取讀取逾時或失敗。請再試一次；若持續發生，建議重新開啟 ClipAI。'),
    ('uia_focus_restore_failed', '選取讀取逾時或失敗。請再試一次；若持續發生，建議重新開啟 ClipAI。'),
    ('source_changed', '視窗焦點可能已改變。請點回原本的視窗後再試一次。'),
    ('modifier_timeout', '請先放開 Ctrl／Alt 等按鍵，再試一次。'),
    ('uia_unsupported', '這次沒有偵測到選取內容。請先反白一段文字，或改用剪貼簿。'),
    ('something_new', '這次沒有偵測到選取內容。請先反白一段文字，或改用剪貼簿。'),
    ('', '這次沒有偵測到選取內容。請先反白一段文字，或改用剪貼簿。'),
])
def test_guidance_contains_problem_and_action(reason, detail):
    assert selection_failure_guidance(reason) == '讀不到反白的文字：' + detail
