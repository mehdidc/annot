import os
from collections import defaultdict
from flask import Flask, request, redirect, render_template, url_for, Response
from flask_sqlalchemy import SQLAlchemy, Pagination
from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql.expression import func, select
from sqlalchemy.orm import aliased

from flask.ext.sqlalchemy_cache import CachingQuery
from flask.ext.sqlalchemy_cache import FromCache
from flask.ext.sqlalchemy import SQLAlchemy, Model

from flask.ext.cache import Cache

from flask.ext.login import LoginManager
from flask.ext.login import login_user , logout_user , current_user , login_required
from flask.ext.login import UserMixin  


from trueskill import Rating, quality_1vs1, rate_1vs1
from itertools import product
import random
import numpy as np

import hashlib
import json

def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('google.com', 0))
    ip = s.getsockname()[0]
    return ip

DEBUG = True
IMG_SERVER = 'http://{}:5001'.format(get_ip())

app = Flask(__name__)


db_filename = 'data.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(db_filename)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_PROTECTION'] = None
app.config['SECRET_KEY'] = '123456790'

#app.config['CACHE_TYPE'] = 'memcached'

Model.query_class = CachingQuery
db = SQLAlchemy(app, session_options={'query_cls': CachingQuery})

cache = Cache(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.session_protection = None

@login_manager.user_loader
def load_user(id):
    return User.query.get(id)

# DB Design

class Match(db.Model):
    __tablename__ = 'Match'
    id = db.Column(db.Integer, primary_key=True)
    left_id = db.Column(db.Integer, ForeignKey('Image.id'))
    right_id = db.Column(db.Integer, ForeignKey('Image.id'))
    datetime = Column(DateTime, default=func.now())
    experiment =  db.Column(db.String(50))
    ip = db.Column(db.String(50))
    user_id = db.Column(db.Integer, ForeignKey('User.id'))

    left = relationship('Image', foreign_keys='Match.left_id')
    right = relationship('Image', foreign_keys='Match.right_id')

class Image(db.Model):
    __tablename__ = 'Image'

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), unique=True)

    def __repr__(self):
        return '<Image {}>'.format(self.url)

class User(db.Model, UserMixin):

    __tablename__ = 'User'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True)
    pwdhash = db.Column(db.String(200))

    @staticmethod
    def new(name, pwd):
        pwdhash = md5(pwd)
        user = User(name=name, pwdhash=pwdhash)
        db.session.add(user)
        db.session.commit()
    
    def is_authenticated(self):
        return False
 
    def is_active(self):
        return True
 
    def is_anonymous(self):
        return False
 
    def get_id(self):
        return unicode(self.id)
 
    def __repr__(self):
        return '<User %r>' % (self.username)

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    username = request.form['username']
    password = request.form['password']
    registered_user = User.query.filter_by(name=username, pwdhash=md5(password)).first()
    if registered_user is None:
        print('Username or Password is invalid' , 'error')
        return redirect(url_for('login'))
    login_user(registered_user)
    return redirect(request.args.get('next') or url_for('index'))

@app.route('/logout/')
def logout():
    next_ = request.args.get('next', 'index')
    logout_user()
    return redirect(url_for(next_)) 

def md5(s):
    m = hashlib.md5()
    m.update(s)
    return m.hexdigest()

class Classification(db.Model):

    __tablename__ = 'Classification'
    id = db.Column(db.Integer, primary_key=True)
    datetime = Column(DateTime, default=func.now())
    img_id = db.Column(db.Integer, ForeignKey('Image.id'))
    user_id = db.Column(db.Integer, ForeignKey('User.id'))
    img = relationship('Image', foreign_keys='Classification.img_id')
    user = relationship('User', foreign_keys='Classification.user_id')

    label = db.Column(db.String(200))
    value = db.Column(db.Integer, default=0)

# Selectors

def random_selector(pattern='%', name='random'):

    def selector_():
        q = Image.query.filter(Image.url.like(pattern))
        img1, img2 = q.order_by(func.random()).limit(2)
        return img1, img2
    selector_.__name__ = name
    return selector_

def fair_selector(pattern='%', name='fair', thresh=0.5, percentile=90):
    def selector_():
        import time
        image_alias = aliased(Image)
        matches = Match.query
        matches = matches.options(FromCache(cache))
        matches = matches.join(Match.left).join(image_alias, Match.right)
        matches = matches.filter(Image.url.like(pattern))
        matches = matches.filter(image_alias.url.like(pattern))

        t = time.time()
        images = [(match.left, match.right) for match in matches]
        print(time.time() - t)

        t = time.time()
        matches_urls = [(left.url, right.url) for left, right in images]
        print(time.time() - t)

    
        t = time.time()
        score = get_scores(images)
        print(time.time() - t)

        percentile_val = np.percentile(score.values(), percentile)
        urls = score.keys()
        urls = filter(lambda url:score[url] > percentile_val, urls)
        t = time.time()
        rating = get_rating(images)
        print(time.time() - t)

        t = time.time()
        match = list(product(urls, urls))
        random.shuffle(match)
        for left, right in match:
            f = get_fairness(rating, left, right)
            if f >= thresh:
                break
        print(time.time() - t)
        return left, right
    selector_.__name__ = name
    return selector_

def build_experiment(name='', question='Which one do you prefer?', selectors=None, w=200, h=200):
    if selectors is None:
        selectors = [random_selector]
    
    def page_gen(selector):
        if request.method == 'POST':
            winner = request.form['winner']
            loser = request.form['loser']
            experiment = request.form['experiment']
            if winner and loser and experiment:
                winner = int(winner)
                loser = int(loser)
                args = {
                    'left': winner,
                    'right': loser,
                    'exp': experiment,
                    'sel': selector
                }
                print('Adding a match between {left} (winner) and {right} (loser) in experiment {exp} where the selector is : {sel}'.format(**args))
                db.session.add(Match(left_id=winner, right_id=loser, experiment=experiment, ip=request.remote_addr))
                db.session.commit()
        selector = selector.replace('/', '')
        for select in selectors:
            if select.__name__ == selector:
                img1, img2 = select()
                break
        return render_template('template.html', 
                               url1=parse(img1.url), url2=parse(img2.url), 
                               id1=img1.id, id2=img2.id,
                               question=question,
                               w=w,
                               h=h,
                               experiment=name)
    
    sel_name = selectors[0].__name__
    def page_gen_default():
        return page_gen(sel_name)
    page_gen_default.__name__ = name + '_default'

    page_gen.__name__ = name
    addr = '/' + name + '/<string:selector>/'
    page_gen = app.route(addr, methods=['GET', 'POST'])(page_gen)
    page_gen = login_required(page_gen)
    addr = '/'+ name + '/'
    page_gen_default = app.route(addr, methods=['GET', 'POST'])(page_gen_default)
    return page_gen

def parse(url):
    return url.format(LOCAL=IMG_SERVER)
app.jinja_env.filters['parse_url'] = parse

@app.route('/matches/')
def matches():
    experiment = request.args.get('experiment')
    if experiment is not None:
        matches = Match.query.filter_by(experiment=experiment)
    else:
        matches = Match.query.all()
    return render_template('matches.html', matches=matches)

@app.route('/ranks/')
def ranks():
    experiment = request.args.get('experiment')
    if experiment is None:
        matches = None
    else:
        matches = Match.query.filter_by(experiment=experiment)
    urls, scores = get_urls_and_scores(matches)
    return render_template('rank.html', rank_url_score=zip(range(1, len(urls) + 1), urls, scores))

def get_urls_and_scores(matches=None):
    matches = get_matches_urls(matches)
    score = get_scores(matches)
    urls = sorted(score.keys(), key=lambda url: -score[url])
    scores = map(lambda url:score[url], urls)
    urls = map(parse, urls)
    return urls, scores


def get_matches_images(matches=None):
    if matches is None:
        matches = Match.query.all()
    matches = [(match.left, match.right) for match in matches]
    return matches

def get_matches_urls(matches=None):
    if matches is None:
        matches = Match.query.all()
    matches = [(match.left.url, match.right.url) for match in matches]
    return matches

def get_scores(matches):
    rating = get_rating(matches)
    return {el: r.mu - 2 * r.sigma for el, r in rating.items()}

def get_rating(matches):
    rating = defaultdict(lambda: Rating())
    for winner, loser in matches:
        rating[winner], rating[loser] = rate_1vs1(rating[winner], rating[loser])
    return rating

def get_fairness(rating, url1, url2):
    return quality_1vs1(rating[url1], rating[url2])

innovative = build_experiment(
        name='innovative', 
        question='Which one is more innovative ? ',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

existing = build_experiment(
        name='existing', 
        question='Which one looks more like existing digits?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

fixating = build_experiment(
        name='fixating', 
        question='Which one is fixating more?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])

noisier = build_experiment(
        name='noisier', 
        question='Which one is noisier ?',
        selectors=[random_selector('%models_mini%', name='random'),
                   fair_selector('%models_mini%', name='fair', thresh=0.5, percentile=90)])


gan = build_experiment(
        name='gan', 
        question='Which one is more good looking/realistic ?',
        selectors=[random_selector('%gan/%', name='random'),
                   fair_selector('%gan%', name='fair', thresh=0.5, percentile=90)],
        w=800,
        h=800)

@app.route('/<selector>', methods=['GET', 'POST'])
def index_sel(selector):
    experiments = [
        innovative,
        existing,
        fixating,
        noisier
    ]
    exp = random.choice(experiments)
    return exp(selector)

@app.route('/', methods=['GET', 'POST'])
def index():
    return index_sel('random')

data_pattern = {
    'creativity': '%models_mini%',
    'gan': '%gan%'
}

experiment_classes = {
    'creativity': [
        ('innovative', 'It is innovative'),
        ('existing', 'It looks like existing digits'),
        ('fixating', 'It is fixating '),
        ('noisy', 'It is noisy'),
        ('aesthetic', 'It is aesthetic')
    ]
}


@app.route('/classifier/', methods=['GET', 'POST'])
@login_required
def classifier():
    user = current_user
    data = request.args.get('data', 'creativity')
    exp = request.args.get('experiment', 'creativity')
    pattern = data_pattern[data]
    classes = experiment_classes[exp]
    if request.method == 'POST':
        if 'class' in request.form:
            labels = request.form.getlist('class')
            value = 1
            img_id = int(request.form['img_id'])
            for label in labels:
                db.session.add(Classification(img_id=img_id, user_id=user.id, label=label, value=value))
            db.session.commit()

    q_existing = db.session.query(Classification, Image).filter(Classification.user_id==user.id).filter(Image.id==Classification.img_id)
    q_existing = q_existing.subquery()
    q_existing = aliased(Image, q_existing)
    q_existing = Image.query.join(q_existing)
    
    q_all = Image.query.filter(Image.url.like(pattern))
    q = q_all.except_(q_existing)
    q = q.order_by(func.random())
    nb = q.count()
    q = q.limit(1)
    img = q.one()
    img.url = parse(img.url)
    return render_template('classify_one.html', img=img, classes=classes, w=250, h=250, nb=nb)

@app.route('/export_data', methods=['GET', 'POST'])
def export_data():
    from lightjob.cli import load_db
    import pandas as pd
    from collections import OrderedDict
    light_db = load_db(folder='../feature_generation/.lightjob')

    def get_hypers(s):
       c = light_db.get_by_id(s)['content']
       s_ref = c['model_summary']
       c_ref = light_db.get_by_id(s_ref)['content']
       return c_ref
    def accept_model(s):
       c = light_db.get_by_id(s)['content']
       s_ref = c['model_summary']
       c_ref = light_db.get_by_id(s_ref)['content']
       return c_ref['dataset'] == 'digits'

    q = db.session.query(Classification, Image, User)
    q = q.filter(Image.id==Classification.img_id)
    q = q.filter(User.id==Classification.user_id)
    rows = [
            {
                'id': get_id_from_url(img.url),
                'label': classif.label,
                'hypers': json.dumps(get_hypers(get_id_from_url(img.url))),
                'user': user.name
            }
        for classif, img, user in q
        if accept_model(get_id_from_url(img.url))
    ]
    df = pd.DataFrame(rows)
    csv_content = df.to_csv(index=False, columns=['id', 'hypers', 'user', 'label'])
    return Response(csv_content, mimetype='text/csv')

def get_id_from_url(url):
    return url.split('/')[-1].split('.')[0]

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='WebServer')
    parser.add_argument("--config-module",
                        type=str, help="config filename",
                        default="config")
    parser.add_argument("--host",
                        type=str,
                        default="0.0.0.0")
    parser.add_argument("--port",
                        type=int,
                        default=5000)
    parser.add_argument("--imgserver",
                        type=str,
                        default=IMG_SERVER)
    args = parser.parse_args()
    IMG_SERVER = args.imgserver
    app.run(host=args.host, port=args.port, debug=DEBUG, threaded=True)
