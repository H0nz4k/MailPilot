"""One-off bulk text messages with a rechecked recipient preview."""
import hashlib
import json
from pathlib import Path
from services.bulk import (BulkData, BulkForm, filter_options, load_bulk_data, preview_for,
                           recipient_rows, validate_message, send_bulk)
from legacy_bridge import configuration


def load_data(config_path):
    config = configuration(config_path)
    database = dict(config.database)
    password = database.pop('password')
    data = load_bulk_data(database,password)
    if config.categories:
        allowed = set(config.categories)
        diners = tuple(d for d in data.diners if d.category in allowed)
        classes = {d.class_name for d in diners if d.class_name}
        data = BulkData(classes=tuple(x for x in data.classes if x[0] in classes),
                        categories=tuple(x for x in data.categories if x[0] in allowed), diners=diners)
    return data


def options(config_path):
    data = load_data(config_path)
    return {'classes':[{'code':c,'note':n} for c,n in filter_options(data,'trida')],
            'categories':[{'code':c,'note':n} for c,n in filter_options(data,'kategorie')]}


def build_preview(config_path, request):
    kind, values = request.get('filter_type'), request.get('values')
    if kind not in ('trida','kategorie') or not isinstance(values,list) or not values or any(not isinstance(v,str) or not v.strip() for v in values):
        raise ValueError('Vyberte alespoň jednu třídu nebo kategorii.')
    data = load_data(config_path)
    known = {code for code,_ in data.options(kind)}
    if not set(values).issubset(known):
        raise ValueError('Výběr obsahuje nedostupnou třídu nebo kategorii.')
    preview = preview_for(data,filter_type=kind,values=values)
    subject, body = request.get('subject') or '', request.get('body') or ''
    if not isinstance(subject,str) or not isinstance(body,str):
        raise ValueError('Předmět a text musí být textové hodnoty.')
    form = BulkForm(subject=subject,body=body)
    rows = recipient_rows(preview)
    digest = hashlib.sha256(json.dumps({'rows':rows,'recipients':preview.recipients,
                       'subject':form.subject,'body':form.body},ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()
    return preview, form, rows, digest


def preview_message(config_path, request):
    preview, _, rows, digest = build_preview(config_path,request)
    return {'rows':[{'name':n,'class_name':c,'category':k,'email':e} for n,c,k,e in rows],
            'recipients':preview.recipient_count,'missing':preview.missing_count,'revision':digest}


def send_message(config_path, request):
    from automaticky_export import read_saved_settings
    from env_store import get_resend_api_key
    from mail_service import normalize_recipient
    from services.web_mail_settings import load_settings, settings_path
    preview, form, _, digest = build_preview(config_path,request)
    validate_message(form,preview)
    if not isinstance(request.get('revision'),str) or request['revision'] != digest:
        raise ValueError('Výběr nebo příjemci se změnili. Znovu zobrazte náhled.')
    path = Path(config_path)
    raw = read_saved_settings(path)
    settings = load_settings(settings_path(path.parent))
    if settings['transport'] != 'resend':
        raise ValueError('Hromadné zprávy zatím používají Resend, stejně jako DataShip 1.4.')
    sender = normalize_recipient(settings['from_email'] or raw.get('mail_odesilatel'))
    key = get_resend_api_key()
    if not key:
        raise ValueError('Chybí Resend API klíč.')
    result = send_bulk(preview,subject=form.subject,body=form.body,api_key=key,sender_email=sender)
    return {'sent':len(result.recipients)}
