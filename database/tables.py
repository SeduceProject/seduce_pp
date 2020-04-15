from database.base import Base
from database.states import user_initial_state, deployment_initial_state
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(200), unique=True)
    _password = Column(Text)
    firstname = Column(Text)
    lastname = Column(Text)
    ssh_key = Column(Text, nullable=True, default=None)
    email_confirmed = Column(Boolean, default=False)
    user_authorized = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    email_confirmation_token = Column(Text, nullable=True, default=None)
    deployments = relationship('Deployment', backref='user', lazy=True)


    def __repr__(self):
        return "User(%s, %s, %s)" % (self.email, self.user_authorized, self.email_confirmed)


    @hybrid_property
    def password(self):
        return self._password


    @password.setter
    def _set_password(self, plaintext):
        from initialization import bcrypt
        self._password = bcrypt.generate_password_hash(plaintext)


class Deployment(Base):
    __tablename__ = 'deployment'
    id = Column(Integer, primary_key=True, autoincrement=True)
    state = Column(String(120), default=deployment_initial_state)
    environment = Column(Text)
    node_name = Column(Text)
    name = Column(Text)
    duration = Column(Text)
    system_size = Column(Text)
    system_pwd = Column(String(60))
    public_key = Column(Text)
    init_script = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    temp_info = Column(Text)
    updated_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)


    def __repr__(self):
        return "Deployment(%s, %s, %s, %s)" % (self.id, self.name, self.state, self.updated_at)


