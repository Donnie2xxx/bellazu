"""Independent home-search areas. Study progress is intentionally outside these areas."""
import re

INVESTMENT = 'investment'
TOGETHER = 'together'
UNASSIGNED = 'unassigned'
AREAS = (INVESTMENT, TOGETHER)


def area_of(item):
    explicit = item.get('workspace')
    if explicit in AREAS:
        return explicit
    if item.get('pc'):
        return TOGETHER
    if item.get('nyc') or item.get('pick'):
        return INVESTMENT
    return UNASSIGNED


def items_for(document, area):
    return [x for x in (document.get('items') or {}).values() if area_of(x) == area]


FILTER_KEYS = re.compile(r'^(hmode|tsel|shared_towns|set_down|set_rm|set_rc|sv_sort|sv_filt|pc_budget|pc_min_price|pc_view|pc_beds|pc_baths|pc_types|pc_sqft|pc_lot|pc_year|pc_maxm|pc_sort|nycf_.+|hst_.+|hpx_.+|hba_.+|hsize_.+|hdays_.+|hcut_.+|hview_.+|happ_.+|hbd_.+|hkd_.+|hsort_.+|rooms_.+|rank_price|mt_price|mt_size)$')
CONTEXT_KEYS = {'set_income','inc_chip','view','go','prop','prop_key','prop_addr','town','town_cache','prop_cache','recent','facts_over','gallery','tsel','from_towns','arv_trail','vstack','nav_k','nav_v','nav_rs','nav_push','nav_pb','nav_restore','nav_isback','sv_chain','sv_prev_sel','pc_n','pc_pa_try','listing_previews','listing_preview','cz_ph','cz_fail','sv_undo','sv_group','comparison'}


def context_key(key):
    return isinstance(key, str) and (key in CONTEXT_KEYS or bool(FILTER_KEYS.fullmatch(key)) or key.startswith(('ml_', 'tp_', 'tpo_', 'ts_', 'ro_', 'ub_', 'un_', 'rm_', 'lv_', 'own_', 'cc_', 'g_', 'arv_', '_hm', 'omni_')))


def criteria(state):
    def simple(value):
        if value is None or isinstance(value, (bool,int,float,str)):
            return value
        if isinstance(value, (list,tuple)):
            return [simple(v) for v in value[:40] if v is None or isinstance(v,(bool,int,float,str))]
        return None
    return {k:simple(v) for k,v in state.items() if isinstance(k,str) and FILTER_KEYS.fullmatch(k)}
