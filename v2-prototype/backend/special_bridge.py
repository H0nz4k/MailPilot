"""Z 17-01 preparation using the existing report implementation."""
from pathlib import Path
from task_lock import task_store_lock
from uuid import uuid4
import json
import tempfile
from credential_store import sanitize_config
from services.config_io import load_raw_config
from services.special import (SpecialForm, apply_special_form, apply_row_mapping, peek_special_form,
                              peek_row_mapping, peek_supplement_rows, row_choices, run_special)
from legacy_bridge import info


def special_defaults(config_path):
    raw = load_raw_config(Path(config_path))
    form = peek_special_form(raw)
    categories = info(config_path)['categories']
    allowed = {item['code'] for item in categories}
    selected = sorted(allowed) if form.use_all_categories else [c for c in form.categories if c in allowed]
    mapping = {key:[c for c in values if c in allowed] for key,values in peek_row_mapping(raw).items()}
    return {'year':form.year,'categories':categories,'selected':selected,'mapping':mapping,
            'supplement_rows':list(peek_supplement_rows(raw)),
            'rows':[{'code':code,'label':label} for code,label in row_choices()]}


def generate_special(config_path, data, output_dir):
    from z17_nastaveni import MAPPABLE_ROWS, parse_z17_year
    raw = load_raw_config(Path(config_path))
    year = parse_z17_year(data.get('year'))
    allowed = {item['code'] for item in info(config_path)['categories']}
    selected = data.get('selected')
    if not isinstance(selected,list) or not selected or any(not isinstance(v,str) or v not in allowed for v in selected):
        raise ValueError('Vyberte alespoň jednu povolenou kategorii.')
    mapping, supplement = data.get('mapping'), data.get('supplement_rows')
    if not isinstance(mapping,dict) or set(mapping)-set(MAPPABLE_ROWS) or not isinstance(supplement,list) or any(row not in MAPPABLE_ROWS for row in supplement):
        raise ValueError('Neplatné mapování řádků výkazu.')
    for values in mapping.values():
        if not isinstance(values,list) or any(not isinstance(c,str) or c not in allowed for c in values):
            raise ValueError('Mapování obsahuje nepovolenou kategorii.')
    destination = Path(output_dir) / f'Z17-{year}-{uuid4().hex[:8]}'
    form = SpecialForm(year=year,output=str(destination),use_all_categories=False,categories=tuple(selected))
    updated = sanitize_config(apply_row_mapping(apply_special_form(raw,form),mapping,supplement))
    with tempfile.TemporaryDirectory(prefix='dataship2-z17-') as tmp:
        temporary_config = Path(tmp)/'config.json'
        temporary_config.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')
        result = run_special(temporary_config,year=year)
    return {'year':result.year,'files':[str(p) for p in result.files],'detail':result.detail}


def save_special(config_path, workspace, password, data):
    from settings_bridge import authorize, workspace_path
    from services.config_io import save_raw_config
    from z17_nastaveni import MAPPABLE_ROWS, parse_z17_year
    authorize(password)
    path = workspace_path(config_path, workspace)
    with task_store_lock(path.parent):
        raw = load_raw_config(path)
        year = parse_z17_year(data.get('year'))
        allowed = {item['code'] for item in info(str(path))['categories']}
        selected, mapping, supplement = data.get('selected'), data.get('mapping'), data.get('supplement_rows')
        if not isinstance(selected,list) or not selected or any(not isinstance(c,str) or c not in allowed for c in selected):
            raise ValueError('Vyberte alespoň jednu povolenou kategorii.')
        if not isinstance(mapping,dict) or set(mapping)-set(MAPPABLE_ROWS) or not isinstance(supplement,list) or any(row not in MAPPABLE_ROWS for row in supplement):
            raise ValueError('Neplatné mapování řádků výkazu.')
        if any(not isinstance(values,list) or any(not isinstance(c,str) or c not in allowed for c in values) for values in mapping.values()):
            raise ValueError('Mapování obsahuje nepovolenou kategorii.')
        # Do not erase mappings outside the current administrator's permitted scope.
        previous = peek_row_mapping(raw)
        merged = {row:[c for c in previous[row] if c not in allowed] + list(mapping.get(row,[])) for row in MAPPABLE_ROWS}
        previous_form = peek_special_form(raw)
        form = SpecialForm(year=year,output=previous_form.output,use_all_categories=False,categories=tuple(selected))
        save_raw_config(path, apply_row_mapping(apply_special_form(raw,form),merged,supplement))
    return {'saved':True}
