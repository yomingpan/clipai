"""User guidance derived from core's sole selection reason taxonomy."""
from ClipAI.core.models import SelectionGuidanceCategory, selection_guidance_category


_GUIDANCE = {
    SelectionGuidanceCategory.ENGINE: '選取讀取逾時或失敗。請再試一次；若持續發生，建議重新開啟 ClipAI。',
    SelectionGuidanceCategory.FOCUS: '視窗焦點可能已改變。請點回原本的視窗後再試一次。',
    SelectionGuidanceCategory.MODIFIER: '請先放開 Ctrl／Alt 等按鍵，再試一次。',
    SelectionGuidanceCategory.NO_SELECTION: '這次沒有偵測到選取內容。請先反白一段文字，或改用剪貼簿。',
}


def selection_failure_guidance(reason: str) -> str:
    return '讀不到反白的文字：' + _GUIDANCE[selection_guidance_category(reason)]
