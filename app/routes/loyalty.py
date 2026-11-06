from datetime import timedelta
import json
import re
import os
import time
import logging

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from app.database import db
from app.models import (Company, LoyaltyProgram, LoyaltyCustomer, LoyaltyStamp, LoyaltyCampaign,
                        LoyaltyPushSubscription, LoyaltyPlanPurchase, utcnow)
from app.routes.portal import current_user, login_required

loyalty_bp = Blueprint('loyalty', __name__, url_prefix='/lealtad')
TRIAL_DAYS = 14


def google_wallet_configured():
    return bool(os.getenv("GOOGLE_WALLET_ISSUER_ID") and os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


def _google_wallet_client():
    """Create an authenticated Google Wallet REST session from the service account."""
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession

    key_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not key_path or not os.path.isfile(key_path):
        raise RuntimeError("No se encuentra el archivo de credenciales de Google Wallet.")
    credentials = service_account.Credentials.from_service_account_file(
        key_path, scopes=["https://www.googleapis.com/auth/wallet_object.issuer"]
    )
    return credentials, AuthorizedSession(credentials)


def _google_wallet_ids(customer):
    issuer_id = os.getenv("GOOGLE_WALLET_ISSUER_ID", "").strip()
    if not issuer_id:
        raise RuntimeError("Falta GOOGLE_WALLET_ISSUER_ID en el entorno.")
    return issuer_id, f"{issuer_id}.noxtium_company_{customer.company_id}", f"{issuer_id}.customer_{customer.id}"


def _google_wallet_class(customer, program, session, class_id):
    base = "https://walletobjects.googleapis.com/walletobjects/v1/loyaltyClass"
    response = session.get(f"{base}/{class_id}", timeout=20)
    if response.status_code == 200:
        class_data = response.json()
        if class_data.get("reviewStatus") != "approved":
            raise RuntimeError("Google recibió la clase de fidelización, pero todavía está en revisión. Espera a que su estado sea APPROVED en Google Wallet Console y vuelve a pulsar el botón.")
        return
    if response.status_code != 404:
        raise RuntimeError(f"Google Wallet no pudo consultar la clase ({response.status_code}): {response.text[:500]}")
    logo_url = url_for("loyalty.wallet_logo", company_id=customer.company_id, _external=True)
    body = {
        "id": class_id,
        "issuerName": "NOXTIUM",
        "programName": (program.business_name or program.title)[:20],
        "programLogo": {"sourceUri": {"uri": logo_url}, "contentDescription": {"defaultValue": {"language": "es", "value": f"Logo de {program.business_name}"}}},
        "hexBackgroundColor": program.color if re.fullmatch(r"#[0-9a-fA-F]{6}", program.color or "") else "#333333",
        "reviewStatus": "UNDER_REVIEW",
    }
    created = session.post(base, json=body, timeout=20)
    if created.status_code not in (200, 201, 409):
        raise RuntimeError(f"Google Wallet no pudo crear la clase ({created.status_code}): {created.text[:700]}")
    class_data = created.json() if created.content else {}
    if class_data.get("reviewStatus") != "approved":
        raise RuntimeError("Se creó la clase de Google Wallet y quedó pendiente de revisión. Cuando Google la marque como APPROVED, vuelve a pulsar Añadir a Google Wallet.")


def _google_wallet_object(customer, program, session, class_id, object_id):
    base = "https://walletobjects.googleapis.com/walletobjects/v1/loyaltyObject"
    progress = f"{customer.stamps} de {program.stamps_goal} sellos"
    body = {
        "id": object_id,
        "classId": class_id,
        "state": "ACTIVE",
        "accountId": f"cliente-{customer.id}",
        "accountName": customer.name[:100],
        "barcode": {"type": "QR_CODE", "value": customer.token, "alternateText": "Código de tarjeta NOXTIUM"},
        "hexBackgroundColor": program.color if re.fullmatch(r"#[0-9a-fA-F]{6}", program.color or "") else "#333333",
        "textModulesData": [
            {"id": "progress", "header": "Progreso", "body": progress},
            {"id": "reward", "header": "Recompensa", "body": (program.reward_text or "Recompensa disponible")[:500]},
        ],
    }
    response = session.get(f"{base}/{object_id}", timeout=20)
    if response.status_code == 404:
        created = session.post(base, json=body, timeout=20)
        if created.status_code not in (200, 201, 409):
            raise RuntimeError(f"Google Wallet no pudo crear la tarjeta ({created.status_code}): {created.text[:700]}")
    elif response.status_code == 200:
        updated = session.patch(f"{base}/{object_id}", json=body, timeout=20)
        if updated.status_code not in (200, 201):
            raise RuntimeError(f"Google Wallet no pudo actualizar la tarjeta ({updated.status_code}): {updated.text[:700]}")
    else:
        raise RuntimeError(f"Google Wallet no pudo consultar la tarjeta ({response.status_code}): {response.text[:500]}")
    return body


def _google_wallet_save_url(customer, program):
    import google.auth.crypt
    import google.auth.jwt

    credentials, session = _google_wallet_client()
    _issuer, class_id, object_id = _google_wallet_ids(customer)
    _google_wallet_class(customer, program, session, class_id)
    wallet_object = _google_wallet_object(customer, program, session, class_id, object_id)
    signer = google.auth.crypt.RSASigner.from_service_account_file(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
    claims = {
        "iss": credentials.service_account_email,
        "aud": "google",
        "typ": "savetowallet",
        "iat": int(time.time()),
        "origins": [request.host_url.rstrip("/")],
        "payload": {"loyaltyObjects": [wallet_object]},
    }
    token = google.auth.jwt.encode(signer, claims).decode("utf-8")
    return f"https://pay.google.com/gp/v/save/{token}"


def _sync_google_wallet_customer(customer):
    """Best-effort sync after a stamp; never roll back the loyalty transaction."""
    if not google_wallet_configured():
        return
    try:
        _credentials, session = _google_wallet_client()
        _issuer, class_id, object_id = _google_wallet_ids(customer)
        program = db.session.get(LoyaltyProgram, customer.program_id)
        if not program:
            return
        response = session.get(f"https://walletobjects.googleapis.com/walletobjects/v1/loyaltyObject/{object_id}", timeout=15)
        if response.status_code == 404:
            return  # The customer has not added the pass yet.
        if response.status_code != 200:
            raise RuntimeError(f"Consulta de pase: {response.status_code} {response.text[:300]}")
        body = _google_wallet_object(customer, program, session, class_id, object_id)
        updated = session.patch(f"https://walletobjects.googleapis.com/walletobjects/v1/loyaltyObject/{object_id}", json=body, timeout=15)
        if updated.status_code not in (200, 201):
            raise RuntimeError(f"Actualización de pase: {updated.status_code} {updated.text[:300]}")
    except Exception:
        current_app.logger.exception("No se pudo sincronizar la tarjeta de Google Wallet del cliente %s", customer.id)



def get_program(company_id, create=False):
    program = LoyaltyProgram.query.filter_by(company_id=company_id).first()
    if not program and create:
        company = db.session.get(Company, company_id)
        program = LoyaltyProgram(company_id=company_id, business_name=company.name if company else 'Mi negocio')
        db.session.add(program)
        db.session.commit()
    return program


def trial_status(program):
    # A demo only starts after an administrator approves the explicit request.
    if not program or not program.trial_started_at:
        return None, False, 0
    end = program.trial_started_at + timedelta(days=TRIAL_DAYS)
    remaining = max(0, (end - utcnow()).total_seconds())
    return end, remaining > 0, int((remaining + 86399) // 86400)



@loyalty_bp.get('/')
@login_required
def dashboard():
    user = current_user()
    if user.role == 'admin': abort(403)
    program = get_program(user.company_id, create=True)
    end, active, days = trial_status(program)
    paid = LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id, status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at > utcnow()).first() is not None
    if not active and not paid: return redirect(url_for('loyalty.pricing'))
    customers = LoyaltyCustomer.query.filter_by(company_id=user.company_id).order_by(LoyaltyCustomer.last_visit_at.asc().nullsfirst()).all()
    stale_count = sum(1 for c in customers if not c.last_visit_at or c.last_visit_at < utcnow()-timedelta(days=30))
    return render_template('loyalty_dashboard.html', program=program, customers=customers, days_left=days,
                           trial_active=active, paid=paid, stale_count=stale_count, now=utcnow(),
                           enroll_url=url_for('loyalty.enroll_page', company_id=user.company_id, _external=True))


@loyalty_bp.route('/configurar', methods=['GET','POST'])
@login_required
def configure():
    user=current_user()
    if user.role == 'admin': abort(403)
    program=get_program(user.company_id, create=True)
    end, active, _days = trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid:
        return redirect(url_for('loyalty.pricing'))
    if request.method == 'POST':
        program.business_name=(request.form.get('business_name') or '').strip()[:150] or program.business_name
        program.title=(request.form.get('title') or 'Tarjeta de lealtad').strip()[:120]
        program.icon=(request.form.get('icon') or '⭐')[:20]
        program.stamp_icon=(request.form.get('stamp_icon') or '✦')[:20]
        color=(request.form.get('color') or '#6d5dfc').strip()
        import re
        if re.fullmatch(r'#[0-9a-fA-F]{6}', color): program.color=color
        try: program.stamps_goal=max(1,min(30,int(request.form.get('stamps_goal','5'))))
        except ValueError: pass
        program.reward_text=(request.form.get('reward_text') or 'Obtén una recompensa').strip()[:255]
        db.session.commit(); flash('Diseño de tarjeta actualizado.', 'success')
        return redirect(url_for('loyalty.dashboard'))
    return render_template('loyalty_configure.html', program=program)


@loyalty_bp.get('/precios')
def pricing():
    user=current_user()
    trial_request = None
    if user and user.role != 'admin':
        get_program(user.company_id, create=True)
        trial_request = (LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id, plan_code='trial14')
                         .order_by(LoyaltyPlanPurchase.created_at.desc()).first())
    trial_active=False; trial_days_left=0
    if user and user.role != 'admin':
        _end, trial_active, trial_days_left = trial_status(get_program(user.company_id))
    return render_template('loyalty_pricing.html', user=user, trial_request=trial_request,
                           trial_active=trial_active, trial_days_left=trial_days_left)


@loyalty_bp.post('/demo/solicitar')
@login_required
def request_trial():
    user=current_user()
    if user.role == 'admin': abort(403)
    program=get_program(user.company_id, create=True)
    existing=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id, plan_code='trial14').first()
    if existing:
        flash('Tu empresa ya registró una solicitud o utilizó su demostración de 14 días.', 'warning')
        return redirect(url_for('loyalty.pricing'))
    purchase=LoyaltyPlanPurchase(company_id=user.company_id, plan_code='trial14', amount=0, status='PENDING')
    db.session.add(purchase)
    db.session.commit()
    flash('Solicitud de demostración enviada. Los 14 días comenzarán cuando NOXTIUM la apruebe.', 'success')
    return redirect(url_for('loyalty.pricing'))


@loyalty_bp.post('/contratar')
@login_required
def contract():
    user=current_user()
    if user.role == 'admin': abort(403)
    code=request.form.get('plan')
    plans={'monthly':(50000,30),'six_months':(250000,183),'team':(80000,30)}
    if code not in plans: abort(400)
    amount,days=plans[code]
    purchase=LoyaltyPlanPurchase(company_id=user.company_id, plan_code=code, amount=amount, status='PENDING')
    db.session.add(purchase); db.session.commit()
    # Payment checkout is deliberately isolated; until provider credentials/webhook are configured, this is a pending payment request.
    return render_template('loyalty_payment.html', purchase=purchase)


@loyalty_bp.post('/pago/<int:purchase_id>/solicitar')
@login_required
def request_payment(purchase_id):
    user=current_user()
    purchase=LoyaltyPlanPurchase.query.filter_by(id=purchase_id, company_id=user.company_id).first_or_404()
    receipt=request.files.get('receipt')
    if not receipt or not receipt.filename:
        flash('Adjunta el comprobante de pago.', 'error')
        return redirect(url_for('loyalty.pricing'))
    from pathlib import Path
    from werkzeug.utils import secure_filename
    from uuid import uuid4
    safe=secure_filename(receipt.filename)
    ext=safe.rsplit('.',1)[-1].lower() if '.' in safe else ''
    if ext not in {'png','jpg','jpeg','pdf'}:
        flash('Formato no permitido. Usa PNG, JPG, JPEG o PDF.', 'error')
        return redirect(url_for('loyalty.pricing'))
    folder=Path(current_app.config['RECEIPTS_UPLOAD_FOLDER']); folder.mkdir(parents=True,exist_ok=True)
    name=f'lealtad_{purchase.id}_{uuid4().hex}_{safe}'
    receipt.save(folder/name)
    purchase.receipt_filename=name
    purchase.status='UNDER_REVIEW'
    db.session.commit()
    flash('Comprobante recibido. NOXTIUM revisará el pago antes de activar el módulo.', 'success')
    return redirect(url_for('loyalty.pricing'))


@loyalty_bp.get('/admin/comprobante/<int:purchase_id>')
@login_required
def admin_receipt(purchase_id):
    user=current_user()
    if user.role != 'admin': abort(403)
    purchase=db.session.get(LoyaltyPlanPurchase,purchase_id)
    if not purchase or not purchase.receipt_filename: abort(404)
    from flask import send_from_directory
    from pathlib import Path
    folder=Path(current_app.config['RECEIPTS_UPLOAD_FOLDER'])
    return send_from_directory(folder, purchase.receipt_filename, as_attachment=False)


@loyalty_bp.get('/admin/pagos')
@login_required
def admin_payments():
    user=current_user()
    if user.role != 'admin': abort(403)
    purchases=LoyaltyPlanPurchase.query.order_by(LoyaltyPlanPurchase.created_at.desc()).all()
    return render_template('loyalty_admin_payments.html', purchases=purchases)


@loyalty_bp.post('/admin/pagos/<int:purchase_id>/aprobar')
@login_required
def approve_payment(purchase_id):
    user=current_user()
    if user.role != 'admin': abort(403)
    purchase=db.session.get(LoyaltyPlanPurchase,purchase_id)
    if not purchase: abort(404)
    if purchase.plan_code == 'trial14' and purchase.status != 'PENDING': abort(404)
    if purchase.plan_code != 'trial14' and purchase.status != 'UNDER_REVIEW': abort(404)
    now=utcnow()
    if purchase.plan_code == 'trial14':
        program=get_program(purchase.company_id, create=True)
        if program.trial_started_at:
            flash('Esta empresa ya tiene una demostración iniciada.', 'warning')
            return redirect(url_for('loyalty.admin_payments'))
        program.trial_started_at=now
        purchase.starts_at=now
        purchase.expires_at=now+timedelta(days=TRIAL_DAYS)
        purchase.status='ACTIVE'
        db.session.commit()
        flash('Demostración de 14 días aprobada. El conteo comenzó en este momento.', 'success')
        return redirect(url_for('loyalty.admin_payments'))
    duration=183 if purchase.plan_code=='six_months' else 30
    current=LoyaltyPlanPurchase.query.filter_by(company_id=purchase.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.expires_at>now).order_by(LoyaltyPlanPurchase.expires_at.desc()).first()
    purchase.starts_at=max(now,current.expires_at) if current and current.expires_at else now
    purchase.expires_at=purchase.starts_at+timedelta(days=duration)
    purchase.status='ACTIVE'
    db.session.commit()
    flash('Plan de tarjetas de lealtad activado.', 'success')
    return redirect(url_for('loyalty.admin_payments'))


@loyalty_bp.post('/clientes/registrar/<int:company_id>')
def enroll(company_id):
    program=get_program(company_id)
    if not program: abort(404)
    end,active,days=trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid:
        return render_template('loyalty_public_expired.html', program=program), 402
    name=(request.form.get('name') or '').strip()[:150]
    phone=''.join(ch for ch in (request.form.get('phone') or '') if ch.isdigit() or ch=='+')[:50]
    if not name or len(phone)<7 or not request.form.get('privacy_consent'):
        flash('Escribe tu nombre, un teléfono válido y acepta el tratamiento de datos para crear la tarjeta.', 'error'); return redirect(url_for('loyalty.enroll_page', company_id=company_id))
    customer=LoyaltyCustomer.query.filter_by(company_id=company_id, phone=phone).first()
    if not customer:
        customer=LoyaltyCustomer(company_id=company_id, program_id=program.id, name=name, phone=phone)
        db.session.add(customer)
    customer.name=name
    customer.privacy_consent=True
    # Consent is explicit per channel and captured with timestamp/version for audit.
    customer.consent_whatsapp=bool(request.form.get('consent_whatsapp'))
    customer.consent_sms=bool(request.form.get('consent_sms'))
    customer.consent_push=bool(request.form.get('consent_push'))
    customer.notification_consent=customer.consent_whatsapp or customer.consent_sms or customer.consent_push
    customer.consent_at=utcnow() if customer.notification_consent else None
    customer.consent_text_version='2026-11-v1' if customer.notification_consent else None
    db.session.commit()
    return redirect(url_for('loyalty.wallet', token=customer.token))


@loyalty_bp.get('/unirse/<int:company_id>')
def enroll_page(company_id):
    program=get_program(company_id)
    if not program: abort(404)
    return render_template('loyalty_enroll.html', program=program, company_id=company_id)


@loyalty_bp.get('/manifest/<token>.webmanifest')
def wallet_manifest(token):
    customer=LoyaltyCustomer.query.filter_by(token=token).first_or_404()
    program=db.session.get(LoyaltyProgram, customer.program_id)
    response=jsonify({
        'name': f'{program.business_name} · {program.title}',
        'short_name': program.business_name[:24],
        'start_url': url_for('loyalty.wallet', token=token),
        'scope': '/lealtad/', 'display': 'standalone',
        'background_color': '#ffffff', 'theme_color': program.color,
        'icons': [{'src': url_for('static', filename='icons/loyalty.svg'), 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any maskable'}]
    })
    response.headers['Content-Type']='application/manifest+json'
    return response


@loyalty_bp.get('/service-worker.js')
def wallet_service_worker():
    from flask import send_from_directory, make_response
    response=make_response(send_from_directory(current_app.static_folder, 'loyalty-sw.js'))
    response.headers['Service-Worker-Allowed']='/lealtad/'
    response.headers['Content-Type']='application/javascript'
    return response


@loyalty_bp.get('/tarjeta/<token>')
def wallet(token):
    customer=LoyaltyCustomer.query.filter_by(token=token).first_or_404()
    program=db.session.get(LoyaltyProgram, customer.program_id)
    return render_template('loyalty_wallet.html', customer=customer, program=program,
                           google_wallet_enabled=google_wallet_configured())


@loyalty_bp.get('/google-wallet/logo/<int:company_id>.png')
def wallet_logo(company_id):
    program=get_program(company_id)
    if not program: abort(404)
    from PIL import Image, ImageDraw
    from flask import send_file
    import io
    image=Image.new('RGB',(512,512),program.color if re.fullmatch(r"#[0-9a-fA-F]{6}", program.color or "") else "#333333")
    draw=ImageDraw.Draw(image)
    initials=''.join(part[0] for part in (program.business_name or 'NOXTIUM').split()[:2]).upper() or 'N'
    draw.ellipse((76,76,436,436),outline='white',width=14)
    draw.text((256,256),initials,fill='white',anchor='mm',stroke_width=1)
    output=io.BytesIO(); image.save(output,format='PNG'); output.seek(0)
    return send_file(output,mimetype='image/png',max_age=86400)


@loyalty_bp.get('/google-wallet/<token>')
def add_to_google_wallet(token):
    customer=LoyaltyCustomer.query.filter_by(token=token).first_or_404()
    program=db.session.get(LoyaltyProgram, customer.program_id)
    if not google_wallet_configured():
        abort(503, description='Google Wallet no está configurado en el servidor.')
    try:
        return redirect(_google_wallet_save_url(customer, program))
    except Exception as exc:
        current_app.logger.exception('Error generando pase Google Wallet para cliente %s', customer.id)
        flash(f'No se pudo preparar Google Wallet: {str(exc)[:220]}', 'error')
        return redirect(url_for('loyalty.wallet', token=token))


@loyalty_bp.get('/qr/<token>.png')
def customer_qr(token):
    customer=LoyaltyCustomer.query.filter_by(token=token).first_or_404()
    import qrcode, io
    from flask import send_file
    img=qrcode.make(url_for('loyalty.stamp_page', token=token, _external=True))
    buf=io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png', download_name='mi-tarjeta.png')


@loyalty_bp.get('/qr-negocio/<int:company_id>.png')
@login_required
def business_qr(company_id):
    user=current_user()
    if user.company_id != company_id or user.role == 'admin': abort(403)
    import qrcode, io
    from flask import send_file
    img=qrcode.make(url_for('loyalty.enroll_page', company_id=company_id, _external=True))
    buf=io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png', download_name='qr-inscripcion.png')


@loyalty_bp.get('/escanear')
@login_required
def scan_page():
    user=current_user()
    if user.role == 'admin': abort(403)
    program=get_program(user.company_id)
    end,active,days=trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid: return redirect(url_for('loyalty.pricing'))
    return render_template('loyalty_scan.html')


@loyalty_bp.post('/escanear/buscar')
@login_required
def scan_lookup():
    user=current_user()
    if user.role == 'admin': abort(403)
    data=request.get_json(silent=True) or {}
    token=(data.get('token') or '').strip()
    if not re.fullmatch(r'[a-fA-F0-9]{32,64}', token):
        return jsonify(ok=False, message='El QR no corresponde a una tarjeta válida.'), 400
    customer=LoyaltyCustomer.query.filter_by(token=token, company_id=user.company_id).first()
    if not customer:
        return jsonify(ok=False, message='Esta tarjeta no pertenece a tu negocio o no existe.'), 404
    return jsonify(ok=True, name=customer.name, phone=customer.phone,
                   stamps=customer.stamps, goal=customer.program_id and db.session.get(LoyaltyProgram, customer.program_id).stamps_goal,
                   icon=db.session.get(LoyaltyProgram, customer.program_id).stamp_icon,
                   confirm_url=url_for('loyalty.stamp_page', token=customer.token))


@loyalty_bp.get('/tarjeta-datos/<token>')
def wallet_data(token):
    customer=LoyaltyCustomer.query.filter_by(token=token).first_or_404()
    program=db.session.get(LoyaltyProgram, customer.program_id)
    return jsonify(stamps=customer.stamps, goal=program.stamps_goal, stamp_icon=program.stamp_icon,
                   reward_text=program.reward_text, updated_at=customer.last_visit_at.isoformat() if customer.last_visit_at else None)


@loyalty_bp.get('/sellar/<token>')
@login_required
def stamp_page(token):
    user=current_user()
    if user.role == 'admin': abort(403)
    customer=LoyaltyCustomer.query.filter_by(token=token, company_id=user.company_id).first_or_404()
    program=get_program(user.company_id)
    end,active,days=trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid: return redirect(url_for('loyalty.pricing'))
    return render_template('loyalty_stamp.html', customer=customer, program=program)


@loyalty_bp.post('/sellar/<token>')
@login_required
def stamp(token):
    user=current_user()
    if user.role == 'admin': abort(403)
    program=get_program(user.company_id)
    end,active,days=trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid: return redirect(url_for('loyalty.pricing'))
    customer=LoyaltyCustomer.query.filter_by(token=token, company_id=user.company_id).first_or_404()
    db.session.add(LoyaltyStamp(company_id=user.company_id, customer_id=customer.id, approved_by_user_id=user.id))
    customer.stamps += 1; customer.last_visit_at=utcnow()
    db.session.commit()
    _sync_google_wallet_customer(customer)
    flash('Sello aprobado y visita registrada.', 'success')
    return redirect(url_for('loyalty.dashboard'))


@loyalty_bp.route('/promociones', methods=['GET','POST'])
@login_required
def campaigns():
    user=current_user()
    if user.role == 'admin': abort(403)
    program=get_program(user.company_id, create=True)
    end,active,days=trial_status(program)
    paid=LoyaltyPlanPurchase.query.filter_by(company_id=user.company_id,status='ACTIVE').filter(LoyaltyPlanPurchase.plan_code != 'trial14', LoyaltyPlanPurchase.expires_at>utcnow()).first() is not None
    if not active and not paid: return redirect(url_for('loyalty.pricing'))
    customers=LoyaltyCustomer.query.filter_by(company_id=user.company_id).order_by(LoyaltyCustomer.name.asc()).all()
    if request.method=='POST':
        title=(request.form.get('title') or '').strip()[:150]
        message=(request.form.get('message') or '').strip()[:2000]
        target_type=request.form.get('target_type','mass')
        channel=request.form.get('channel','push')
        target_id=request.form.get('customer_id', type=int)
        if not title or not message:
            flash('Completa el título y el mensaje.', 'error')
            return redirect(url_for('loyalty.campaigns'))
        if channel != 'push':
            flash('Este canal todavía requiere conectar un proveedor de WhatsApp Business o SMS. No se marcará como enviado.', 'warning')
            return redirect(url_for('loyalty.campaigns'))
        query=LoyaltyPushSubscription.query.join(LoyaltyCustomer, LoyaltyCustomer.id==LoyaltyPushSubscription.customer_id).filter(
            LoyaltyPushSubscription.company_id==user.company_id, LoyaltyCustomer.consent_push.is_(True))
        if target_type=='single':
            customer=LoyaltyCustomer.query.filter_by(id=target_id, company_id=user.company_id, consent_push=True).first()
            if not customer:
                flash('El cliente no existe o no autorizó notificaciones push.', 'error')
                return redirect(url_for('loyalty.campaigns'))
            query=query.filter(LoyaltyPushSubscription.customer_id==customer.id)
        else:
            target_type='mass'
        recipients=query.all(); sent=0; failures=0
        public_key=current_app.config.get('VAPID_PUBLIC_KEY','')
        private_key=current_app.config.get('VAPID_PRIVATE_KEY','')
        subject=current_app.config.get('VAPID_SUBJECT','mailto:soporte@noxtium.com')
        if public_key and private_key and recipients:
            try:
                from pywebpush import webpush
                payload=json.dumps({'title':title,'body':message,'url':url_for('loyalty.dashboard',_external=True)})
                for sub in recipients:
                    try:
                        webpush({'endpoint':sub.endpoint,'keys':{'p256dh':sub.p256dh,'auth':sub.auth}}, payload, vapid_private_key=private_key, vapid_claims={'sub':subject})
                        sent+=1
                    except Exception:
                        failures+=1
            except ImportError:
                failures=len(recipients)
        campaign=LoyaltyCampaign(company_id=user.company_id,title=title,message=message,sent_count=sent,
            target_type=target_type,target_customer_id=target_id if target_type=='single' else None,channel='push')
        db.session.add(campaign); db.session.commit()
        if not public_key or not private_key:
            flash('Promoción guardada, pero no enviada: faltan las claves VAPID del servidor.', 'warning')
        else:
            flash(f'Envío push finalizado: {sent} notificaciones procesadas; {failures} fallidas.', 'success' if sent else 'warning')
        return redirect(url_for('loyalty.campaigns'))
    history=LoyaltyCampaign.query.filter_by(company_id=user.company_id).order_by(LoyaltyCampaign.created_at.desc()).limit(20).all()
    return render_template('loyalty_campaigns.html', history=history, customers=customers)


@loyalty_bp.post('/push/<token>')
def save_push(token):
    customer=LoyaltyCustomer.query.filter_by(token=token, consent_push=True).first_or_404()
    data=request.get_json(silent=True) or {}
    endpoint=data.get('endpoint'); keys=data.get('keys') or {}
    if not endpoint or not keys.get('p256dh') or not keys.get('auth'): return jsonify(ok=False),400
    sub=LoyaltyPushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        sub=LoyaltyPushSubscription(company_id=customer.company_id,customer_id=customer.id,endpoint=endpoint,p256dh=keys['p256dh'],auth=keys['auth'])
        db.session.add(sub)
    else:
        sub.customer_id=customer.id; sub.company_id=customer.company_id; sub.p256dh=keys['p256dh']; sub.auth=keys['auth']
    db.session.commit(); return jsonify(ok=True)
