import sys
from datetime import date, timedelta
from functools import wraps

from flask import (Flask, render_template, redirect, url_for,
                   request, abort, Response, flash)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)

from models import (
    db, Judge, JudicialYear, JudicialVacation,
    Chamber, ChamberDay, ChamberRole, SpecialDate, JourSansAudience,
    SessionAssignment, WEEKDAY_NAMES,
)

# ── App setup ──────────────────────────────────────────────────────────────
import os

app = Flask(__name__)
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///tribunal.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

_engine_kwargs = {}
if _db_url.startswith('postgresql://') and '+' not in _db_url.split('://')[0]:
    import ssl, certifi
    _db_url = _db_url.replace('?sslmode=require', '').replace('&sslmode=require', '')
    _db_url = _db_url.replace('postgresql://', 'postgresql+pg8000://', 1)
    _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    _engine_kwargs = {'connect_args': {'ssl_context': _ssl_ctx}}

app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = _engine_kwargs
app.config['SECRET_KEY'] = os.environ.get(
    'SECRET_KEY', 'tribunal-planning-secret-2025'
)
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Veuillez vous connecter pour accéder à cette page.'

@login_manager.user_loader
def load_user(uid):
    return Judge.query.get(int(uid))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── French locale helpers ──────────────────────────────────────────────────
FRENCH_MONTHS = {
    1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
    5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
    9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre',
}
FRENCH_WEEKDAYS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']


@app.template_filter('fr_date')
def fr_date(d):
    return f'{FRENCH_WEEKDAYS[d.weekday()]} {d.day} {FRENCH_MONTHS[d.month]} {d.year}'


@app.template_filter('fr_month')
def fr_month(d):
    return f'{FRENCH_MONTHS[d.month]} {d.year}'


@app.template_filter('fr_weekday')
def fr_weekday(d):
    return FRENCH_WEEKDAYS[d.weekday()]


@app.context_processor
def inject_globals():
    return {'today': date.today()}


# ── Calendar / business logic ──────────────────────────────────────────────
def get_easter(year):
    a = year % 19; b = year // 100; c = year % 100
    d = b // 4;   e = b % 4;       f = (b + 8) // 25
    g = (b - f + 1) // 3;          h = (19*a + b - d - g + 15) % 30
    i = c // 4;   k = c % 4;       l = (32 + 2*e + 2*i - h - k) % 7
    m = (a + 11*h + 22*l) // 451
    month = (h + l - 7*m + 114) // 31
    day   = ((h + l - 7*m + 114) % 31) + 1
    return date(year, month, day)


def get_public_holidays(start_year, end_year):
    holidays = {}
    for year in range(start_year, end_year + 1):
        e = get_easter(year)
        holidays.update({
            date(year, 1, 1):  "Jour de l'An",
            e:                 'Pâques',
            e + timedelta(1):  'Lundi de Pâques',
            date(year, 5, 1):  'Fête du Travail',
            date(year, 5, 8):  'Victoire 1945',
            e + timedelta(39): 'Ascension',
            e + timedelta(49): 'Pentecôte',
            e + timedelta(50): 'Lundi de Pentecôte',
            date(year, 7, 14): 'Fête Nationale',
            date(year, 8, 15): 'Assomption',
            date(year, 11, 1): 'Toussaint',
            date(year, 11, 11):'Armistice 1918',
            date(year, 12, 25):'Noël',
        })
    return holidays


def classify_date(d, chamber, public_holidays, vacations, jsa_dict):
    """Return (status, note) for a date that falls on a chamber sitting day."""
    if d in jsa_dict:
        return 'pas_audience', jsa_dict[d].reason
    special = next((s for s in chamber.special_dates if s.date == d), None)
    if special:
        return 'special', special.description
    if d in public_holidays:
        return 'ferie', public_holidays[d]
    vac = next((v for v in vacations if v.start_date <= d <= v.end_date), None)
    if vac:
        return 'vacation', f'Vacations judiciaires — {vac.label}'
    return 'audience', ''


def generate_agenda(chamber):
    jy = JudicialYear.query.first()
    if not jy:
        return []
    vacations     = JudicialVacation.query.all()
    public_hols   = get_public_holidays(jy.start_date.year, jy.end_date.year)
    jsa_dict      = {j.date: j for j in JourSansAudience.query.all()}
    wd_set        = chamber.weekdays_set

    results = []
    cur = jy.start_date
    while cur <= jy.end_date:
        if cur.weekday() in wd_set:
            status, note = classify_date(cur, chamber, public_hols, vacations, jsa_dict)
            results.append({
                'date':    cur,
                'weekday': FRENCH_WEEKDAYS[cur.weekday()],
                'status':  status,
                'note':    note,
            })
        cur += timedelta(days=1)
    return results


def group_by_month(sessions):
    groups = {}
    for s in sessions:
        key = (s['date'].year, s['date'].month)
        groups.setdefault(key, []).append(s)
    return [
        {'label': f"{FRENCH_MONTHS[m]} {y}", 'sessions': items}
        for (y, m), items in sorted(groups.items())
    ]


def get_busy_judge_ids(target_date):
    return {
        sa.judge_id
        for sa in SessionAssignment.query.filter_by(date=target_date).all()
    }


def get_planning_for_month(chamber, year, month):
    all_sessions = generate_agenda(chamber)
    month_sessions = [s for s in all_sessions
                      if s['date'].year == year and s['date'].month == month]

    result = []
    for s in month_sessions:
        d = s['date']
        assignments = SessionAssignment.query.filter_by(chamber_id=chamber.id, date=d).all()
        presidents  = [a for a in assignments if a.role == 'president']
        assesseurs  = [a for a in assignments if a.role == 'assesseur']

        if s['status'] == 'audience':
            busy = get_busy_judge_ids(d)
            avail_pres = [
                cr.judge for cr in ChamberRole.query.filter_by(
                    chamber_id=chamber.id, role='president').all()
                if cr.judge_id not in busy
            ]
            avail_asses = [
                cr.judge for cr in ChamberRole.query.filter_by(
                    chamber_id=chamber.id, role='assesseur').all()
                if cr.judge_id not in busy
            ]
        else:
            avail_pres = avail_asses = []

        result.append({
            **s,
            'presidents':          presidents,
            'assesseurs':          assesseurs,
            'available_presidents': avail_pres,
            'available_assesseurs': avail_asses,
            'is_complete':          len(presidents) >= 1 and len(assesseurs) >= 2,
        })
    return result


def _prev_next_month(year, month):
    pm = month - 1 or 12
    py = year - (1 if month == 1 else 0)
    nm = month % 12 + 1
    ny = year + (1 if month == 12 else 0)
    return (py, pm), (ny, nm)


# ══════════════════════════════════════════════════════════════════════════
# Auth
# ══════════════════════════════════════════════════════════════════════════

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        judge = Judge.query.filter(
            db.func.lower(Judge.email) == email
        ).first()
        if judge and judge.check_password(password) and judge.is_active:
            login_user(judge, remember=request.form.get('remember') == '1')
            return redirect(request.args.get('next') or url_for('index'))
        flash('Email ou mot de passe incorrect.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ══════════════════════════════════════════════════════════════════════════
# Main views
# ══════════════════════════════════════════════════════════════════════════

@app.route('/')
@login_required
def index():
    chambers = Chamber.query.order_by(Chamber.sort_order).all()
    jy = JudicialYear.query.first()
    return render_template('index.html', chambers=chambers, jy=jy)


def _auto_fill_sole_president(chamber):
    """If chamber has exactly one president role, auto-assign them to every
    unassigned audience session (skipped if they're already busy that day)."""
    pres_roles = [r for r in chamber.roles if r.role == 'president']
    if len(pres_roles) != 1:
        return
    sole = pres_roles[0]
    changed = False
    for s in generate_agenda(chamber):
        if s['status'] != 'audience':
            continue
        d = s['date']
        if SessionAssignment.query.filter_by(chamber_id=chamber.id, date=d, role='president').first():
            continue
        busy = {sa.judge_id for sa in SessionAssignment.query.filter_by(date=d).all()}
        if sole.judge_id not in busy:
            db.session.add(SessionAssignment(
                chamber_id=chamber.id, date=d,
                judge_id=sole.judge_id, role='president'))
            changed = True
    if changed:
        db.session.commit()


def _augment_sessions(chamber, sessions):
    """Attach assignment data (and available judges for admin) to each session dict."""
    # One query for all assignments of this chamber — avoids N+1
    all_ch_assignments = SessionAssignment.query.filter_by(chamber_id=chamber.id).all()
    by_date = {}
    for a in all_ch_assignments:
        by_date.setdefault(a.date, []).append(a)

    # One query for all assignments across ALL chambers (for availability)
    all_assignments = SessionAssignment.query.all()
    busy_by_date: dict = {}
    for a in all_assignments:
        busy_by_date.setdefault(a.date, set()).add(a.judge_id)

    pres_roles  = (ChamberRole.query.filter_by(chamber_id=chamber.id, role='president')
                   .join(Judge).filter(Judge.is_active == True).all())
    asses_roles = (ChamberRole.query.filter_by(chamber_id=chamber.id, role='assesseur')
                   .join(Judge).filter(Judge.is_active == True).all())

    for s in sessions:
        d = s['date']
        day = by_date.get(d, [])
        s['presidents']  = [a for a in day if a.role == 'president']
        s['assesseurs_assigned'] = [a for a in day if a.role == 'assesseur']
        s['is_complete'] = len(s['presidents']) >= 1 and len(s['assesseurs_assigned']) >= 2

        if s['status'] == 'audience':
            busy = busy_by_date.get(d, set())
            s['available_presidents'] = [r.judge for r in pres_roles  if r.judge_id not in busy]
            s['available_assesseurs'] = [r.judge for r in asses_roles if r.judge_id not in busy]
        else:
            s['available_presidents'] = []
            s['available_assesseurs'] = []

    return sessions


@app.route('/agenda/<int:chamber_id>', methods=['GET', 'POST'])
@login_required
def agenda(chamber_id):
    chamber = db.get_or_404(Chamber, chamber_id)

    if request.method == 'POST':
        if not current_user.is_admin:
            abort(403)
        action   = request.form.get('action')
        date_str = request.form.get('date', '')

        if action == 'assign':
            d        = date.fromisoformat(date_str)
            judge_id = int(request.form['judge_id'])
            role     = request.form['role']
            busy     = get_busy_judge_ids(d)
            if judge_id not in busy:
                existing = SessionAssignment.query.filter_by(
                    chamber_id=chamber.id, date=d, judge_id=judge_id).first()
                if not existing:
                    db.session.add(SessionAssignment(
                        chamber_id=chamber.id, date=d,
                        judge_id=judge_id, role=role))
                    db.session.commit()

        elif action == 'unassign':
            sa = db.get_or_404(SessionAssignment, int(request.form['assignment_id']))
            db.session.delete(sa)
            db.session.commit()

        return redirect(url_for('agenda', chamber_id=chamber_id) + f'#s-{date_str}')

    _auto_fill_sole_president(chamber)
    sessions = _augment_sessions(chamber, generate_agenda(chamber))
    groups   = group_by_month(sessions)
    audience_sessions = [s for s in sessions if s['status'] == 'audience']
    stats = {
        'total':        len(sessions),
        'audience':     len(audience_sessions),
        'complete':     sum(1 for s in audience_sessions if s['is_complete']),
        'special':      sum(1 for s in sessions if s['status'] == 'special'),
        'ferie':        sum(1 for s in sessions if s['status'] == 'ferie'),
        'vacation':     sum(1 for s in sessions if s['status'] == 'vacation'),
        'pas_audience': sum(1 for s in sessions if s['status'] == 'pas_audience'),
    }
    return render_template('agenda.html', chamber=chamber, groups=groups, stats=stats)


@app.route('/agenda/<int:chamber_id>/print')
@login_required
def agenda_print(chamber_id):
    chamber  = db.get_or_404(Chamber, chamber_id)
    sessions = _augment_sessions(chamber, generate_agenda(chamber))
    groups   = group_by_month(sessions)
    jy       = JudicialYear.query.first()
    return render_template('agenda_print.html', chamber=chamber, groups=groups, jy=jy)


# ── Day view ───────────────────────────────────────────────────────────────

@app.route('/day')
@login_required
def day_today():
    t = date.today()
    return redirect(url_for('day_view', year=t.year, month=t.month, day=t.day))


@app.route('/day/<int:year>/<int:month>/<int:day>')
@login_required
def day_view(year, month, day):
    try:
        target = date(year, month, day)
    except ValueError:
        abort(404)

    vacations   = JudicialVacation.query.all()
    public_hols = get_public_holidays(year, year)
    jsa_dict    = {j.date: j for j in JourSansAudience.query.all()}
    chambers    = Chamber.query.order_by(Chamber.sort_order).all()

    day_data = []
    for chamber in chambers:
        if target.weekday() not in chamber.weekdays_set:
            continue
        status, note = classify_date(target, chamber, public_hols, vacations, jsa_dict)
        assignments  = SessionAssignment.query.filter_by(
            chamber_id=chamber.id, date=target).all()
        presidents   = [a for a in assignments if a.role == 'president']
        assesseurs   = [a for a in assignments if a.role == 'assesseur']
        day_data.append({
            'chamber':     chamber,
            'status':      status,
            'note':        note,
            'presidents':  presidents,
            'assesseurs':  assesseurs,
            'is_complete': len(presidents) >= 1 and len(assesseurs) >= 2,
        })

    prev_d = target - timedelta(days=1)
    next_d = target + timedelta(days=1)
    return render_template('day_view.html',
                           target=target, day_data=day_data,
                           prev_d=prev_d, next_d=next_d)


# ── Monthly planning ───────────────────────────────────────────────────────

@app.route('/planning/<int:chamber_id>')
@login_required
def planning_current(chamber_id):
    t = date.today()
    return redirect(url_for('planning', chamber_id=chamber_id, year=t.year, month=t.month))


@app.route('/planning/<int:chamber_id>/<int:year>/<int:month>', methods=['GET', 'POST'])
@login_required
def planning(chamber_id, year, month):
    chamber = db.get_or_404(Chamber, chamber_id)

    if request.method == 'POST':
        if not current_user.is_admin:
            abort(403)
        action = request.form.get('action')

        if action == 'assign':
            try:
                d        = date.fromisoformat(request.form['date'])
                judge_id = int(request.form['judge_id'])
                role     = request.form['role']
            except (ValueError, KeyError):
                abort(400)

            busy = get_busy_judge_ids(d)
            if judge_id in busy:
                flash('Ce juge est déjà assigné à une audience ce jour-là.', 'error')
            else:
                exists = SessionAssignment.query.filter_by(
                    chamber_id=chamber.id, date=d, judge_id=judge_id).first()
                if not exists:
                    db.session.add(SessionAssignment(
                        chamber_id=chamber.id, date=d,
                        judge_id=judge_id, role=role,
                    ))
                    db.session.commit()

        elif action == 'unassign':
            sa = db.get_or_404(SessionAssignment, int(request.form['assignment_id']))
            db.session.delete(sa)
            db.session.commit()

        return redirect(url_for('planning', chamber_id=chamber_id,
                                year=year, month=month) +
                        f'#s-{request.form.get("date", "")}')

    sessions_data = get_planning_for_month(chamber, year, month)
    prev, nxt     = _prev_next_month(year, month)
    month_label   = f'{FRENCH_MONTHS[month]} {year}'
    total    = sum(1 for s in sessions_data if s['status'] == 'audience')
    complete = sum(1 for s in sessions_data if s['status'] == 'audience' and s['is_complete'])

    return render_template('planning.html',
                           chamber=chamber, year=year, month=month,
                           month_label=month_label, sessions_data=sessions_data,
                           prev=prev, nxt=nxt,
                           total=total, complete=complete)


# ── Statistics ─────────────────────────────────────────────────────────────

@app.route('/stats')
@login_required
def stats():
    chambers = Chamber.query.order_by(Chamber.sort_order).all()
    judges   = Judge.query.filter_by(is_active=True).order_by(Judge.name).all()

    # Per-judge totals
    judge_stats = []
    max_total = 0
    for judge in judges:
        pres  = SessionAssignment.query.filter_by(judge_id=judge.id, role='president').count()
        asses = SessionAssignment.query.filter_by(judge_id=judge.id, role='assesseur').count()
        total = pres + asses
        max_total = max(max_total, total)

        # Breakdown per chamber
        breakdown = []
        for c in chambers:
            cp = SessionAssignment.query.filter_by(
                judge_id=judge.id, chamber_id=c.id, role='president').count()
            ca = SessionAssignment.query.filter_by(
                judge_id=judge.id, chamber_id=c.id, role='assesseur').count()
            if cp or ca:
                breakdown.append({'chamber': c, 'president': cp, 'assesseur': ca})

        judge_stats.append({
            'judge':     judge,
            'president': pres,
            'assesseur': asses,
            'total':     total,
            'breakdown': breakdown,
        })

    judge_stats.sort(key=lambda x: -x['total'])

    # Per-chamber planning coverage
    chamber_stats = []
    for c in chambers:
        planned  = db.session.query(
            db.func.count(db.func.distinct(SessionAssignment.date))
        ).filter_by(chamber_id=c.id).scalar() or 0
        assigned = SessionAssignment.query.filter_by(chamber_id=c.id).count()
        # Total audience sessions in the year (rough count)
        all_ag = generate_agenda(c)
        total_audience = sum(1 for s in all_ag if s['status'] == 'audience')
        chamber_stats.append({
            'chamber':       c,
            'sessions_done': planned,
            'total_audience':total_audience,
            'total_assigned':assigned,
        })

    return render_template('stats.html',
                           judge_stats=judge_stats, chamber_stats=chamber_stats,
                           max_total=max_total or 1)


# ── Personal schedule ──────────────────────────────────────────────────────

@app.route('/mon-planning')
@login_required
def my_schedule():
    assignments = (
        SessionAssignment.query
        .filter_by(judge_id=current_user.id)
        .join(Chamber)
        .order_by(SessionAssignment.date)
        .all()
    )

    groups: dict = {}
    for a in assignments:
        key = (a.date.year, a.date.month)
        groups.setdefault(key, []).append(a)

    grouped = [
        {'label': f'{FRENCH_MONTHS[m]} {y}', 'assignments': items}
        for (y, m), items in sorted(groups.items())
    ]
    return render_template('my_schedule.html', grouped=grouped)


@app.route('/mon-planning/export.ics')
@login_required
def my_schedule_ics():
    assignments = (
        SessionAssignment.query
        .filter_by(judge_id=current_user.id)
        .join(Chamber)
        .order_by(SessionAssignment.date)
        .all()
    )

    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0',
        'PRODID:-//Tribunal Planning//FR',
        'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
    ]
    for a in assignments:
        c    = a.chamber
        role = 'Président' if a.role == 'president' else 'Assesseur'
        dt   = a.date.strftime('%Y%m%d')
        dt1  = (a.date + timedelta(1)).strftime('%Y%m%d')
        desc = f'{role} — {c.name}'
        if c.start_time:
            desc += f'\\nHeure : {c.start_time}'
        lines += [
            'BEGIN:VEVENT',
            f'UID:sa-{a.id}@tribunal',
            f'DTSTART;VALUE=DATE:{dt}',
            f'DTEND;VALUE=DATE:{dt1}',
            f'SUMMARY:{c.name} ({role})',
            f'DESCRIPTION:{desc}',
            'STATUS:CONFIRMED',
            'END:VEVENT',
        ]
    lines.append('END:VCALENDAR')

    return Response(
        '\r\n'.join(lines),
        mimetype='text/calendar',
        headers={'Content-Disposition':
                 f'attachment; filename="planning_{current_user.name.replace(" ", "_")}.ics"'},
    )


# ══════════════════════════════════════════════════════════════════════════
# Config — judicial year & vacations
# ══════════════════════════════════════════════════════════════════════════

@app.route('/config')
@login_required
@admin_required
def config_index():
    return render_template('config/index.html')


@app.route('/config/year', methods=['GET', 'POST'])
@login_required
@admin_required
def config_year():
    jy        = JudicialYear.query.first()
    vacations = JudicialVacation.query.order_by(JudicialVacation.type).all()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_year':
            s = date.fromisoformat(request.form['start_date'])
            e = date.fromisoformat(request.form['end_date'])
            if jy:
                jy.start_date, jy.end_date = s, e
            else:
                db.session.add(JudicialYear(start_date=s, end_date=e))
            db.session.commit()
        elif action == 'add_vacation':
            db.session.add(JudicialVacation(
                type=request.form['type'],
                start_date=date.fromisoformat(request.form['start_date']),
                end_date=date.fromisoformat(request.form['end_date']),
            ))
            db.session.commit()
        elif action == 'delete_vacation':
            v = db.get_or_404(JudicialVacation, int(request.form['vacation_id']))
            db.session.delete(v); db.session.commit()
        return redirect(url_for('config_year'))

    return render_template('config/year.html', jy=jy, vacations=vacations)


# ══════════════════════════════════════════════════════════════════════════
# Config — chambers
# ══════════════════════════════════════════════════════════════════════════

@app.route('/config/chambers')
@login_required
@admin_required
def config_chambers():
    chambers = Chamber.query.order_by(Chamber.sort_order).all()
    return render_template('config/chambers.html', chambers=chambers)


@app.route('/config/chamber/new', methods=['GET', 'POST'])
@login_required
@admin_required
def config_chamber_new():
    if request.method == 'POST':
        max_order = db.session.query(db.func.max(Chamber.sort_order)).scalar() or 0
        chamber = Chamber(
            name=request.form['name'].strip(),
            start_time=request.form.get('start_time', '').strip(),
            sort_order=max_order + 1,
        )
        db.session.add(chamber)
        db.session.flush()
        for wd in request.form.getlist('weekdays'):
            db.session.add(ChamberDay(chamber_id=chamber.id, weekday=int(wd)))
        db.session.commit()
        return redirect(url_for('config_chamber_edit', chamber_id=chamber.id))
    all_weekdays = list(WEEKDAY_NAMES.items())
    return render_template('config/chamber_new.html', all_weekdays=all_weekdays)


@app.route('/config/chamber/<int:chamber_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def config_chamber_edit(chamber_id):
    chamber = db.get_or_404(Chamber, chamber_id)
    all_judges = Judge.query.filter_by(is_active=True).order_by(Judge.name).all()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            chamber.name       = request.form['name'].strip()
            chamber.start_time = request.form['start_time'].strip()
            db.session.commit()

        elif action == 'update_days':
            ChamberDay.query.filter_by(chamber_id=chamber.id).delete()
            for wd in request.form.getlist('weekdays'):
                db.session.add(ChamberDay(chamber_id=chamber.id, weekday=int(wd)))
            db.session.commit()

        elif action == 'add_role':
            judge_id = int(request.form['judge_id'])
            role     = request.form['role']
            max_order = db.session.query(db.func.max(ChamberRole.sort_order))\
                          .filter_by(chamber_id=chamber.id).scalar() or 0
            existing = ChamberRole.query.filter_by(
                chamber_id=chamber.id, judge_id=judge_id, role=role).first()
            if not existing:
                db.session.add(ChamberRole(
                    chamber_id=chamber.id, judge_id=judge_id,
                    role=role, sort_order=max_order + 1,
                ))
                db.session.commit()

        elif action == 'delete_role':
            cr = db.get_or_404(ChamberRole, int(request.form['role_id']))
            db.session.delete(cr); db.session.commit()

        return redirect(url_for('config_chamber_edit', chamber_id=chamber.id))

    all_weekdays     = list(WEEKDAY_NAMES.items())
    current_weekdays = {d.weekday for d in chamber.days}
    assigned_combos  = {(r.judge_id, r.role) for r in chamber.roles}
    return render_template('config/chamber_edit.html',
                           chamber=chamber, all_judges=all_judges,
                           all_weekdays=all_weekdays,
                           current_weekdays=current_weekdays,
                           assigned_combos=assigned_combos)


# ══════════════════════════════════════════════════════════════════════════
# Config — judges
# ══════════════════════════════════════════════════════════════════════════

@app.route('/config/judges')
@login_required
@admin_required
def config_judges():
    judges = Judge.query.order_by(Judge.name).all()
    return render_template('config/judges.html', judges=judges)


@app.route('/config/judge/new', methods=['GET', 'POST'])
@login_required
@admin_required
def config_judge_new():
    if request.method == 'POST':
        name  = request.form['name'].strip()
        email = request.form.get('email', '').strip().lower() or None
        pw    = request.form.get('password', '').strip() or None
        is_admin = request.form.get('is_admin') == '1'

        if Judge.query.filter_by(name=name).first():
            flash(f'Un juge nommé « {name} » existe déjà.', 'error')
            return render_template('config/judge_edit.html', judge=None)

        judge = Judge(name=name, email=email, is_admin=is_admin)
        if pw:
            judge.set_password(pw)
        db.session.add(judge)
        db.session.commit()
        return redirect(url_for('config_judges'))

    return render_template('config/judge_edit.html', judge=None)


@app.route('/config/judge/<int:judge_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def config_judge_edit(judge_id):
    judge = db.get_or_404(Judge, judge_id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update':
            judge.name     = request.form['name'].strip()
            judge.email    = request.form.get('email', '').strip().lower() or None
            judge.is_admin = request.form.get('is_admin') == '1'
            judge.is_active= request.form.get('is_active') != '0'
            pw = request.form.get('password', '').strip()
            if pw:
                judge.set_password(pw)
            db.session.commit()

        elif action == 'delete':
            if SessionAssignment.query.filter_by(judge_id=judge.id).count():
                flash('Impossible de supprimer : ce juge a des audiences assignées.', 'error')
            else:
                db.session.delete(judge); db.session.commit()
                return redirect(url_for('config_judges'))

        return redirect(url_for('config_judge_edit', judge_id=judge.id))

    return render_template('config/judge_edit.html', judge=judge)


# ══════════════════════════════════════════════════════════════════════════
# Config — special dates & jours sans audience
# ══════════════════════════════════════════════════════════════════════════

@app.route('/config/special-dates', methods=['GET', 'POST'])
@login_required
@admin_required
def config_special_dates():
    chambers     = Chamber.query.order_by(Chamber.sort_order).all()
    special_dates = SpecialDate.query.outerjoin(Chamber).order_by(SpecialDate.date).all()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            cid = request.form.get('chamber_id') or None
            db.session.add(SpecialDate(
                chamber_id=int(cid) if cid else None,
                date=date.fromisoformat(request.form['date']),
                description=request.form['description'].strip(),
            ))
            db.session.commit()
        elif action == 'delete':
            sd = db.get_or_404(SpecialDate, int(request.form['special_date_id']))
            db.session.delete(sd); db.session.commit()
        return redirect(url_for('config_special_dates'))

    return render_template('config/special_dates.html',
                           special_dates=special_dates, chambers=chambers)


@app.route('/config/jours-sans-audience', methods=['GET', 'POST'])
@login_required
@admin_required
def config_jsa():
    jsas = JourSansAudience.query.order_by(JourSansAudience.date).all()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            db.session.add(JourSansAudience(
                date=date.fromisoformat(request.form['date']),
                reason=request.form['reason'].strip(),
            ))
            db.session.commit()
        elif action == 'delete':
            j = db.get_or_404(JourSansAudience, int(request.form['jsa_id']))
            db.session.delete(j); db.session.commit()
        return redirect(url_for('config_jsa'))

    return render_template('config/jours_sans_audience.html', jsas=jsas)


# ══════════════════════════════════════════════════════════════════════════
# Error pages
# ══════════════════════════════════════════════════════════════════════════

@app.errorhandler(403)
def forbidden(_):
    return render_template('error.html', code=403,
                           message='Accès réservé aux administrateurs.'), 403


@app.errorhandler(404)
def not_found(_):
    return render_template('error.html', code=404,
                           message='Page introuvable.'), 404


# ══════════════════════════════════════════════════════════════════════════
# Startup
# ══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    with app.app_context():
        if '--reset' in sys.argv:
            db.drop_all()
            print('Database dropped.')
        db.create_all()
        if Judge.query.count() == 0:
            from seed import seed
            seed()
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get('PORT', 5000)),
        debug=os.environ.get('FLASK_DEBUG', '0') == '1',
    )
