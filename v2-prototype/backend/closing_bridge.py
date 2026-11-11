"""Read and generate existing monthly closing reports in a unique temporary folder."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4
import json
import tempfile

from credential_store import sanitize_config
from services.closing import peek_closing_form, apply_closing_form, run_closing
from services.config_io import load_raw_config


def closing_defaults(config_path):
    form = peek_closing_form(load_raw_config(Path(config_path)))
    return {'year':form.year,'month':form.month,'reports':list(form.reports),
            'arch_variant':form.arch_variant,'include_bulk_arch':form.include_bulk_arch,
            'recap_variant':form.recap_variant,'pack_zip':form.pack_zip}


def generate_closing(config_path, request, output_dir):
    from uzaverka_nastaveni import ARCH_VARIANTS, REKAPITULACE_VARIANTS, SUPPORTED_REPORTS, parse_period
    path = Path(config_path)
    raw = load_raw_config(path)
    year, month = parse_period(request.get('year'), request.get('month'))
    reports = request.get('reports')
    if not isinstance(reports,list) or not reports or any(x not in SUPPORTED_REPORTS for x in reports):
        raise ValueError('Vyberte alespoň jednu dostupnou sestavu.')
    arch, recap = request.get('arch_variant'), request.get('recap_variant')
    if arch not in ARCH_VARIANTS or recap not in REKAPITULACE_VARIANTS:
        raise ValueError('Neplatná varianta sestavy.')
    for key in ('include_bulk_arch','pack_zip'):
        if not isinstance(request.get(key),bool):
            raise ValueError('Neplatné nastavení sestavy.')
    destination = Path(output_dir) / f'Uzaverka-{year}-{month:02d}-{uuid4().hex[:8]}'
    form = replace(peek_closing_form(raw),year=year,month=month,reports=tuple(reports),
                   output=str(destination),pack_zip=request['pack_zip'],send_mail=False,
                   arch_variant=arch,include_bulk_arch=request['include_bulk_arch'],
                   recap_variant=recap,use_all_categories=False)
    updated = sanitize_config(apply_closing_form(raw,form))
    with tempfile.TemporaryDirectory(prefix='dataship2-closing-') as tmp:
        temporary_config = Path(tmp)/'config.json'
        temporary_config.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')
        result = run_closing(temporary_config,year=year,month=month)
    return {'status':result.status, 'files':[str(p) for p in result.files],
            'attachments':[str(p) for p in result.attachments], 'detail':result.detail}
