import datetime

from flask_uploads import UploadSet, configure_uploads
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import RadioField, IntegerField, SubmitField
from wtforms.validators import Optional, ValidationError

from app import app, db
from app.domain import Rule, NONE_ENUM, TaskInfoStatus, Workload, HashcatMode, OnOff
from app.word_magic.wordlist import estimate_runtime_fmt, wordlists_available, wordlist_path_from_name, \
    find_wordlist_by_path


def check_incomplete_tasks():
    for task in UploadedTask.query.filter_by(completed=False):
        task.status = TaskInfoStatus.ABORTED
        task.completed = True
    db.session.commit()


class UploadedTask(db.Model):
    __tablename__ = "uploads"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    filename = db.Column(db.String(128))
    wordlist = db.Column(db.String(128))
    rule = db.Column(db.String(128))
    hashcat_args = db.Column(db.String(1024), default='')
    uploaded_time = db.Column(db.DateTime, index=True, default=datetime.datetime.now)
    duration = db.Column(db.Interval, default=datetime.timedelta)
    status = db.Column(db.String(256), default=TaskInfoStatus.SCHEDULED)
    found_key = db.Column(db.String(256))
    completed = db.Column(db.Boolean, default=False)
    essid = db.Column(db.String(64))
    bssid = db.Column(db.String(64))


class UploadForm(FlaskForm):
    wordlist = RadioField('Wordlist', choices=wordlists_available(), default=NONE_ENUM, description="The higher the rate, the better")
    rule = RadioField('Rule', choices=((NONE_ENUM, "(None)"), (Rule.BEST_64.value, Rule.BEST_64.value)),
                      default=NONE_ENUM)
    timeout = IntegerField('Timeout in minutes, optional', validators=[Optional()])
    capture = FileField('Capture', validators=[FileRequired(), FileAllowed(HashcatMode.valid_suffixes(),
                                                                           message='Airodump & Hashcat capture files only')])
    workload = RadioField("Workload", choices=tuple((wl.value, wl.name) for wl in Workload),
                          default=Workload.Default.value)
    brain = RadioField("Hashcat Brain", choices=tuple((enum.value, enum.name) for enum in OnOff),
                       default=OnOff.OFF.value, description="Hashcat Brain skips already tried password candidates")
    submit = SubmitField('Submit')

    def __init__(self):
        super().__init__()
        self.wordlist.choices = wordlists_available()

    def get_wordlist_path(self):
        return wordlist_path_from_name(self.wordlist.data)

    def get_rule(self):
        return Rule.from_data(self.rule.data)

    @property
    def runtime(self):
        runtime = estimate_runtime_fmt(wordlist_path=self.get_wordlist_path(), rule=self.get_rule())
        return runtime

    @staticmethod
    def validate_wordlist(form, field):
        wordlist = wordlist_path_from_name(field.data)
        if wordlist is None:
            # fast mode
            return

        # update the wordlists
        wordlists_available()

        wordlist = find_wordlist_by_path(wordlist)
        if wordlist is None:
            raise ValidationError(f"The chosen wordlist does not exist anymore. Refresh the page.")


cap_uploads = UploadSet(name='files', extensions=HashcatMode.valid_suffixes(), default_dest=lambda app: app.config['CAPTURES_DIR'])
configure_uploads(app, cap_uploads)
