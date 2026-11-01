"""Proposed Harness-owned basis field helper, not a second goal/strategy engine."""
import hashlib,json,re
def basis(*,fact_revision,law_revision,goal_revision):
    if any(not isinstance(x,str) or not x for x in (fact_revision,law_revision,goal_revision)):
        raise ValueError('all_basis_revisions_required')
    value={'fact_revision':fact_revision,'law_revision':law_revision,'goal_revision':goal_revision}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def strategy_status(saved_basis,current_basis):
    if any(not isinstance(x,str) or re.fullmatch(r'[0-9a-f]{64}',x) is None for x in (saved_basis,current_basis)):
        return 'STALE_REQUIRES_REVIEW'
    return 'CURRENT' if saved_basis==current_basis else 'STALE_REQUIRES_REVIEW'


# --- V8 2026-10-14 机械暂停紧箍咒（用户终裁：机械边界+两条件） ---
# 机械边界暂停必须写 Goal 账 + 原生 UI 常显"已暂停·原因·一键续跑"；续跑是显式用户动作。
# 机械暂停不得变相成为"自动停"：无原因记录/无 UI 呈现/无续跑入口的暂停视为缺陷。
PAUSE_REASONS = ('BUDGET_LIMIT', 'TIME_LIMIT', 'NO_PROGRESS', 'PERMISSION_MISSING')

def pause_entry(reason, detail=''):
    if reason not in PAUSE_REASONS:
        raise ValueError('unknown_pause_reason')
    return {'reason': reason, 'detail': detail, 'resumable': True, 'resume': 'explicit_user_action'}
