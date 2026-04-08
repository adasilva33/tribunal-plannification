from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

WEEKDAY_NAMES = {0: 'Lundi', 1: 'Mardi', 2: 'Mercredi', 3: 'Jeudi', 4: 'Vendredi'}


class Judge(db.Model):
    __tablename__ = 'judge'
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False, unique=True)
    email         = db.Column(db.String(150), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    is_admin      = db.Column(db.Boolean, default=False, nullable=False)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)

    chamber_roles = db.relationship('ChamberRole', backref='judge', cascade='all, delete-orphan')
    assignments   = db.relationship('SessionAssignment', backref='judge', cascade='all, delete-orphan')

    # ── Flask-Login interface ──────────────────────────────
    def get_id(self):           return str(self.id)
    @property
    def is_authenticated(self): return bool(self.password_hash and self.is_active)
    @property
    def is_anonymous(self):     return False

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return bool(self.password_hash) and check_password_hash(self.password_hash, pw)

    @property
    def can_login(self):
        return bool(self.email and self.password_hash)


class JudicialYear(db.Model):
    __tablename__ = 'judicial_year'
    id         = db.Column(db.Integer, primary_key=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date   = db.Column(db.Date, nullable=False)


class JudicialVacation(db.Model):
    __tablename__ = 'judicial_vacation'
    id         = db.Column(db.Integer, primary_key=True)
    type       = db.Column(db.String(10), nullable=False)   # 'ete' | 'hiver'
    start_date = db.Column(db.Date, nullable=False)
    end_date   = db.Column(db.Date, nullable=False)

    @property
    def label(self):
        return 'Été' if self.type == 'ete' else 'Hiver'


class Chamber(db.Model):
    __tablename__ = 'chamber'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)
    sheet_name = db.Column(db.String(50))
    start_time = db.Column(db.String(10))
    sort_order = db.Column(db.Integer, default=0)

    days          = db.relationship('ChamberDay', backref='chamber',
                                    cascade='all, delete-orphan', order_by='ChamberDay.weekday')
    roles         = db.relationship('ChamberRole', backref='chamber',
                                    cascade='all, delete-orphan', order_by='ChamberRole.sort_order')
    special_dates = db.relationship('SpecialDate', backref='chamber',
                                    cascade='all, delete-orphan', order_by='SpecialDate.date')
    assignments   = db.relationship('SessionAssignment', backref='chamber',
                                    cascade='all, delete-orphan', order_by='SessionAssignment.date')

    @property
    def days_display(self):
        return ', '.join(WEEKDAY_NAMES[d.weekday] for d in self.days)

    @property
    def weekdays_set(self):
        return {d.weekday for d in self.days}

    @property
    def president_roles(self):
        return [r for r in self.roles if r.role == 'president']

    @property
    def assesseur_roles(self):
        return [r for r in self.roles if r.role == 'assesseur']

    # Backward-compat properties used by existing templates
    @property
    def president(self):
        pr = next((r for r in self.roles if r.role == 'president'), None)
        return pr.judge.name if pr else None

    @property
    def assesseurs(self):
        """Returns ChamberRole objects; each has a .name proxy for template compat."""
        return self.assesseur_roles


class ChamberDay(db.Model):
    __tablename__ = 'chamber_day'
    id         = db.Column(db.Integer, primary_key=True)
    chamber_id = db.Column(db.Integer, db.ForeignKey('chamber.id'), nullable=False)
    weekday    = db.Column(db.Integer, nullable=False)   # 0=Mon … 4=Fri


class ChamberRole(db.Model):
    __tablename__ = 'chamber_role'
    id         = db.Column(db.Integer, primary_key=True)
    chamber_id = db.Column(db.Integer, db.ForeignKey('chamber.id'), nullable=False)
    judge_id   = db.Column(db.Integer, db.ForeignKey('judge.id'), nullable=False)
    role       = db.Column(db.String(20), nullable=False)   # 'president' | 'assesseur'
    sort_order = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint('chamber_id', 'judge_id', 'role', name='uq_chamber_judge_role'),
    )

    @property
    def name(self):
        """Backward compat — used by templates that do assesseur.name."""
        return self.judge.name


class SpecialDate(db.Model):
    __tablename__ = 'special_date'
    id          = db.Column(db.Integer, primary_key=True)
    chamber_id  = db.Column(db.Integer, db.ForeignKey('chamber.id'), nullable=True)
    date        = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(200))


class JourSansAudience(db.Model):
    __tablename__ = 'jour_sans_audience'
    id     = db.Column(db.Integer, primary_key=True)
    date   = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(200))


class SessionAssignment(db.Model):
    """One judge assigned to one role for a specific (chamber, date) session."""
    __tablename__ = 'session_assignment'
    id         = db.Column(db.Integer, primary_key=True)
    chamber_id = db.Column(db.Integer, db.ForeignKey('chamber.id'), nullable=False)
    date       = db.Column(db.Date, nullable=False)
    judge_id   = db.Column(db.Integer, db.ForeignKey('judge.id'), nullable=False)
    role       = db.Column(db.String(20), nullable=False)   # 'president' | 'assesseur'

    __table_args__ = (
        db.UniqueConstraint('chamber_id', 'date', 'judge_id', name='uq_session_chamber_judge'),
    )

