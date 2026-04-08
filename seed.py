"""
Fresh-install seed — creates all reference data + an admin account.
Run automatically when the DB is empty (first launch of app.py).
"""
from datetime import date, timedelta
from models import (
    db, Judge, JudicialYear, JudicialVacation,
    Chamber, ChamberDay, ChamberRole, SpecialDate, JourSansAudience,
)


def excel_to_date(n: int) -> date:
    return date(1899, 12, 30) + timedelta(days=int(n))


# ── Chamber definitions ────────────────────────────────────────────────────
# days: list of weekday ints (0=Mon … 4=Fri)
# president + assesseurs: names that become Judge records
CHAMBERS_DATA = [
    {
        'name': '1ère chambre - CTX GAL', 'sheet_name': 'Chambre_1',
        'start_time': '14h00', 'days': [0],
        'president': 'T. MARMILLON',
        'assesseurs': ['M. SCHMIDT', 'S. STREMSDOERFER', 'M. CARTE', 'J. BANOS',
                       'P. PEREZ', 'JF. ROCHER', 'P. FAVRE', 'G. JOLY',
                       'F. BALDINI', 'F. PECH', 'G. LECAILLON-NEGRIN'],
    },
    {
        'name': '2ème chambre - CTX GAL', 'sheet_name': 'Chambre_2',
        'start_time': '14h00', 'days': [1],
        'president': 'JP. LEYRAUD',
        'assesseurs': ['C. CHARBONNIER', 'H. CARDON', 'Y. PARIS', 'M. DE ROQUEFEUIL',
                       'M. SAGNIMORTE', 'JB. DUCATEZ', 'PH. PACAUD', 'P. DURET',
                       'S. MEZIN', 'JA. GRANGE', 'L. LOUGERSTAY'],
    },
    {
        'name': '3ème chambre - CTX GAL', 'sheet_name': 'Chambre_3',
        'start_time': '14h00', 'days': [2],
        'president': 'P. SPICA',
        'assesseurs': ['J. SALORD', 'P. BLANDIN', 'D. MARTINET', 'P. PROST',
                       'Y. AYOUBI', 'L. URREA', 'C. MISSIRIAN', 'A. TAKAHASHI',
                       'D. CONTENT-HOBLINGRE', 'F. FAYARD', 'M. BOUILHOL'],
    },
    {
        'name': '4ème chambre - CTX GAL', 'sheet_name': 'Chambre_4',
        'start_time': '14h00', 'days': [3],
        'president': 'R. DUPLESSY',
        'assesseurs': ['M. ROUX', 'L. CAIMANT', 'M. LOURDEAUX', 'D. SUC',
                       'P. GALONNIER', 'J. SOLEYMIEUX', 'S. LECANTE', 'Y. MOLINA',
                       'V. FRADIN', 'L. DUPORT', 'H. PARISI'],
    },
    {
        'name': '5ème chambre - REFERES', 'sheet_name': 'Chambre_5',
        'start_time': '8h30', 'days': [0, 2],
        'president': 'P. BOCCARDI',
        'assesseurs': ['I. CRIBIER', 'JY. BON', 'E. BALDACCHINO', 'M. SCHMIDT',
                       'R. DUPLESSY', 'F. HAHNLEN', 'P. SPICA', 'T. MARMILLON',
                       'M. DE ROQUEFEUIL', 'J. SALORD', 'J. FAYARD',
                       'S. STREMSDOERFER', 'M. LOURDEAUX'],
    },
    {
        'name': '6ème chambre - RGT AMIABLE', 'sheet_name': 'Chambre_6',
        'start_time': '', 'days': [0, 1, 2, 3, 4],
        'president': 'F. TOUSSAINT',
        'assesseurs': ['P. ZEN', 'JP. LEYRAUD', 'P. SPICA', 'L. CAIMANT',
                       'D. SUC', 'D. MARTINET', 'M. CARTE', 'P. PEREZ',
                       'L. URREA', 'S. LECANTE', 'P. FAVRE', 'C. MISSIRIAN'],
    },
    {
        'name': '7ème chambre - CPC', 'sheet_name': 'Chambre_7',
        'start_time': '13h30', 'days': [1],
        'president': 'PJ. ANCETTE',
        'assesseurs': ['P. REYNAUD', 'JY. BON', 'F. TOUSSAINT', 'M. CARTE',
                       'P. GALONNIER', 'JB. DUCATEZ', 'G. JOLY', 'C. MISSIRIAN'],
    },
    {
        'name': '8ème chambre - CPC', 'sheet_name': 'Chambre_8',
        'start_time': '13h30', 'days': [2],
        'president': 'S. LEGROS',
        'assesseurs': ['D. MAURIN', 'T. REGOND', 'P. BLANDIN', 'L. CAIMANT',
                       'L. URREA', 'JF. ROCHER', 'V. FRADIN'],
    },
    {
        'name': '9ème chambre - CPC et sanctions', 'sheet_name': 'Chambre_9',
        'start_time': '13h30', 'days': [3],
        'president': 'I. CRIBIER',
        'assesseurs': ['J. DELILLE', 'J. FAYARD', 'JP. LEYRAUD', 'JF. RAMAY',
                       'H. OUMÉDIAN', 'D. SUC', 'P. PROST', 'PH. PACAUD'],
    },
    {
        'name': 'JUGES COMMISSAIRES', 'sheet_name': 'Juges commissaires',
        'start_time': '8h30', 'days': [0, 1, 2, 3, 4],
        'president': "G. BRUN D'ARRE",
        'assesseurs': ['D. MAURIN', "G. BRUN D'ARRE", 'P. REYNAUD', 'T. REGOND',
                       'JP. GIBERT', 'E. BALDACCHINO', 'F. HAHNLEN', 'PJ. ANCETTE',
                       'H. OUMÉDIAN', 'O. PICARD', 'J. FAYARD', 'L. CAIMANT', 'J. DELILLE'],
    },
    {
        'name': 'PREVENTION-DETECTION', 'sheet_name': 'Prévention-détection',
        'start_time': '', 'days': [0, 1, 2, 3, 4],
        'president': 'P. BLANDIN',
        'assesseurs': ['P. REYNAUD', 'S. LEGROS', 'T. REGOND', 'JP. GIBERT', 'JF. RAMAY'],
    },
    {
        'name': 'ORIENTATION', 'sheet_name': 'Orientation',
        'start_time': '9h00', 'days': [4],
        'president': 'E. BALDACCHINO',
        'assesseurs': ['C. CHARBONNIER', 'JP. LEYRAUD', 'R. DUPLESSY', 'F. TOUSSAINT',
                       'P. SPICA', 'T. MARMILLON', 'P. BOCCARDI', 'J. SALORD', 'D. MARTINET'],
    },
]

SPECIAL_DATES_DATA = [
    ('7ème chambre - CPC', 45867, 'Appel causes et CPC'),
    ('7ème chambre - CPC', 45874, 'Appel causes et CPC'),
    ('7ème chambre - CPC', 45895, 'Appel causes et CPC'),
    ('7ème chambre - CPC', 45902, 'Appel causes et CPC'),
    ('7ème chambre - CPC', 46014, 'Appel causes et CPC'),
    ('5ème chambre - REFERES', 45868, 'Audience'),
    ('5ème chambre - REFERES', 45875, 'Audience'),
    ('5ème chambre - REFERES', 45903, 'Audience'),
    ('5ème chambre - REFERES', 46013, 'Audience'),
]

JOURS_SANS_AUDIENCE_DATA = [
    (45779, 'Pas audience'),
    (45807, 'Pas audience'),
    (45971, 'Pas audience'),
]


def seed():
    # Wipe all tables in dependency order
    for Model in [JourSansAudience, SpecialDate, ChamberRole, ChamberDay,
                  Chamber, JudicialVacation, JudicialYear, Judge]:
        Model.query.delete()

    # ── Judicial year ──────────────────────────────────────────────────────
    db.session.add(JudicialYear(
        start_date=excel_to_date(45688),
        end_date=excel_to_date(46053),
    ))

    # ── Vacations ──────────────────────────────────────────────────────────
    db.session.add(JudicialVacation(type='ete',   start_date=excel_to_date(45866), end_date=excel_to_date(45905)))
    db.session.add(JudicialVacation(type='hiver', start_date=excel_to_date(46013), end_date=excel_to_date(46025)))

    # ── Judges — collect all unique names across chambers ─────────────────
    all_names: set[str] = set()
    for cd in CHAMBERS_DATA:
        all_names.add(cd['president'])
        all_names.update(cd['assesseurs'])

    judge_map: dict[str, Judge] = {}
    for name in sorted(all_names):
        j = Judge(name=name)
        db.session.add(j)
        judge_map[name] = j

    # Admin account
    admin = Judge(name='Administrateur', email='admin@tribunal.fr', is_admin=True)
    admin.set_password('admin123')
    db.session.add(admin)

    db.session.flush()   # assign IDs

    # ── Chambers + roles ───────────────────────────────────────────────────
    for i, cd in enumerate(CHAMBERS_DATA):
        chamber = Chamber(
            name=cd['name'], sheet_name=cd['sheet_name'],
            start_time=cd['start_time'], sort_order=i,
        )
        db.session.add(chamber)
        db.session.flush()

        for wd in cd['days']:
            db.session.add(ChamberDay(chamber_id=chamber.id, weekday=wd))

        pres_judge = judge_map.get(cd['president'])
        if pres_judge:
            db.session.add(ChamberRole(
                chamber_id=chamber.id, judge_id=pres_judge.id,
                role='president', sort_order=0,
            ))

        for j_idx, a_name in enumerate(cd['assesseurs']):
            a_judge = judge_map.get(a_name)
            if a_judge:
                try:
                    db.session.add(ChamberRole(
                        chamber_id=chamber.id, judge_id=a_judge.id,
                        role='assesseur', sort_order=j_idx + 1,
                    ))
                    db.session.flush()
                except Exception:
                    db.session.rollback()

    db.session.flush()

    # ── Special dates ──────────────────────────────────────────────────────
    chamber_by_name = {c.name: c for c in Chamber.query.all()}
    for chamber_name, serial, description in SPECIAL_DATES_DATA:
        c = chamber_by_name.get(chamber_name)
        db.session.add(SpecialDate(
            chamber_id=c.id if c else None,
            date=excel_to_date(serial),
            description=description,
        ))

    # ── Jours sans audience ────────────────────────────────────────────────
    for serial, reason in JOURS_SANS_AUDIENCE_DATA:
        db.session.add(JourSansAudience(date=excel_to_date(serial), reason=reason))

    db.session.commit()
    print('Base de données initialisée avec les données du fichier Excel.')
    print('Compte admin : admin@tribunal.fr / admin123')
