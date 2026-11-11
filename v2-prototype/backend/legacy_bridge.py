"""Read-only access to the 1.4 configuration and report services for DataShip 2."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

from services.database import probe_connection
from stravovaci_sestava import load_config, fetch_report, create_pdf


def configuration(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('Vyberte konfigurační soubor DataShip 1.4.')
    return load_config(Path(path), date_override=date.today().isoformat())


def info(path):
    config = configuration(path)
    db = dict(config.database)
    password = db.pop('password')
    connection = probe_connection(db, password, remember=False)
    allowed = set(config.categories)
    categories = [{'code': code, 'name': name or code} for code, name in connection.categories
                  if not allowed or code in allowed]
    return {'subject': connection.subject_name or connection.database_name, 'categories': categories}


def collection(request, output_dir):
    config = configuration(request.get('config_path'))
    start, end = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
    if not 0 <= (end - start).days <= 365:
        raise ValueError('Období musí obsahovat nejvýše 366 dní a datum do nesmí předcházet datu od.')
    status = request.get('status')
    if status not in ('both', 'collected', 'uncollected'):
        raise ValueError('Neplatný stav odběru.')
    category = request.get('category', 'all')
    if category != 'all':
        if config.categories and category not in config.categories:
            raise ValueError('Kategorie není povolená konfigurací.')
        categories = (category,)
    else:
        categories = config.categories
    config = replace(config, report_date=start, report_end_date=end, categories=categories,
                     collection_status=status, category_separation=False, show_by_categories=True)
    report = fetch_report(config)
    rows = [{'date': r.order_date.isoformat(), 'name': r.name or '[bez jména]', 'number': r.diner_number,
             'category': r.category_name or r.category_code, 'meal': r.meal_type,
             'menu': r.menu, 'collected': r.collected} for r in report.diners]
    result = {'rows': rows, 'collected': sum(r.collected is True for r in report.diners),
              'uncollected': sum(r.collected is False for r in report.diners)}
    if request.get('action') == 'legacy_pdf':
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        path = output / f'Odběry-{start}-{end}-{uuid4().hex[:8]}.pdf'
        create_pdf(config, report, output_path=path)
        result['pdf'] = str(path)
    return result
