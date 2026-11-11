"""DataShip 2 prototype engine: synthetic rows through the 1.4 report and PDF code."""
import json
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.collection_report import fetch_collection_period
from stravovaci_sestava import AppConfig, create_pdf

FIXTURE = [
    ("Anna Nováková", "ZACI", "Žáci", "Oběd", 1, "A", 1001, "3.A", True),
    ("Jan Dvořák", "ZACI", "Žáci", "Oběd", 2, "A", 1002, "3.B", False),
    ("Eva Veselá", "ZAM", "Zaměstnanci", "Oběd", 1, "B", 2001, "", True),
    ("Petr Černý", "HOST", "Hosté", "Oběd", 1, "C", 3001, "", False),
]

class FixtureCursor:
    def execute(self, query, params):
        self.params = params
    def fetchall(self):
        selected, wanted = self.params[2], self.params[5]
        return [row for row in FIXTURE if row[1] in selected and (wanted is None or row[8] is wanted)]


def handle(request):
    if request.get('action') == 'import_workspace':
        from workspace_import import import_workspace
        from legacy_bridge import configuration
        configuration(request.get('config_path'))
        return import_workspace(request.get('config_path'), request['workspace_dir'])
    if request.get('action') == 'workspace_status':
        path = Path(request['workspace_dir']) / 'config.json'
        return {'exists': path.is_file(), 'config_path': str(path) if path.is_file() else None}
    if request.get('action') == 'legacy_delete_task':
        from legacy_bridge import delete_task
        return delete_task(request.get('config_path'), request.get('task_id'), request.get('revision'))
    if request.get('action') == 'legacy_wizard_edit':
        from legacy_bridge import wizard_edit_data
        return wizard_edit_data(request.get('config_path'), request.get('task_id'))
    if request.get('action') == 'legacy_update_task':
        from legacy_bridge import update_task
        return update_task(request.get('config_path'), request.get('task_id'), request.get('changes'), request.get('revision'))
    if request.get('action') == 'legacy_set_task_enabled':
        from legacy_bridge import set_task_enabled
        return set_task_enabled(request.get('config_path'), request.get('task_id'), request.get('enabled'), request.get('revision'))
    if request.get('action') == 'legacy_wizard_pdf':
        from legacy_bridge import preview_wizard
        return preview_wizard(request.get('config_path'), request.get('data', {}), request['output_dir'])
    if request.get('action') == 'repair_scheduler':
        from legacy_bridge import repair_scheduler
        return repair_scheduler(request.get('config_path'), request['workspace_dir'])
    if request.get('action') == 'remove_scheduler':
        from legacy_bridge import remove_scheduler
        return remove_scheduler(request.get('config_path'), request['workspace_dir'])
    if request.get('action') == 'install_scheduler':
        from legacy_bridge import install_scheduler
        return install_scheduler(request.get('config_path'), request['workspace_dir'])
    if request.get('action') == 'legacy_control_scheduler':
        from legacy_bridge import control_scheduler
        return control_scheduler(request.get('config_path'), request.get('operation'))
    if request.get('action') == 'legacy_scheduler_status':
        from legacy_bridge import scheduler_status
        return scheduler_status(request.get('config_path'))
    if request.get('action') == 'legacy_options':
        from legacy_bridge import filter_options
        return filter_options(request.get('config_path'), request.get('date'))
    if request.get('action') == 'legacy_tasks':
        from legacy_bridge import tasks
        return tasks(request.get('config_path'))
    if request.get('action') == 'legacy_save_task':
        from legacy_bridge import save_task
        return save_task(request.get('config_path'), request.get('data', {}))
    if request.get('action') == 'legacy_info':
        from legacy_bridge import info
        return info(request.get('config_path'))
    if request.get('action') in ('legacy_preview', 'legacy_pdf'):
        from legacy_bridge import collection
        return collection(request, request['output_dir'])
    start = date.fromisoformat(request['start'])
    end = date.fromisoformat(request['end'])
    status = request['status']
    category = request.get('category', 'all')
    if status not in {'both', 'collected', 'uncollected'} or category not in {'all', 'ZACI', 'ZAM', 'HOST'}:
        raise ValueError('Neplatný filtr.')
    categories = ('ZACI', 'ZAM', 'HOST') if category == 'all' else (category,)
    config = AppConfig(database={}, report_date=start, report_end_date=end, categories=categories,
                       language='česky', menu_list_number=1, collection_status=status,
                       category_separation=False, show_by_categories=True, pdf_orientation='na_sirku')
    report = fetch_collection_period(FixtureCursor(), config, categories, 'UKÁZKA – smyšlená jídelna')
    rows = [{'date': r.order_date.isoformat(), 'name': r.name, 'number': r.diner_number,
             'category': r.category_name, 'meal': r.meal_type, 'menu': r.menu,
             'collected': r.collected} for r in report.diners]
    result = {'rows': rows, 'collected': sum(r.collected is True for r in report.diners),
              'uncollected': sum(r.collected is False for r in report.diners)}
    if request.get('action') == 'pdf':
        output = Path(request['output_dir'])
        output.mkdir(parents=True, exist_ok=True)
        path = output / f"Ukazkove-odbery-{start}-{end}-{uuid4().hex[:8]}.pdf"
        create_pdf(config, report, output_path=path)
        result['pdf'] = str(path)
    return result

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        from task_lock import task_store_lock
        from services.web_mail_worker import main
        sys.argv.pop(1)
        try:
            config_index = sys.argv.index('--config')
            config_dir = Path(sys.argv[config_index + 1]).resolve().parent
        except (ValueError, IndexError):
            raise SystemExit('Pro worker je nutné uvést --config a cestu ke konfiguraci.')
        try:
            with task_store_lock(config_dir, timeout=0, name='.dataship-v2-worker.lock'):
                raise SystemExit(main())
        except TimeoutError:
            raise SystemExit('Pro tuto konfiguraci již běží jiný worker DataShip 2.')
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        print(json.dumps({'ok': True, 'data': handle(json.load(sys.stdin))}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        sys.exit(1)
